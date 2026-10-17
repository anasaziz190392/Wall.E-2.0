"""Tell every supplier the outcome: an award e-mail (with the PO attached) for the selected supplier and a polite
regret e-mail for everybody else.

Privacy rules (same spirit as the closed rooms):
  * an award mail only contains that supplier's OWN agreed terms,
  * a regret mail never contains the winner, any competing price, the buyer's budget or a score,
  * `check_leaks` re-scans the final (possibly hand-edited) text before anything is sent.

Sending uses plain SMTP (works with Gmail / Outlook / any relay). Without SMTP settings the UI offers the drafts as
.eml files instead, so the feature is usable and testable without credentials.
"""
from __future__ import annotations

import io
import os
import smtplib
import ssl
import zipfile
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Callable, Optional

from decision import Decision
from models import NegotiationResult, RFQ, SupplierProfile
from rfq_intake import is_valid_email
from security import find_secrets


# ------------------------------------------------------------------ config
@dataclass
class SmtpConfig:
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    sender: str = ""
    security: str = "starttls"          # "starttls" | "ssl" | "none"

    @property
    def configured(self) -> bool:
        return bool(self.host and is_valid_email(self.sender))

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        g = os.getenv
        try:
            port = int(g("SMTP_PORT", "587"))
        except ValueError:
            port = 587
        user = g("SMTP_USER", "")
        return cls(host=g("SMTP_HOST", ""), port=port, username=user, password=g("SMTP_PASSWORD", ""),
                   sender=g("SMTP_FROM", user), security=g("SMTP_SECURITY", "starttls").lower())


@dataclass
class Attachment:
    filename: str
    data: bytes
    mime: str = "application/pdf"


@dataclass
class Notification:
    supplier: str
    to: str
    kind: str                           # "award" | "regret"
    subject: str
    body: str
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class SendResult:
    supplier: str
    to: str
    kind: str
    status: str                         # "sent" | "failed" | "skipped"
    detail: str = ""


# ------------------------------------------------------------------ drafting
def _signature(rfq: RFQ, decision: Decision) -> str:
    lines = [decision.approver or "Procurement Team", rfq.buyer_company or "Procurement"]
    if is_valid_email(rfq.buyer_email):
        lines.append(rfq.buyer_email)
    return "\n".join(lines)


def _item_lines(rfq: RFQ) -> str:
    return "\n".join(f"  - {i.quantity:,} {i.unit} x {i.description}" for i in rfq.items)


def _award_text(rfq: RFQ, decision: Decision, room, po_no: str) -> tuple[str, str]:
    f = room.final_offer
    subject = f"Purchase order {po_no} - your proposal has been selected"
    body = (f"Dear {room.supplier} team,\n\n"
            f"Thank you for taking part in our request for quotation. We are pleased to inform you that "
            f"{rfq.buyer_company or 'we'} {'has' if rfq.buyer_company else 'have'} selected your proposal "
            f"for the following package:\n\n{_item_lines(rfq)}\n\n"
            f"Agreed terms\n"
            f"  - Package price:  USD {f.price:,.2f}\n"
            f"  - Delivery:       {f.delivery_days} days\n"
            f"  - Payment terms:  Net {f.payment_days} days\n"
            f"  - Purchase order: {po_no}\n\n"
            f"The purchase order is attached. Please acknowledge receipt and confirm the delivery date "
            f"by replying to this e-mail.\n\n"
            f"Kind regards,\n{_signature(rfq, decision)}\n")
    return subject, body


def _regret_text(rfq: RFQ, decision: Decision, room) -> tuple[str, str]:
    subject = f"Update on our request for quotation - {rfq.item}"
    if decision.selected is None:
        outcome = ("After careful evaluation we have decided not to place an order for this request at this "
                   "time.")
    elif room.final_offer is None:
        outcome = ("We were not able to reach mutually acceptable terms within the negotiation rounds, and "
                   "we have decided to proceed with another supplier for this request.")
    else:
        outcome = ("After careful evaluation of all proposals we have decided to proceed with another "
                   "supplier for this request. This reflects an overall assessment of commercial and "
                   "delivery terms.")
    body = (f"Dear {room.supplier} team,\n\n"
            f"Thank you for the time and effort you put into responding to our request for quotation:\n\n"
            f"{_item_lines(rfq)}\n\n{outcome}\n\n"
            f"We value your participation and hope to work with you on future opportunities.\n\n"
            f"Kind regards,\n{_signature(rfq, decision)}\n")
    return subject, body


def build_notifications(rfq: RFQ, result: NegotiationResult, decision: Decision,
                        suppliers: list[SupplierProfile], po_pdf: Optional[bytes] = None) -> list[Notification]:
    """One draft per participating supplier. The recipient comes from the supplier table (manual or Google Form)."""
    mail_of = {s.name: s.email for s in suppliers}
    out = []
    for room in result.rooms:
        to = mail_of.get(room.supplier, "")
        if decision.selected == room.supplier:
            subject, body = _award_text(rfq, decision, room, decision.po_no or "")
            att = ([Attachment(f"{decision.po_no}_{room.supplier.replace(' ', '_')}.pdf", po_pdf)]
                   if po_pdf else [])
            out.append(Notification(room.supplier, to, "award", subject, body, att))
        else:
            subject, body = _regret_text(rfq, decision, room)
            out.append(Notification(room.supplier, to, "regret", subject, body))
    # award first, then the rest in the original order
    return sorted(out, key=lambda n: n.kind != "award")


def check_leaks(rfq: RFQ, result: NegotiationResult, suppliers: list[SupplierProfile],
                notifications: list[Notification]) -> list[str]:
    """Scan the (possibly hand-edited) mail text for numbers that must never leave a closed room."""
    warns = []
    for n in notifications:
        secrets = {"the buyer's budget ceiling": rfq.max_price}
        secrets.update({f"{s.name}'s floor price": s.floor_price for s in suppliers if s.name != n.supplier})
        for room in result.rooms:
            if room.supplier != n.supplier:       # another supplier's quoted numbers
                secrets.update({f"{room.supplier}'s offer ({o.price:,.0f})": o.price for o in room.offers
                                if o.party == "supplier"})
        text = n.subject + "\n" + n.body
        for label in find_secrets(text, secrets):
            warns.append(f"{n.supplier} ({n.kind} e-mail) mentions {label}")
    return warns


# ------------------------------------------------------------------ sending
def to_message(n: Notification, cfg: SmtpConfig, company: str = "", reply_to: str = "") -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((company, cfg.sender)) if company else cfg.sender
    msg["To"] = n.to
    msg["Subject"] = n.subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if is_valid_email(reply_to):
        msg["Reply-To"] = reply_to
    msg.set_content(n.body)
    for a in n.attachments:
        maintype, _, subtype = a.mime.partition("/")
        msg.add_attachment(a.data, maintype=maintype, subtype=subtype or "octet-stream", filename=a.filename)
    return msg


def _connect(cfg: SmtpConfig):
    ctx = ssl.create_default_context()
    if cfg.security == "ssl":
        server = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=30, context=ctx)
    else:
        server = smtplib.SMTP(cfg.host, cfg.port, timeout=30)
        if cfg.security == "starttls":
            server.starttls(context=ctx)
    if cfg.username:
        server.login(cfg.username, cfg.password)
    return server


def send_notifications(notifications: list[Notification], cfg: SmtpConfig, company: str = "", reply_to: str = "",
                       connect: Callable[[SmtpConfig], object] = _connect) -> list[SendResult]:
    """Send every notification over one SMTP connection. Never raises: each outcome is reported per supplier."""
    results: list[SendResult] = []
    todo = []
    for n in notifications:
        if not is_valid_email(n.to):
            results.append(SendResult(n.supplier, n.to, n.kind, "skipped",
                                      "no valid e-mail address" if not n.to.strip() else "invalid e-mail address"))
        else:
            todo.append(n)
    if not todo:
        return results
    if not cfg.configured:
        return results + [SendResult(n.supplier, n.to, n.kind, "failed", "SMTP is not configured") for n in todo]
    try:
        server = connect(cfg)
    except Exception as e:                                             # bad host / login / TLS
        return results + [SendResult(n.supplier, n.to, n.kind, "failed", f"could not connect: {e}") for n in todo]
    try:
        for n in todo:
            try:
                server.send_message(to_message(n, cfg, company, reply_to))
                results.append(SendResult(n.supplier, n.to, n.kind, "sent"))
            except Exception as e:
                results.append(SendResult(n.supplier, n.to, n.kind, "failed", str(e)[:200]))
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return results


def eml_zip(notifications: list[Notification], sender: str = "procurement@example.com", company: str = "",
            reply_to: str = "") -> bytes:
    """Drafts as .eml files (open in Outlook / Apple Mail / Thunderbird and press send)."""
    cfg = SmtpConfig(sender=sender)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in notifications:
            name = f"{n.kind}_{n.supplier.replace(' ', '_')}.eml"
            z.writestr(name, to_message(n, cfg, company, reply_to).as_bytes())
    return buf.getvalue()
