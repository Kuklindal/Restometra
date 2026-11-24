import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text

from .analytics import collect, prepare_day
from .db import SessionFactory, engine
from .models import DailyMetrics, DailyProcessingRun, Restaurant, RunStatus
from .restaurants import get_settings
from .schedule import Calendar, dates

logger = logging.getLogger(__name__)
RETRY_DELAY = timedelta(minutes=5)


def _lock_params(restaurant_id: int, day: date):
    return {"restaurant": restaurant_id, "day": day.toordinal()}


def queue_run(db, restaurant_id: int, day: date):
    acquired = db.scalar(
        text("SELECT pg_try_advisory_xact_lock(:restaurant, :day)"),
        _lock_params(restaurant_id, day),
    )
    if not acquired:
        return False
    run = db.get(DailyProcessingRun, (restaurant_id, day))
    if run is None:
        run = DailyProcessingRun(restaurant_id=restaurant_id, day=day)
        db.add(run)
    run.status = RunStatus.PENDING
    run.updated_at = datetime.now(UTC)
    run.error = None
    db.commit()
    return True


def process_day(restaurant_id: int, day: date, now: datetime, *, force: bool = False):
    key = (restaurant_id, day)
    # Hold a session-level lock through both commits so RUNNING is visible and
    # another worker can reclaim a crashed run as soon as its connection closes.
    with engine.connect() as connection:
        params = _lock_params(restaurant_id, day)
        if not connection.scalar(text("SELECT pg_try_advisory_lock(:restaurant, :day)"), params):
            return None
        connection.commit()
        try:
            with SessionFactory(bind=connection) as db:
                return _process_locked(db, key, now, force)
        finally:
            connection.rollback()
            connection.execute(text("SELECT pg_advisory_unlock(:restaurant, :day)"), params)
            connection.commit()


def _process_locked(db, key, now, force):
    restaurant_id, day = key
    restaurant = db.get(Restaurant, restaurant_id, with_for_update={"read": True})
    if restaurant is None or day < restaurant.tracking_since:
        return None
    run = db.get(DailyProcessingRun, key)
    if run and not force:
        if run.status == RunStatus.COMPLETED:
            return run.status
        if run.status == RunStatus.WAITING_FOR_INPUT and not run.input_complete:
            return run.status
        if run.status == RunStatus.FAILED and run.updated_at and now - run.updated_at < RETRY_DELAY:
            return run.status

    plan = Calendar(get_settings(db, restaurant)).day(day)
    if not plan.windows and not (run and db.get(DailyMetrics, key)):
        return None
    if plan.ready_at and plan.ready_at > now:
        return None
    if run is None:
        run = DailyProcessingRun(restaurant_id=restaurant_id, day=day, input_complete=False)
        db.add(run)
    run.updated_at = now
    run.error = None
    if plan.windows and not run.input_complete:
        run.status = RunStatus.WAITING_FOR_INPUT
        db.commit()
        return run.status

    run.status = RunStatus.RUNNING
    db.commit()
    try:
        metrics = db.get(DailyMetrics, key)
        visits = prepare_day(db, restaurant_id, plan) if plan.windows else []
        if metrics is None:
            metrics = DailyMetrics(restaurant_id=restaurant_id, day=day)
            db.add(metrics)
        metrics.schedule = plan.snapshot()
        metrics.visits = visits
        by_table = defaultdict(list)
        for visit in metrics.visits:
            by_table[str(visit["table_id"])].append(visit)
        metrics.aggregates = {
            "all": collect(metrics.visits),
            "by_table": {table: collect(rows) for table, rows in by_table.items()},
        }
        run.status = RunStatus.COMPLETED
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Daily aggregation failed for restaurant %s on %s", restaurant_id, day)
        run = db.get(DailyProcessingRun, key)
        run.status = RunStatus.FAILED
        run.error = "Ошибка ежедневного расчёта."
        db.commit()
    return run.status


def scan(now: datetime | None = None):
    now = now or datetime.now(UTC)
    ready = []
    with SessionFactory() as db:
        for restaurant in db.scalars(select(Restaurant).order_by(Restaurant.id)):
            calendar = Calendar(get_settings(db, restaurant))
            runs = {
                run.day: run
                for run in db.scalars(
                    select(DailyProcessingRun).where(
                        DailyProcessingRun.restaurant_id == restaurant.id
                    )
                )
            }
            current_day = now.astimezone(calendar.zone).date()
            for day in dates(restaurant.tracking_since, current_day):
                run = runs.get(day)
                if run and (
                    run.status == RunStatus.COMPLETED
                    or (run.status == RunStatus.WAITING_FOR_INPUT and not run.input_complete)
                ):
                    continue
                plan = calendar.day(day)
                if (plan.ready_at and plan.ready_at <= now) or (run and not plan.windows):
                    ready.append((restaurant.id, day))
    for restaurant_id, day in ready:
        process_day(restaurant_id, day, now)
