import re
from datetime import date
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

Clock = Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]
Minutes = Annotated[int, Field(ge=0, le=1440)]


class Interval(BaseModel):
    opens: Clock
    closes: Clock

    @model_validator(mode="after")
    def distinct_endpoints(self):
        if self.opens == self.closes:
            raise ValueError("Время открытия и закрытия совпадает. Выберите «Круглосуточно».")
        return self


class DayHours(BaseModel):
    mode: Literal["closed", "intervals", "all_day"]
    intervals: list[Interval] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def match_mode(self):
        if bool(self.intervals) != (self.mode == "intervals"):
            raise ValueError("У рабочего дня должен быть хотя бы один рабочий интервал.")
        return self


class ScheduleOverride(BaseModel):
    day: date
    hours: DayHours


class RestaurantSettings(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    timezone: Annotated[str, Field(max_length=80)]
    observation_minutes: Minutes
    processing_delay_minutes: Minutes
    weekly_hours: list[DayHours] = Field(min_length=7, max_length=7)
    overrides: list[ScheduleOverride] = Field(max_length=400)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        try:
            if not re.fullmatch(r"[A-Za-z0-9_+\-/]+", value):
                raise ValueError
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Укажите часовой пояс IANA, например Asia/Krasnoyarsk.") from None
        return value
