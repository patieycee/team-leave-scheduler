# Design Decisions

The task brief is deliberately ambiguous in several places. Below are the
interpretations I chose, the alternatives I considered, and why.

## 1. The 30% rule — how it rounds, and for whom it counts

**Decision:** `max_allowed_on_leave = floor(team_size * 0.30)`, and it is
evaluated **per working day**, against **currently APPROVED** leave only
(not pending).

**Alternatives considered:**
- *Round to nearest whole person* (e.g. team of 4 → round(1.2) → 1; team
  of 5 → round(1.5) → 2). Rejected: for some team sizes this rounds
  *up*, which means more than 30% of the team could legally be on leave
  at once — that directly contradicts the rule as stated ("no more
  than 30%").
- *Ceiling*. Rejected for the same reason, more aggressively — a team of
  4 would allow 2 people off (50%).
- *Apply the cap once for the whole request range* rather than per day.
  Rejected: a 5-day request could start when the team is under-booked
  and end when it's fully booked (or vice versa); checking only the
  start date (or only the whole range as one unit) can silently let an
  invalid day slip through, or block a request that's actually fine.
- *Count PENDING requests toward the cap, not just APPROVED.* Rejected:
  a pending request hasn't actually removed anyone from the roster yet.
  Counting it would mean two people requesting the same day could
  block each other from ever being approved, even if the manager would
  have been happy to approve either one. The cap should reflect who is
  *actually* going to be absent, which is only decided at approval
  time. (Note: this does mean a manager could approve two pending
  requests that individually looked fine but jointly exceed the cap if
  approved in the wrong order — the second approval attempt will
  correctly fail at that point, since the check re-runs on every
  approval.)

**Why floor, specifically:** "no more than 30%" is a ceiling on
permitted absence, not a target. Floor is the only rounding strategy
that can never exceed the literal 30% for any team size, which makes it
the conservative, defensible reading of a compliance-flavoured rule.

## 2. Weekends and public holidays inside a leave range

**Decision:** Weekend days and public-holiday dates are simply excluded
from the "working days" set. A request is allowed to span a weekend or
a holiday (e.g. Fri–Mon) — the system does not reject it — but those
non-working days are skipped when (a) counting leave taken and (b)
checking the 30% cap.

**Alternatives considered:**
- *Reject any request that touches a Saturday, Sunday, or holiday.*
  Rejected: this would make a perfectly normal "long weekend" request
  (Fri–Mon) impossible to submit as a single request, forcing the
  employee to split it into two, which is worse UX for no rule-safety
  benefit — the business rule already says weekends aren't working
  days, i.e. they're implicitly excluded, not forbidden.
- *Count holidays against the leave balance if they fall inside a
  range.* Rejected: this directly contradicts the explicit rule
  "Public holidays do not count against the employee's leave balance."
- *Still count a holiday as "at capacity" for the 30% rule* (i.e. treat
  it as a working day for capacity purposes, just not for balance).
  Rejected: if it's a holiday, *nobody* is expected to be at work that
  day, so nobody can meaningfully be described as unusually "on leave"
  relative to the team's availability. Excluding it from both checks
  keeps the two rules consistent with each other.

## 3. What "overlapping" means, and when it's checked

**Decision:** A new request is rejected at **submission time** if its
date range intersects any existing request for the *same employee* that
is currently **PENDING or APPROVED**. Rejected requests never block a
new submission. The check is a plain date-range intersection
(`new.start <= existing.end AND new.end >= existing.start`), not
restricted to working days.

**Alternatives considered:**
- *Only block against APPROVED requests*, allow overlapping PENDING
  ones. Rejected: this creates an obvious race condition — two
  overlapping pending requests for the same employee could both later
  be approved (nothing was checked at approval time to catch this),
  since the approval-time capacity check only looks at *other* team
  members, not the same employee's own other requests. Blocking at
  submission time on PENDING+APPROVED closes that gap cleanly and
  matches the plain-English meaning of "an employee can't have two
  leave requests for the same days in flight at once."
- *Only compare working days*, ignoring weekends inside the range for
  the overlap check specifically. Rejected: this adds complexity for
  no real benefit — the concern behind the overlap rule is "does the
  employee have two conflicting claims to the same calendar dates,"
  which is a simpler, calendar-level question than the capacity rule.

## Other choices worth noting (not asked for, but relevant)

- **Frontend:** plain HTML/JS instead of a framework, given the time
  budget and the brief's explicit note that visual design isn't scored.
  All validation logic lives in the backend service layer regardless of
  which frontend calls it.
- **Database:** SQLite, for zero-setup local running and because the
  brief explicitly allows it.
