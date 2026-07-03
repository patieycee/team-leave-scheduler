"""
Business rule implementation for the Team Leave Scheduler.

The rules, and the specific interpretation chosen for each ambiguity, are
documented in DECISIONS.md at the repo root. Summary of the decisions
encoded here:

1. 30% team cap: max_allowed = floor(team_size * 0.30). Floor is used
   because it is the only rounding mode that can never permit MORE than
   30% of a team to be on leave simultaneously (ceiling/round can, for
   small teams).
2. The 30% cap is evaluated PER WORKING DAY, not once for the whole
   request range, and only against APPROVED leave (a request only
   "removes" a person from the team once it is actually approved).
3. Weekends are never working days: they do not count toward the leave
   balance and are excluded from the 30% capacity check.
4. A public holiday inside a leave range is excluded from the leave
   balance and from the 30% capacity check (nobody is "at work" that
   day, so nobody can be "on leave" relative to it).
5. "Overlap" is checked against a single employee's own PENDING and
   APPROVED requests (not REJECTED ones) using a plain date-range
   intersection test, at submission time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import floor

from sqlalchemy.orm import Session

from . import models


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5 = Saturday, 6 = Sunday


def get_holiday_set(db: Session) -> set[date]:
    return {h.date for h in db.query(models.PublicHoliday).all()}


def working_days_in_range(start: date, end: date, holidays: set[date]) -> list[date]:
    """All dates in [start, end] that are neither a weekend nor a public holiday."""
    days = []
    current = start
    while current <= end:
        if not is_weekend(current) and current not in holidays:
            days.append(current)
        current += timedelta(days=1)
    return days


def max_allowed_on_leave(team_size: int) -> int:
    """No more than 30% of a team may be on leave on the same working day.

    floor() is used deliberately -- see module docstring / DECISIONS.md.
    """
    return floor(team_size * 0.30)


@dataclass
class OverlapResult:
    overlaps: bool
    conflicting_request_id: int | None = None


def find_overlap(
    db: Session, employee_id: int, start: date, end: date, exclude_request_id: int | None = None
) -> OverlapResult:
    """Check whether [start, end] overlaps an existing PENDING or APPROVED
    request for the same employee. REJECTED requests never block."""
    query = (
        db.query(models.LeaveRequest)
        .filter(models.LeaveRequest.employee_id == employee_id)
        .filter(models.LeaveRequest.status.in_([models.LeaveStatus.PENDING, models.LeaveStatus.APPROVED]))
        .filter(models.LeaveRequest.start_date <= end)
        .filter(models.LeaveRequest.end_date >= start)
    )
    if exclude_request_id is not None:
        query = query.filter(models.LeaveRequest.id != exclude_request_id)

    existing = query.first()
    if existing:
        return OverlapResult(overlaps=True, conflicting_request_id=existing.id)
    return OverlapResult(overlaps=False)


@dataclass
class CapacityResult:
    ok: bool
    violating_dates: list[date]
    max_allowed: int
    team_size: int


def check_team_capacity(
    db: Session, employee: models.Employee, start: date, end: date, exclude_request_id: int | None = None
) -> CapacityResult:
    """Check whether approving a request for `employee` covering
    [start, end] would push any single working day over the team's 30% cap.

    Only currently APPROVED leave for teammates counts toward the cap
    (see decision #2 above).
    """
    holidays = get_holiday_set(db)
    working_days = working_days_in_range(start, end, holidays)

    team_size = db.query(models.Employee).filter(models.Employee.team == employee.team).count()
    cap = max_allowed_on_leave(team_size)

    if not working_days:
        return CapacityResult(ok=True, violating_dates=[], max_allowed=cap, team_size=team_size)

    # Pull all approved requests for this team once, then check in-memory
    # (cheaper than one query per day for a 30-day window).
    approved = (
        db.query(models.LeaveRequest)
        .join(models.Employee)
        .filter(models.Employee.team == employee.team)
        .filter(models.LeaveRequest.status == models.LeaveStatus.APPROVED)
    )
    if exclude_request_id is not None:
        approved = approved.filter(models.LeaveRequest.id != exclude_request_id)
    approved = approved.all()

    violating = []
    for day in working_days:
        count_on_leave = sum(
            1
            for r in approved
            if r.employee_id != employee.id and r.start_date <= day <= r.end_date
        )
        # +1 for the employee whose request we're evaluating
        if count_on_leave + 1 > cap:
            violating.append(day)

    return CapacityResult(ok=len(violating) == 0, violating_dates=violating, max_allowed=cap, team_size=team_size)
