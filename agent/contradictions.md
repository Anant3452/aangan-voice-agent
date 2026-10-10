# Contradictions & gaps between the source files

Sources compared: `qualified.md` (Q), `services.md` (S), `pricing.md` (P), the brief (B), and the 40 enquiry transcripts (T/W/F — what the front desk actually does).

For each: what conflicts → the rule the agent uses now → whether **you must confirm with Nikhil** before go-live.

Legend: 🔴 **Confirm with Nikhil** (affects who gets booked or what the caller is told) · 🟡 Confirm when convenient · 🟢 Resolved from the files, no confirmation needed

---

## A. Contradictions

### 1. Timeline rule — 6 weeks vs 8–10 weeks vs design + execution 🔴
- **S:** "we cannot begin execution on a project that needs to be ready in under **6 weeks** from today."
- **Q (criterion 3):** "site must be available for execution within **8–10 weeks** of the consultation… if someone needs it done in 3 weeks, we cannot serve them."
- **T07 front desk:** "a room redesign with execution takes **at least 8–10 weeks** from start to finish."
- **S also:** design 3–4 weeks + execution 8–16 weeks = **11–20 weeks** realistic minimum — longer than either rule.
- Q's wording is also ambiguous: "available for execution *within* 8–10 weeks" can be read as a *maximum* wait (site must be ready soon), not a minimum lead time.

**Recommended rule (in the prompt):** treat 8–10 weeks as a **minimum time to completion**. Under 8 weeks → fail (offer a later start). No deadline or 10+ weeks → pass. A site that isn't available yet (possession pending) is **not** a fail — design can start before possession (T15, W06).
**Ask Nikhil:** (a) Is the minimum 6, 8 or 10 weeks? (b) Does a far-off site (possession in 6+ months) fail criterion 3, or is it fine?

### 2. Does ONE failed criterion decline, or TWO? 🔴
- **Q (top):** "If it **fails one**, close gracefully — don't forward an incomplete lead."
- **Q ("At the boundary"):** "**Two or more** criteria fail: decline gracefully."
- That leaves one fail undefined in the second rule. Every transcript with a single fail (T03 area, T04 advice-only, T10 budget, T19 type) was declined.

**Recommended rule:** **one clear fail = Decline** (matches the top rule and front-desk practice).
**Ask Nikhil:** confirm. If he means "two", T03/T04/T10/T19-type calls would get booked — a big change.

### 3. Commercial minimum size — 500 sq ft (T18) not in services.md 🔴
- **T18 front desk:** "Our commercial projects are typically **500 sq ft or more**."
- **S:** commercial "up to approximately 3,000 sq ft" — states a max, no min. S also says a *single room* is a valid residential project, so a 180 sq ft space isn't obviously too small.

**Recommended rule:** decline commercial spaces **under ~500 sq ft** (reason `below_min_size`), as the front desk did.
**Ask Nikhil:** is 500 sq ft the real floor? Write it into services.md either way.

### 4. Commercial above 3,000 sq ft 🟡
- **S:** "up to approximately 3,000 sq ft" — doesn't say whether larger is a decline.

**Recommended rule:** don't decline; book with flag `large_project` so Nikhil decides. (Residential has no upper limit — T12's 5,500 sq ft villa was welcomed.)

### 5. "Adjoining areas" is undefined 🔴
- **S** lists localities "and adjoining areas" and says "Pune city and PCMC"; **Q** says "Pune city or PCMC".
- **Kharadi (T10)** — not listed, but within Pune city (PMC) next to Viman Nagar → treated as in-area (T10 was declined on budget, not location).
- **Nanded City (T08)** — not listed; off Sinhagad Road, next to listed Shivane/Warje → treated as in-area.
- **Talegaon (F03)** — explicitly excluded in both Q and S, even though F03 calls it "near Pune" and has a strong budget → out.
- **Hinjewadi** is listed under PCMC, though parts are technically PMRDA — so S already isn't strict about municipal boundaries.

**Recommended rule (in the prompt):** three explicit lists — listed / adjoining (treat as in) / out. Anything not on a list: ask one question ("which part of Pune is that closest to?"); if still unclear → **Ask** (front desk confirms), never a guess.
**Ask Nikhil:** approve the "adjoining" list, and decide on the grey ones: **Wagholi, Lavale, Pirangut, Chakan, Moshi, Khadakwasla, Manjri**.

### 6. Budget: "address the misalignment" vs "never say a number" 🔴
- **Q (criterion 4):** if a volunteered budget is clearly too low, "address the misalignment on the call."
- **P:** the agent must never say "any specific number, range, or per-sq-ft figure."
- To judge "clearly below", the agent needs *some* internal threshold — which is itself a number it might leak.

**Recommended rule:** one internal-only threshold in the prompt — a volunteered total **under ₹3 lakh** for any project with execution fails (P's cheapest item, a single room, starts at ₹3.5 lakh). The agent addresses it **without numbers**, the way T10's front desk did. It never repeats the caller's figure. The backend also scans every agent line for ₹/lakh/sq-ft figures and flags any leak.
**Ask Nikhil:** approve ₹3 lakh as the "clearly below" line. (F08's ₹4–5 lakh for living + kitchen is borderline; under this rule it passes on budget and fails on timeline.)

### 7. Decision-maker: "not sufficient on its own" vs "don't push" 🟡
- **Q (criterion 5):** "'I'm just doing initial research for my in-laws' is not sufficient on its own."
- **Q (boundary):** "Unclear on 4 or 5: do not push. Treat as qualified."
- **T14:** son calling for parents; parents will attend → front desk booked.

**Recommended rule:** ask once if the owners can join; yes → Book, flag `acting_on_behalf`. Unsure → still Book, flag it, note the uncertainty. Never decline on criterion 5 alone.

### 8. "Free consultation" — said by the front desk, not in any file 🔴
- **T02, T13:** "the consultation is **free** and there's no obligation."
- No file says this, and "free" is a pricing statement.

**Recommended rule:** the agent does **not** say "free" until Nikhil confirms. If confirmed, add one approved sentence to the pricing section of the prompt.

### 9. The price-quoting ask vs pricing.md (THE CUT) 🔴
- **B (Nikhil):** "the system should be able to quote our standard per-square-foot pricing."
- **P (Nikhil's own guide):** "No number from this guide should be quoted to a client." Lists exactly what the agent must never say.

**Rule:** no quoting — only the approved line. Reasons are in the README (P's own warning, carpet vs built-up confusion, 3× spread between tiers per T13, the anchoring and trust risk, and no human checking each call). **Tell Nikhil explicitly** — this is a deliberate cut of something he asked for.

### 10. Single-room scope — which rooms? 🟡
- **S (typical scope):** "Single room: bedroom or living room."
- **S (residential) & Q:** any "individual room" with complete redesign + execution is fine.

**Recommended rule:** any one room with full execution passes (kitchen included). Confirm whether a kitchen-only or bathroom-only job counts.

### 11. Retail/hospitality "as primary projects" 🟢
- **S:** "We do not take on retail or hospitality … **as primary projects**" (suggests secondary might be OK) vs "Restaurants, hotels, retail stores, gyms: out of scope."

**Rule:** decline all of them (T19, W07 precedent). The "primary" wording should be cleaned up in services.md.

---

## B. Gaps (nothing in the files covers these)

### 12. Complaint callback promise outside office hours 🔴
T09 promised "someone senior … within 15 minutes" — at 11:32 am. The agent also answers at 2 am.
**Recommended rule:** 9 am–9 pm → "within 15 minutes"; otherwise → "first thing tomorrow, by 10 am, flagged urgent". Unclaimed complaints re-alert every 10 minutes during the day.
**Ask Nikhil:** who is the senior backup when he's unavailable, and is the 15-minute promise realistic?

### 13. Consultation slots & calendar 🔴
No file says when designers are available. Transcripts show weekday and Saturday morning slots (W03: Saturday 10:30 am) and site visits.
**Recommended rule:** the agent offers two slots from a configured list; the designer who claims the lead confirms. We do **not** assume Vaani can write to a live calendar.
**Ask Nikhil:** standard slot times, whether Saturdays/Sundays are bookable, and how fast a designer must confirm.

### 14. Repeat callers who were never followed up (T16, W08) 🟡
No rule exists. W08's note says "escalate to senior designer for same-day outreach."
**Recommended rule:** the agent apologises, re-takes details and books on the spot. The backend also detects a prior call from the same number with no claim → marks the lead **PRIORITY** and copies Nikhil's urgent chat.

### 15. AI disclosure & call recording 🔴
Not in any file. Your rule: disclose if asked and offer a human callback.
**Recommended rule (in the prompt):** the greeting already says "virtual assistant" and "calls are recorded". Honest disclosure is always given if asked. Recording notice is good practice under India's DPDP Act, since we store transcripts.
**Ask Nikhil:** OK with the agent introducing itself as a virtual assistant up front?

### 16. Language — Marathi 🟡
W03 shows Hindi/Hinglish. Pune callers may speak Marathi. No file mentions it.
**Recommended rule:** mirror Hindi/Hinglish fully; Marathi if the voice model handles it naturally, otherwise continue politely in Hindi/English. Check what Vaani actually supports.

### 17. Not-a-lead calls (vendors, job seekers, wrong numbers) 🟢
**Rule:** Decline with `reason_code = not_a_lead`. The dashboard excludes these from qualification percentages.

### 18. Who the agent says it is (voice gender for Hindi verbs) 🟢
Hindi verbs are gendered ("kar sakti/sakta hoon"). The prompt notes this. Match it to the Vaani voice you choose.

---

## Summary — must confirm with Nikhil before go-live

| # | Item | Current default |
|---|---|---|
| 1 | Minimum timeline (6 vs 8–10 wks); far-future sites | 8 wks min to completion; far-future OK |
| 2 | One fail or two fails → decline | One clear fail declines |
| 3 | 500 sq ft commercial minimum | Decline under ~500 |
| 5 | Adjoining-area list + grey localities | List in prompt; grey → Ask |
| 6 | "Clearly below" budget line | Under ₹3 lakh (internal only) |
| 8 | Can we say "free consultation"? | Not said |
| 9 | Price quoting cut | Cut — explain why |
| 12 | Complaint callback SLA + senior backup | 15 min by day, 10 am next day at night |
| 13 | Consultation slots / calendar | Configured list, designer confirms |
| 15 | Up-front AI + recording disclosure | Yes, in greeting |
