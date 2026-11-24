import csv
import io
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .db import get_db
from .models import (
    DailyMetrics,
    DailyProcessingRun,
    Restaurant,
    RestaurantScheduleOverride,
    RestaurantTable,
)
from .processing import queue_run
from .reports import make_report
from .restaurants import get_settings, tables_for
from .schedule import Calendar, validate_schedule
from .schemas import RestaurantSettings

router = APIRouter(prefix="/api/v1")
Db = Annotated[Session, Depends(get_db)]


def restaurant_or_404(db, restaurant_id, *, lock=False):
    restaurant = db.get(Restaurant, restaurant_id, with_for_update=lock)
    if restaurant is None:
        raise HTTPException(404, "Ресторан не найден.")
    return restaurant


@router.get("/health")
def health(db: Db):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/restaurants")
def restaurants(db: Db):
    return [
        {
            "id": r.id,
            "name": r.name,
            "timezone": r.timezone,
            "is_demo": r.is_demo,
            "tracking_since": r.tracking_since,
            "latest_day": db.scalar(
                select(func.max(DailyProcessingRun.day)).where(
                    DailyProcessingRun.restaurant_id == r.id, DailyProcessingRun.input_complete
                )
            ),
        }
        for r in db.scalars(select(Restaurant).order_by(Restaurant.id))
    ]


@router.get("/restaurants/{restaurant_id}/settings", response_model=RestaurantSettings)
def settings(restaurant_id: int, db: Db):
    return get_settings(db, restaurant_or_404(db, restaurant_id))


@router.put("/restaurants/{restaurant_id}/settings", response_model=RestaurantSettings)
def update_settings(restaurant_id: int, payload: RestaurantSettings, db: Db):
    try:
        validate_schedule(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    restaurant = restaurant_or_404(db, restaurant_id, lock=True)
    values = payload.model_dump(mode="json", exclude={"overrides"})
    for name, value in values.items():
        setattr(restaurant, name, value)
    db.execute(
        delete(RestaurantScheduleOverride).where(
            RestaurantScheduleOverride.restaurant_id == restaurant_id
        )
    )
    db.add_all(
        RestaurantScheduleOverride(
            restaurant_id=restaurant_id, day=item.day, hours=item.hours.model_dump(mode="json")
        )
        for item in payload.overrides
    )
    db.commit()
    return payload


@router.get("/restaurants/{restaurant_id}/tables")
def tables(restaurant_id: int, db: Db):
    restaurant_or_404(db, restaurant_id)
    return [{"id": row.id, "name": row.name} for row in db.scalars(tables_for(restaurant_id))]


def check_dates(start, end):
    if not (2 <= start.year <= end.year <= 9998) or not (0 <= (end - start).days < 366):
        raise HTTPException(422, "Выберите корректный период от 1 до 366 дней.")


def get_report(db, restaurant_id, start, end, table_id):
    check_dates(start, end)
    restaurant = restaurant_or_404(db, restaurant_id)
    if table_id is not None and not db.scalar(
        tables_for(restaurant_id).where(RestaurantTable.id == table_id)
    ):
        raise HTTPException(404, "Столик не найден.")
    return make_report(db, restaurant, start, end, table_id)


@router.get("/restaurants/{restaurant_id}/reports")
def report(restaurant_id: int, start: date, end: date, db: Db, table_id: int | None = None):
    return get_report(db, restaurant_id, start, end, table_id)


@router.get("/restaurants/{restaurant_id}/reports.csv")
def report_csv(
    restaurant_id: int,
    start: date,
    end: date,
    db: Db,
    table_id: int | None = None,
    kind: str = "days",
):
    report = get_report(db, restaurant_id, start, end, table_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    columns = [
        ("completed_visits", "Завершённые визиты"),
        ("average_duration_seconds", "Средняя длительность, с"),
        ("median_duration_seconds", "Медианная длительность, с"),
        ("average_first_contact_seconds", "Ожидание официанта, с"),
    ]
    event_columns = [
        ("WAITER_CONTACT", "Контакты"),
        ("FOOD_SERVED", "Подачи блюд"),
        ("DRINK_SERVED", "Подачи напитков"),
        ("BILL_PRESENTED", "Принесение счёта"),
    ]
    states = {
        "CLOSED": "Выходной",
        "PROCESSED": "Обработан",
        "INCOMPLETE": "Неполные данные",
        "UNPROCESSED": "Не обработан",
    }
    if kind == "days":
        writer.writerow(["Дата", "Статус"] + [label for _, label in columns + event_columns])
        prefix = [(item["day"], states[item["status"]], item["metrics"]) for item in report["days"]]
    elif kind == "tables":
        writer.writerow(["Столик"] + [label for _, label in columns + event_columns])
        prefix = [(csv_name(item["name"]), item["metrics"]) for item in report["tables"]]
    else:
        raise HTTPException(422, "Недоступный вид экспорта.")
    for *labels, metrics in prefix:
        values = metrics or {}
        writer.writerow(
            labels
            + [values.get(key) for key, _ in columns]
            + [values.get("counts", {}).get(key) for key, _ in event_columns]
        )
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="restometra-{kind}.csv"'},
    )


def csv_name(name):
    if name.startswith(("+", "-", "@", "=", "\t", "\r", "\n")):
        return "'" + name
    return name


@router.post("/restaurants/{restaurant_id}/processing/{day}", status_code=202)
def enqueue(restaurant_id: int, day: date, db: Db):
    check_dates(day, day)
    restaurant = restaurant_or_404(db, restaurant_id)
    plan = Calendar(get_settings(db, restaurant)).day(day)
    if day < restaurant.tracking_since or (
        not plan.windows and not db.get(DailyMetrics, (restaurant_id, day))
    ):
        raise HTTPException(422, "Для этой даты нет операционного дня.")
    if not queue_run(db, restaurant_id, day):
        raise HTTPException(409, "Этот день уже обрабатывается.")
    return {"status": "PENDING"}
