import argparse
import html
import json
import math
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://api.wakatime.com/api/v1/users/current/stats/last_7_days"
START_MARKER = "<!-- WAKATIME:START -->"
END_MARKER = "<!-- WAKATIME:END -->"
GROUPS = (
    ("languages", "💬 Programming Languages", 5),
    ("editors", "🔥 Editors", 5),
    ("operating_systems", "💻 Operating Systems", 3),
)


def fetch_stats():
    token = os.environ["WAKATIME_TOKEN"].strip()
    if not token:
        raise ValueError("WAKATIME_TOKEN must contain a personal OAuth token")
    response = requests.get(
        API_URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=(10, 60),
    )
    response.raise_for_status()
    if response.status_code != 200:
        raise RuntimeError(f"WakaTime statistics are not ready: HTTP {response.status_code}")
    payload = response.json()
    if payload.get("error") or payload.get("errors"):
        raise RuntimeError("WakaTime returned an API error")
    data = payload["data"]
    if data["is_up_to_date"] is not True:
        raise RuntimeError("WakaTime is still calculating the current statistics")
    result = {key: data[key] for key in (
        "range", "start", "end", "timezone", "is_including_today",
        "total_seconds_including_other_language", "human_readable_total_including_other_language",
    )}
    for key, _, _ in GROUPS:
        result[key] = [{field: item[field] for field in ("name", "total_seconds", "percent", "text")} for item in data[key]]
    return result


def validate_stats(data):
    if data["range"] != "last_7_days":
        raise ValueError("WakaTime must return the requested last_7_days range")
    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("WakaTime returned an invalid time range")
    ZoneInfo(data["timezone"])
    total = data["total_seconds_including_other_language"]
    if not math.isfinite(total) or total < 0:
        raise ValueError("WakaTime returned an invalid total duration")
    if type(data["is_including_today"]) is not bool:
        raise ValueError("WakaTime must identify whether the range includes today")
    for key, _, _ in GROUPS:
        names = set()
        for item in data[key]:
            if not isinstance(item["name"], str) or not item["name"].strip() or item["name"] in names:
                raise ValueError(f"WakaTime returned an invalid or repeated {key} name")
            names.add(item["name"])
            seconds = item["total_seconds"]
            percent = item["percent"]
            if not math.isfinite(seconds) or seconds < 0 or not math.isfinite(percent) or not 0 <= percent <= 100:
                raise ValueError(f"WakaTime returned invalid {key} statistics")
            if not isinstance(item["text"], str):
                raise ValueError("WakaTime must provide a formatted duration")


def escape_cell(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ")


def render_stats(data):
    validate_stats(data)
    timezone = ZoneInfo(data["timezone"])
    start = datetime.fromisoformat(data["start"]).astimezone(timezone).date().isoformat()
    end = datetime.fromisoformat(data["end"]).astimezone(timezone).date().isoformat()
    lines = ["**This Week I Spent My Time On**", "", f"🕑 Time Zone: {escape_cell(data['timezone'])}", ""]
    for key, title, limit in GROUPS:
        lines.extend([f"**{title}**", ""])
        rows = sorted(data[key], key=lambda item: (-item["total_seconds"], item["name"]))[:limit]
        if rows:
            lines.extend(["| Name | Time | Share |", "| --- | ---: | ---: |"])
            lines.extend(f"| {escape_cell(item['name'])} | {escape_cell(item['text'])} | {item['percent']:.2f}% |" for item in rows)
        else:
            lines.append("No activity recorded in this period.")
        lines.append("")
    lines.extend([f"Range: {start} → {end}  ", f"Last 7 days total: {escape_cell(data['human_readable_total_including_other_language'])}"])
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
