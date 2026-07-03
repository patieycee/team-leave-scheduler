import enum
from sqlalchemy import Column, Integer, String, Date, Enum, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship

from .database import Base


class LeaveStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    team = Column(String, nullable=False, index=True)

    leave_requests = relationship("LeaveRequest", back_populates="employee")


class PublicHoliday(Base):
    __tablename__ = "public_holidays"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(Enum(LeaveStatus), nullable=False, default=LeaveStatus.PENDING, index=True)
    created_at = Column(DateTime, server_default=func.now())
    decided_at = Column(DateTime, nullable=True)

    employee = relationship("Employee", back_populates="leave_requests")
