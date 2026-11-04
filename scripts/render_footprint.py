import colorsys
import math
from collections import Counter
from datetime import date
from pathlib import Path

import svgwrite


WIDTH = 1200
HEIGHT = 860
BACKGROUND = "#0b1020"
PANEL = "#111a2c"
BORDER = "#25334a"
FOREGROUND = "#edf3ff"
MUTED = "#9aaec9"
ACCENT = "#76d9cf"
FONT = "Arial, Helvetica, sans-serif"


def compact_number(value):
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,}"


def bounds(left, top, right, bottom):
    assert 0 <= left <= right <= WIDTH, (left, right)
    assert 0 <= top <= bottom <= HEIGHT, (top, bottom)


def rectangle(drawing, x, y, width, height, **attributes):
    bounds(x, y, x + width, y + height)
    return drawing.add(drawing.rect((x, y), (width, height), **attributes))


def polygon(drawing, points, **attributes):
    bounds(
        min(x for x, _ in points),
        min(y for _, y in points),
        max(x for x, _ in points),
        max(y for _, y in points),
    )
    return drawing.add(drawing.polygon(points, **attributes))


def circle(drawing, cx, cy, radius, **attributes):
    margin = attributes.get("stroke_width", 0) / 2
    bounds(cx - radius - margin, cy - radius - margin, cx + radius + margin, cy + radius + margin)
    return drawing.add(drawing.circle((cx, cy), radius, **attributes))


def text(drawing, value, x, y, size=14, color=FOREGROUND, anchor="start", weight="normal", max_width=None):
    value = str(value)
    # 固定文字宽度，使不同设备上的字体替代仍遵守页面边界。
    widths = {" ": 0.28, "i": 0.24, "l": 0.24, "I": 0.28, "t": 0.3, "f": 0.3, "r": 0.34, "j": 0.24, "m": 0.84, "w": 0.76, "M": 0.84, "W": 0.94}
    width = sum(widths.get(character, 0.56) for character in value) * size
    if max_width is not None and width > max_width:
        size *= max_width / width
        width = max_width
    left = x if anchor == "start" else x - width if anchor == "end" else x - width / 2
    bounds(left, y - size, left + width, y + size * 0.25)
    return drawing.add(
        drawing.text(
            value,
            insert=(x, y),
            fill=color,
            font_size=size,
            font_family=FONT,
            font_weight=weight,
            text_anchor=anchor,
            textLength=width,
            lengthAdjust="spacingAndGlyphs",
        )
    )


def point(cx, cy, radius, angle):
    radians = math.radians(angle)
    return cx + radius * math.cos(radians), cy + radius * math.sin(radians)


def calendar_color(week_index, week_count, brightness):
    hue = 0.76 - 0.36 * week_index / max(week_count - 1, 1)
    channels = colorsys.hsv_to_rgb(hue, 0.52, brightness)
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in channels)


def draw_calendar(drawing, calendar, period_start, period_end):
    rectangle(drawing, 28, 242, 740, 350, fill=PANEL, stroke=BORDER, rx=16)
    text(drawing, "A year of contributions", 52, 273, size=19, weight="bold")
    text(drawing, "One tile per day · height follows contribution count", 52, 296, size=12, color=MUTED)
    weeks = calendar["weeks"]
    assert len(weeks) <= 54, len(weeks)
    days = [day for week in weeks for day in week["contributionDays"]]
    maximum = max((day["contributionCount"] for day in days), default=0)
    week_step = min(11, 572 / max(len(weeks) - 1, 1))

    tiles = [(week_index, day) for week_index, week in enumerate(weeks) for day in week["contributionDays"]]
    # 根据投影深度绘制日期，保证前方柱体正确覆盖后方柱体。
    tiles.sort(key=lambda item: (item[0] + item[1]["weekday"], item[0]))
    for week_index, day in tiles:
        weekday = day["weekday"]
        count = day["contributionCount"]
        assert 0 <= weekday <= 6 and count >= 0, day
        assert (date.fromisoformat(day["date"]).weekday() + 1) % 7 == weekday, day
        cx = 142 + week_index * week_step - weekday * 11
        cy = 365 + (week_index + weekday) * 3.25
        height = 54 * math.sqrt(count / maximum) if maximum else 0
        strength = count / maximum if maximum else 0
        top_color = calendar_color(week_index, len(weeks), 0.32 + 0.6 * math.sqrt(strength))
        if count:
            polygon(drawing, [(cx - 11, cy), (cx, cy + 3.25), (cx, cy + 3.25 - height), (cx - 11, cy - height)], fill=calendar_color(week_index, len(weeks), 0.32 + 0.24 * strength))
            polygon(drawing, [(cx, cy + 3.25), (cx + 11, cy), (cx + 11, cy - height), (cx, cy + 3.25 - height)], fill=calendar_color(week_index, len(weeks), 0.2 + 0.22 * strength))
        tile = polygon(drawing, [(cx, cy - height - 3.25), (cx + 11, cy - height), (cx, cy - height + 3.25), (cx - 11, cy - height)], fill=top_color, stroke=BACKGROUND, stroke_width=0.7)
        tile.set_desc(title=f"{day['date']}: {count:,} contributions")

    text(drawing, period_start, 52, 580, size=12, color=MUTED)
    text(drawing, period_end, 742, 580, size=12, color=MUTED, anchor="end")
    text(drawing, f"Busiest day: {maximum:,}", 397, 580, size=12, color=MUTED, anchor="middle")


def draw_radar(drawing, activity):
    rectangle(drawing, 784, 242, 388, 350, fill=PANEL, stroke=BORDER, rx=16)
    text(drawing, "Contribution types", 808, 273, size=19, weight="bold")
    text(drawing, "Logarithmic scale · log10(count + 1)", 808, 296, size=12, color=MUTED)
    values = [activity[key] for key in ("commits", "issues", "pull_requests", "reviews", "repositories")]
    assert all(isinstance(value, int) and value >= 0 for value in values), values
    cx, cy, radius = 978, 425, 84
    exponent = max(1, math.ceil(math.log10(max(values, default=0) + 1)))
    denominator = math.log10(10**exponent + 1)

    for power in range(1, exponent + 1):
        distance = radius * math.log10(10**power + 1) / denominator
        polygon(drawing, [point(cx, cy, distance, -90 + index * 72) for index in range(5)], fill="none", stroke=BORDER, stroke_width=1)
        text(drawing, compact_number(10**power), cx + 7, cy - distance + 12, size=9, color=MUTED, max_width=35)

    for index in range(5):
        endpoint = point(cx, cy, radius, -90 + index * 72)
        drawing.add(drawing.line((cx, cy), endpoint, stroke=BORDER, stroke_width=1))

    vertices = [point(cx, cy, radius * math.log10(value + 1) / denominator, -90 + index * 72) for index, value in enumerate(values)]
    polygon(drawing, vertices, fill=ACCENT, fill_opacity=0.24, stroke=ACCENT, stroke_width=2)
    for x, y in vertices:
        circle(drawing, x, y, 3, fill=ACCENT)

    positions = [(978, 316), (1106, 395), (1049, 537), (907, 537), (850, 395)]
    for label, value, (x, y) in zip(("Commits", "Issues", "Pull requests", "Reviews", "Repositories"), values, positions):
        text(drawing, label, x, y, size=12, color=MUTED, anchor="middle", max_width=110)
        text(drawing, f"{value:,}", x, y + 18, size=15, weight="bold", anchor="middle", max_width=110)
    text(drawing, "Counts cover the contribution window", 978, 576, size=11, color=MUTED, anchor="middle")


def draw_languages(drawing, repositories):
    rectangle(drawing, 28, 608, 1144, 220, fill=PANEL, stroke=BORDER, rx=16)
    text(drawing, "Languages across participated repositories", 52, 640, size=19, weight="bold")
    text(drawing, "Primary language · repository count", 52, 663, size=12, color=MUTED)
    counts = Counter(repository["language"] for repository in repositories)
    colors = {repository["language"]: repository["language_color"] for repository in repositories}
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    groups = ordered[:5]
    remaining = sum(count for _, count in ordered[5:])
    if remaining:
        groups.append(("Other languages", remaining))
        colors["Other languages"] = "#667b9a"

    cx, cy, radius, stroke = 150, 749, 53, 23
    circle(drawing, cx, cy, radius, fill="none", stroke=BORDER, stroke_width=stroke)
    circumference = 2 * math.pi * radius
    offset = 0
    for label, count in groups:
        length = circumference * count / len(repositories)
        circle(drawing, cx, cy, radius, fill="none", stroke=colors[label], stroke_width=stroke, stroke_dasharray=(length, max(0, circumference - length)), stroke_dashoffset=-offset, transform=f"rotate(-90 {cx} {cy})")
        offset += length

    text(drawing, str(len(repositories)), cx, cy + 1, size=28, weight="bold", anchor="middle", max_width=76)
    text(drawing, "repos", cx, cy + 21, size=12, color=MUTED, anchor="middle")

    if not groups:
        text(drawing, "No participated repositories returned", 250, 747, size=15, color=MUTED, max_width=500)
    for index, (label, count) in enumerate(groups):
        column, row = divmod(index, 3)
        x = 250 + column * 292
        y = 708 + row * 38
        rectangle(drawing, x, y - 11, 11, 11, fill=colors[label], rx=3)
        text(drawing, label, x + 22, y, size=14, max_width=180)
        text(drawing, str(count), x + 245, y, size=14, color=MUTED, anchor="end", max_width=40)

    text(drawing, "Repository metrics", 873, 707, size=14, weight="bold")
    text(drawing, "Recently contributed public", 873, 733, size=12, color=MUTED)
    text(drawing, "repositories, including your own.", 873, 752, size=12, color=MUTED)
    text(drawing, "Stars and forks are totals across", 873, 779, size=12, color=MUTED)
    text(drawing, "these participated repositories.", 873, 798, size=12, color=MUTED)


def render_footprint(payload: dict, output: Path) -> None:
    repositories = payload["repositories"]
    calendar = payload["calendar"]
    period_start = payload["period_start"]
    period_end = payload["period_end"]
    assert date.fromisoformat(period_start) <= date.fromisoformat(period_end)
    day_count = (date.fromisoformat(period_end) - date.fromisoformat(period_start)).days + 1
    assert all(repository["stars"] >= 0 and repository["forks"] >= 0 for repository in repositories)
    drawing = svgwrite.Drawing(size=(WIDTH, HEIGHT), viewBox=f"0 0 {WIDTH} {HEIGHT}", profile="full")
    drawing.set_desc(title=f"Contribution Footprint for {payload['login']}", desc=f"GitHub contribution counts from {period_start} through {period_end}; repository metrics cover {payload['repository_scope'].lower()}.")
    rectangle(drawing, 0, 0, WIDTH, HEIGHT, fill=BACKGROUND, rx=20)
    rectangle(drawing, 28, 35, 4, 50, fill=ACCENT, rx=2)
    text(drawing, "Contribution Footprint", 48, 64, size=30, weight="bold")
    text(drawing, "Code, collaboration, and the projects along the way.", 48, 87, size=13, color=MUTED)
    text(drawing, f"@{payload['login']}", 1152, 57, size=18, color=ACCENT, anchor="end", max_width=440)
    text(drawing, f"{period_start} — {period_end} · UTC", 1152, 82, size=13, color=MUTED, anchor="end")

    statistics = [
        ("Contributions", calendar["totalContributions"], f"{day_count} completed UTC days"),
        ("Participated repos", len(repositories), "Recent public activity"),
        ("Repository stars", sum(repository["stars"] for repository in repositories), "Across participated repos"),
        ("Repository forks", sum(repository["forks"] for repository in repositories), "Across participated repos"),
    ]
    for index, (label, value, caption) in enumerate(statistics):
        x = 28 + index * 290
        rectangle(drawing, x, 111, 274, 91, fill=PANEL, stroke=BORDER, rx=13)
        text(drawing, label, x + 18, 136, size=12, color=MUTED)
        text(drawing, f"{value:,}", x + 18, 170, size=29, weight="bold", max_width=238)
        text(drawing, caption, x + 18, 189, size=11, color=MUTED)
    text(drawing, f"Repository totals: {payload['repository_scope']}", 48, 225, size=12, color=MUTED, max_width=1104)
    draw_calendar(drawing, calendar, period_start, period_end)
    draw_radar(drawing, payload["activity"])
    draw_languages(drawing, repositories)
    text(drawing, "Source: GitHub GraphQL API", 48, 850, size=11, color=MUTED)
    text(drawing, "Updated automatically with GitHub Actions", 1152, 850, size=11, color=MUTED, anchor="end")
    output.parent.mkdir(parents=True, exist_ok=True)
    drawing.saveas(str(output), pretty=True)
