from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .schemas import DayHours, RestaurantSettings

DAY = timedelta(days=1)
WEEK_ANCHOR = date(2025, 1, 6)


def dates(start: date, end: date):
    for offset in range((end - start).days + 1):
        yield start + offset * DAY


def wall_intervals(day: date, hours: DayHours):
    midnight = datetime.combine(day, time.min)
    if hours.mode == "all_day":
        return [(midnight, midnight + DAY)]
    intervals = []
    for span in hours.intervals:
        start = datetime.combine(day, time.fromisoformat(span.opens))
        end = datetime.combine(day, time.fromisoformat(span.closes))
        intervals.append((start, end if end > start else end + DAY))
    return sorted(intervals)


def check_conflicts(intervals):
    ordered = sorted(intervals)
    for (_, previous_end), (start, _) in zip(ordered, ordered[1:], strict=False):
        if start < previous_end:
            raise ValueError(f"Рабочие интервалы пересекаются ({start:%d.%m.%Y %H:%M}).")


def validate_schedule(settings: RestaurantSettings):
    overrides = {item.day: item.hours for item in settings.overrides}
    if len(overrides) != len(settings.overrides):
        raise ValueError("Для одной даты допускается только одно исключение.")
    if any(not 2 <= day.year <= 9998 for day in overrides):
        raise ValueError("Дата исключения вне поддерживаемого диапазона.")
    weekly = [
        interval
        for day in dates(WEEK_ANCHOR, WEEK_ANCHOR + 7 * DAY)
        for interval in wall_intervals(day, settings.weekly_hours[day.weekday()])
    ]
    try:
        check_conflicts(weekly)
    except ValueError as exc:
        raise ValueError("Рабочие интервалы недельного графика пересекаются.") from exc
    for day in overrides:
        check_conflicts(
            interval
            for near in dates(day - DAY, day + DAY)
            for interval in wall_intervals(
                near, overrides.get(near, settings.weekly_hours[near.weekday()])
            )
        )


@dataclass(frozen=True)
class Window:
    opens_at: datetime
    closes_at: datetime
    observed_until: datetime

    def snapshot(self):
        return {key: value.isoformat() for key, value in vars(self).items()}


@dataclass(frozen=True)
class OperatingDay:
    day: date
    timezone: str
    windows: list[Window]
    ready_at: datetime | None
    is_override: bool

    def snapshot(self):
        return {
            "timezone": self.timezone,
            "windows": [window.snapshot() for window in self.windows],
            "ready_at": self.ready_at.isoformat() if self.ready_at else None,
            "is_override": self.is_override,
        }


class Calendar:
    def __init__(self, settings: RestaurantSettings):
        self.settings = settings
        self.zone = ZoneInfo(settings.timezone)
        self.overrides = {item.day: item.hours for item in settings.overrides}

    def _intervals(self, day: date):
        hours = self.overrides.get(day, self.settings.weekly_hours[day.weekday()])
        for start, end in wall_intervals(day, hours):
            # Use the first occurrence of ambiguous local times, and advance gaps to
            # the next valid wall minute so adjacent intervals share a boundary.
            start, end = self._utc(start), self._utc(end)
            if start < end:
                yield start, end

    def _utc(self, wall: datetime):
        while True:
            utc = wall.replace(tzinfo=self.zone, fold=0).astimezone(UTC)
            if utc.astimezone(self.zone).replace(tzinfo=None) == wall:
                return utc
            wall += timedelta(minutes=1)

    def day(self, day: date) -> OperatingDay:
        current = list(self._intervals(day))
        next_day = list(self._intervals(day + DAY))
        following_day = list(self._intervals(day + 2 * DAY))
        observation = timedelta(minutes=self.settings.observation_minutes)
        windows = []
        # Night shifts can close on day + 1. A 24 h observation can reach day + 2.
        starts = sorted(start for start, _ in current + next_day + following_day)
        for start, end in current:
            until = min(
                end + observation, min((s for s in starts if s >= end), default=end + observation)
            )
            windows.append(Window(start, end, until))
        ready = None
        if windows:
            ready = windows[-1].observed_until + timedelta(
                minutes=self.settings.processing_delay_minutes
            )
        return OperatingDay(day, self.settings.timezone, windows, ready, day in self.overrides)

    def operating_date(self, timestamp: datetime) -> date | None:
        local_day = timestamp.astimezone(self.zone).date()
        for day in dates(local_day - 2 * DAY, local_day):
            if any(w.opens_at <= timestamp < w.observed_until for w in self.day(day).windows):
                return day
        return None
