from collections import Counter
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select

from .models import EventType, RestaurantTable, Review, ServiceEvent, Visit
from .restaurants import tables_for

FIRST_CONTACT_LIMIT = 5 * 60
VISIT_LIMIT = 120 * 60
COUNTED_EVENTS = (
    EventType.WAITER_CONTACT,
    EventType.FOOD_SERVED,
    EventType.DRINK_SERVED,
    EventType.BILL_PRESENTED,
)


def prepare_day(db, restaurant_id, plan):
    in_windows = [
        and_(Visit.started_at >= span.opens_at, Visit.started_at < span.observed_until)
        for span in plan.windows
    ]
    visits = list(
        db.scalars(
            select(Visit)
            .where(
                Visit.table_id.in_(
                    tables_for(restaurant_id).with_only_columns(RestaurantTable.id).order_by(None)
                ),
                or_(
                    Visit.operating_date == plan.day,
                    and_(Visit.operating_date.is_(None), or_(*in_windows)),
                ),
            )
            .order_by(Visit.id)
            .with_for_update()
        )
    )
    events_by_visit = {visit.id: [] for visit in visits}
    if visits:
        events = db.scalars(
            select(ServiceEvent)
            .where(ServiceEvent.visit_id.in_(events_by_visit))
            .order_by(ServiceEvent.occurred_at, ServiceEvent.id)
        )
        for event in events:
            events_by_visit[event.visit_id].append(event)

    zone = ZoneInfo(plan.timezone)
    details = []
    for visit in visits:
        visit.operating_date = plan.day
        events = events_by_visit[visit.id]
        valid_events = [
            event
            for event in events
            if event.review_status != Review.REJECTED
            and event.occurred_at >= visit.started_at
            and (visit.ended_at is None or event.occurred_at <= visit.ended_at)
        ]
        counts = Counter(event.event_type for event in valid_events)
        contact = next(
            (
                event.occurred_at
                for event in valid_events
                if event.event_type == EventType.WAITER_CONTACT
            ),
            None,
        )
        duration = (
            (visit.ended_at - visit.started_at).total_seconds()
            if visit.ended_at is not None and visit.ended_at >= visit.started_at
            else None
        )
        details.append(
            {
                "id": visit.id,
                "table_id": visit.table_id,
                "started_at": visit.started_at.isoformat(),
                "ended_at": visit.ended_at.isoformat() if visit.ended_at else None,
                "hour": visit.started_at.astimezone(zone).hour,
                "duration_seconds": duration,
                "first_contact_seconds": (contact - visit.started_at).total_seconds()
                if contact
                else None,
                "counts": {event_type: counts[event_type] for event_type in COUNTED_EVENTS},
                "events": [
                    {
                        "id": event.id,
                        "type": event.event_type,
                        "occurred_at": event.occurred_at.isoformat(),
                        "source": event.source,
                        "review_status": event.review_status,
                        "confidence": event.confidence,
                        "order_id": event.order_id,
                    }
                    for event in events
                ],
            }
        )
    details.sort(key=lambda row: (datetime.fromisoformat(row["started_at"]), row["id"]))
    return details


def collect(visits):
    durations = [v["duration_seconds"] for v in visits if v["duration_seconds"] is not None]
    contacts = [
        v["first_contact_seconds"] for v in visits if v["first_contact_seconds"] is not None
    ]
    hours = Counter(v["hour"] for v in visits)
    return {
        "started_visits": len(visits),
        "durations": durations,
        "contacts": contacts,
        "counts": {kind: sum(v["counts"][kind] for v in visits) for kind in COUNTED_EVENTS},
        "hours": [hours[hour] for hour in range(24)],
    }


def summarize(buckets):
    durations = [value for bucket in buckets for value in bucket["durations"]]
    contacts = [value for bucket in buckets for value in bucket["contacts"]]
    return {
        "started_visits": sum(bucket["started_visits"] for bucket in buckets),
        "completed_visits": len(durations),
        "duration_samples": len(durations),
        "average_duration_seconds": sum(durations) / len(durations) if durations else None,
        "median_duration_seconds": median(durations) if durations else None,
        "contact_samples": len(contacts),
        "average_first_contact_seconds": sum(contacts) / len(contacts) if contacts else None,
        "median_first_contact_seconds": median(contacts) if contacts else None,
        "late_first_contacts": sum(value > FIRST_CONTACT_LIMIT for value in contacts),
        "long_visits": sum(value > VISIT_LIMIT for value in durations),
        "counts": {
            kind: sum(bucket["counts"][kind] for bucket in buckets) for kind in COUNTED_EVENTS
        },
        "hours": [sum(bucket["hours"][hour] for bucket in buckets) for hour in range(24)],
    }
