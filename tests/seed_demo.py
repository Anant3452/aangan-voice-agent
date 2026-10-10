"""
Loads T01–T20 into your LOCAL database (data/aangan.db) as demo data.

    .venv/bin/python -m tests.seed_demo           # add the demo calls (safe to run twice)
    .venv/bin/python -m tests.seed_demo --reset   # remove all demo rows first

The seeding logic lives in app/demo.py (the Vercel deployment uses it too).
"""
import sys

from app import db, demo

if __name__ == "__main__":
    db.init_db()
    if "--reset" in sys.argv:
        print(f"Removed {demo.reset()} demo enquiries.")
    print(f"Added {demo.seed()} demo enquiries (T01–T20, Sep 2026). Open http://localhost:8000/dashboard")
