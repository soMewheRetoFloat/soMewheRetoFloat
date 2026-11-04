import ast
import hashlib
import json
from pathlib import Path

from defusedxml import ElementTree
import yaml

from render_footprint import HEIGHT, WIDTH, render_footprint
from update_profile import validate_profile


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = {"svg": "http://www.w3.org/2000/svg"}


def main():
    for path in (ROOT / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    workflow = yaml.load(
        (ROOT / ".github/workflows/profile-data.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    if "schedule" not in workflow["on"] or "workflow_dispatch" not in workflow["on"]:
        raise ValueError("The workflow must support scheduled and manual updates")
    payload = json.loads((ROOT / "data/profile-data.json").read_text(encoding="utf-8"))
    validate_profile(payload)
    if payload["login"] != "soMewheRetoFloat":
        raise ValueError("Contribution data belongs to a different GitHub user")
    output = ROOT / "assets/images/github-footprint.svg"
    root = ElementTree.parse(output).getroot()
    if root.attrib["viewBox"] != f"0 0 {WIDTH} {HEIGHT}":
        raise ValueError("Unexpected SVG canvas")
    if root.findall(".//svg:script", NAMESPACE) or root.findall(".//svg:image", NAMESPACE):
        raise ValueError("The SVG must contain its complete chart without external resources")
    titles = [element.text for element in root.findall(".//svg:title", NAMESPACE)]
    days = [day for week in payload["calendar"]["weeks"] for day in week["contributionDays"]]
    for day in days:
        title = f"{day['date']}: {day['contributionCount']:,} contributions"
        if titles.count(title) != 1:
            raise ValueError(f"The SVG must display exactly one tile for {day['date']}")
    texts = [element.text for element in root.findall(".//svg:text", NAMESPACE)]
    expected_values = [payload["calendar"]["totalContributions"], len(payload["repositories"])]
    expected_values.extend(sum(item[key] for item in payload["repositories"]) for key in ("stars", "forks"))
    for count in expected_values:
        if f"{count:,}" not in texts:
            raise ValueError(f"Missing metric in SVG: {count}")
    for element in root.findall(".//svg:text", NAMESPACE):
        size = float(element.attrib["font-size"])
        x = float(element.attrib["x"])
        y = float(element.attrib["y"])
        length = float(element.attrib["textLength"])
        anchor = element.attrib.get("text-anchor", "start")
        left = x if anchor == "start" else x - length if anchor == "end" else x - length / 2
        if not (0 <= left <= left + length <= WIDTH and 0 <= y - size <= y + size * 0.25 <= HEIGHT):
            raise ValueError(f"Text exceeds SVG canvas: {element.text}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for resource in ("azusa.gif", "assets/images/github-footprint.svg"):
        if f'src="{resource}"' not in readme or not (ROOT / resource).is_file():
            raise ValueError(f"Missing README resource: {resource}")
    build_directory = ROOT / ".build"
    build_directory.mkdir(exist_ok=True)
    repeated = build_directory / "github-footprint.svg"
    render_footprint(payload, repeated)
    if hashlib.sha256(output.read_bytes()).digest() != hashlib.sha256(repeated.read_bytes()).digest():
        raise ValueError("Rendering the same GitHub snapshot produced different output")
    print(f"Validated {len(days)} dates, {len(payload['repositories'])} repositories, SVG metrics, boundaries and reproducibility")


if __name__ == "__main__":
    main()
