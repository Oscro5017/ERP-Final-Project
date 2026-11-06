"""Manually overwrite Open-Meteo model history for a date range.

This script is intentionally never run during tests or backend startup.
Usage: python -m scripts.resync_weather_history 2026-10-17 2026-11-01
"""

import argparse
import logging
from datetime import date, timedelta

from app.database import SessionLocal
from app.services.weather import fetch_and_save_weather_for_date

logger = logging.getLogger("erp.weather.resync")


def main() -> int:
    parser = argparse.ArgumentParser(description="Overwrite saved weather-model values from Open-Meteo.")
    parser.add_argument("start_date", type=date.fromisoformat)
    parser.add_argument("end_date", type=date.fromisoformat)
    args = parser.parse_args()
    if args.start_date > args.end_date:
        parser.error("start_date must not be after end_date")

    updated = skipped = failed = 0
    current = args.start_date
    with SessionLocal() as db:
        while current <= args.end_date:
            try:
                result = fetch_and_save_weather_for_date(db, current)
                if result is None:
                    skipped += 1
                else:
                    updated += 1
            except Exception:
                db.rollback()
                logger.exception("Weather resync failed for %s; continuing with the next date.", current)
                failed += 1
            current += timedelta(days=1)

    print(f"Weather model resync finished: updated={updated}, incomplete={skipped}, failed={failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
