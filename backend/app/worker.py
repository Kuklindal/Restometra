import argparse
import logging
from datetime import UTC, date, datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from .processing import process_day, scan


def main():
    parser = argparse.ArgumentParser(description="Фоновый расчёт Restometra")
    parser.add_argument("--date", type=date.fromisoformat, help="Явно пересчитать указанную дату")
    parser.add_argument("--restaurant", type=int, default=1)
    parser.add_argument("--once", action="store_true", help="Разово обработать готовые даты")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.date:
        status = process_day(args.restaurant, args.date, datetime.now(UTC), force=True)
        print(status or "Дата пока не готова, закрыта или уже обрабатывается.")
        return
    if args.once:
        scan()
        return
    scheduler = BlockingScheduler(timezone=UTC)
    scheduler.add_job(
        scan, "interval", seconds=30, next_run_time=datetime.now(UTC), max_instances=1
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
