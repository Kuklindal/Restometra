from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schedule import Calendar, validate_schedule
from app.schemas import DayHours, RestaurantSettings


def hours(*spans):
    return {"mode": "intervals", "intervals": [{"opens": a, "closes": b} for a, b in spans]}


def sample():
    return {
        "name": "Север",
        "timezone": "Asia/Krasnoyarsk",
        "observation_minutes": 30,
        "processing_delay_minutes": 60,
        "weekly_hours": [
            {"mode": "closed"},
            hours(("11:00", "22:00")),
            hours(("11:00", "15:00"), ("17:00", "22:00")),
            hours(("12:00", "23:00")),
            hours(("12:00", "02:00")),
            hours(("12:00", "02:00")),
            {"mode": "all_day"},
        ],
        "overrides": [{"day": "2026-01-11", "hours": hours(("12:00", "22:00"))}],
    }


def test_weekend_and_dst():
    values = sample()
    values["weekly_hours"][5] = hours(("12:00", "23:00"))
    values["timezone"] = "Europe/Berlin"
    settings = RestaurantSettings.model_validate(values)
    validate_schedule(settings)
    calendar = Calendar(settings)
    assert not calendar.day(date(2026, 1, 5)).windows
    assert calendar.day(date(2026, 1, 6)).windows[0].opens_at.hour == 10
    assert calendar.day(date(2026, 1, 8)).windows[0].opens_at.hour == 11
    assert len(calendar.day(date(2026, 1, 7)).windows) == 2
    spring = calendar.day(date(2026, 3, 29)).windows[0]
    autumn = calendar.day(date(2026, 10, 25)).windows[0]
    assert spring.closes_at - spring.opens_at == timedelta(hours=23)
    assert autumn.closes_at - autumn.opens_at == timedelta(hours=25)


def test_night_shift_override_and_separate_delays():
    day = date(2026, 1, 9)
    settings = RestaurantSettings.model_validate(
        {
            **sample(),
            "weekly_hours": [
                *sample()["weekly_hours"][:6],
                hours(("12:00", "22:00")),
            ],
        }
    )
    validate_schedule(settings)
    calendar = Calendar(settings)
    schedule = calendar.day(day)
    window = schedule.windows[0]
    assert window.closes_at == datetime(2026, 1, 9, 19, tzinfo=UTC)
    assert window.observed_until == datetime(2026, 1, 9, 19, 30, tzinfo=UTC)
    assert schedule.ready_at == datetime(2026, 1, 9, 20, 30, tzinfo=UTC)
    assert calendar.operating_date(datetime(2026, 1, 9, 19, 15, tzinfo=UTC)) == day
    assert calendar.operating_date(window.observed_until) is None
    assert calendar.operating_date(datetime(2026, 1, 10, 6, tzinfo=UTC)) == date(2026, 1, 10)
    assert calendar.day(date(2026, 1, 11)).is_override


def test_observation_is_capped_by_next_interval_and_midnight_boundary():
    values = sample()
    values["weekly_hours"][5] = hours(("02:00", "23:00"))
    values["weekly_hours"][2] = hours(("11:00", "15:00"), ("15:10", "22:00"))
    settings = RestaurantSettings.model_validate(values)
    validate_schedule(settings)
    calendar = Calendar(settings)
    weds = calendar.day(date(2026, 1, 7)).windows
    assert weds[0].observed_until == weds[1].opens_at
    friday = calendar.day(date(2026, 1, 9)).windows[0]
    saturday = calendar.day(date(2026, 1, 10)).windows[0]
    assert friday.observed_until == saturday.opens_at
    assert calendar.operating_date(saturday.opens_at) == date(2026, 1, 10)


@pytest.mark.parametrize(
    "spans",
    [
        (("11:00", "15:00"), ("14:30", "22:00")),
        (("12:00", "02:00"),),
    ],
)
def test_reject_overlapping_weekly_schedule(spans):
    values = sample()
    values["weekly_hours"][5] = hours(*spans)
    settings = RestaurantSettings.model_validate(values)
    with pytest.raises(ValueError, match="пересекаются"):
        validate_schedule(settings)


def test_override_can_close_and_open_days_but_cannot_overlap_neighbor():
    values = sample()
    values["weekly_hours"][5] = hours(("12:00", "23:00"))
    values["overrides"] = [
        {"day": "2026-01-06", "hours": {"mode": "closed"}},
        {"day": "2026-01-05", "hours": hours(("10:00", "16:00"))},
    ]
    configured = RestaurantSettings.model_validate(values)
    validate_schedule(configured)
    assert not Calendar(configured).day(date(2026, 1, 6)).windows
    assert len(Calendar(configured).day(date(2026, 1, 5)).windows) == 1
    values["overrides"] = [{"day": "2026-01-10", "hours": hours(("01:00", "16:00"))}]
    with pytest.raises(ValueError, match="пересекаются"):
        validate_schedule(RestaurantSettings.model_validate(values))


def test_reject_equal_or_invalid_clock():
    for span in [("12:00", "12:00"), ("24:00", "12:00"), ("11:60", "12:00")]:
        with pytest.raises(ValidationError):
            DayHours.model_validate(hours(span))
