"""Self-test for Google Form intake:  python test_intake.py"""
import pandas as pd

from rfq_intake import (is_valid_email, merge_supplier_contacts, rows_to_rfqs,
                        rows_to_supplier_profiles, to_csv_url)

# ---- legacy single-item form (v2.1) still parses ----
df = pd.DataFrame([
    {"Timestamp": "10/17/2026 10:00:00", "Company / requester name": "Acme", "Contact email": "a@acme.com",
     "Item / product description": "Steel brackets", "Quantity": "1,200",
     "Max price - total budget ceiling in USD (private)": "$75,000",
     "Target delivery (days)": 10, "Latest acceptable delivery (days) (private)": 20,
     "Preferred payment terms (Net days)": 45, "Shortest acceptable payment terms (Net days) (private)": 30,
     "Counter-offer rounds (1-6)": 4},
    {"Timestamp": "10/17/2026 11:00:00", "Company / requester name": "Bad", "Contact email": "b@x.com",
     "Item / product description": "Junk", "Quantity": "abc",
     "Max price - total budget ceiling in USD (private)": 1000,
     "Target delivery (days)": 5, "Latest acceptable delivery (days) (private)": 9,
     "Preferred payment terms (Net days)": 30, "Shortest acceptable payment terms (Net days) (private)": 15,
     "Counter-offer rounds (1-6)": None},
])
rows = rows_to_rfqs(df)
assert len(rows) == 2 and rows[0]["rfq"] is None and rows[0]["error"]          # newest first, bad row flagged
r = rows[1]["rfq"]
assert (r.item, r.quantity, r.max_price, r.max_delivery_days, r.min_payment_days, r.max_rounds) == \
       ("Steel brackets", 1200, 75000.0, 20, 30, 4)
assert (r.buyer_company, r.buyer_email) == ("Acme", "a@acme.com") and rows[1]["suppliers"] == []
assert to_csv_url("https://docs.google.com/spreadsheets/d/ABC123/edit#gid=7").endswith("ABC123/export?format=csv&gid=7")

# ---- v2.2 multi-item form with supplier contacts ----
common = {"Company / requester name": "Acme", "Contact email": "buyer@acme.com",
          "Max price - total budget ceiling in USD (private)": "120,000", "Target delivery (days)": 14,
          "Latest acceptable delivery (days) (private)": 21, "Preferred payment terms (Net days)": 60,
          "Shortest acceptable payment terms (Net days) (private)": 30, "Counter-offer rounds (1-6)": None}
multi = pd.DataFrame([
    {"Timestamp": "t1", **common,
     "Item 1 - description": "CNC housings", "Item 1 - quantity": 500.0,
     "Item 2 - description": "Steel brackets", "Item 2 - quantity": "1,200",
     "Item 3 - description": None, "Item 3 - quantity": None,
     "Supplier 1 - name": "Apex Metals", "Supplier 1 - email": "sales@apex.example",
    "Supplier 1 - opening_ask (USD)": "58,000", "Supplier 1 - floor_price (USD, private)": 41000,
    "Supplier 1 - standard_delivery_days": 18, "Supplier 1 - min_delivery_days": 12,
    "Supplier 1 - preferred_payment_days (Net days)": 30,
    "Supplier 1 - expedite_premium_pct_per_day": 1.5, "Supplier 1 - credit_cost_pct_per_day": 0.03,
     "Supplier 2 - name": "Borealis Fabrication", "Supplier 2 - email": "quotes@borealis.example",
    "Supplier 2 - opening_ask (USD)": 54000, "Supplier 2 - floor_price (USD, private)": 44500,
    "Supplier 2 - standard_delivery_days": 15, "Supplier 2 - min_delivery_days": 13,
    "Supplier 2 - preferred_payment_days (Net days)": 45,
    "Supplier 2 - expedite_premium_pct_per_day": 1.5, "Supplier 2 - credit_cost_pct_per_day": 0.03,
     "Supplier 3 - name": None, "Supplier 3 - email": None},
    {"Timestamp": "t2", **common,
     "Item 1 - description": "Half filled", "Item 1 - quantity": None,
     "Item 2 - description": None, "Item 2 - quantity": None,
     "Supplier 1 - name": None, "Supplier 1 - email": None},
])
out = rows_to_rfqs(multi)
assert out[0]["rfq"] is None and "Item 1" in out[0]["error"]                  # description without quantity -> flagged
ok = out[1]
rfq = ok["rfq"]
assert [(i.description, i.quantity) for i in rfq.items] == [("CNC housings", 500), ("Steel brackets", 1200)]
assert rfq.max_price == 120000 and rfq.max_rounds == 3                        # blank optional -> default
assert (rfq.buyer_company, rfq.buyer_email) == ("Acme", "buyer@acme.com")     # supplier columns are not mistaken for buyer ones
assert ok["suppliers"] == [
    {"name": "Apex Metals", "email": "sales@apex.example", "opening_ask": 58000.0,
     "floor_price": 41000.0, "standard_delivery_days": 18, "min_delivery_days": 12,
     "preferred_payment_days": 30, "expedite_premium_pct_per_day": 1.5, "credit_cost_pct_per_day": 0.03},
    {"name": "Borealis Fabrication", "email": "quotes@borealis.example", "opening_ask": 54000.0,
     "floor_price": 44500.0, "standard_delivery_days": 15, "min_delivery_days": 13,
     "preferred_payment_days": 45, "expedite_premium_pct_per_day": 1.5, "credit_cost_pct_per_day": 0.03},
]
supplier_cols = ["name", "email", "opening_ask", "floor_price", "standard_delivery_days", "min_delivery_days",
                 "preferred_payment_days", "expedite_premium_pct_per_day", "credit_cost_pct_per_day"]
existing = pd.DataFrame([{"name": "Apex Metals", "email": "", "opening_ask": 1, "floor_price": 1,
                          "standard_delivery_days": 1, "min_delivery_days": 1, "preferred_payment_days": 1,
                          "expedite_premium_pct_per_day": 0, "credit_cost_pct_per_day": 0}], columns=supplier_cols)
merged, matched, added = merge_supplier_contacts(existing, ok["suppliers"], rfq.max_price)
assert (matched, added) == (1, 1)
assert merged.loc[0, "opening_ask"] == 58000 and merged.loc[0, "floor_price"] == 41000
assert merged.loc[1, "standard_delivery_days"] == 15 and merged.loc[1, "credit_cost_pct_per_day"] == 0.03

# ---- standalone supplier registration form ----
supplier_responses = pd.DataFrame([
    {"Timestamp": "t3", "Supplier name": "Apex Metals", "Contact email": "sales@apex.example",
        "Opening Ask (USD)": "58,000", "Floor price (USD, private)": 41000,
        "Standard delivery days": 18, "Min delivery days": 12,
        "Preferred payment days (Net days)": 30, "Expedite premium pct per day": 1.5,
        "Credit cost pct per day": 0.03},
    {"Timestamp": "t4", "Supplier name": "Invalid Co", "Contact email": "not-an-email",
        "Opening Ask (USD)": 50000, "Floor price (USD, private)": 50000,
        "Standard delivery days": 10, "Min delivery days": 11,
        "Preferred payment days (Net days)": 30, "Expedite premium pct per day": 1.5,
        "Credit cost pct per day": 0.03},
])
registrations = rows_to_supplier_profiles(supplier_responses)
assert registrations[0]["profile"] is None and registrations[0]["error"]
assert registrations[1]["profile"] == ok["suppliers"][0]
assert registrations[1]["label"].startswith("Apex Metals")

# Actual Google response-sheet header labels: Std/Fastest delivery, Preferred terms, Expedite %, Credit %.
actual_sheet_headers = pd.DataFrame([{
    "Timestamp": "10/17/2026 14:45:36", "Supplier Name": "Wall E Limited",
    "Contact E-mail": "adarsh71yadav40@gmail.com", "Opening Ask (USD)": 55000,
    "Floor Price · Private (USD)": 46000, "Std Delivery (Days)": 17,
    "Fastest Delivery (Days)": 14, "Preferred Terms (Net Days)": 30,
    "Expedite % / Day": 1.5, "Credit % / Day": 0.4,
}])
actual_profile = rows_to_supplier_profiles(actual_sheet_headers)[0]["profile"]
assert actual_profile == {
    "name": "Wall E Limited", "email": "adarsh71yadav40@gmail.com", "opening_ask": 55000.0,
    "floor_price": 46000.0, "standard_delivery_days": 17, "min_delivery_days": 14,
    "preferred_payment_days": 30, "expedite_premium_pct_per_day": 1.5, "credit_cost_pct_per_day": 0.4,
}
assert is_valid_email("a@b.co") and not is_valid_email("a@b") and not is_valid_email("")
print("INTAKE TESTS PASSED")
