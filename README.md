# Aangan Studio: AI phone agent and enquiry backend

MESA *AI and its Application*, Case 03.

**Live demo:** https://aangan-voice-agent-dusky.vercel.app/dashboard
(The live site shows the T01–T20 calls from the September file, with simulated designer claims. Changes you make there reset; see §10.)

Nikhil's problem: about 200 enquiries a month, about 48% get no reply within 48 hours, a third arrive after the
front desk closes, and designers receive leads "as a forwarded message with no context".

**What this builds:**
- An AI phone agent (on the Vaani voice platform) answers every call, 24/7.
- It checks the caller against Nikhil's own rubric (`qualified.md`).
- It books a consultation or declines politely, and escalates complaints from existing clients.
- Everything around it is built here:
  - the backend that receives each finished call
  - a designer handoff note that never re-asks what was already asked
  - Telegram alerts with a one-tap **Claim** button
  - a daily email digest
  - SQLite logging
  - a one-page dashboard showing what it generates and what it costs
  - a test harness built from the real September calls

Scope: **phone only**. WhatsApp and the web form plug into the same pipeline later (see §9).

```
 Caller ──► Vaani agent ──(end-of-call webhook)──► /webhooks/vaani
            (agent/system_prompt.md)                     │
                                                         ▼
                              vaani_adapter  (MOCK schema, swap later)
                                                         │  Enquiry
                                                         ▼
     pipeline:  de-duplicate → rubric check (rules.py) → pricing guardrail → repeat/dropped-call check
                → store (SQLite) → handoff note → route
                                                         │
                     ┌───────────────────────┬───────────┴──────────┬──────────────────────┐
                     ▼                       ▼                      ▼                      ▼
          Book → designers group   Escalate → Nikhil's      Ask → front-desk chat   Decline → logged
          [✋ Claim this lead]     urgent chat [✅ I'm on it]                         (digest + dashboard)
                     │
          scheduler: re-alert every 20 min → after 3 tries → Nikhil · daily email digest at 08:30
                     │
          dashboard: /dashboard   (what it generates · what it costs · ROI)
```

---

## 1. Run it locally

Needs Python 3.11 or newer. Everything installs into a local `.venv`.

```bash
python3 -m venv .venv
```
```bash
.venv/bin/pip install -r requirements-dev.txt
```
```bash
cp .env.example .env
```

Run the tests (33 tests: webhook, rubric check, guardrail, handoff, routing, logging, metrics, all T01–T20 cases):
```bash
.venv/bin/pytest -q
```

Replay T01–T20 and print the decision table:
```bash
.venv/bin/python -m tests.replay
```

Load the demo data and start the server:
```bash
.venv/bin/python -m tests.seed_demo --reset
```
```bash
.venv/bin/uvicorn app.main:app --reload
```

Then open **http://localhost:8000/dashboard**.

With an empty `.env`, everything runs in **dry-run mode**:
- Telegram messages are written to `data/outbox.log`.
- Digests are saved to `data/digests/`.

That means the whole flow works offline in class.

Preview the email digest for any day:
```bash
.venv/bin/python -m app.notify.email_digest 2026-09-22
```

---

## 2. What's where

| Path | What it is |
|---|---|
| `agent/system_prompt.md` | **Paste into Vaani.** Part A is the conversation. Part B is the end-of-call JSON. |
| `agent/output_schema.json` | The JSON the agent must produce: caller, five criteria, decision, reason, slot, flags |
| `agent/contradictions.md` | 18 conflicts and gaps between the source files, with recommended rules. 🔴 = confirm with Nikhil |
| `app/channels/` | One adapter per channel → one shared `Enquiry` shape. `vaani_adapter.py` holds the **mock** field map |
| `app/pipeline.py` | The steps every enquiry goes through |
| `app/rules.py` | `qualified.md` as code. Re-checks the agent's decision |
| `app/guardrails.py` | Scans the agent's speech for anything that looks like a price |
| `app/handoff.py` | The designer note (plain text and Telegram versions) |
| `app/notify/telegram.py` | Routing, the Claim button, edits after a claim, dry-run mode |
| `app/notify/email_digest.py` | The daily digest (record and fallback) |
| `app/scheduler.py` | Re-alerts and the digest timer |
| `app/db.py` | SQLite: `enquiries`, `events` (history of each enquiry), `alerts` |
| `app/costs.py`, `app/metrics.py` | Cost per call, and every dashboard number |
| `app/demo.py`, `demo/cases/*.json` | T01–T20 as mock agent outputs with the expected decision, plus the demo seeder |
| `config/assumptions.yaml` | **Every rate and business number**, labelled ASSUMPTION or "from the brief" |
| `dashboard/index.html` | The single-page dashboard (no build step, no CDN) |
| `api/index.py`, `vercel.json` | Vercel entry point |

---

## 3. Connecting to Vaani

**What we know and what we don't.** We searched for public docs on Vaani's end-of-call webhook and couldn't
confirm a payload format. Several products use the Vaani name, and the docs we found were unreachable or didn't
describe the payload. So **no field name in this code is presented as Vaani's real format.**

All the guessed names live in one dict, `MOCK_FIELD_MAP`, in `app/channels/vaani_adapter.py`, under a warning banner.

Steps to connect the real thing:
1. **Deploy the server somewhere with HTTPS and a persistent disk** (see §10).
   - Set `PUBLIC_BASE_URL`, `WEBHOOK_TOKEN`, `LINK_SECRET` and `DASHBOARD_PASSWORD` in `.env`.
2. **Create the agent in Vaani.**
   - Paste **Part A** of `agent/system_prompt.md` as its instructions.
   - Put **Part B** wherever Vaani does post-call extraction (an analysis prompt, structured output, or an end-call function).
   - Set up the `{{current_datetime}}` and `{{available_slots}}` placeholders using Vaani's variable syntax.
3. **Capture one real payload.**
   - Point Vaani's end-of-call webhook at `https://YOUR-HOST/webhooks/vaani/capture?token=WEBHOOK_TOKEN`.
   - Make one test call. The payload is saved, and also echoed back in the response.
4. **Edit `MOCK_FIELD_MAP`** so each entry points at the real field.
   - Adjust `_parse_transcript` and `_parse_time` only if the shapes differ.
   - Nothing else changes, because the rest of the pipeline only sees `Enquiry`.
5. **Switch the webhook** to `https://YOUR-HOST/webhooks/vaani?token=WEBHOOK_TOKEN`.
   - Run `.venv/bin/python -m tests.replay --live https://YOUR-HOST` to check the live server.
6. **If Vaani can't produce the structured JSON at all,** calls still arrive.
   - The backend marks them **Ask + needs review**, so a person reads the transcript. Nothing is silently dropped.
   - The next improvement would be the backend running Part B itself on the transcript with an LLM.

**Safety nets on every call:**
- **Duplicate deliveries are ignored**, matched on call ID.
- **The rubric check:** if the agent's decision contradicts its own criteria, the rubric wins and the call is flagged for review. A complaint is never downgraded.
- **The pricing guardrail** scans the *agent's* lines only.
- **Repeat callers are caught by phone number:** within 14 days, and in any format (`+91…`, `0…`).
- **A dropped call** is linked to the caller's call-back within 30 minutes, and then stops being chased.

---

## 4. Setting up Telegram

1. **Create the bot.** In Telegram, message **@BotFather**, send `/newbot`, and copy the token into `TELEGRAM_BOT_TOKEN`.
2. **Create the groups:**
   - **Aangan Designers:** the designers. Qualified leads go here.
   - **Aangan Urgent:** Nikhil and seniors. Complaints, priority leads, and leads nobody claimed.
   - *(optional)* **Aangan Front Desk:** Ask follow-ups and guardrail alerts. If you skip it, these go to the digest only.
3. **Add the bot to each group** and send `/start@YourBotName` in each one.
4. **Get the chat IDs:** run `.venv/bin/python -m app.notify.telegram_cli chats`, then copy the IDs (negative numbers) into
   `TELEGRAM_DESIGNERS_CHAT_ID`, `TELEGRAM_URGENT_CHAT_ID` and `TELEGRAM_FRONTDESK_CHAT_ID`.
5. **Set up button taps.** Set `TELEGRAM_WEBHOOK_SECRET` to any random string, then choose one:
   - **Deployed:** `.venv/bin/python -m app.notify.telegram_cli set-webhook` (taps go to `/telegram/webhook`).
   - **On a laptop:** `.venv/bin/python -m app.notify.telegram_cli poll` (no public URL needed).

How claiming works:
- **First tap wins.** The database makes sure two simultaneous taps can't both succeed.
- **Every copy of the alert is updated** to "✅ Claimed by Meera at 11:53 AM (12 min after the call)", and the button disappears.
- **Only the configured chats are accepted,** so a stranger who finds the bot can't claim leads.
- **People not on Telegram** can claim from the dashboard.

Timing defaults (all in `config/assumptions.yaml`):
- A lead nobody claims is re-posted every 20 min. After 3 tries it goes to Nikhil's urgent chat.
- Complaints re-alert every 10 min.
- From 9pm to 8am alerts arrive **silently** and re-alerts pause.

**Email digest:** fill in the `SMTP_*` and `DIGEST_TO` settings. For Gmail, use an *app password*, not the account
password. It's sent daily at 08:30 for the previous day.

---

## 5. The Cut: why the agent never quotes a price

Nikhil asked for it in so many words: *"the system should be able to quote our standard per-square-foot pricing."*
We deliberately didn't build it. The agent says only the approved line from `pricing.md`:

> "Pricing depends on the site, the materials you choose, and the scope — your designer will walk you through it in
> detail at the consultation. I can book that for you right now if you'd like."

Why:
1. **Nikhil's own pricing guide forbids it.** The first line of `pricing.md` says *"No number from this guide should be quoted to a
   client,"* and it lists the exact phrases the agent must never say. Building the feature would contradict the
   studio's own written policy.
2. **The ranges are too wide to be honest on a phone call.**
   - Residential runs from ₹1,800 to over ₹3,500 per sq ft. The front desk itself said a premium kitchen can cost 3× a standard one (T13).
   - Any number the agent gives becomes the anchor the client holds the designer to.
3. **Carpet vs built-up area.** The rates are per sq ft of *carpet* area. Callers mix the two up. T01 said
   "carpet", T02 just said "sq ft". That's a 20–30% error before the conversation even starts.
4. **The price depends on things the agent can't see:** site condition, the custom-furniture ratio, material brands, and timeline
   pressure (pricing.md, "What affects pricing").
5. **There's no human checking a quote before it's spoken.** One wrong figure goes out to every caller, 24/7, and
   it's recorded.
6. **Deflecting doesn't lose good leads.** T02 and T13 both pushed for a ballpark twice, accepted the deflection,
   and booked. qualified.md agrees that asking about pricing does *not* disqualify anyone.

**Enforced twice.** The prompt forbids it, and `app/guardrails.py` scans the agent's side of every transcript for ₹,
"lakh", "per sq ft", "starting from" and similar phrases. A hit flags the call for review, alerts the front desk, and
counts on the dashboard.

**What we kept:** the one budget behaviour Nikhil *does* want (qualified.md criterion 4). If a caller volunteers a
budget that's clearly too low (T10: ₹1–1.5 L for a kitchen and a bedroom), the agent says so honestly, **without stating
any number**.

---

## 6. Telegram vs email

| | Telegram | Email |
|---|---|---|
| Seen within minutes on a site visit | ✅ Phone notification | ❌ Often hours later |
| One-tap Claim in a shared group | ✅ Native buttons | ❌ No real equivalent |
| Shows who has it, so no duplicate calls | ✅ Message edited for everyone | ❌ |
| Searchable record, forwardable, works for Nikhil's reporting | ⚠️ Chat history only | ✅ |
| Cost | Free | Free |

**Decision: Telegram for action, email for the record.**
- The brief's own number decides it: answered within an hour converts at 4× next-day. Leads have to reach a designer *on their phone* and be claimed *by one person*.
- Telegram does that. Email doesn't.
- The **daily email digest** includes the full designer note for every booked lead. So it's both the written record Nikhil can search and file, and the fallback if Telegram is ever down.

**Why not WhatsApp**, even though everyone already uses it:
- WhatsApp's official Business API **can't post to groups**, so there's no shared "first to claim".
- It charges per conversation, and proactive alerts need Meta-approved templates.
- Unofficial WhatsApp group bots break WhatsApp's terms and get numbers banned.

Slack or Teams would only make sense if the studio already paid for them.

---

## 7. Test harness: T01–T20 against qualified.md

`.venv/bin/python -m tests.replay` sends every phone transcript through the real webhook as a mock agent output.

```
ID   | C1 C2 C3 C4 C5 | Decision | Expected | OK | Reason
T01  |  ✓  ✓  ✓  ✓  ✓  | Book     | Book     | ✓  | Full 3BHK redesign in Kothrud, relaxed timeline.
T02  |  ✓  ✓  ✓  ✓  ✓  | Book     | Book     | ✓  | Full 2BHK redesign in Wakad; asked about price twice and was deflected.
T03  |  ✓  ✗  ?  ✓  ✓  | Decline  | Decline  | ✓  | Site is in Nashik, outside Pune/PCMC.
T04  |  ✗  ?  ?  ✓  ✓  | Decline  | Decline  | ✓  | Wants ideas and advice only, no execution.
T05  |  ✓  ✓  ✓  ✓  ✓  | Book     | Book     | ✓  | 4BHK Koregaon Park complete redesign; personal referral via Nikhil's friend.
T06  |  ✓  ✓  ✓  ✓  ✓  | Book     | Book     | ✓  | 800 sq ft bare-shell office fitout in Baner by December.
T07  |  ✓  ?  ✗  ✓  ✓  | Decline  | Decline  | ✓  | Wants it done before Diwali (~3 weeks); offered a post-Diwali start, caller will think.
T08  |  ✓  ✓  ✓  ✓  ✓  | Book     | Book     | ✓  | After-hours call: Nanded City 2BHK full interiors (simulated details).
T09  |  –  –  –  –  –  | Escalate | Escalate | ✓  | Existing client: designer unresponsive for 5 days.
T10  |  ✓  ✓  ?  ✗  ✓  | Decline  | Decline  | ✓  | Volunteered budget clearly below a kitchen + bedroom with execution.
T11  |  ✓  ✓  ?  ✓  ✓  | Ask      | Ask      | ✓  | Rented Baner 2BHK, good fit, but completion timeline not established.
T12  |  ✓  ✓  ✓  ✓  ✓  | Book     | Book     | ✓  | 5,500 sq ft new villa in Kalyani Nagar, full design, March move-in.
T13  |  ✓  ✓  ?  ✓  ✓  | Ask      | Ask      | ✓  | Aundh 3BHK, keen to book, but completion timeline not established.
T14  |  ✓  ✓  ?  ✓  ?  | Ask      | Ask      | ✓  | Son calling for parents' Hadapsar 3BHK; timeline not established.
T15  |  ✓  ✓  ✓  ✓  ✓  | Book     | Book     | ✓  | Undri 2BHK full home; design during the 6 weeks before possession.
T16  |  ✓  ✓  ?  ✓  ✓  | Ask      | Ask      | ✓  | Repeat caller (Monday enquiry never followed up); timeline not established.
T17a |  ?  ?  ?  ✓  ✓  | Ask      | Ask      | ✓  | Line dropped before any details.
T17  |  ✓  ✓  ✓  ✓  ✓  | Book     | Book     | ✓  | Pimple Saudagar 3BHK, standard full-home scope, March.  [linked to #17]
T18  |  ✗  ?  ?  ✓  ✓  | Decline  | Decline  | ✓  | 180 sq ft coworking pod, below the ~500 sq ft commercial minimum.
T19  |  ✗  ✓  ?  ✓  ✓  | Decline  | Decline  | ✓  | Restaurant interiors are out of scope.
T20  |  ✓  ✓  ✓  ✓  ✓  | Book     | Book     | ✓  | Magarpatta 2BHK, full scope, January execution start.

Totals: Book 9, Ask 5, Decline 6, Escalate 1        21/21 match qualified.md
```

**What the 21/21 proves.** The backend applies the rubric exactly as written. The mock agent outputs and the expected decisions
both come from our reading of qualified.md, so this does *not* yet prove the live agent judges calls correctly. That needs
real Vaani test calls.

**How to read it:**
- **The mocks use only facts from the transcripts.** Where the transcript never answers something the agent *would* ask, the criterion stays `?`.
  - **T11, T13, T14 and T16 were booked by the human front desk without anyone asking when the project had to be done.**
  - Under qualified.md, criterion 3 is then unclear, so the agent asks once, and the honest mock result is **Ask**.
  - On a live call they'd almost certainly become **Book** after that one question. This is the agent being *more* consistent than the front desk, and it's worth saying in class.
- **T08 was a missed call.** Its case is marked **SIMULATED**, with invented project details, to show the call the agent would have answered at 10:47pm.
- **T17** appears twice: the dropped first attempt (T17a) and the call-back two minutes later.
  - The backend links them automatically, and stops chasing the dropped one.
- **T16 is a repeat caller.** It's an Ask, but the alert *also* goes to Nikhil's urgent chat so it can't slip a second time.
- **T20 called at 9:15am,** before the front desk opens, so it's counted as after-hours.

**Demo data:** `tests.seed_demo` loads the same 21 calls into `data/aangan.db`, marked `is_demo`.
- The claims are simulated, with invented designer names and times.
- T20 is left unclaimed on purpose, so "Needs attention" has something in it.
- The dashboard's **Demo data** switch hides all of it, and re-alerts ignore demo rows.

---

## 8. Dashboard: what it shows and where the numbers come from

- **What it generates:**
  - A before vs now comparison, using the brief's ~48% unanswered and ~33% after-hours
  - Calls answered, % answered within 5 min, after-hours share
  - Qualified %, consultations booked
  - A funnel: calls → enquiries → qualified → booked → claimed
  - Decline reasons
  - Escalations, with acknowledgement time
  - Call → designer claim time (median and % within 1 hour)
  - Pipeline value: qualified leads × ₹8–14 L, *gross, before conversion*
  - Calls by hour, with front-desk hours shaded
- **Enquiries:**
  - "Needs attention" cards
  - A searchable table with filters
  - Click any row for a side panel: the reason, each criterion with its evidence, the exact designer note, the history, and the transcript
- **What it costs:**
  - Voice, phone line, LLM, messaging, and hosting/fixed costs
  - Cost per enquiry, per qualified lead and per booked consultation
  - A monthly projection with a call-volume slider
  - ROI
- **Every rate is in `config/assumptions.yaml`**, labelled **ASSUMPTION** or "Known". Replace the voice rate first: at ₹6/min it's about 75% of the cost of each call.
- **Volume:** the default is 200 calls a month, from the brief. That's cautious for phone only. In the September sample 20 of 40 enquiries came by phone.
- **Average call length: 4 min 47 s.** It's the mean of the 19 answered transcript calls. T08 was missed, and T17's 1:12 dropped attempt is excluded. After 30 real calls, the dashboard switches to the logged average.
- **Cost:** ₹37.98 per call and about ₹8,900 a month at 200 calls.
- **ROI, in order of how defensible it is:**
  1. **Break-even:** monthly cost ÷ (₹11 L average project × 25% margin) works out to **one extra project every ~31 months**. Lead with this one.
  2. **The full model:** slow enquiries (48% × volume) × qualified share × (4× − 1) × a 3% base conversion ≈ about 4 extra projects a month. The 48% and 4× come from the brief. The 3% and 25% are assumptions.
- **The CSV export** (`/api/export.csv`) lets Nikhil take the raw numbers into Excel without copying anything by hand.

---

## 9. Extending to WhatsApp and the web form

The code is already shaped for this. Each channel needs only an adapter that produces an `Enquiry` with the same
`agent_output` JSON. The rubric check, handoff note, Telegram routing, logging and dashboard are all shared.
The stubs are `app/channels/whatsapp_adapter.py` and `webform_adapter.py`, and the routes `/webhooks/whatsapp` and
`/webhooks/webform` return "planned" (501) today.

- **WhatsApp:**
  - The WhatsApp Business API sends incoming messages to our server.
  - A text version of the same prompt replies instantly, in Hindi or Hinglish where needed (W03).
  - When the conversation ends or goes quiet, it produces the Part B JSON.
  - Photos (W09) are stored as links in the handoff note.
  - `answer_delay_sec` becomes time to first reply. `duration_sec` is empty.
- **Web form:**
  - The form fields map almost one-to-one onto `project`, `budget` and `source`, so the five criteria are filled straight from the form.
  - Anything unclear (F04: "Location: Pune, Budget: reasonable") becomes **Ask**.
  - The phone agent then makes **one outbound call** to ask the missing question, and that call comes back through the Vaani adapter.

How the other 20 enquiries would flow:

| ID | What it is | Expected decision | Note |
|---|---|---|---|
| W01 | Viman Nagar 4BHK, referral, 7:14pm | Book | Instant reply instead of 16 h. Note "weekdays after 6pm / weekends" in the slot |
| W02 | "per sq ft for a 2BHK?" | Ask | Pricing line + one question, sent instantly. The real thread waited 2 days |
| W03 | Pimple Nilakh 3BHK, Hindi | Ask → Book | Agent replies in Hindi and asks the timeline once. "Budget bhi hai" counts as a pass |
| W04 | Chinchwad 1,200 sq ft office, Jan | Book | Asked for a calendar link; the designer confirms the slot |
| W05 | Baner 2BHK, Saturday 6:44pm | Ask | **Lost to a 2-day delay.** The instant reply is the fix |
| W06 | Koregaon Park 3BHK, referral, possession 15 Oct | Book | Site visit after possession |
| W07 | Gym, Kothrud | Decline | `out_of_scope_type` |
| W08 | Aundh 2BHK, "messaged 4 days ago" | Ask | Repeat-contact flag → also posted to Nikhil's urgent chat |
| W09 | Aundh living/dining, photos | Ask → Book | Photos kept as links |
| W10 | Hinjewadi 3BHK, "just exploring" | Ask | `nurture_later`: re-engage in 4–6 weeks |
| F01 | Kalyani Nagar 2BHK, Dec–Feb | Book | |
| F02 | Baner, 2 rooms, referral | Book | |
| F03 | Talegaon, ₹15–20 L | Decline | Outside the area. A strong lead, so worth raising with Nikhil (contradictions #5) |
| F04 | "cost of interior design, please call me" | Ask | Outbound call to qualify |
| F05 | Hinjewadi 2,200 sq ft office, CEO referral | Book | Ready to move fast. Large and urgent → priority |
| F06 | NIBM 4BHK, ₹35–40 L firm, 3 studios shortlisted | Book | Budget volunteered and plausible; note "not flexible upward" for the designer |
| F07 | Anonymous, "email me the price list" | Ask | Never send a price list. Reply with the pricing line and an invitation |
| F08 | Wakad, 3 weeks before guests arrive | Decline | `timeline_too_short` + `nurture_later` |
| F09 | Kondhwa 3BHK, builder referral, March 2027 | Book | |
| F10 | Aundh 3BHK + 2 home offices, ₹18–22 L | Book | Opinionated clients wanting a collaborative process; note it for the designer |

---

## 10. Deployment

**The live demo runs on Vercel.** Vercel runs the app per request, which has two limits:
- **Data resets.** Its filesystem is read-only except `/tmp`, so the SQLite database lives there. Each new instance re-loads the T01–T20 demo (`DEMO_SEED=true`). Claims you make on the live site reset when the instance restarts. `POST /api/demo/reset` restores the starting state on demand.
- **No re-alert loop.** Nothing runs between requests, so the every-minute loop is off. To drive re-alerts and the digest, point an external cron (for example cron-job.org, every minute) at `/tasks/tick?token=CRON_TOKEN`.

To redeploy after a change:
```bash
vercel deploy --prod
```

**For real use,** deploy to a host with a persistent disk and an always-on process, such as Render, Railway or a ₹800/month VM:
- Run `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Set `DEMO_SEED=false` and `SCHEDULER_ENABLED=true`.
- Fill in `.env` from `.env.example`.

---

## 11. Before go-live: confirm with Nikhil

See `agent/contradictions.md`. The 🔴 items change who gets booked or what callers hear:
- The minimum timeline: 6 weeks or 8–10 weeks?
- Does one failed criterion decline, or two?
- The 500 sq ft commercial minimum
- The "adjoining areas" list, and the unclear places (Wagholi, Moshi and others)
- The internal "clearly too low" budget line (₹3 L)
- Whether the agent may call the consultation "free"
- The pricing cut itself
- The complaint callback promise at night
- Consultation slots
- Announcing up front that it's an AI and the call is recorded

## 12. Privacy, security and known limits

- **Privacy:** transcripts contain names and phone numbers.
  - Transcript links are **signed** (`LINK_SECRET`), so they can't be guessed.
  - The dashboard and APIs need `DASHBOARD_PASSWORD` for real data. The live demo is left open because it only holds the anonymised case transcripts.
  - Webhooks need `WEBHOOK_TOKEN`, button taps need `TELEGRAM_WEBHOOK_SECRET`, and `/tasks/tick` needs `CRON_TOKEN`.
  - Secrets live only in `.env`, which is gitignored.
  - Decide how long to keep data. India's DPDP Act expects you to keep personal data only as long as it's needed.
- **Not built:**
  - Live calendar booking. The agent offers configured slots, and the designer confirms.
  - An LLM backup that pulls the structured data from the transcript when Vaani doesn't provide it.
  - Multi-server scaling. The scheduler runs in a single process, which is fine at about 200 calls a month.
- **Unconfirmed:**
  - Vaani's webhook format, pricing, variable syntax, language support and post-call features.
  - Everything that depends on them is isolated in `vaani_adapter.py`, `assumptions.yaml` and Part B of the prompt.
