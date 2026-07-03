from datetime import date, datetime
from pydantic import BaseModel, field_validator

from .models import LeaveStatus


class EmployeeOut(BaseModel):
    id: int
    name: str
    team: str

    class Config:
        from_attributes = True


class LeaveRequestCreate(BaseModel):
    employee_id: int
    start_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def end_not_before_start(cls, v, info):
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date cannot be before start_date")
        return v


class LeaveRequestOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    team: str
    start_date: date
    end_date: date
    status: LeaveStatus
    created_at: datetime | None = None
    decided_at: datetime | None = None

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    detail: str
