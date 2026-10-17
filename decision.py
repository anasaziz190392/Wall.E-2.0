"""Human-in-the-loop decision after the agents finish negotiating.

The orchestrator only *recommends* a supplier (best weighted score). Nothing is awarded until a person either
  - approves the recommendation,
  - picks a different supplier manually (an "override"), or
  - rejects every offer.
The Decision is the single source of truth for the PO and for who is sent an award / regret e-mail.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel

from models import NegotiationResult, Room
from po_generator import po_number

Mode = Literal["approve", "manual", "reject_all"]
MODE_LABEL = {"approve": "Approved AI recommendation", "manual": "Manual selection",
              "reject_all": "All offers rejected"}


class Decision(BaseModel):
    mode: Mode
    selected: Optional[str] = None          # awarded supplier (None when everything is rejected)
    recommended: Optional[str] = None       # what the agents recommended at the time
    approver: str = ""
    comment: str = ""
    decided_at: dt.datetime
    po_no: Optional[str] = None

    @property
    def overridden(self) -> bool:
        return self.mode == "manual" and self.selected != self.recommended

    @property
    def label(self) -> str:
        return "Manual selection (override of AI recommendation)" if self.overridden else MODE_LABEL[self.mode]


def eligible_rooms(result: NegotiationResult) -> list[Room]:
    """Suppliers that actually reached acceptable terms, best score first."""
    return sorted((r for r in result.rooms if r.final_offer), key=lambda r: r.score, reverse=True)


def make_decision(result: NegotiationResult, mode: Mode, selected: Optional[str] = None,
                  approver: str = "", comment: str = "", now: Optional[dt.datetime] = None) -> Decision:
    now = now or dt.datetime.now()
    names = [r.supplier for r in eligible_rooms(result)]
    if mode == "approve":
        if not result.winner:
            raise ValueError("There is no recommendation to approve - no supplier reached acceptable terms.")
        selected = result.winner
    elif mode == "manual":
        if selected not in names:
            raise ValueError("Pick one of the suppliers that reached a deal.")
    elif mode == "reject_all":
        selected = None
    else:  # pragma: no cover
        raise ValueError(f"Unknown mode {mode!r}")
    return Decision(mode=mode, selected=selected, recommended=result.winner, approver=approver.strip(),
                    comment=comment.strip(), decided_at=now,
                    po_no=po_number(selected, now.date()) if selected else None)


def status_of(room: Room, decision: Decision) -> str:
    """'Awarded' | 'Not selected' | 'No deal' for one supplier, given the decision."""
    if decision.selected == room.supplier:
        return "Awarded"
    return "Not selected" if room.final_offer else "No deal"
