from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.historical.models import HistoricalEvent


def validate_events(path: Path) -> int:
    raw_events = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for index, raw_event in enumerate(raw_events, start=1):
        try:
            event = HistoricalEvent.model_validate(raw_event)
        except Exception as exc:  # pydantic exposes rich validation exceptions.
            errors.append(f"row {index}: {exc}")
            continue

        if not event.sources:
            errors.append(f"row {index}: {event.title} has no sources")

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Validation passed: {len(raw_events)} events")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate historical event JSON data.")
    parser.add_argument(
        "path",
        nargs="?",
        default="data/samples/events_600_900_sample.json",
        help="Path to a historical event JSON file.",
    )
    args = parser.parse_args()
    return validate_events(Path(args.path))


if __name__ == "__main__":
    raise SystemExit(main())
