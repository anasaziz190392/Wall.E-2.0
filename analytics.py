"""Savings dashboard maths. All 'manual' figures are transparent, adjustable assumptions."""
from __future__ import annotations

from models import NegotiationResult, RFQ


def savings_metrics(rfq: RFQ, result: NegotiationResult, elapsed_s: float,
                    minutes_per_email: float = 15, wait_hours_per_round: float = 24,
                    rfqs_per_year: int = 100) -> dict | None:
    win = next((r for r in result.rooms if r.supplier == result.winner), None)
    if not win or not win.final_offer:
        return None
    final = win.final_offer.price
    first_asks = [next(o.price for o in r.offers if o.party == "supplier") for r in result.rooms]
    avg_first = sum(first_asks) / len(first_asks)
    emails = len(result.rooms) + sum(len(r.offers) for r in result.rooms)   # 1 RFQ mail per supplier + every offer
    rounds_used = max(o.round for r in result.rooms for o in r.offers)
    effort_h = emails * minutes_per_email / 60
    cycle_d = rounds_used * wait_hours_per_round / 24
    return {
        "final": final,
        "saved_vs_budget": rfq.max_price - final,
        "saved_vs_budget_pct": 100 * (rfq.max_price - final) / rfq.max_price,
        "avg_first_ask": avg_first,
        "saved_vs_avg_ask": avg_first - final,
        "saved_vs_avg_ask_pct": 100 * (avg_first - final) / avg_first,
        "emails": emails,
        "effort_hours": effort_h,
        "cycle_days": cycle_d,
        "agent_seconds": elapsed_s,
        "annual_saving": (avg_first - final) * rfqs_per_year,
        "annual_hours": effort_h * rfqs_per_year,
        "first_asks": {r.supplier: a for r, a in zip(result.rooms, first_asks)},
    }
