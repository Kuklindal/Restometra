import argparse
import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from .db import SessionFactory
from .models import (
    DailyProcessingRun,
    EventType,
    Order,
    Restaurant,
    RestaurantScheduleOverride,
    RestaurantTable,
    Review,
    RunStatus,
    ServiceEvent,
    Source,
    Visit,
    Zone,
)
from .processing import scan
from .schedule import DAY, Calendar, dates, validate_schedule
from .schemas import DayHours, Interval, RestaurantSettings, ScheduleOverride

DEMO_ZONE = "Asia/Krasnoyarsk"


def make_settings(start: date):
    afternoon = DayHours(mode="intervals", intervals=[Interval(opens="12:00", closes="23:00")])
    night = DayHours(mode="intervals", intervals=[Interval(opens="12:00", closes="02:00")])
    split = DayHours(
        mode="intervals",
        intervals=[
            Interval(opens="11:00", closes="15:00"),
            Interval(opens="17:00", closes="22:30"),
        ],
    )
    settings = RestaurantSettings(
        name="Ресторан «Север»",
        timezone=DEMO_ZONE,
        observation_minutes=30,
        processing_delay_minutes=60,
        weekly_hours=[
            DayHours(mode="closed"),
            afternoon,
            split,
            afternoon,
            night,
            night,
            afternoon,
        ],
        overrides=[
            ScheduleOverride(
                day=start + 13 * DAY,
                hours=DayHours(
                    mode="intervals", intervals=[Interval(opens="13:00", closes="19:00")]
                ),
            )
        ],
    )
    validate_schedule(settings)
    return settings


def add_visit(db, rng, table, start, number, late=False):
    duration = rng.randint(33, 143)
    end = start + timedelta(minutes=duration)
    visit = Visit(table_id=table.id, started_at=start, ended_at=end if number % 19 else None)
    db.add(visit)
    db.flush()
    order = Order(visit_id=visit.id, reference=f"DEMO-{visit.id}")
    db.add(order)
    db.flush()

    def event(kind, minute, *, with_order=False, pending=False):
        db.add(
            ServiceEvent(
                visit_id=visit.id,
                order_id=order.id if with_order else None,
                event_type=kind,
                occurred_at=start + timedelta(minutes=minute),
                source=Source.DEMO,
                confidence=0.86 if pending else 0.99,
                review_status=Review.PENDING if pending else Review.CONFIRMED,
            )
        )

    event(EventType.VISIT_STARTED, 0)
    if number % 11:
        event(
            EventType.WAITER_CONTACT,
            rng.randint(7, 12) if late or number % 6 == 0 else rng.uniform(0.8, 4.5),
            pending=number % 10 == 0,
        )
        if number % 3:
            event(EventType.WAITER_CONTACT, 21)
    event(EventType.ORDER_CREATED, 12, with_order=True)
    if number % 4 == 0:
        event(EventType.ORDER_UPDATED, 15, with_order=True)
    event(EventType.DRINK_SERVED, 16, with_order=True)
    event(EventType.FOOD_SERVED, 25, with_order=True)
    if number % 3 == 0:
        event(EventType.FOOD_SERVED, 30, with_order=True)
    if number % 7:
        event(EventType.BILL_PRESENTED, duration - 3, with_order=True)
        event(EventType.ORDER_CLOSED, duration - 1, with_order=True)
    if visit.ended_at:
        event(EventType.VISIT_ENDED, duration)


def seed(end: date):
    start = end - 35 * DAY
    rng = random.Random(415)
    with SessionFactory.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(415, 0)"))
        if db.scalar(select(Restaurant.id).where(Restaurant.is_demo).limit(1)):
            return False
        settings = make_settings(start)
        restaurant = Restaurant(
            **settings.model_dump(mode="json", exclude={"overrides"}),
            tracking_since=start,
            is_demo=True,
        )
        db.add(restaurant)
        db.flush()
        db.add_all(
            RestaurantScheduleOverride(
                restaurant_id=restaurant.id, day=item.day, hours=item.hours.model_dump(mode="json")
            )
            for item in settings.overrides
        )
        zone = Zone(restaurant_id=restaurant.id, name="Основной зал")
        db.add(zone)
        db.flush()
        tables = [
            RestaurantTable(zone_id=zone.id, name=f"Столик {index:02d}") for index in range(1, 9)
        ]
        db.add_all(tables)
        db.flush()
        calendar = Calendar(settings)
        working_days = [day for day in dates(start, end) if calendar.day(day).windows]
        for index, day in enumerate(working_days):
            plan = calendar.day(day)
            complete = index not in (8, len(working_days) - 3)
            db.add(
                DailyProcessingRun(
                    restaurant_id=restaurant.id,
                    day=day,
                    input_complete=complete,
                    status=RunStatus.PENDING,
                )
            )
            weekend = day.weekday() in (4, 5)
            count = rng.randint(22, 42) if weekend else rng.randint(12, 27)
            if not complete:
                count = 4
            for number in range(count):
                span = plan.windows[number % len(plan.windows)]
                span_minutes = int((span.closes_at - span.opens_at).total_seconds() / 60)
                offset = int(rng.betavariate(2.5, 1.8) * (span_minutes - 40))
                if weekend and number == 1:
                    offset = span_minutes - 20
                add_visit(
                    db,
                    rng,
                    rng.choice(tables),
                    span.opens_at + timedelta(minutes=offset),
                    number,
                    late=weekend and number == 1,
                )
    return True


def main():
    parser = argparse.ArgumentParser(description="Создать демонстрационные данные Restometra")
    default_end = datetime.now(ZoneInfo(DEMO_ZONE)).date() - 2 * DAY
    parser.add_argument("--end-date", type=date.fromisoformat, default=default_end)
    parser.add_argument("--no-process", action="store_true")
    args = parser.parse_args()
    if not date(2000, 2, 6) <= args.end_date <= default_end:
        parser.error("Дата должна быть не раньше 2000-02-06 и не позднее позавчера.")
    created = seed(args.end_date)
    print(
        "Демонстрационные данные загружены."
        if created
        else "Демонстрационные данные уже существуют."
    )
    if not args.no_process:
        scan(datetime.now(UTC))


if __name__ == "__main__":
    main()
