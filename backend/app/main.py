from datetime import date, datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models, schemas, business_rules
from .database import get_db
from .seed import seed

app = FastAPI(title="Team Leave Scheduler API")

# Wide open CORS: this is a local demo app with no auth (explicitly out of
# scope per the brief), so there is no sensitive session to protect.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    seed()


def _to_leave_request_out(r: models.LeaveRequest) -> schemas.LeaveRequestOut:
    return schemas.LeaveRequestOut(
        id=r.id,
        employee_id=r.employee_id,
        employee_name=r.employee.name,
        team=r.employee.team,
        start_date=r.start_date,
        end_date=r.end_date,
        status=r.status,
        created_at=r.created_at,
        decided_at=r.decided_at,
    )


@app.get("/employees", response_model=list[schemas.EmployeeOut])
def list_employees(db: Session = Depends(get_db)):
    return db.query(models.Employee).order_by(models.Employee.team, models.Employee.name).all()


@app.get("/leave-requests", response_model=list[schemas.LeaveRequestOut])
def list_leave_requests(
    days: int = 30,
    status: models.LeaveStatus | None = None,
    db: Session = Depends(get_db),
):
    """List leave requests overlapping the next `days` days (default 30).
    Optionally filter by status. Defaults to showing everything so the
    manager can see pending requests alongside approved leave.
    """
    today = date.today()
    window_end = today + timedelta(days=days)

    query = (
        db.query(models.LeaveRequest)
        .filter(models.LeaveRequest.start_date <= window_end)
        .filter(models.LeaveRequest.end_date >= today)
    )
    if status is not None:
        query = query.filter(models.LeaveRequest.status == status)

    results = query.order_by(models.LeaveRequest.start_date).all()
    return [_to_leave_request_out(r) for r in results]


@app.post("/leave-requests", response_model=schemas.LeaveRequestOut, status_code=201)
def submit_leave_request(payload: schemas.LeaveRequestCreate, db: Session = Depends(get_db)):
    employee = db.query(models.Employee).get(payload.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    overlap = business_rules.find_overlap(db, employee.id, payload.start_date, payload.end_date)
    if overlap.overlaps:
        raise HTTPException(
            status_code=409,
            detail=f"This request overlaps existing request #{overlap.conflicting_request_id} for this employee.",
        )

    leave_request = models.LeaveRequest(
        employee_id=employee.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=models.LeaveStatus.PENDING,
    )
    db.add(leave_request)
    db.commit()
    db.refresh(leave_request)
    return _to_leave_request_out(leave_request)


@app.post("/leave-requests/{request_id}/approve", response_model=schemas.LeaveRequestOut)
def approve_leave_request(request_id: int, db: Session = Depends(get_db)):
    leave_request = db.query(models.LeaveRequest).get(request_id)
    if leave_request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if leave_request.status != models.LeaveStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Request is already {leave_request.status.value}, not pending.")

    capacity = business_rules.check_team_capacity(
        db, leave_request.employee, leave_request.start_date, leave_request.end_date,
        exclude_request_id=leave_request.id,
    )
    if not capacity.ok:
        dates_str = ", ".join(d.isoformat() for d in capacity.violating_dates)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Approving this request would exceed the 30% team cap "
                f"({capacity.max_allowed} of {capacity.team_size} for team '{leave_request.employee.team}') "
                f"on: {dates_str}"
            ),
        )

    leave_request.status = models.LeaveStatus.APPROVED
    leave_request.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(leave_request)
    return _to_leave_request_out(leave_request)


@app.post("/leave-requests/{request_id}/reject", response_model=schemas.LeaveRequestOut)
def reject_leave_request(request_id: int, db: Session = Depends(get_db)):
    leave_request = db.query(models.LeaveRequest).get(request_id)
    if leave_request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if leave_request.status != models.LeaveStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Request is already {leave_request.status.value}, not pending.")

    leave_request.status = models.LeaveStatus.REJECTED
    leave_request.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(leave_request)
    return _to_leave_request_out(leave_request)
