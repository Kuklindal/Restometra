from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import defer

from .analytics import summarize
from .models import DailyMetrics, DailyProcessingRun, RunStatus
from .restaurants import get_settings, tables_for
from .schedule import Calendar, dates


def make_report(db, restaurant, start: date, end: date, table_id: int | None = None):
    def query(model):
        return select(model).where(
            model.restaurant_id == restaurant.id, model.day.between(start, end)
        )

    with_details = start == end or table_id is not None
    snapshots_query = query(DailyMetrics)
    if not with_details:
        snapshots_query = snapshots_query.options(defer(DailyMetrics.visits))
    snapshots = {row.day: row for row in db.scalars(snapshots_query)}
    runs = {row.day: row for row in db.scalars(query(DailyProcessingRun))}
    calendar = Calendar(get_settings(db, restaurant))
    table_map = {row.id: row.name for row in db.scalars(tables_for(restaurant.id))}
    days, detail, excluded = [], [], []
    selected_buckets = []
    by_table = defaultdict(list)
    processed_days = 0
    for day in dates(start, end):
        snapshot = snapshots.get(day)
        run = runs.get(day)
        schedule = snapshot.schedule if snapshot else calendar.day(day).snapshot()
        if not schedule["windows"]:
            status = "CLOSED"
        elif snapshot:
            status = "PROCESSED"
        elif run and run.status == RunStatus.WAITING_FOR_INPUT:
            status = "INCOMPLETE"
        else:
            status = "UNPROCESSED"
        if status in ("INCOMPLETE", "UNPROCESSED"):
            excluded.append({"day": day, "status": status})
        day_summary = None
        if status == "PROCESSED":
            processed_days += 1
            grouped = snapshot.aggregates["by_table"]
            if table_id is None:
                bucket = snapshot.aggregates["all"]
                for table, item in grouped.items():
                    by_table[int(table)].append(item)
            else:
                bucket = grouped.get(str(table_id))
            if bucket is not None:
                selected_buckets.append(bucket)
            day_summary = summarize([bucket] if bucket is not None else [])
            if with_details:
                detail.extend(
                    dict(
                        visit,
                        operating_date=day,
                        timezone=schedule["timezone"],
                        table_name=table_map.get(visit["table_id"]),
                    )
                    for visit in snapshot.visits
                    if table_id is None or visit["table_id"] == table_id
                )
        days.append(
            {
                "day": day,
                "status": status,
                "run_status": run.status if run else None,
                "error": run.error if run else None,
                "historical": snapshot is not None,
                "schedule": schedule,
                "metrics": day_summary,
            }
        )

    return {
        "start": start,
        "end": end,
        "table_id": table_id,
        "metrics": summarize(selected_buckets) if processed_days else None,
        "days": days,
        "missing_days": excluded,
        "visits": detail,
        "tables": [
            {"id": table, "name": name, "metrics": summarize(by_table[table])}
            for table, name in table_map.items()
        ]
        if table_id is None and processed_days
        else [],
    }
