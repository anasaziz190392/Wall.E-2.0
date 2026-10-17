"""Pydantic schemas: every message between agents is a validated, structured bid."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ----------------------------- PRIVATE / PUBLIC INPUTS -----------------------------
class LineItem(BaseModel):
    """One line of a multi-item RFQ. A single supplier quotes the whole package."""
    description: str = Field(min_length=1)
    quantity: int = Field(1, gt=0)
    unit: str = "pcs"
    ref_unit_price: Optional[float] = Field(
        None, gt=0, description="PRIVATE, optional: only used to split the agreed package price across PO lines")

    @field_validator("description", "unit", mode="before")
    @classmethod
    def _strip(cls, v):
        return str(v).strip() if v is not None else v


class PublicLineItem(BaseModel):
    description: str
    quantity: int
    unit: str = "pcs"


def describe_items(items) -> str:
    """'500 pcs x CNC housings; 200 pcs x Steel brackets'"""
    return "; ".join(f"{i.quantity:,} {i.unit} x {i.description}" for i in items)


class RFQ(BaseModel):
    """Buyer's full RFQ. `max_price` is PRIVATE to the buyer agent.

    `max_price` is the ceiling for the WHOLE package (all line items together).
    `RFQ(item=..., quantity=...)` still works and creates a one-line RFQ.
    """
    items: list[LineItem] = Field(
        default_factory=lambda: [LineItem(description="CNC-machined aluminium housings", quantity=500)],
        min_length=1)
    max_price: float = Field(50_000, gt=0, description="PRIVATE: total budget ceiling for the package (USD)")
    target_delivery_days: int = Field(14, gt=0)
    max_delivery_days: int = Field(21, gt=0, description="PRIVATE: latest acceptable delivery")
    preferred_payment_days: int = Field(60, ge=0, description="Net-X payment terms the buyer wants")
    min_payment_days: int = Field(30, ge=0, description="PRIVATE: shortest payment terms buyer accepts")
    max_rounds: int = Field(3, ge=1, le=6)
    buyer_company: str = ""
    buyer_email: str = ""

    @model_validator(mode="before")
    @classmethod
    def _legacy_single_item(cls, data):
        if isinstance(data, dict) and "items" not in data and ("item" in data or "quantity" in data):
            data = dict(data)
            data["items"] = [{"description": data.pop("item", "Item"), "quantity": data.pop("quantity", 1)}]
        return data

    # --- convenience views (keep the one-item API working) ---
    @property
    def item(self) -> str:
        return self.items[0].description if len(self.items) == 1 else f"{len(self.items)} line items"

    @property
    def quantity(self) -> int:
        return sum(i.quantity for i in self.items)

    @property
    def items_text(self) -> str:
        return describe_items(self.items)

    def to_public(self) -> "PublicRFQ":
        return PublicRFQ(item=self.item, quantity=self.quantity, max_rounds=self.max_rounds,
                         items=[PublicLineItem(description=i.description, quantity=i.quantity, unit=i.unit)
                                for i in self.items])


class PublicRFQ(BaseModel):
    """The only RFQ view suppliers ever receive (no budget, no limits, no reference prices)."""
    item: str
    quantity: int
    max_rounds: int
    items: list[PublicLineItem] = []

    @property
    def items_text(self) -> str:
        return describe_items(self.items) if self.items else f"{self.quantity:,} x {self.item}"


class SupplierProfile(BaseModel):
    """Supplier's hidden economics. `floor_price` is PRIVATE to that supplier agent."""
    name: str
    email: str = Field("", description="Contact for award / regret notifications (never sent to agents)")
    opening_ask: float = Field(gt=0)
    floor_price: float = Field(gt=0, description="PRIVATE: minimum margin-safe price at standard terms")
    standard_delivery_days: int = Field(gt=0)
    min_delivery_days: int = Field(gt=0, description="Fastest possible (expedited)")
    preferred_payment_days: int = Field(30, ge=0)
    expedite_premium_pct_per_day: float = 1.5   # price uplift per day pulled in vs standard
    credit_cost_pct_per_day: float = 0.03       # financing cost per extra payment day

    @field_validator("email", mode="before")
    @classmethod
    def _clean_email(cls, v):
        if v is None or (isinstance(v, float) and v != v):   # None / NaN from an empty table cell
            return ""
        return str(v).strip()


def effective_floor(p: SupplierProfile, delivery_days: int, payment_days: int) -> float:
    """Supplier's true walk-away price once expedite + credit costs are included."""
    delivery_days = max(delivery_days, p.min_delivery_days)
    expedite_days = max(0, p.standard_delivery_days - delivery_days)
    credit_days = max(0, payment_days - p.preferred_payment_days)
    return (p.floor_price
            * (1 + p.expedite_premium_pct_per_day / 100 * expedite_days)
            * (1 + p.credit_cost_pct_per_day / 100 * credit_days))


# ----------------------------- NEGOTIATION MESSAGES -----------------------------
class LLMOffer(BaseModel):
    """Schema the LLM must return (validated before guardrails are applied)."""
    action: Literal["counter", "accept", "reject"]
    price: float
    delivery_days: int
    payment_days: int
    message: str = ""


class Offer(BaseModel):
    party: Literal["buyer", "supplier"]
    round: int
    price: float
    delivery_days: int
    payment_days: int
    action: Literal["counter", "accept", "reject"] = "counter"
    message: str = ""


class Room(BaseModel):
    """One closed negotiation room = buyer agent <-> ONE supplier agent."""
    supplier: str
    offers: list[Offer] = []
    status: Literal["open", "deal", "no_deal"] = "open"
    final_offer: Optional[Offer] = None
    score: float = 0.0


class NegotiationResult(BaseModel):
    rooms: list[Room]
    winner: Optional[str] = None
    leak_warnings: list[str] = []
