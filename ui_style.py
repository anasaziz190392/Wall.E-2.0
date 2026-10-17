"""Look & feel: enterprise theme (CSS) and small HTML helpers (header, KPI cards, status chips)."""
from __future__ import annotations

from html import escape

import streamlit as st

NAVY, INK, SLATE, MUTED = "#0b1f3a", "#0f172a", "#475569", "#64748b"
BLUE, BORDER, BG = "#2563eb", "#e2e8f0", "#f4f6fa"
# supplier line colours for charts (dark = supplier ask, light = buyer offer)
SERIES = [("#1d4ed8", "#93b4f5"), ("#0f766e", "#7fd1c7"), ("#b45309", "#f1c27d"),
          ("#7c3aed", "#c4b0f5"), ("#be123c", "#f2a3b5"), ("#475569", "#b6c0cc")]

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {{ --navy:{NAVY}; --ink:{INK}; --slate:{SLATE}; --muted:{MUTED}; --blue:{BLUE}; --border:{BORDER}; }}

/* ---- base ---- */
.stApp {{ background:{BG}; color:{INK}; }}
.stApp, .stMarkdown, .stMarkdown p, label, input, textarea, button, th, td, h1, h2, h3, h4,
[data-baseweb="select"] div, [data-testid="stCaptionContainer"] {{ font-family:'Inter','Segoe UI',system-ui,sans-serif; }}
.block-container {{ padding-top:1.1rem; padding-bottom:4rem; max-width:1280px; }}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{ visibility:hidden; height:0; }}
[data-testid="stHeader"] {{ background:transparent; }}
h1,h2,h3,h4 {{ color:{NAVY}; letter-spacing:-0.01em; }}
h3 {{ font-size:1.05rem !important; font-weight:600 !important; }}

/* ---- sidebar ---- */
[data-testid="stSidebar"] {{ background:#ffffff; border-right:1px solid {BORDER}; }}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ font-size:.78rem !important; text-transform:uppercase;
  letter-spacing:.08em; color:{MUTED}; font-weight:600 !important; margin-top:.4rem; }}

/* ---- header band ---- */
.hub-header {{ background:linear-gradient(120deg,{NAVY} 0%,#12315c 60%,#1e4a8a 100%); border-radius:14px;
  padding:18px 24px; display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
  box-shadow:0 6px 18px rgba(11,31,58,.18); margin-bottom:14px; }}
.hub-brand {{ display:flex; align-items:center; gap:14px; }}
.hub-logo {{ width:42px; height:42px; border-radius:11px; background:rgba(255,255,255,.12); display:flex;
  align-items:center; justify-content:center; color:#fff; font-weight:700; font-size:20px;
  border:1px solid rgba(255,255,255,.25); }}
.hub-title {{ color:#fff; font-size:1.25rem; font-weight:700; letter-spacing:-.01em; line-height:1.2; }}
.hub-sub {{ color:#b8c8e4; font-size:.82rem; margin-top:2px; }}
.hub-chips {{ display:flex; gap:8px; flex-wrap:wrap; }}
.hub-chips .chip {{ background:rgba(255,255,255,.1); color:#e6eefb; border:1px solid rgba(255,255,255,.22); }}

/* ---- step navigation ---- */
.st-key-navbar {{ margin-bottom:6px; }}
.st-key-navbar [data-testid="stButtonGroup"] button {{ font-weight:600; padding:.5rem 1.05rem; }}

/* ---- cards / containers ---- */
[data-testid="stVerticalBlockBorderWrapper"] {{ background:#fff; border-radius:12px; border-color:{BORDER} !important;
  box-shadow:0 1px 2px rgba(15,23,42,.04); }}
.sec-title {{ font-size:.98rem; font-weight:650; color:{NAVY}; margin:2px 0 0 0; }}
.sec-sub {{ font-size:.82rem; color:{MUTED}; margin:1px 0 10px 0; }}
.eyebrow {{ font-size:.7rem; font-weight:600; letter-spacing:.09em; text-transform:uppercase; color:{MUTED}; }}

/* ---- KPI cards ---- */
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin:4px 0 14px; }}
.kpi {{ background:#fff; border:1px solid {BORDER}; border-radius:12px; padding:14px 16px;
  box-shadow:0 1px 2px rgba(15,23,42,.04); border-top:3px solid {BLUE}; }}
.kpi.good {{ border-top-color:#059669; }} .kpi.warn {{ border-top-color:#d97706; }}
.kpi.bad {{ border-top-color:#dc2626; }} .kpi.neutral {{ border-top-color:#94a3b8; }}
.kpi .k-label {{ font-size:.72rem; font-weight:600; text-transform:uppercase; letter-spacing:.07em; color:{MUTED}; }}
.kpi .k-value {{ font-size:1.55rem; font-weight:700; color:{NAVY}; margin-top:4px; letter-spacing:-.02em; line-height:1.15; }}
.kpi .k-sub {{ font-size:.8rem; color:{SLATE}; margin-top:3px; }}

/* ---- chips ---- */
.chip {{ display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px; font-size:.74rem;
  font-weight:600; border:1px solid transparent; white-space:nowrap; }}
.chip.dot::before {{ content:""; width:7px; height:7px; border-radius:50%; background:currentColor; }}
.chip.blue {{ background:#eaf1ff; color:#1d4ed8; border-color:#cddcfb; }}
.chip.green {{ background:#e8f8f1; color:#047857; border-color:#bfe9d6; }}
.chip.amber {{ background:#fff6e5; color:#b45309; border-color:#f6dcab; }}
.chip.red {{ background:#feecec; color:#b91c1c; border-color:#f6c4c4; }}
.chip.grey {{ background:#f1f5f9; color:#475569; border-color:#e2e8f0; }}

/* ---- callouts ---- */
.callout {{ border-radius:12px; padding:14px 18px; border:1px solid {BORDER}; background:#fff; margin:6px 0 12px; }}
.callout.good {{ background:#f0faf5; border-color:#bfe9d6; }} .callout.bad {{ background:#fef4f4; border-color:#f6c4c4; }}
.callout.info {{ background:#f1f6ff; border-color:#cddcfb; }} .callout.warn {{ background:#fffaf0; border-color:#f6dcab; }}
.callout .c-title {{ font-weight:650; color:{NAVY}; font-size:1rem; }}
.callout .c-body {{ color:{SLATE}; font-size:.88rem; margin-top:3px; }}

/* ---- workflow list in sidebar ---- */
.flow {{ list-style:none; padding:0; margin:4px 0 8px; }}
.flow li {{ display:flex; align-items:center; gap:10px; padding:5px 0; font-size:.86rem; color:{SLATE}; }}
.flow .bullet {{ width:18px; height:18px; border-radius:50%; border:2px solid #cbd5e1; flex:none; display:flex;
  align-items:center; justify-content:center; font-size:10px; color:#fff; }}
.flow li.done {{ color:{INK}; }} .flow li.done .bullet {{ background:#059669; border-color:#059669; }}
.flow li.now .bullet {{ border-color:{BLUE}; }} .flow li.now {{ color:{NAVY}; font-weight:600; }}

/* ---- buttons / inputs ---- */
.stButton > button, .stDownloadButton > button {{ border-radius:9px; font-weight:600; }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{ background:{NAVY}; border-color:{NAVY}; }}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {{ background:#16335f; border-color:#16335f; }}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border-radius:10px; overflow:hidden; }}
[data-testid="stTabs"] button[role="tab"] {{ font-weight:600; }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chip(text: str, tone: str = "grey", dot: bool = False) -> str:
    return f'<span class="chip {tone}{" dot" if dot else ""}">{escape(text)}</span>'


def header(chips: list[str]) -> None:
    st.markdown(
        '<div class="hub-header"><div class="hub-brand"><div class="hub-logo">N</div><div>'
        '<div class="hub-title">Negotiation Hub</div>'
        '<div class="hub-sub">Closed-room sourcing &amp; RFQ negotiation platform</div></div></div>'
        f'<div class="hub-chips">{"".join(chips)}</div></div>', unsafe_allow_html=True)


def section(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="sec-title">{escape(title)}</div>' + (f'<div class="sec-sub">{escape(sub)}</div>' if sub else ""),
                unsafe_allow_html=True)


def kpis(cards: list[tuple]) -> None:
    """cards: (label, value, sub, tone) - tone in '', good, warn, bad, neutral."""
    html = "".join(
        f'<div class="kpi {c[3] if len(c) > 3 else ""}"><div class="k-label">{escape(str(c[0]))}</div>'
        f'<div class="k-value">{escape(str(c[1]))}</div>'
        + (f'<div class="k-sub">{escape(str(c[2]))}</div>' if len(c) > 2 and c[2] else "") + "</div>"
        for c in cards)
    st.markdown(f'<div class="kpis">{html}</div>', unsafe_allow_html=True)


def callout(title: str, body: str = "", tone: str = "info") -> None:
    st.markdown(f'<div class="callout {tone}"><div class="c-title">{title}</div>'
                + (f'<div class="c-body">{body}</div>' if body else "") + "</div>", unsafe_allow_html=True)


def flow(steps: list[tuple[str, bool]], current: int) -> None:
    items = "".join(
        f'<li class="{"done" if done else ("now" if i == current else "")}"><span class="bullet">{"✓" if done else ""}</span>{escape(name)}</li>'
        for i, (name, done) in enumerate(steps))
    st.markdown(f'<ul class="flow">{items}</ul>', unsafe_allow_html=True)
