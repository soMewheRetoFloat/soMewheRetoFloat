import argparse
import html
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://api.wakatime.com/api/v1/users/current/summaries"
START_MARKER = "<!-- WAKATIME:START -->"
END_MARKER = "<!-- WAKATIME:END -->"
GROUPS = (
    ("languages", "💬 Programming Languages", 5),
    ("editors", "🔥 Editors", 5),
    ("operating_systems", "💻 Operating Systems", 3),
)


def validate_seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("WakaTime durations must be finite nonnegative numbers")


def format_duration(seconds):
    validate_seconds(seconds)
    hours, remainder = divmod(round(seconds), 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} hrs {minutes} mins {remaining_seconds} secs"
    if minutes:
        return f"{minutes} mins {remaining_seconds} secs"
    return f"{remaining_seconds} secs"


def normalize_summaries(payload, fetched_at):
    days = payload["data"]
    if len(days) != 7:
        raise ValueError("WakaTime must return exactly seven daily summaries")
    timezones = {day["range"]["timezone"] for day in days}
    if len(timezones) != 1:
        raise ValueError("WakaTime daily summaries must use the same timezone")
    timezone_name = timezones.pop()
    local_timezone = ZoneInfo(timezone_name)
    daily_totals = []
    for day in days:
        current_date = date.fromisoformat(day["range"]["date"])
        start = datetime.fromisoformat(day["range"]["start"])
        end = datetime.fromisoformat(day["range"]["end"])
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("WakaTime returned an invalid daily time range")
        if start.astimezone(local_timezone).date() != current_date or end.astimezone(local_timezone).date() != current_date:
            raise ValueError("WakaTime summary date differs from its time range")
        seconds = day["grand_total"]["total_seconds"]
        validate_seconds(seconds)
        daily_totals.append({"date": current_date.isoformat(), "total_seconds": seconds})
    total = payload["cumulative_total"]["seconds"]
    validate_seconds(total)
    result = {
        "range": "last_7_days_including_today",
        "start": payload["start"],
        "end": payload["end"],
        "timezone": timezone_name,
        "is_including_today": True,
        "fetched_at": fetched_at.isoformat(),
        "total_seconds_including_other_language": total,
        "human_readable_total_including_other_language": format_duration(total),
        "daily_totals": daily_totals,
    }
    for key, _, _ in GROUPS:
        durations = defaultdict(list)
        for day in days:
            for item in day[key]:
                name = item["name"]
                if not isinstance(name, str) or not name.strip():
                    raise ValueError(f"WakaTime returned an invalid {key} name")
                seconds = item["total_seconds"]
                validate_seconds(seconds)
                durations[name].append(seconds)
        accumulated = {name: math.fsum(values) for name, values in durations.items()}
        group_total = math.fsum(accumulated.values())
        result[key] = [
            {
                "name": name,
                "total_seconds": seconds,
                "percent": seconds / group_total * 100 if group_total else 0.0,
                "text": format_duration(seconds),
            }
            for name, seconds in sorted(accumulated.items(), key=lambda item: (-item[1], item[0]))
        ]
    validate_stats(result)
    return result


def fetch_stats():
    token = os.environ["WAKATIME_TOKEN"].strip()
    if not token:
        raise ValueError("WAKATIME_TOKEN must contain a personal OAuth token")
    response = requests.get(
        API_URL,
        params={"range": "Last 7 Days"},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=(10, 60),
    )
    response.raise_for_status()
    if response.status_code != 200:
        raise RuntimeError(f"WakaTime statistics are not ready: HTTP {response.status_code}")
    payload = response.json()
    if payload.get("error") or payload.get("errors"):
        raise RuntimeError("WakaTime returned an API error")
    return normalize_summaries(payload, datetime.now(timezone.utc))


def validate_stats(data):
    if data["range"] != "last_7_days_including_today":
        raise ValueError("WakaTime must cover the last seven days including today")
    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("WakaTime returned an invalid time range")
    local_timezone = ZoneInfo(data["timezone"])
    fetched_at = datetime.fromisoformat(data["fetched_at"])
    if fetched_at.tzinfo is None or fetched_at.utcoffset() != timedelta(0):
        raise ValueError("The WakaTime fetch timestamp must use UTC")
    first_date = start.astimezone(local_timezone).date()
    last_date = end.astimezone(local_timezone).date()
    if (last_date - first_date).days != 6 or last_date != fetched_at.astimezone(local_timezone).date():
        raise ValueError("WakaTime must return seven dates ending on the fetch date")
    if not start <= fetched_at < end + timedelta(seconds=1):
        raise ValueError("The WakaTime fetch timestamp must belong to the reported period")
    expected_dates = [(first_date + timedelta(days=offset)).isoformat() for offset in range(7)]
    if [day["date"] for day in data["daily_totals"]] != expected_dates:
        raise ValueError("WakaTime daily summaries must contain seven consecutive dates")
    for day in data["daily_totals"]:
        validate_seconds(day["total_seconds"])
    total = data["total_seconds_including_other_language"]
    validate_seconds(total)
    # 保留 API 小数秒，允许总计与每日数值的十毫秒序列化误差。
    if not math.isclose(math.fsum(day["total_seconds"] for day in data["daily_totals"]), total, rel_tol=0, abs_tol=0.01):
        raise ValueError("WakaTime cumulative duration differs from daily totals")
    if data["human_readable_total_including_other_language"] != format_duration(total):
        raise ValueError("The WakaTime total duration text must match its numeric value")
    if data["is_including_today"] is not True:
        raise ValueError("The WakaTime period must include the fetch date")
    for key, _, _ in GROUPS:
        names = set()
        group_total = math.fsum(item["total_seconds"] for item in data[key])
        for item in data[key]:
            if not isinstance(item["name"], str) or not item["name"].strip() or item["name"] in names:
                raise ValueError(f"WakaTime returned an invalid or repeated {key} name")
            names.add(item["name"])
            seconds = item["total_seconds"]
            percent = item["percent"]
            validate_seconds(seconds)
            if type(percent) not in (int, float) or not math.isfinite(percent) or not 0 <= percent <= 100:
                raise ValueError(f"WakaTime returned invalid {key} statistics")
            expected_percent = seconds / group_total * 100 if group_total else 0.0
            if not math.isclose(percent, expected_percent, rel_tol=0, abs_tol=0.000001):
                raise ValueError(f"WakaTime {key} percentages must match aggregated durations")
            if item["text"] != format_duration(seconds):
                raise ValueError("WakaTime duration text must match its numeric value")


def escape_cell(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ")


def render_stats(data):
    validate_stats(data)
    local_timezone = ZoneInfo(data["timezone"])
    start = datetime.fromisoformat(data["start"]).astimezone(local_timezone).date().isoformat()
    end = datetime.fromisoformat(data["end"]).astimezone(local_timezone).date().isoformat()
    fetched_at = datetime.fromisoformat(data["fetched_at"]).astimezone(local_timezone).strftime("%Y-%m-%d %H:%M")
    lines = ["**Last 7 Days, Including Today**", "", f"🕑 Time Zone: {escape_cell(data['timezone'])}", ""]
    for key, title, limit in GROUPS:
        lines.extend([f"**{title}**", ""])
        rows = sorted(data[key], key=lambda item: (-item["total_seconds"], item["name"]))[:limit]
        if rows:
            lines.extend(["| Name | Time | Share |", "| --- | ---: | ---: |"])
            lines.extend(f"| {escape_cell(item['name'])} | {escape_cell(item['text'])} | {item['percent']:.2f}% |" for item in rows)
        else:
            lines.append("No activity recorded in this period.")
        lines.append("")
    lines.extend([
        f"Range: {start} → {end}",
        "",
        f"Last 7 days total: {escape_cell(data['human_readable_total_including_other_language'])}",
        "",
        f"Last synced: {fetched_at} {escape_cell(data['timezone'])}",
    ])
    return "\n".join(lines)


def replace_section(readme, content):
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError("README must contain one WakaTime marker pair")
    before, _, remaining = readme.partition(START_MARKER)
    _, marker, after = remaining.partition(END_MARKER)
    if not marker:
        raise ValueError("WakaTime markers are in the wrong order")
    return f"{before}{START_MARKER}\n{content}\n{END_MARKER}{after}"


def main():
    parser = argparse.ArgumentParser(description="Update profile from personal WakaTime statistics")
    parser.add_argument("--from-data", type=Path, help="Use a previously fetched WakaTime snapshot")
    args = parser.parse_args()
    data = json.loads(args.from_data.read_text(encoding="utf-8")) if args.from_data else fetch_stats()
    content = render_stats(data)
    readme_path = ROOT / "README.md"
    updated = replace_section(readme_path.read_text(encoding="utf-8"), content)
    data_path = ROOT / "data/wakatime.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme_path.write_text(updated, encoding="utf-8")
    print("Updated WakaTime language, editor and operating-system statistics")


if __name__ == "__main__":
    main()
