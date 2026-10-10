"""
Replays T01–T20 (from the September enquiries file) through the real webhook and
prints what the backend decided against what qualified.md says it should decide.

    .venv/bin/python -m tests.replay                         # in-process, throwaway database
    .venv/bin/python -m tests.replay --live https://YOUR-HOST  # against a running server

Exit code 1 if any decision or criterion differs from the expected one.
"""
import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore", message=".*httpx.*")   # harmless test-client notice

LIVE = sys.argv[sys.argv.index("--live") + 1] if "--live" in sys.argv else None
if not LIVE:   # must be set before the app is imported
    os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "replay.db")
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["TELEGRAM_BOT_TOKEN"] = ""
    os.environ["DEMO_SEED"] = "false"

from app.demo import case_to_payload, load_cases  # noqa: E402

SYMBOL = {"pass": "✓", "fail": "✗", "unclear": "?", "not_assessed": "–", None: "·"}
KEYS = ("c1_real_project", "c2_service_area", "c3_timeline", "c4_budget", "c5_decision_maker")


def post_all(cases):
    if LIVE:
        import requests
        token = os.getenv("WEBHOOK_TOKEN", "")
        url = f"{LIVE.rstrip('/')}/webhooks/vaani" + (f"?token={token}" if token else "")
        return [requests.post(url, json=case_to_payload(c), timeout=20).json() for c in cases]
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        return [client.post("/webhooks/vaani", json=case_to_payload(c)).json() for c in cases]


def main() -> int:
    cases = load_cases()
    results = post_all(cases)
    rows = {}
    if not LIVE:
        from app import db
        rows = {r["external_id"]: r for r in db.list_enquiries(500)}

    header = f"{'ID':<5}| C1 C2 C3 C4 C5 | {'Decision':<9}| {'Expected':<9}| OK | Reason"
    print(header)
    print("-" * (len(header) + 40))
    failures = 0
    for case, res in zip(cases, results):
        out = case["agent_output"]
        crit = [out["criteria"][k]["result"] for k in KEYS]
        ok = res.get("decision") == case["expected"]["decision"] and crit == case["expected"]["criteria"]
        failures += not ok
        extras = []
        if res.get("needs_review"):
            extras.append("REVIEW: " + "; ".join(res["review_reasons"]))
        related = rows.get(f"demo-{case['id']}", {}).get("related_enquiry_id")
        if related:
            extras.append(f"linked to #{related}")
        reason = out["reason"] + (f"  [{' · '.join(extras)}]" if extras else "")
        print(f"{case['id']:<5}|  {'  '.join(SYMBOL[c] for c in crit)}  | {res.get('decision', 'ERROR'):<9}| "
              f"{case['expected']['decision']:<9}| {'✓ ' if ok else '✗ '} | {reason}")

    decisions = [r.get("decision") for r in results]
    print()
    print("Totals: " + ", ".join(f"{d} {decisions.count(d)}" for d in ("Book", "Ask", "Decline", "Escalate")))
    print("Key: ✓ pass  ✗ fail  ? unclear  – not assessed (complaint)")
    print(f"{len(cases) - failures}/{len(cases)} match qualified.md" + ("" if not failures else "  ← CHECK THE ✗ ROWS"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
