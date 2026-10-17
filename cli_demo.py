"""Run the negotiation without the UI:  python cli_demo.py"""
from app_defaults import DEFAULT_RFQ, DEFAULT_SUPPLIERS
from orchestrator import run_negotiation
from po_generator import generate_po_pdf

res = run_negotiation(DEFAULT_RFQ, DEFAULT_SUPPLIERS, on_event=print)
print("\nWinner:", res.winner, "| leak warnings:", res.leak_warnings)
for r in res.rooms:
    print(f"{r.supplier:22} {r.status:8} score={r.score:5}", r.final_offer and f"price={r.final_offer.price:,.0f}")
if res.winner:
    room = next(r for r in res.rooms if r.supplier == res.winner)
    open("PO_demo.pdf", "wb").write(generate_po_pdf(DEFAULT_RFQ, room))
    print("Saved PO_demo.pdf")
