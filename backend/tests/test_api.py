"""
End-to-end API tests using FastAPI's TestClient. These exercise the full
request/response cycle (routing, validation, DB, business rules) rather
than calling business_rules.py functions directly.

Each test gets an isolated in-memory SQLite DB via dependency override,
so these do not touch the real leave_scheduler.db file.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app import models


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # keep the same in-memory DB across connections
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed two employees on the same small team directly (bypassing the
    # CSV-based seed() which targets the real DB).
    session = TestingSession()
    session.add_all([
        # Small team (size 3, cap = floor(0.9) = 0) -> used for the
        # over-capacity test.
        models.Employee(id=1, name="Alice", team="Engineering"),
        models.Employee(id=2, name="Bob", team="Engineering"),
        models.Employee(id=3, name="Carol", team="Engineering"),
        # Larger team (size 4, cap = floor(1.2) = 1) -> used for the
        # happy-path approve/reject tests.
        models.Employee(id=4, name="Dana", team="Operations"),
        models.Employee(id=5, name="Evan", team="Operations"),
        models.Employee(id=6, name="Faith", team="Operations"),
        models.Employee(id=7, name="Grace", team="Operations"),
    ])
    session.commit()
    session.close()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def next_monday() -> date:
    d = date.today() + timedelta(days=1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


def test_submit_and_approve_flow(client):
    monday = next_monday()
    resp = client.post("/leave-requests", json={
        "employee_id": 4, "start_date": monday.isoformat(), "end_date": monday.isoformat(),
    })
    assert resp.status_code == 201
    request_id = resp.json()["id"]
    assert resp.json()["status"] == "pending"

    approve_resp = client.post(f"/leave-requests/{request_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"


def test_submit_rejects_overlap(client):
    monday = next_monday()
    client.post("/leave-requests", json={
        "employee_id": 1, "start_date": monday.isoformat(), "end_date": monday.isoformat(),
    })
    resp = client.post("/leave-requests", json={
        "employee_id": 1, "start_date": monday.isoformat(), "end_date": monday.isoformat(),
    })
    assert resp.status_code == 409


def test_approve_rejects_when_over_capacity(client):
    # Team of 3 -> cap = floor(0.9) = 0. Any approval should be rejected.
    monday = next_monday()
    resp = client.post("/leave-requests", json={
        "employee_id": 1, "start_date": monday.isoformat(), "end_date": monday.isoformat(),
    })
    request_id = resp.json()["id"]

    approve_resp = client.post(f"/leave-requests/{request_id}/approve")
    assert approve_resp.status_code == 409
    assert "30%" in approve_resp.json()["detail"]


def test_reject_flow(client):
    monday = next_monday()
    resp = client.post("/leave-requests", json={
        "employee_id": 2, "start_date": monday.isoformat(), "end_date": monday.isoformat(),
    })
    request_id = resp.json()["id"]

    reject_resp = client.post(f"/leave-requests/{request_id}/reject")
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"


def test_cannot_decide_a_request_twice(client):
    monday = next_monday()
    resp = client.post("/leave-requests", json={
        "employee_id": 2, "start_date": monday.isoformat(), "end_date": monday.isoformat(),
    })
    request_id = resp.json()["id"]
    client.post(f"/leave-requests/{request_id}/reject")

    second = client.post(f"/leave-requests/{request_id}/approve")
    assert second.status_code == 409


def test_list_leave_requests_within_window(client):
    monday = next_monday()
    far_future = date.today() + timedelta(days=90)
    client.post("/leave-requests", json={
        "employee_id": 1, "start_date": monday.isoformat(), "end_date": monday.isoformat(),
    })
    client.post("/leave-requests", json={
        "employee_id": 2, "start_date": far_future.isoformat(), "end_date": far_future.isoformat(),
    })

    resp = client.get("/leave-requests?days=30")
    dates = [r["start_date"] for r in resp.json()]
    assert monday.isoformat() in dates
    assert far_future.isoformat() not in dates
