from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class EventType(StrEnum):
    VISIT_STARTED = "VISIT_STARTED"
    WAITER_CONTACT = "WAITER_CONTACT"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_UPDATED = "ORDER_UPDATED"
    FOOD_SERVED = "FOOD_SERVED"
    DRINK_SERVED = "DRINK_SERVED"
    BILL_PRESENTED = "BILL_PRESENTED"
    ORDER_CLOSED = "ORDER_CLOSED"
    VISIT_ENDED = "VISIT_ENDED"


class Source(StrEnum):
    DEMO = "DEMO"
    MANUAL = "MANUAL"
    VIDEO = "VIDEO"
    R_KEEPER = "R_KEEPER"


class Review(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    timezone: Mapped[str]
    weekly_hours: Mapped[list] = mapped_column(JSON)
    observation_minutes: Mapped[int]
    processing_delay_minutes: Mapped[int]
    tracking_since: Mapped[date]
    is_demo: Mapped[bool]


class RestaurantScheduleOverride(Base):
    __tablename__ = "restaurant_schedule_overrides"

    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"), primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    hours: Mapped[dict] = mapped_column(JSON)


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"), index=True)
    name: Mapped[str]


class RestaurantTable(Base):
    __tablename__ = "restaurant_tables"
    __table_args__ = (UniqueConstraint("zone_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    name: Mapped[str]


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("restaurant_tables.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operating_date: Mapped[date | None] = mapped_column(index=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), index=True)
    reference: Mapped[str | None]


class ServiceEvent(Base):
    __tablename__ = "service_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    event_type: Mapped[str]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str]
    confidence: Mapped[float | None]
    review_status: Mapped[str]


class DailyProcessingRun(Base):
    __tablename__ = "daily_processing_runs"

    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"), primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(default=RunStatus.PENDING)
    input_complete: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None]


class DailyMetrics(Base):
    __tablename__ = "daily_metrics"

    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"), primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    schedule: Mapped[dict] = mapped_column(JSON)
    visits: Mapped[list] = mapped_column(JSON)
    aggregates: Mapped[dict] = mapped_column(JSON)
