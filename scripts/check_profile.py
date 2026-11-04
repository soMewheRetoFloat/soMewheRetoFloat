import argparse
import ast
import json
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
import yaml

from update_wakatime import END_MARKER, START_MARKER, render_stats, replace_section


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Validate profile content and WakaTime statistics")
    parser.add_argument("--structure-only", action="store_true")
    args = parser.parse_args()
    for path in (ROOT / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    document = BeautifulSoup(MarkdownIt("commonmark", {"html": True}).enable("table").render(readme), "html.parser")
    for image in document.find_all("img"):
        if not image.get("alt"):
            raise ValueError("Profile images require alternative text")
        resource = image["src"]
        parsed = urlparse(resource)
        if parsed.scheme:
            if parsed.scheme != "https":
                raise ValueError("External images must use HTTPS")
        elif not (ROOT / resource).is_file():
            raise ValueError(f"Missing profile image: {resource}")
    for heading in ("About Me", "WakaTime", "Tech Stack", "Contact"):
        if not any(heading in item.get_text() for item in document.find_all("h3")):
            raise ValueError(f"Missing profile section: {heading}")
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError("The WakaTime section requires one marker pair")
    workflow = yaml.load((ROOT / ".github/workflows/profile-data.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if "schedule" not in workflow["on"] or "workflow_dispatch" not in workflow["on"]:
        raise ValueError("The workflow must support scheduled and manual updates")
    snapshot = ROOT / "data/wakatime.json"
    if snapshot.is_file() and not args.structure_only:
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        if replace_section(readme, render_stats(data)) != readme:
            raise ValueError("README statistics do not match the WakaTime snapshot")
        print("WakaTime snapshot and displayed statistics verified")
    elif not snapshot.is_file():
        print("WakaTime connection is pending; no account statistics have been fetched")
    print("Profile Markdown, images, section structure and workflow configuration verified")


if __name__ == "__main__":
    main()
