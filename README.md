# Aangan Studio: AI phone agent and enquiry backend

MESA *AI and its Application*, Case 03.

**Live demo:** https://aangan-voice-agent-dusky.vercel.app/dashboard
(The live site shows the T01–T20 calls from the September file, with simulated designer claims.)

An AI phone agent on the Vaani voice platform answers every call to the studio, 24/7.
- It checks each caller against Nikhil's rubric (`qualified.md`).
- It books a consultation or declines politely.
- It escalates complaints from existing clients.

This repo is everything around the agent:

| Path | What it is |
|---|---|
| `agent/system_prompt.md` | Prompt to paste into Vaani. Part A is the conversation; Part B is the end-of-call JSON |
| `agent/output_schema.json` | The structured output: five criteria, decision, reason, slot, flags |
| `agent/contradictions.md` | Conflicts between the source files, with recommended rules. 🔴 = confirm with Nikhil |
| `app/` | FastAPI backend: Vaani webhook (adapter with a **mock** schema), rubric check, pricing guardrail, designer handoff note, Telegram routing with a Claim button, daily email digest, SQLite logging, cost model |
| `dashboard/index.html` | One-page dashboard: what it generates, what it costs, ROI |
| `config/assumptions.yaml` | Every rate and business number, labelled ASSUMPTION or "from the brief" |
| `demo/cases/` | T01–T20 as mock agent outputs, each with the expected decision |

## Run locally

Set up a virtual environment and install dependencies:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

Start the server with the demo calls loaded:
```bash
DEMO_SEED=true .venv/bin/uvicorn app.main:app --reload
```

Then open http://localhost:8000/dashboard.

## The pricing cut

Nikhil asked for the agent to quote per-sq-ft prices. We deliberately left that out.
- **The agent only uses the approved line in `pricing.md`.** That file itself says no number should be quoted to a client.
- **The rates are too wide to quote honestly by phone:** ₹1,800 to over ₹3,500 per sq ft.
- **Carpet vs built-up area confusion** adds 20–30% error.
- **No human checks a figure before it's spoken.**
- **The backend scans every call for leaked prices** (`app/guardrails.py`).

## Deployment notes (Vercel)

- **Data resets:** Vercel runs the app per request, and the SQLite database lives in `/tmp`. Each new instance re-seeds the demo data, so it's a **demo deployment**: changes such as claims reset.
- **No re-alert loop:** the every-minute loop is off on Vercel. Point an external cron at `/tasks/tick?token=CRON_TOKEN` to drive re-alerts and the digest.
- **For real use,** deploy to a host with a persistent disk (Render, Railway or a small VM), set `DEMO_SEED=false`, and fill in `.env` from `.env.example`.

The full setup guide (Vaani, Telegram, email, tests) is coming in the next update.
