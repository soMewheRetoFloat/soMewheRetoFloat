import json
import os
from pathlib import Path

import requests


GROUPS = ("languages", "editors", "operating_systems")
TOKEN = os.environ["WAKATIME_TOKEN"].strip()
if not TOKEN:
    raise ValueError("WAKATIME_TOKEN must contain a personal OAuth token")

response = requests.get(
    "https://api.wakatime.com/api/v1/users/current/summaries",
    params={"range": "Last 7 Days"},
    headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
    timeout=(10, 60),
)
scope_headers = {
    key: value
    for key, value in response.headers.items()
    if key.lower() in {"x-oauth-scopes", "x-accepted-oauth-scopes", "oauth-scope", "x-scope"}
}
print(json.dumps({"http_status": response.status_code, "scope_headers": scope_headers}))

if response.status_code == 200:
    payload = response.json()
    summaries = []
    for day in payload["data"]:
        filtered = {
            "range": {key: day["range"][key] for key in ("date", "start", "end", "timezone")},
            "grand_total": {key: day["grand_total"][key] for key in ("total_seconds", "text")},
        }
        for key in GROUPS:
            filtered[key] = [
                {field: item[field] for field in ("name", "total_seconds", "percent", "text")}
                for item in day[key]
            ]
        summaries.append(filtered)
    filtered_payload = {
        "start": payload["start"],
        "end": payload["end"],
        "cumulative_total": {key: payload["cumulative_total"][key] for key in ("seconds", "text")},
        "data": summaries,
    }
    target = Path(".work/summaries.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(filtered_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "start": filtered_payload["start"],
        "end": filtered_payload["end"],
        "total_seconds": filtered_payload["cumulative_total"]["seconds"],
        "days": [{"date": day["range"]["date"], "seconds": day["grand_total"]["total_seconds"]} for day in summaries],
    }))
