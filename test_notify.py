"""Self-test for award / regret e-mails:  python test_notify.py   (no network: SMTP is faked)"""
import email
import zipfile
import io

from app_defaults import DEFAULT_RFQ, DEFAULT_SUPPLIERS
from decision import make_decision
from models import LineItem, RFQ, SupplierProfile
from notifier import (Notification, SmtpConfig, build_notifications, check_leaks, eml_zip, send_notifications,
                      to_message)
from orchestrator import run_negotiation
from po_generator import generate_po_pdf

rfq = RFQ(items=[LineItem(description="CNC housings", quantity=500), LineItem(description="Brackets", quantity=200)],
          max_price=50_000, buyer_company="Acme Manufacturing", buyer_email="buyer@acme.example")
sups = [s.model_copy(update={"email": f"sales@{s.name.split()[0].lower()}.example"}) for s in DEFAULT_SUPPLIERS]
sups[2] = sups[2].model_copy(update={"email": ""})                     # one supplier has no address
res = run_negotiation(rfq, sups)
winner = next(r for r in res.rooms if r.supplier == res.winner)

# ---- approved AI pick: 1 award (with PO) + regrets ----
d = make_decision(res, "approve", approver="Dana Lee")
pdf = generate_po_pdf(rfq, winner, po_no=d.po_no, approved_by=d.approver)
ns = build_notifications(rfq, res, d, sups, pdf)
assert len(ns) == len(sups) and ns[0].kind == "award" and ns[0].supplier == res.winner
assert [n.kind for n in ns].count("regret") == len(sups) - 1
award = ns[0]
assert d.po_no in award.subject and "CNC housings" in award.body and "Brackets" in award.body
assert f"{winner.final_offer.price:,.2f}" in award.body and award.attachments[0].data[:4] == b"%PDF"
for n in ns[1:]:
    assert not n.attachments
    assert res.winner not in n.body and "50,000" not in n.body and "score" not in n.body.lower()
assert check_leaks(rfq, res, sups, ns) == []

# ---- a hand-edited regret mail that leaks something is caught ----
bad = Notification(ns[1].supplier, ns[1].to, "regret", "x",
                   f"We chose a rival at {winner.final_offer.price:,.0f}; our budget was 50,000.")
w = check_leaks(rfq, res, sups, [bad])
assert any("budget" in x for x in w) and len(w) >= 1

# ---- manual override and reject-all wording ----
loser = next(r.supplier for r in res.rooms if r.final_offer and r.supplier != res.winner)
d2 = make_decision(res, "manual", loser)
assert build_notifications(rfq, res, d2, sups)[0].supplier == loser
d3 = make_decision(res, "reject_all")
ns3 = build_notifications(rfq, res, d3, sups)
assert all(n.kind == "regret" and "not to place an order" in n.body for n in ns3)

# ---- SMTP: fake server, per-recipient outcome, no exception ever escapes ----
class FakeServer:
    sent, closed = [], False
    def send_message(self, msg):
        if "fail@" in msg["To"]:
            raise RuntimeError("550 mailbox unavailable")
        FakeServer.sent.append(msg)
    def quit(self):
        FakeServer.closed = True

cfg = SmtpConfig(host="smtp.example", sender="procurement@acme.example", username="u", password="p")
ns[1].to = "fail@nowhere.example"
results = send_notifications(ns, cfg, "Acme Manufacturing", rfq.buyer_email, connect=lambda c: FakeServer())
by = {r.supplier: r for r in results}
assert by[ns[0].supplier].status == "sent" and by[ns[1].supplier].status == "failed"
assert by[ns[2].supplier].status == ("skipped" if not ns[2].to else "sent")
assert FakeServer.closed and FakeServer.sent[0]["Reply-To"] == "buyer@acme.example"
assert FakeServer.sent[0].get_content_type() == "multipart/mixed"            # PO attached
assert [r.status for r in send_notifications(ns, SmtpConfig(), connect=lambda c: FakeServer())].count("failed") >= 1

def boom(_):
    raise OSError("connection refused")
assert all(r.status in ("failed", "skipped") for r in send_notifications(ns, cfg, connect=boom))

# ---- .eml drafts fallback ----
z = zipfile.ZipFile(io.BytesIO(eml_zip(ns, "procurement@acme.example", "Acme")))
assert len(z.namelist()) == len(ns)
parsed = email.message_from_bytes(z.read(z.namelist()[0]))
assert parsed["Subject"] == ns[0].subject
print("NOTIFY TESTS PASSED")
