#!/usr/bin/env python3
"""Validate the Daily Report bot configuration files.

Checks `config/holidays.yml` and `config/members.yml` against the rules
documented in their headers. Exits non-zero when any error is found so it can
be wired into CI or a pre-commit hook.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - surfaced as a clear setup error
    print("ERROR: PyYAML is not installed. Run: pip install -r requirements.txt")
    sys.exit(2)

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent
HOLIDAYS_PATH = REPO_ROOT / "config" / "holidays.yml"
MEMBERS_PATH = REPO_ROOT / "config" / "members.yml"


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.info: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def note(self, msg: str) -> None:
        self.info.append(msg)


def _load_yaml(path: Path, report: Report) -> Any:
    if not path.exists():
        report.error(f"{path.relative_to(REPO_ROOT)}: file is missing")
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        report.error(f"{path.relative_to(REPO_ROOT)}: invalid YAML ({exc})")
        return None


def validate_holidays(report: Report) -> None:
    data = _load_yaml(HOLIDAYS_PATH, report)
    if data is None:
        return
    if not isinstance(data, dict):
        report.error("holidays.yml: top-level document must be a mapping")
        return

    tz = data.get("timezone")
    if not tz:
        report.error("holidays.yml: missing required 'timezone' key")
    elif ZoneInfo is not None:
        try:
            ZoneInfo(str(tz))
            report.note(f"holidays.yml: timezone = {tz} (valid)")
        except ZoneInfoNotFoundError:
            report.error(f"holidays.yml: unknown timezone '{tz}'")

    year_keys = [k for k in data if k != "timezone"]
    total = 0
    for year in year_keys:
        if not isinstance(year, int):
            report.error(f"holidays.yml: year key '{year}' must be an integer")
            continue
        entries = data[year]
        if not isinstance(entries, list):
            report.error(f"holidays.yml: {year} must be a list of holidays")
            continue
        seen: set[str] = set()
        for idx, entry in enumerate(entries):
            where = f"holidays.yml[{year}][{idx}]"
            if not isinstance(entry, dict):
                report.error(f"{where}: each holiday must be a mapping")
                continue
            date = entry.get("date")
            name = entry.get("name")
            if not name:
                report.error(f"{where}: missing 'name'")
            if not isinstance(date, dt.date):
                report.error(f"{where}: 'date' must be YYYY-MM-DD (got {date!r})")
                continue
            if date.year != year:
                report.error(
                    f"{where}: date {date.isoformat()} is not in section year {year}"
                )
            iso = date.isoformat()
            if iso in seen:
                report.error(f"{where}: duplicate date {iso}")
            seen.add(iso)
            total += 1
        report.note(f"holidays.yml: {year} -> {len(entries)} holiday(s)")
    report.note(f"holidays.yml: {total} holiday(s) across {len(year_keys)} year(s)")


def _validate_person(entry: Any, where: str, report: Report) -> str | None:
    if not isinstance(entry, dict):
        report.error(f"{where}: each person must be a mapping")
        return None
    slack_id = entry.get("slack_id")
    if not slack_id:
        report.error(f"{where}: missing required 'slack_id'")
    if not entry.get("name"):
        report.error(f"{where}: missing 'name'")
    return slack_id


def validate_members(report: Report) -> None:
    data = _load_yaml(MEMBERS_PATH, report)
    if data is None:
        return
    if not isinstance(data, dict):
        report.error("members.yml: top-level document must be a mapping")
        return

    for channel_id, cfg in data.items():
        where = f"members.yml[{channel_id}]"
        if not str(channel_id).startswith("C"):
            report.error(f"{where}: channel key should be a Slack Channel ID (starts with 'C')")
        if not isinstance(cfg, dict):
            report.error(f"{where}: value must be a mapping")
            continue
        for key in ("project", "channel", "members", "recipients"):
            if key not in cfg:
                report.error(f"{where}: missing required key '{key}'")
        for list_key in ("members", "exclude", "recipients"):
            value = cfg.get(list_key)
            if value is None:
                continue
            if not isinstance(value, list):
                report.error(f"{where}.{list_key}: must be a list")
                continue
            seen_ids: set[str] = set()
            for idx, person in enumerate(value):
                sid = _validate_person(person, f"{where}.{list_key}[{idx}]", report)
                if sid:
                    if sid in seen_ids:
                        report.error(f"{where}.{list_key}: duplicate slack_id {sid}")
                    seen_ids.add(sid)
        members = cfg.get("members") or []
        recipients = cfg.get("recipients") or []
        report.note(
            f"members.yml[{channel_id}] project={cfg.get('project')!r} "
            f"members={len(members)} recipients={len(recipients)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet", action="store_true", help="only print errors and the final verdict"
    )
    args = parser.parse_args()

    report = Report()
    validate_holidays(report)
    validate_members(report)

    if not args.quiet:
        for line in report.info:
            print(f"  info: {line}")
    for line in report.errors:
        print(f"  ERROR: {line}")

    if report.errors:
        print(f"\nFAILED: {len(report.errors)} problem(s) found.")
        return 1
    print("\nOK: all configuration files are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
