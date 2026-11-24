import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app import processing
from app.db import get_db
from app.main import app
from app.models import (
    DailyMetrics,
    DailyProcessingRun,
    EventType,
    Restaurant,
    RestaurantTable,
    Review,
    RunStatus,
    ServiceEvent,
    Source,
    Visit,
    Zone,
)

FRIDAY = date(2026, 1, 9)
SATURDAY = date(2026, 1, 10)
SUNDAY = date(2026, 1, 11)
MONDAY = date(2026, 1, 12)
NOW = datetime(2026, 1, 12, 7, tzinfo=UTC)
NIGHT = {"mode": "intervals", "intervals": [{"opens": "12:00", "closes": "02:00"}]}
CLOSED = {"mode": "closed"}


@pytest.fixture
def database(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Для интеграционных тестов укажите TEST_DATABASE_URL")
    schema = "restometra_test_" + uuid4().hex
    control = create_engine(url)
    engine = create_engine(
        url, connect_args={"options": f"-c search_path={schema} -c timezone=UTC"}
    )
    with control.begin() as conn:
        conn.execute(CreateSchema(schema))
    try:
        with engine.begin() as conn:
            config = Config(Path(__file__).resolve().parents[1] / "alembic.ini")
            config.attributes["connection"] = conn
            command.upgrade(config, "head")
            command.check(config)

        sessions = sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(processing, "engine", engine)
        monkeypatch.setattr(processing, "SessionFactory", sessions)

        def test_db():
            with sessions() as db:
                yield db

        monkeypatch.setitem(app.dependency_overrides, get_db, test_db)
        yield sessions
    finally:
        engine.dispose()
        with control.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        control.dispose()


@pytest.fixture
def dataset(database):
    with database.begin() as db:
        restaurant = Restaurant(
            name="Север",
            timezone="Asia/Krasnoyarsk",
            weekly_hours=[CLOSED, CLOSED, CLOSED, CLOSED, NIGHT, NIGHT, NIGHT],
            observation_minutes=30,
            processing_delay_minutes=60,
            tracking_since=FRIDAY,
            is_demo=True,
        )
        db.add(restaurant)
        db.flush()
        zone = Zone(restaurant_id=restaurant.id, name="Зал")
        db.add(zone)
        db.flush()
        first = RestaurantTable(zone_id=zone.id, name="Столик 1")
        second = RestaurantTable(zone_id=zone.id, name="Столик 2")
        db.add_all([first, second])
        db.flush()
        db.add_all(
            DailyProcessingRun(
                restaurant_id=restaurant.id,
                day=day,
                input_complete=True,
                status=status,
                updated_at=NOW,
            )
            for day, status in [(FRIDAY, RunStatus.PENDING), (SATURDAY, RunStatus.RUNNING)]
        )
        # Friday's first visit starts after local midnight and lasts until after closing.
        starts = [datetime(2026, 1, 9, 18, tzinfo=UTC)] + [
            datetime(2026, 1, 10, 9, minute, tzinfo=UTC) for minute in (0, 30, 50)
        ]
        for i, start in enumerate(starts):
            visit = Visit(
                table_id=first.id if i < 2 else second.id,
                started_at=start,
                ended_at=start + timedelta(minutes=[180, 40, 40, 100][i]),
            )
            db.add(visit)
            db.flush()
            for kind, offset, review in (
                [
                    (EventType.VISIT_STARTED, 0, Review.CONFIRMED),
                    (EventType.WAITER_CONTACT, 1, Review.REJECTED),
                    (EventType.WAITER_CONTACT, 6, Review.CONFIRMED),
                    (EventType.WAITER_CONTACT, 11, Review.CONFIRMED),
                    (EventType.FOOD_SERVED, 16, Review.PENDING),
                    (EventType.FOOD_SERVED, 20, Review.CONFIRMED),
                    (EventType.BILL_PRESENTED, 170, Review.CONFIRMED),
                ]
                if i == 0
                else [(EventType.VISIT_STARTED, 0, Review.CONFIRMED)]
            ):
                db.add(
                    ServiceEvent(
                        visit_id=visit.id,
                        event_type=kind,
                        source=Source.DEMO,
                        review_status=review,
                        occurred_at=start + timedelta(minutes=offset),
                    )
                )
        return restaurant.id, first.id


def test_start_time_recovery_and_idempotence(database, dataset):
    restaurant, first = dataset
    assert processing.process_day(restaurant, FRIDAY, datetime(2026, 1, 9, 20, tzinfo=UTC)) is None
    assert (
        processing.process_day(restaurant, FRIDAY, datetime(2026, 1, 9, 20, 30, tzinfo=UTC))
        == RunStatus.COMPLETED
    )
    processing.scan(NOW)
    with database() as db:
        assert db.get(DailyProcessingRun, (restaurant, SATURDAY)).status == RunStatus.COMPLETED
        assert (
            db.get(DailyProcessingRun, (restaurant, SUNDAY)).status == RunStatus.WAITING_FOR_INPUT
        )
        assert db.get(DailyProcessingRun, (restaurant, MONDAY)) is None

    with TestClient(app) as client:
        path = f"/api/v1/restaurants/{restaurant}"
        assert client.get("/api/v1/health").json() == {"status": "ok"}
        assert client.get(path + "/tables").json()[0]["id"] == first
        query = {"start": "2026-01-01", "end": "2026-01-31"}
        report = client.get(path + "/reports", params=query).json()
        data = report["metrics"]
        assert data["completed_visits"] == 4
        assert data["average_duration_seconds"] == 90 * 60
        assert data["median_duration_seconds"] == 70 * 60
        assert data["duration_samples"] == 4
        assert data["average_first_contact_seconds"] == 6 * 60
        assert data["contact_samples"] == 1
        assert data["counts"] == {
            "WAITER_CONTACT": 2,
            "FOOD_SERVED": 2,
            "DRINK_SERVED": 0,
            "BILL_PRESENTED": 1,
        }
        assert {"day": SUNDAY.isoformat(), "status": "INCOMPLETE"} in report["missing_days"]
        assert not any(item["day"] == MONDAY.isoformat() for item in report["missing_days"])
        assert sum(table["metrics"]["completed_visits"] for table in report["tables"]) == 4
        table = client.get(path + "/reports", params={**query, "table_id": first}).json()
        assert table["metrics"]["completed_visits"] == 2
        assert len(table["visits"]) == 2
        assert table["visits"][0]["operating_date"] == FRIDAY.isoformat()
        assert len(table["visits"][0]["events"]) == 7
        assert table["visits"][1]["first_contact_seconds"] is None
        export = client.get(path + "/reports.csv", params=query)
        assert export.status_code == 200 and "Неполные данные" in export.text
        assert client.post(path + f"/processing/{FRIDAY}").status_code == 202
        assert client.get(path + "/reports", params=query).json()["metrics"] == data
    processing.scan(NOW)
    assert processing.process_day(restaurant, FRIDAY, NOW, force=True) == RunStatus.COMPLETED
    with database() as db:
        assert db.scalar(select(func.count()).select_from(DailyMetrics)) == 2
        assert db.scalar(select(func.count()).select_from(ServiceEvent)) == 10


def test_edit_schedule_preserves_history_until_explicit_reprocessing(database, dataset):
    restaurant, _ = dataset
    processing.scan(NOW)
    with TestClient(app) as client:
        base = f"/api/v1/restaurants/{restaurant}"
        query = {"start": FRIDAY.isoformat(), "end": FRIDAY.isoformat()}
        before = client.get(base + "/reports", params=query).json()["days"][0]
        settings = client.get(base + "/settings").json()
        invalid = dict(
            settings, overrides=[{"day": SATURDAY.isoformat(), "hours": {"mode": "all_day"}}]
        )
        assert client.put(base + "/settings", json=invalid).status_code == 422
        settings["weekly_hours"][4] = CLOSED
        assert client.put(base + "/settings", json=settings).status_code == 200
        processing.scan(NOW)
        assert client.get(base + "/reports", params=query).json()["days"][0] == before
        assert client.post(base + f"/processing/{FRIDAY}").status_code == 202
        processing.scan(NOW)
        after = client.get(base + "/reports", params=query).json()["days"][0]
        assert after["status"] == "CLOSED"
        assert after["metrics"] is None
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ServiceEvent)) == 10


def test_db_excludes_competing_worker(database, dataset):
    restaurant, _ = dataset
    with processing.engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:restaurant, :day)"),
            {"restaurant": restaurant, "day": FRIDAY.toordinal()},
        )
        assert processing.process_day(restaurant, FRIDAY, NOW) is None
        with TestClient(app) as client:
            assert (
                client.post(f"/api/v1/restaurants/{restaurant}/processing/{FRIDAY}").status_code
                == 409
            )
    assert processing.process_day(restaurant, FRIDAY, NOW) == RunStatus.COMPLETED
