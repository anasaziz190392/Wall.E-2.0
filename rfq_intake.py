"""Fetch RFQs submitted through the Google Form (via its linked Google Sheet).

Two ways to read the response sheet:
  1. Link / CSV URL  - sheet shared "Anyone with the link can view" (or File > Share > Publish to web > CSV). No keys.
  2. Service account - sheet stays private; share it with the service account's e-mail. Needs `gspread`.
"""
from __future__ import annotations

import io
import json
import re
from typing import Optional

import pandas as pd
import requests

from models import RFQ

# form question title (lower-cased, matched by keyword) -> RFQ field
FIELD_KEYWORDS = [
    ("item", ("item", "product", "description")),           # legacy single-item forms only
    ("quantity", ("quantity", "qty")),                      # legacy single-item forms only
    ("max_price", ("max price", "budget")),
    ("target_delivery_days", ("target delivery",)),
    ("max_delivery_days", ("latest", "max delivery")),
    ("preferred_payment_days", ("preferred payment",)),
    ("min_payment_days", ("shortest", "min payment")),
    ("max_rounds", ("round",)),
]
META_KEYWORDS = {"requester": ("company", "name", "requester"), "email": ("email", "e-mail")}

# multi-item / supplier-contact slots:  "Item 2 - description", "Item 2 - quantity", "Supplier 1 - email" ...
_ITEM_COL = re.compile(r"\bitem\s*#?\s*(\d+)\b")
_SUPPLIER_COL = re.compile(r"\bsupplier\s*#?\s*(\d+)\b")
_EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
SUPPLIER_PROFILE_FIELDS = (
    "opening_ask", "floor_price", "standard_delivery_days", "min_delivery_days",
    "preferred_payment_days", "expedite_premium_pct_per_day", "credit_cost_pct_per_day",
)
SUPPLIER_INTEGER_FIELDS = {"standard_delivery_days", "min_delivery_days", "preferred_payment_days"}
SUPPLIER_PROFILE_ALIASES = {
    "opening_ask": ("opening ask",),
    "floor_price": ("floor price",),
    "standard_delivery_days": ("standard delivery", "std delivery"),
    "min_delivery_days": ("minimum delivery", "min delivery", "fastest delivery", "fastest"),
    "preferred_payment_days": ("preferred payment", "preferred terms", "payment terms"),
    "expedite_premium_pct_per_day": ("expedite premium", "expedite %", "expedite"),
    "credit_cost_pct_per_day": ("credit cost", "credit %", "credit"),
}


def is_valid_email(addr: str) -> bool:
    return bool(_EMAIL_RE.match((addr or "").strip()))


def to_csv_url(url: str) -> str:
    """Turn a normal Google Sheet link into its CSV export URL; leave published/CSV links alone."""
    url = url.strip()
    if "output=csv" in url or "format=csv" in url:
        return url
    m = re.search(r"/spreadsheets/d/([\w-]+)", url)
    if not m:
        raise ValueError("That doesn't look like a Google Sheets link.")
    gid = re.search(r"[#&?]gid=(\d+)", url)
    return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv&gid={gid.group(1) if gid else 0}"


def fetch_from_url(url: str, timeout: int = 20) -> pd.DataFrame:
    r = requests.get(to_csv_url(url), timeout=timeout)
    if r.status_code in (401, 403) or "accounts.google.com" in r.url:
        raise PermissionError("Sheet is private. Share it as 'Anyone with the link: Viewer', "
                              "or use the service-account option.")
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def fetch_from_service_account(sheet_url: str, creds_json: str | dict) -> pd.DataFrame:
    try:
        import gspread
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pip install gspread to use a service account") from e
    creds = creds_json if isinstance(creds_json, dict) else json.loads(creds_json)
    ws = gspread.service_account_from_dict(creds).open_by_url(sheet_url).sheet1
    return pd.DataFrame(ws.get_all_records())


def _match(columns, keywords) -> Optional[str]:
    normalize = lambda value: re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    normalized_keywords = tuple(normalize(keyword) for keyword in keywords)
    for c in columns:
        low = normalize(c)
        if any(k in low for k in normalized_keywords):
            return c
    return None


def _slot_columns(cols, pattern):
    """Map numbered item/supplier response columns to their field names."""
    slots: dict[int, dict[str, str]] = {}
    for c in cols:
        low = str(c).lower()
        m = pattern.search(low)
        if not m:
            continue
        n = int(m.group(1))
        if "email" in low or "e-mail" in low:
            kind = "email"
        elif pattern is _SUPPLIER_COL and any(field in low for field in SUPPLIER_PROFILE_FIELDS):
            kind = next(field for field in SUPPLIER_PROFILE_FIELDS if field in low)
        elif pattern is _SUPPLIER_COL and re.search(r"\bname\s*$", low):
            kind = "name"
        elif "qty" in low or "quantity" in low:
            kind = "qty"
        elif "unit price" in low or "reference" in low:
            kind = "ref"
        elif "unit" in low:
            kind = "unit"
        elif pattern is _SUPPLIER_COL:
            kind = "name"
        else:
            kind = "desc"      # item: description / supplier: name
        slots.setdefault(n, {})[kind] = c
    return dict(sorted(slots.items()))


def _cell(row, col) -> str:
    if not col or pd.isna(row[col]):
        return ""
    return str(row[col]).strip()


def _int(v) -> int:
    return int(float(str(v).replace(",", "")))


def rows_to_supplier_profiles(df: pd.DataFrame) -> list[dict]:
    """Parse supplier-registration form responses into validated supplier profiles, newest first."""
    if df is None or df.empty:
        return []
    cols = list(df.columns)
    field_columns = {
        "name": _match(cols, ("supplier name", "company name", "supplier")),
        "email": _match(cols, ("contact email", "supplier email", "e-mail")),
        **{field: _match(cols, SUPPLIER_PROFILE_ALIASES[field]) for field in SUPPLIER_PROFILE_FIELDS},
    }
    ts_col = _match(cols, ("timestamp",))
    profiles = []
    for idx, row in df.iterrows():
        entry = {"index": int(idx), "timestamp": _cell(row, ts_col), "profile": None, "error": None}
        try:
            name = _cell(row, field_columns["name"])
            email = _cell(row, field_columns["email"])
            if not name:
                raise ValueError("Supplier name is required")
            if not is_valid_email(email):
                raise ValueError("A valid supplier contact e-mail is required")
            profile = {"name": name, "email": email}
            for field in SUPPLIER_PROFILE_FIELDS:
                raw = _cell(row, field_columns[field])
                if not raw:
                    raise ValueError(f"{field} is required")
                number = float(re.sub(r"[^\d.-]", "", raw))
                profile[field] = int(number) if field in SUPPLIER_INTEGER_FIELDS else number
            if profile["floor_price"] >= profile["opening_ask"]:
                raise ValueError("floor_price must be below opening_ask")
            if profile["min_delivery_days"] > profile["standard_delivery_days"]:
                raise ValueError("min_delivery_days cannot exceed standard_delivery_days")
            entry["profile"] = profile
        except Exception as e:
            entry["error"] = str(e).splitlines()[0][:120]
        label_name = entry["profile"]["name"] if entry["profile"] else _cell(row, field_columns["name"]) or "invalid supplier"
        entry["label"] = f"{label_name} · {entry['timestamp'] or f'row {idx + 1}'}"
        profiles.append(entry)
    return profiles[::-1]


def rows_to_rfqs(df: pd.DataFrame) -> list[dict]:
    """Return [{'label', 'rfq' (RFQ|None), 'error', 'requester', 'email', 'suppliers', 'timestamp'}] newest first.

    `suppliers` contains the name, e-mail, and any submitted profile fields from Supplier 1..N slots.
    """
    if df is None or df.empty:
        return []
    cols = list(df.columns)
    item_slots = _slot_columns(cols, _ITEM_COL)
    sup_slots = _slot_columns(cols, _SUPPLIER_COL)
    slot_cols = {c for sl in (*item_slots.values(), *sup_slots.values()) for c in sl.values()}
    plain = [c for c in cols if c not in slot_cols]
    fmap = {f: _match([c for c in plain if "timestamp" not in str(c).lower()], kws) for f, kws in FIELD_KEYWORDS}
    if item_slots:                                   # new multi-item form: ignore the single-item keywords
        fmap["item"] = fmap["quantity"] = None
    ts_col = _match(cols, ("timestamp",))
    meta = {k: _match(plain, kws) for k, kws in META_KEYWORDS.items()}
    out = []
    for i, row in df.iterrows():
        entry = {"index": int(i), "rfq": None, "error": None, "suppliers": [],
                 "timestamp": _cell(row, ts_col),
                 "requester": _cell(row, meta["requester"]),
                 "email": _cell(row, meta["email"])}
        try:
            data = {f: row[c] for f, c in fmap.items() if c and pd.notna(row[c]) and str(row[c]).strip() != ""}
            for k in ("target_delivery_days", "max_delivery_days",
                      "preferred_payment_days", "min_payment_days", "max_rounds"):
                if k in data:
                    data[k] = _int(data[k])
            if "max_price" in data:
                data["max_price"] = float(re.sub(r"[^\d.]", "", str(data["max_price"])))
            if item_slots:
                items = []
                for n, sl in item_slots.items():
                    desc, qty = _cell(row, sl.get("desc")), _cell(row, sl.get("qty"))
                    if not desc and not qty:
                        continue                      # empty optional slot
                    if not desc or not qty:
                        raise ValueError(f"Item {n} needs both a description and a quantity")
                    it = {"description": desc, "quantity": _int(qty)}
                    if _cell(row, sl.get("unit")):
                        it["unit"] = _cell(row, sl["unit"])
                    ref = re.sub(r"[^\d.]", "", _cell(row, sl.get("ref")))
                    if ref:
                        it["ref_unit_price"] = float(ref)
                    items.append(it)
                if not items:
                    raise ValueError("No line items in this response")
                data["items"] = items
            else:
                if "item" in data:
                    data["item"] = str(data["item"]).strip()
                if "quantity" in data:
                    data["quantity"] = _int(data["quantity"])
            if entry["requester"]:
                data["buyer_company"] = entry["requester"]
            if entry["email"]:
                data["buyer_email"] = entry["email"]
            entry["rfq"] = RFQ(**data)
        except Exception as e:
            entry["error"] = str(e).splitlines()[0][:120]
        for n, sl in sup_slots.items():
            name, mail = _cell(row, sl.get("name", sl.get("desc"))), _cell(row, sl.get("email"))
            if name:
                supplier = {"name": name, "email": mail}
                for field in SUPPLIER_PROFILE_FIELDS:
                    value = _cell(row, sl.get(field))
                    if value:
                        number = float(re.sub(r"[^\d.-]", "", value))
                        supplier[field] = int(number) if field in SUPPLIER_INTEGER_FIELDS else number
                entry["suppliers"].append(supplier)
        who = entry["requester"] or entry["email"] or "unknown"
        item = entry["rfq"].item if entry["rfq"] else "invalid row"
        entry["label"] = f"#{i + 1} · {entry['timestamp'] or '—'} · {who} · {item}"
        out.append(entry)
    return out[::-1]


def merge_supplier_contacts(df: pd.DataFrame, contacts: list[dict], budget: float) -> tuple[pd.DataFrame, int, int]:
    """Merge supplier contacts and submitted agent economics into the supplier table.

    * a contact whose name matches an existing row (case-insensitive) updates its e-mail and supplied economics,
    * an unknown name is appended with PLACEHOLDER economics for any fields omitted from the form (review them!).
    Existing rows are never removed. Returns (new table, matched, added).
    """
    out = df.copy()
    matched = added = 0
    for c in contacts:
        name, mail = str(c.get("name", "")).strip(), str(c.get("email", "")).strip()
        if not name:
            continue
        profile = {field: c[field] for field in SUPPLIER_PROFILE_FIELDS if c.get(field) is not None}
        for field in profile:
            if field not in SUPPLIER_INTEGER_FIELDS:
                out[field] = pd.to_numeric(out[field], errors="coerce").astype(float)
        hit = out.index[out["name"].astype(str).str.strip().str.lower() == name.lower()]
        if len(hit):
            if mail:
                out.loc[hit[0], "email"] = mail
            for field, value in profile.items():
                out.loc[hit[0], field] = value
            matched += 1
        else:
            supplier = {"name": name, "email": mail, "opening_ask": round(budget * 1.2, -2),
                        "floor_price": round(budget * 0.88, -2), "standard_delivery_days": 14,
                        "min_delivery_days": 10, "preferred_payment_days": 30,
                        "expedite_premium_pct_per_day": 1.5, "credit_cost_pct_per_day": 0.03}
            supplier.update(profile)
            out.loc[len(out)] = supplier
            added += 1
    return out.reset_index(drop=True), matched, added
