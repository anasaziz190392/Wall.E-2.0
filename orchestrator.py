"""Deterministic N-round counter-offer loop run in Python.

Rooms are isolated: each supplier only ever sees buyer offers addressed to it. The only
cross-room information is an anonymised 'best competing ask' that the buyer may use.
"""
from __future__ import annotations

from typing import Callable, Optional

from agents import BuyerAgent, LLMConfig, SupplierAgent
from models import NegotiationResult, RFQ, Room, SupplierProfile

W_PRICE, W_DELIVERY, W_PAYMENT = 0.60, 0.25, 0.15


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_deal(rfq: RFQ, price: float, delivery: int, payment: int) -> float:
    price_s = _clamp((rfq.max_price - price) / (rfq.max_price * 0.4))
    span = max(1, rfq.max_delivery_days - rfq.target_delivery_days)
    delivery_s = _clamp(1 - max(0, delivery - rfq.target_delivery_days) / span)
    payment_s = _clamp(payment / max(1, rfq.preferred_payment_days))
    return round(100 * (W_PRICE * price_s + W_DELIVERY * delivery_s + W_PAYMENT * payment_s), 1)


def run_negotiation(rfq: RFQ, suppliers: list[SupplierProfile], llm: Optional[LLMConfig] = None,
                    on_event: Optional[Callable[[str], None]] = None) -> NegotiationResult:
    log = on_event or (lambda s: None)
    buyer = BuyerAgent(rfq, llm)
    public = rfq.to_public()
    agents = {s.name: SupplierAgent(s, public, llm) for s in suppliers}
    rooms = {s.name: Room(supplier=s.name) for s in suppliers}
    last_buyer, last_sup = {}, {}

    for rnd in range(1, rfq.max_rounds + 1):
        log(f"Round {rnd}")
        market_best = min((o.price for o in last_sup.values()), default=None)
        for name, agent in agents.items():
            room = rooms[name]
            if room.status != "open":
                continue
            bo = buyer.opening() if rnd == 1 else buyer.counter(rnd, last_buyer[name], last_sup[name], market_best)
            room.offers.append(bo)
            last_buyer[name] = bo
            so = agent.respond(rnd, bo)
            room.offers.append(so)
            last_sup[name] = so
            if so.action == "accept":
                room.status, room.final_offer = "deal", so
            elif buyer.evaluate(rnd, so):
                from models import Offer
                acc = Offer(party="buyer", round=rnd, price=so.price, delivery_days=so.delivery_days,
                            payment_days=so.payment_days, action="accept",
                            message="Your counter-offer is within our parameters. Accepted.")
                room.offers.append(acc)
                room.status, room.final_offer = "deal", acc
            elif rnd == rfq.max_rounds:
                room.status = "no_deal"
            log(f"  {name}: buyer {bo.price:,.0f} -> supplier {so.action} {so.price:,.0f}")

    best, best_score = None, -1.0
    for r in rooms.values():
        if r.final_offer:
            f = r.final_offer
            r.score = score_deal(rfq, f.price, f.delivery_days, f.payment_days)
            if r.score > best_score:
                best, best_score = r.supplier, r.score

    return NegotiationResult(rooms=list(rooms.values()), winner=best,
                             leak_warnings=leak_audit(rfq, suppliers, list(rooms.values())))


def leak_audit(rfq: RFQ, suppliers: list[SupplierProfile], rooms: list[Room]) -> list[str]:
    """Flag any message that spells out a private number (budget or a supplier floor)."""
    secrets = {"buyer budget": rfq.max_price, **{f"{s.name} floor": s.floor_price for s in suppliers}}
    warns = []
    for room in rooms:
        for o in room.offers:
            for label, v in secrets.items():
                if f"{int(v)}" in o.message.replace(",", "") or f"{int(v):,}" in o.message:
                    warns.append(f"[{room.supplier}] {o.party} message mentions {label}")
    return warns
