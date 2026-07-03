"""
Seeds the database from backend/data/employees.csv and
backend/data/public_holidays.json.

Public holiday dates are regenerated relative to "today" each time this
script runs (rather than using the static committed dates verbatim).
This is purely so that the demo / video walkthrough always has holidays
that fall within the next 60 days, regardless of when it is run or
reviewed. The committed public_holidays.json is still the source of
truth for holiday NAMES and offsets; only the dates are shifted forward.
"""
import csv
import json
from datetime import date, timedelta
from pathlib import Path

from .database import Base, engine, SessionLocal
from . import models

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(models.Employee).count() == 0:
            with open(DATA_DIR / "employees.csv", newline="") as f:
                for row in csv.DictReader(f):
                    db.add(models.Employee(id=int(row["id"]), name=row["name"], team=row["team"]))
            db.commit()
            print("Seeded employees.")
        else:
            print("Employees already seeded, skipping.")

        if db.query(models.PublicHoliday).count() == 0:
            with open(DATA_DIR / "public_holidays.json") as f:
                raw_holidays = json.load(f)

            today = date.today()
            # Shift committed sample holidays to sensible near-future offsets
            # (10, 25, 45 days out) so they always land inside the 60-day window.
            offsets = [10, 25, 45]
            for holiday, offset in zip(raw_holidays, offsets):
                h_date = today + timedelta(days=offset)
                db.add(models.PublicHoliday(date=h_date, name=holiday["name"]))
            db.commit()
            print("Seeded public holidays.")
        else:
            print("Public holidays already seeded, skipping.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
