from sqlalchemy import select

from .models import Restaurant, RestaurantScheduleOverride, RestaurantTable, Zone
from .schemas import RestaurantSettings


def get_settings(db, restaurant: Restaurant) -> RestaurantSettings:
    overrides = db.scalars(
        select(RestaurantScheduleOverride)
        .where(RestaurantScheduleOverride.restaurant_id == restaurant.id)
        .order_by(RestaurantScheduleOverride.day)
    )
    return RestaurantSettings(
        name=restaurant.name,
        timezone=restaurant.timezone,
        observation_minutes=restaurant.observation_minutes,
        processing_delay_minutes=restaurant.processing_delay_minutes,
        weekly_hours=restaurant.weekly_hours,
        overrides=[{"day": row.day, "hours": row.hours} for row in overrides],
    )


def tables_for(restaurant_id: int):
    return (
        select(RestaurantTable)
        .join(Zone, RestaurantTable.zone_id == Zone.id)
        .where(Zone.restaurant_id == restaurant_id)
        .order_by(RestaurantTable.id)
    )
