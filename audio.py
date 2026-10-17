"""Listen to the negotiation. Uses the browser's built-in speech engine (Web Speech API):
no extra Python packages, no API keys, works offline in Chrome / Edge / Safari."""
from __future__ import annotations

import json
import re

from models import NegotiationResult, RFQ


def _clean(msg: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", msg).strip()


def _offer_sentence(o, supplier: str) -> str:
    who = "The buyer" if o.party == "buyer" else supplier
    verb = "accepts at" if o.action == "accept" else "proposes"
    return (f"Round {o.round}. {who} {verb} {o.price:,.0f} dollars, {o.delivery_days} days delivery, "
            f"net {o.payment_days} days payment. {_clean(o.message)}")


def build_segments(rfq: RFQ, result: NegotiationResult, scope: str = "Full negotiation",
                   savings: dict | None = None) -> list[dict]:
    segs = []
    if scope in ("Full negotiation",) or scope in [r.supplier for r in result.rooms]:
        segs.append({"role": "narrator", "label": "Narrator",
                     "text": f"Negotiation for {rfq.items_text}. {rfq.max_rounds} rounds, "
                             f"{len(result.rooms)} supplier rooms."})
        for room in result.rooms:
            if scope != "Full negotiation" and room.supplier != scope:
                continue
            segs.append({"role": "narrator", "label": "Narrator", "text": f"Room: {room.supplier}."})
            for o in room.offers:
                segs.append({"role": o.party, "label": f"{o.party.title()} · R{o.round}",
                             "text": _offer_sentence(o, room.supplier)})
    if scope in ("Full negotiation", "Deal summary"):
        win = next((r for r in result.rooms if r.supplier == result.winner), None)
        if win and win.final_offer:
            f = win.final_offer
            text = (f"Deal summary. The winner is {win.supplier} at {f.price:,.0f} dollars, delivered in "
                    f"{f.delivery_days} days with net {f.payment_days} payment terms. Score {win.score} out of 100.")
            if savings:
                text += (f" That is {savings['saved_vs_budget']:,.0f} dollars under budget and "
                         f"{savings['saved_vs_avg_ask']:,.0f} dollars below the average first ask.")
        else:
            text = "Deal summary. No supplier reached acceptable terms."
        segs.append({"role": "narrator", "label": "Summary", "text": text})
    return segs


def transcript_text(segs: list[dict]) -> str:
    return "\n\n".join(f"[{s['label']}] {s['text']}" for s in segs)


_HTML = """
<style>
 body{font-family:Helvetica,Arial,sans-serif;margin:0;color:#1d2730}
 .bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
 button{padding:8px 14px;border:0;border-radius:8px;background:#1a7a7a;color:#fff;font-size:15px;cursor:pointer}
 button.alt{background:#55616c} select,input{font-size:13px;max-width:190px}
 #list{max-height:300px;overflow:auto;border:1px solid #d5d9dc;border-radius:10px;padding:8px;background:#fafafa}
 .line{padding:7px 10px;margin:4px 0;border-radius:8px;font-size:14px;line-height:1.35;cursor:pointer;border-left:4px solid #bbb}
 .buyer{border-color:#1a7a7a}.supplier{border-color:#b8650f}.narrator{border-color:#7a7f85;font-style:italic}
 .on{background:#fff3d6;box-shadow:0 0 0 2px #f0b45a inset}
 small{color:#55616c}
</style>
<div class="bar">
 <button id="play">▶ Play</button><button id="pause" class="alt">⏸ Pause</button><button id="stop" class="alt">⏹ Stop</button>
 <label><small>Speed</small> <input id="rate" type="range" min="0.7" max="1.5" step="0.1" value="1"></label>
</div>
<div class="bar">
 <label><small>Buyer voice</small> <select id="vb"></select></label>
 <label><small>Supplier voice</small> <select id="vs"></select></label>
</div>
<div id="list"></div>
<small id="msg">Click any line to start from there.</small>
<script>
const segs = __DATA__;
const list=document.getElementById('list'), rate=document.getElementById('rate'), msg=document.getElementById('msg');
const esc=t=>t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
segs.forEach((s,i)=>{const d=document.createElement('div');d.className='line '+s.role;d.id='l'+i;
  d.innerHTML='<b>'+esc(s.label)+'</b> '+esc(s.text);d.onclick=()=>start(i);list.appendChild(d);});
let idx=0, run=0, voices=[];
function fill(){voices=speechSynthesis.getVoices().filter(v=>v.lang.toLowerCase().startsWith('en'));
  ['vb','vs'].forEach((id,k)=>{const el=document.getElementById(id);const keep=el.value;el.innerHTML='';
    voices.forEach((v,i)=>{const o=document.createElement('option');o.value=i;o.text=v.name;el.appendChild(o);});
    el.value=keep||Math.min(k,Math.max(0,voices.length-1));});}
speechSynthesis.onvoiceschanged=fill; fill();
if(!('speechSynthesis' in window)) msg.textContent='Speech synthesis is not supported in this browser (try Chrome or Edge).';
function mark(i){document.querySelectorAll('.line').forEach(e=>e.classList.remove('on'));
  const e=document.getElementById('l'+i); if(e){e.classList.add('on');e.scrollIntoView({block:'nearest'});}}
function speak(token){
  if(token!==run) return;
  if(idx>=segs.length){mark(-1);msg.textContent='Finished.';return;}
  const s=segs[idx]; mark(idx);
  const u=new SpeechSynthesisUtterance(s.text);
  const v=voices[document.getElementById(s.role==='supplier'?'vs':'vb').value]; if(v) u.voice=v;
  u.rate=parseFloat(rate.value); u.pitch=s.role==='supplier'?0.85:1.0;
  u.onend=()=>{ if(token===run){idx++;speak(token);} };
  u.onerror=()=>{};
  speechSynthesis.speak(u);
}
function start(i){speechSynthesis.cancel();run++;idx=i;msg.textContent='Playing…';speak(run);}
document.getElementById('play').onclick=()=>start(0);
document.getElementById('pause').onclick=()=>{ if(speechSynthesis.paused){speechSynthesis.resume();msg.textContent='Playing…';}
  else{speechSynthesis.pause();msg.textContent='Paused.';} };
document.getElementById('stop').onclick=()=>{run++;speechSynthesis.cancel();mark(-1);msg.textContent='Stopped.';};
window.addEventListener('beforeunload',()=>speechSynthesis.cancel());
</script>
"""


def audio_player(segments: list[dict], height: int = 470) -> None:
    import streamlit as st                      # imported here so the transcript builder works without Streamlit
    import streamlit.components.v1 as components

    data = json.dumps(segments).replace("</", "<\\/")
    html = _HTML.replace("__DATA__", data).strip()
    if hasattr(st, "iframe"):            # newer Streamlit (components.v1.html is being retired)
        st.iframe(html, height=height)
    else:                                # older Streamlit
        components.html(html, height=height, scrolling=False)
