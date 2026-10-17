# Closed-Room B2B Negotiation Hub v2.2 (AI Hackathon 2.0 – Use Case 1)

Buyer agent + 2–3 supplier agents negotiate in **isolated rooms** through a deterministic counter-offer
loop. The best deal wins and a **Purchase Order PDF** is generated.

## Run locally in VS Code
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py             # opens http://localhost:8501
python test_core.py              # optional self-tests (also test_intake.py, test_notify.py)
```
No API key needed (rule-based agents). For LLM agents: copy `.env.example` -> `.env`, add a key, and turn on
**Use LLM agents** in the sidebar. Press **F5** in VS Code to run/debug (`.vscode/launch.json`).

## New in v2
| Feature | Where | Demo tip |
|---|---|---|
| 🔴 **Live replay** | sidebar toggle + speed | Each offer streams into the chat with a typing indicator while the price chart updates |
| 🛡️ **Red-team lab** | "Red-team lab" tab | Pick a preset attack, then switch the two defence layers off to see the leak; use **attack matrix** to compare all 4 settings |
| 📊 **Savings dashboard** | Outcome → "Savings dashboard" | Saved vs budget and vs average first ask, cycle time, effort avoided, annual projection (assumptions editable) |
| 🔊 **Audio** | "Transcripts & audio" | Play full negotiation, one supplier, or the deal summary. Separate buyer/supplier voices, speed, click a line to jump. Also downloads a .txt transcript |

Audio uses the browser's built-in speech engine (Chrome / Edge / Safari), so it needs no extra packages or keys.
Pick different voices in the two dropdowns if only one sounds available.

## New in v2.2 – multi-item RFQs, human approval, supplier notifications, enterprise UI
The app is now a five-step workflow: **1 RFQ → 2 Suppliers → 3 Negotiation → 4 Decision & notify → 5 Security lab**.

| Feature | How it works |
|---|---|
| **Several items in one RFQ** | Step 1 has a line-item table (description, quantity, unit, optional reference unit price). One supplier quotes the **whole package** as a single price; the budget ceiling is also for the package. The PO lists every line and splits the agreed price pro rata (by quantity × reference price when every line has one, otherwise by quantity) so the lines add up exactly. Suppliers only ever see description / quantity / unit. |
| **Approval or manual selection** | After the agents finish they only *recommend* (best weighted score). In step 4 you choose **Approve recommendation**, **Select a supplier manually** (override – the app shows the price / score difference) or **Reject all offers**, add your name and a comment, then confirm. The decision (including overrides) drives the PO and the e-mails; **Change decision** is available until the first e-mail has been sent. |
| **Supplier notifications** | After confirming, press **Send e-mails**. The selected supplier gets an *award* e-mail with the PO PDF attached and only its own agreed terms; every other supplier gets a courteous *regret* e-mail (no winner, competing price, budget or score). All drafts are editable, a privacy check blocks sending if a private number slipped into the text, and results are tracked per supplier (retry failed ones). |
| **Supplier e-mail addresses** | Either a **Contact e-mail** column in step 2, the Google Form (see below), or typed directly on the notify step. Suppliers without a valid address are skipped and flagged. |
| **Sending** | Fill **E-mail delivery** in the sidebar (or `SMTP_*` in `.env`; Gmail needs an app password). With no SMTP settings you can still **download the drafts as .eml files** and send them from Outlook / Apple Mail. |
| **Enterprise UI** | New theme (`.streamlit/config.toml` + `ui_style.py`): header band, step navigation, KPI cards, status chips, workflow tracker in the sidebar, cleaner tables. |

**Buyer RFQ form:** run `createRfqForm` in `google_form_setup.gs` for the buyer form, which collects requirements and can optionally include supplier invite slots.

**Supplier registration form:** run `createSupplierForm` to create a separate supplier-facing form and response sheet. It collects supplier name, contact e-mail, `opening_ask`, `floor_price`, `standard_delivery_days`, `min_delivery_days`, `preferred_payment_days`, `expedite_premium_pct_per_day`, and `credit_cost_pct_per_day`. Keep the response sheet private: floor prices and cost assumptions are confidential agent inputs. In workflow step 2 (**Suppliers**), expand **Import supplier registration form responses**, fetch the supplier sheet, select a valid submission, then choose **Add / update this supplier**. Existing suppliers are matched by name; imported profiles remain editable in the supplier table.
Forms created with v2.1 keep working (one item, no supplier e-mails – add them by hand).


## New in v2.1 – RFQs from a Google Form (or manual)
Step 1 → **RFQ source**: keep typing RFQs by hand, or pull buyer submissions from a Google Form.

**One-time setup (your Google account)**
1. Go to <https://script.google.com> (signed in with the account that should own the form) → *New project*.
2. Paste `google_form_setup.gs`, run `createRfqForm`, accept the permissions.
3. Open *Execution log*: it prints the **FORM** link (send to buyers) and the **SHEET** link (responses land here).
4. Sheet → *Share* → "Anyone with the link: Viewer", then put the sheet link in `.env` as `GOOGLE_SHEET_URL`
   (or paste it in step 1).

**Using it:** *Google Form responses* → **Fetch responses** → pick a response → **Load into RFQ**.
The fields stay editable, so you can tweak before running the negotiation.

**Keeping the sheet private** (the form collects private budget limits): create a Google Cloud service account,
enable the Sheets API, share the response sheet with the service account's e-mail, and paste its JSON key in the
step 1 (or `GOOGLE_SERVICE_ACCOUNT_JSON`). Needs `pip install gspread`.

Question titles are matched by keyword (`rfq_intake.py`), so keep words like *Quantity*, *Max price*, *Target delivery*
if you rename them. `python test_intake.py` self-tests the parser.

## Architecture
| File | Role |
|---|---|
| `models.py` | Pydantic schemas + supplier cost model |
| `agents.py` | Buyer / Supplier agents (private state, LiteLLM + guardrails + rule fallback, `probe()` for red-team) |
| `orchestrator.py` | Round loop, anonymised market pressure, weighted scoring, leak audit |
| `security.py` | Input filter (prompt-injection patterns) + output redactor (masks private numbers) |
| `analytics.py` | Savings and time metrics |
| `audio.py` | Transcript builder and browser text-to-speech player |
| `po_generator.py` | ReportLab PO PDF (multi-line, pro-rata allocation) |
| `rfq_intake.py` | Reads Google Form responses (link or service account) into `RFQ` objects, incl. line items and supplier contacts |
| `decision.py` | Approve / manual-select / reject-all decision record |
| `notifier.py` | Award + regret e-mails, SMTP sending, .eml export, outgoing privacy check |
| `ui_style.py` | Theme CSS and HTML helpers (header, KPI cards, chips) |
| `google_form_setup.gs` | Apps Script that creates the form + response sheet |
| `app.py` | Streamlit UI |
| `test_core.py` / `test_intake.py` / `test_notify.py` | Self-tests: engine, guardrails, security, multi-item PO, decisions, form parsing, e-mails |

## Notes
- Red-team lab without an API key uses a *simulated unguarded model* that spills secrets when asked, so the
  defence layers have something to stop. With an LLM enabled, the real model replies and the same layers apply.
- Scoring: 60% price, 25% delivery, 15% payment terms.
- Supplier prices, floors and delivery times are for the **whole package**, so scale them when you add lines.
- Savings "manual baseline" figures are assumptions you can edit, not measured data.
