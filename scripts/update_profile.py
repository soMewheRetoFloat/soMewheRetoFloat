import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from render_footprint import render_footprint


ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://api.github.com/graphql"
ACTIVITY_QUERY = """
query ProfileActivity($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalRepositoryContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date weekday contributionCount }
        }
      }
    }
  }
}
"""
REPOSITORY_QUERY = """
query ProfileRepositories($login: String!, $cursor: String) {
  user(login: $login) {
    repositoriesContributedTo(
      first: 100
      after: $cursor
      privacy: PUBLIC
      includeUserRepositories: true
      contributionTypes: [COMMIT]
      orderBy: {field: NAME, direction: ASC}
    ) {
      nodes {
        nameWithOwner
        isPrivate
        stargazerCount
        forkCount
        primaryLanguage { name color }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def graphql(session, query, variables):
    response = session.post(
        API_URL,
        json={"query": query, "variables": variables},
        timeout=(10, 60),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False))
    user = payload["data"]["user"]
    if user is None:
        raise ValueError(f"GitHub user does not exist: {variables['login']}")
    return user


def fetch_profile(login, period_end):
    token = os.environ["GH_TOKEN"]
    if not token.strip():
        raise ValueError("GH_TOKEN must contain a GitHub API token")
    period_start = period_end - timedelta(days=364)
    with requests.Session() as session:
        session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "somewhere-profile",
        })
        user = graphql(session, ACTIVITY_QUERY, {
            "login": login,
            "from": f"{period_start.isoformat()}T00:00:00Z",
            "to": f"{period_end.isoformat()}T23:59:59Z",
        })
        activity = user["contributionsCollection"]
        repositories = {}
        cursor = None
        seen_cursors = set()
        while True:
            connection = graphql(session, REPOSITORY_QUERY, {
                "login": login, "cursor": cursor,
            })["repositoriesContributedTo"]
            for repository in connection["nodes"]:
                if repository["isPrivate"]:
                    raise ValueError("Public repository query returned a private repository")
                language = repository["primaryLanguage"]
                name = repository["nameWithOwner"]
                if name in repositories:
                    raise ValueError(f"Repeated repository during pagination: {name}")
                repositories[name] = {
                    "name": name,
                    "stars": repository["stargazerCount"],
                    "forks": repository["forkCount"],
                    "language": language["name"] if language else "Other",
                    "language_color": (language["color"] if language else None) or "#8b949e",
                }
            page_info = connection["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            cursor = page_info["endCursor"]
            if not cursor or cursor in seen_cursors:
                raise ValueError("GitHub returned an invalid pagination cursor")
            seen_cursors.add(cursor)
    return {
        "login": user["login"],
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "calendar": activity["contributionCalendar"],
        "activity": {
            "commits": activity["totalCommitContributions"],
            "issues": activity["totalIssueContributions"],
            "pull_requests": activity["totalPullRequestContributions"],
            "reviews": activity["totalPullRequestReviewContributions"],
            "repositories": activity["totalRepositoryContributions"],
        },
        "repositories": sorted(repositories.values(), key=lambda item: item["name"].casefold()),
        "repository_scope": "Recently contributed public repositories",
    }


def validate_profile(payload):
    start = date.fromisoformat(payload["period_start"])
    end = date.fromisoformat(payload["period_end"])
    if (end - start).days != 364:
        raise ValueError("The contribution period must contain 365 days")
    days = [day for week in payload["calendar"]["weeks"] for day in week["contributionDays"]]
    actual_dates = [date.fromisoformat(day["date"]) for day in days]
    expected_dates = [start + timedelta(days=offset) for offset in range(365)]
    if actual_dates != expected_dates:
        raise ValueError("GitHub contribution dates must cover the requested period exactly")
    for day, current_date in zip(days, actual_dates, strict=True):
        if day["weekday"] != (current_date.weekday() + 1) % 7:
            raise ValueError(f"Incorrect weekday for {day['date']}")
    counts = [day["contributionCount"] for day in days]
    counts.extend(payload["activity"].values())
    for repository in payload["repositories"]:
        counts.extend([repository["stars"], repository["forks"]])
    if any(type(count) is not int or count < 0 for count in counts):
        raise ValueError("All GitHub counts must be nonnegative integers")
    if sum(day["contributionCount"] for day in days) != payload["calendar"]["totalContributions"]:
        raise ValueError("Daily contribution counts differ from the GitHub calendar total")


def main():
    parser = argparse.ArgumentParser(description="Generate a GitHub Contribution Footprint")
    parser.add_argument("--login", default="soMewheRetoFloat")
    parser.add_argument("--data-file", type=Path, default=ROOT / "data/profile-data.json")
    parser.add_argument("--output", type=Path, default=ROOT / "assets/images/github-footprint.svg")
    parser.add_argument("--from-data", type=Path, help="Render a previously fetched GitHub snapshot")
    args = parser.parse_args()
    if args.from_data:
        payload = json.loads(args.from_data.read_text(encoding="utf-8"))
    else:
        period_end = datetime.now(timezone.utc).date() - timedelta(days=1)
        payload = fetch_profile(args.login, period_end)
    if payload["login"].casefold() != args.login.casefold():
        raise ValueError("The GitHub snapshot belongs to a different user")
    validate_profile(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render_footprint(payload, args.output)
    args.data_file.parent.mkdir(parents=True, exist_ok=True)
    args.data_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {args.output.name} for {payload['login']}")
    print(f"Period: {payload['period_start']} to {payload['period_end']}")
    print(f"Contributions: {payload['calendar']['totalContributions']}; repositories: {len(payload['repositories'])}")


if __name__ == "__main__":
    main()
