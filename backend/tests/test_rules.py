"""
Tests for the two rules the brief explicitly requires coverage for:
  1. The 30% team leave cap.
  2. The overlapping-request rule.

Plus a couple of supporting tests for weekend/holiday handling, since
those directly feed into both rules above.

Uses a fresh in-memory SQLite DB per test (via the `db` fixture) so tests
never depend on each other or on the seeded demo data.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models, business_rules


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def make_team(db, team_name: str, size: int) -> list[models.Employee]:
    employees = [models.Employee(name=f"{team_name} Person {i}", team=team_name) for i in range(size)]
    db.add_all(employees)
    db.commit()
    for e in employees:
        db.refresh(e)
    return employees


def approve(db, employee: models.Employee, start: date, end: date) -> models.LeaveRequest:
    r = models.LeaveRequest(
        employee_id=employee.id, start_date=start, end_date=end, status=models.LeaveStatus.APPROVED
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ---------------------------------------------------------------------------
# Rule 1: 30% team cap
# ---------------------------------------------------------------------------

def test_max_allowed_on_leave_uses_floor():
    # Team of 5 -> 30% = 1.5 -> floor -> 1
    assert business_rules.max_allowed_on_leave(5) == 1
    # Team of 10 -> 30% = 3.0 -> floor -> 3
    assert business_rules.max_allowed_on_leave(10) == 3
    # Team of 4 -> 30% = 1.2 -> floor -> 1 (never allowed to round up to 2)
    assert business_rules.max_allowed_on_leave(4) == 1


def test_capacity_rejects_when_cap_already_reached(db):
    # Team of 5 -> cap is 1. One person already approved for a Monday.
    team = make_team(db, "Engineering", 5)
    monday = date(2026, 7, 6)  # a Monday, not a seeded holiday
    approve(db, team[0], monday, monday)

    # A second person on the same team requesting the same day should
    # violate the cap (would be 2 people on leave, cap is 1).
    result = business_rules.check_team_capacity(db, team[1], monday, monday)
    assert result.ok is False
    assert monday in result.violating_dates
    assert result.max_allowed == 1


def test_capacity_allows_when_under_cap(db):
    team = make_team(db, "Operations", 10)  # cap = 3
    monday = date(2026, 7, 6)
    approve(db, team[0], monday, monday)
    approve(db, team[1], monday, monday)

    # A third person requesting the same day is still within the cap of 3.
    result = business_rules.check_team_capacity(db, team[2], monday, monday)
    assert result.ok is True
    assert result.violating_dates == []


def test_capacity_checked_per_working_day_across_a_range(db):
    # Team of 5 -> cap 1. One approved leave covers Mon-Tue.
    team = make_team(db, "Finance", 5)
    monday = date(2026, 7, 6)
    tuesday = date(2026, 7, 7)
    wednesday = date(2026, 7, 8)
    approve(db, team[0], monday, tuesday)

    # A request for Tue-Wed overlaps the cap on Tuesday only.
    result = business_rules.check_team_capacity(db, team[1], tuesday, wednesday)
    assert result.ok is False
    assert result.violating_dates == [tuesday]


# ---------------------------------------------------------------------------
# Rule 2: overlapping requests
# ---------------------------------------------------------------------------

def test_overlap_detected_against_approved_request(db):
    team = make_team(db, "Engineering", 5)
    employee = team[0]
    approve(db, employee, date(2026, 7, 6), date(2026, 7, 10))

    result = business_rules.find_overlap(db, employee.id, date(2026, 7, 8), date(2026, 7, 12))
    assert result.overlaps is True


def test_overlap_detected_against_pending_request(db):
    team = make_team(db, "Engineering", 5)
    employee = team[0]
    pending = models.LeaveRequest(
        employee_id=employee.id,
        start_date=date(2026, 7, 6),
        end_date=date(2026, 7, 10),
        status=models.LeaveStatus.PENDING,
    )
    db.add(pending)
    db.commit()

    result = business_rules.find_overlap(db, employee.id, date(2026, 7, 9), date(2026, 7, 9))
    assert result.overlaps is True


def test_no_overlap_for_adjacent_non_touching_ranges(db):
    team = make_team(db, "Engineering", 5)
    employee = team[0]
    approve(db, employee, date(2026, 7, 6), date(2026, 7, 10))

    # Starts the day after the existing request ends -> no overlap.
    result = business_rules.find_overlap(db, employee.id, date(2026, 7, 11), date(2026, 7, 15))
    assert result.overlaps is False


def test_rejected_request_does_not_block_new_request(db):
    team = make_team(db, "Engineering", 5)
    employee = team[0]
    rejected = models.LeaveRequest(
        employee_id=employee.id,
        start_date=date(2026, 7, 6),
        end_date=date(2026, 7, 10),
        status=models.LeaveStatus.REJECTED,
    )
    db.add(rejected)
    db.commit()

    result = business_rules.find_overlap(db, employee.id, date(2026, 7, 8), date(2026, 7, 8))
    assert result.overlaps is False


def test_overlap_does_not_block_a_different_employee(db):
    team = make_team(db, "Engineering", 5)
    approve(db, team[0], date(2026, 7, 6), date(2026, 7, 10))

    result = business_rules.find_overlap(db, team[1].id, date(2026, 7, 8), date(2026, 7, 8))
    assert result.overlaps is False


# ---------------------------------------------------------------------------
# Supporting rules: weekends and public holidays
# ---------------------------------------------------------------------------

def test_weekends_excluded_from_working_days():
    # 2026-07-04 is a Saturday, 2026-07-05 is a Sunday
    saturday = date(2026, 7, 4)
    sunday = date(2026, 7, 5)
    monday = date(2026, 7, 6)
    days = business_rules.working_days_in_range(saturday, monday, holidays=set())
    assert saturday not in days
    assert sunday not in days
    assert monday in days


def test_public_holiday_excluded_from_working_days():
    monday = date(2026, 7, 6)
    tuesday = date(2026, 7, 7)  # treated as a holiday in this test
    wednesday = date(2026, 7, 8)
    days = business_rules.working_days_in_range(monday, wednesday, holidays={tuesday})
    assert tuesday not in days
    assert monday in days and wednesday in days


def test_holiday_in_range_does_not_count_toward_capacity(db):
    # Team of 5 -> cap 1. Approved leave covers a holiday + a working day.
    team = make_team(db, "Engineering", 5)
    monday = date(2026, 7, 6)  # working day
    holiday = date(2026, 7, 7)  # will be registered as a public holiday
    db.add(models.PublicHoliday(date=holiday, name="Test Holiday"))
    db.commit()

    approve(db, team[0], monday, holiday)

    # A second person requesting only the holiday should NOT be blocked by
    # the cap, since the holiday isn't a working day for anyone.
    result = business_rules.check_team_capacity(db, team[1], holiday, holiday)
    assert result.ok is True
