import argparse
import copy
import hashlib
import json
from pathlib import Path

from lxml import etree
import requests
import tinycss2


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets/tech-stack"
SOURCES = ASSETS / "sources"
OUTPUT = ASSETS / "panel.svg"
SVG = "http://www.w3.org/2000/svg"
NS = {"svg": SVG}
WIDTH = 1200
HEIGHT = 444
ANIMATED = (
    ("python", "Python"),
    ("js", "JavaScript"),
    ("ts", "TypeScript"),
    ("react", "React"),
    ("cpp", "C++"),
)
STATIC = "cs,java,linux,git,md,pytorch,tensorflow,django,sqlite,nextjs,nodejs,unity,unreal,pr,au,ps"
SOURCE_URLS = {
    name: f"https://techstack-generator.vercel.app/{name}-icon.svg"
    for name, _ in ANIMATED
}
SOURCE_URLS["static"] = f"https://skillicons.dev/icons?i={STATIC}&perline=8"


def parse_svg(path):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    root = etree.parse(str(path), parser).getroot()
    if root.tag != f"{{{SVG}}}svg":
        raise ValueError(f"Expected an SVG document: {path.name}")
    return root


def download_sources():
    SOURCES.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCE_URLS.items():
        response = requests.get(url, timeout=(10, 60))
        response.raise_for_status()
        path = SOURCES / f"{name}.svg"
        path.write_bytes(response.content)
        parse_svg(path)


def rewrite_tokens(tokens, ids, classes, animations):
    result = []
    previous = None
    for token in tokens:
        if token.type == "error":
            raise ValueError(f"Invalid CSS: {token.message}")
        if token.type == "hash" and token.value in ids:
            token.value = ids[token.value]
        elif token.type == "ident":
            if previous is not None and previous.type == "literal" and previous.value == "." and token.value in classes:
                token.value = classes[token.value]
            elif token.value in animations:
                token.value = animations[token.value]
        elif token.type in ("url", "string") and token.value.startswith("#") and token.value[1:] in ids:
            value = "#" + ids[token.value[1:]]
            expression = f"url({json.dumps(value)})" if token.type == "url" else json.dumps(value)
            token = tinycss2.parse_component_value_list(expression)[0]
        if hasattr(token, "arguments"):
            token.arguments = rewrite_tokens(token.arguments, ids, classes, animations)
        if hasattr(token, "content") and token.content is not None:
            token.content = rewrite_tokens(token.content, ids, classes, animations)
        result.append(token)
        if token.type not in ("whitespace", "comment"):
            previous = token
    return result


def scope_selectors(tokens, wrapper):
    result = []
    prefix = tinycss2.parse_component_value_list(f"#{wrapper} ")
    result.extend(copy.deepcopy(prefix))
    for token in tokens:
        result.append(token)
        if token.type == "literal" and token.value == ",":
            result.extend(copy.deepcopy(prefix))
    return result


def rewrite_rules(rules, wrapper, ids, classes, animations, keyframes=False):
    for rule in rules:
        if rule.type == "error":
            raise ValueError(f"Invalid CSS rule: {rule.message}")
        if rule.type == "qualified-rule":
            rule.prelude = rewrite_tokens(rule.prelude, ids, classes, animations)
            if not keyframes:
                rule.prelude = scope_selectors(rule.prelude, wrapper)
            rule.content = rewrite_tokens(rule.content, ids, classes, animations)
        elif rule.type == "at-rule":
            rule.prelude = rewrite_tokens(rule.prelude, ids, classes, animations)
            if rule.lower_at_keyword == "import":
                raise ValueError("The Tech Stack panel cannot import external stylesheets")
            if rule.content is not None:
                nested = tinycss2.parse_rule_list(rule.content, skip_comments=False, skip_whitespace=False)
                rewrite_rules(nested, wrapper, ids, classes, animations, keyframes=rule.lower_at_keyword.endswith("keyframes"))
                rule.content = tinycss2.parse_component_value_list(tinycss2.serialize(nested))
    return rules


def namespace_svg(source, name):
    root = copy.deepcopy(source)
    wrapper = f"item-{name}"
    ids = {element.get("id"): f"{name}-{element.get('id')}" for element in root.iter("*") if element.get("id")}
    classes = {value: f"{name}-{value}" for element in root.iter("*") for value in element.get("class", "").split()}
    stylesheets = []
    animations = {}
    for style in root.findall(".//svg:style", NS):
        rules = tinycss2.parse_stylesheet(style.text or "", skip_comments=False, skip_whitespace=False)
        for rule in rules:
            if rule.type == "qualified-rule":
                selector = [token for token in rule.prelude if token.type not in ("whitespace", "comment")]
                if len(selector) == 1 and selector[0].type == "hash" and selector[0].value == source.get("id"):
                    declarations = tinycss2.parse_declaration_list(rule.content, skip_comments=False, skip_whitespace=False)
                    layout = {"position", "top", "right", "bottom", "left", "width", "height", "transform"}
                    declarations = [declaration for declaration in declarations if declaration.type != "declaration" or declaration.lower_name not in layout]
                    rule.content = tinycss2.parse_component_value_list(tinycss2.serialize(declarations))
        stylesheets.append((style, rules))
        for rule in rules:
            if rule.type == "at-rule" and rule.lower_at_keyword.endswith("keyframes"):
                identifiers = [token for token in rule.prelude if token.type == "ident"]
                if len(identifiers) != 1:
                    raise ValueError("A keyframe rule must have exactly one animation name")
                animations[identifiers[0].value] = f"{name}-{identifiers[0].value}"
    for element in root.iter("*"):
        if element.get("id"):
            element.set("id", ids[element.get("id")])
        if element.get("class"):
            element.set("class", " ".join(classes[value] for value in element.get("class").split()))
        for attribute, value in list(element.attrib.items()):
            local = etree.QName(attribute).localname
            if local == "href" and value.startswith("#"):
                element.set(attribute, "#" + ids[value[1:]])
            elif local in ("fill", "stroke", "clip-path", "mask", "filter", "marker-start", "marker-mid", "marker-end", "style"):
                tokens = tinycss2.parse_component_value_list(value)
                element.set(attribute, tinycss2.serialize(rewrite_tokens(tokens, ids, classes, animations)))
            elif local in ("aria-labelledby", "aria-describedby"):
                element.set(attribute, " ".join(ids[value] for value in value.split()))
    for style, rules in stylesheets:
        style.text = tinycss2.serialize(rewrite_rules(rules, wrapper, ids, classes, animations))
    return root, wrapper, len(animations)


def add_element(parent, name, **attributes):
    return etree.SubElement(parent, f"{{{SVG}}}{name}", {key.replace("_", "-"): str(value) for key, value in attributes.items()})


def add_source(panel, name, x, y, width, height):
    source, wrapper, animation_count = namespace_svg(parse_svg(SOURCES / f"{name}.svg"), name)
    group = add_element(panel, "g", id=wrapper)
    source.set("x", str(x))
    source.set("y", str(y))
    source.set("width", str(width))
    source.set("height", str(height))
    source.set("preserveAspectRatio", "xMidYMid meet")
    source.set("overflow", "hidden")
    group.append(source)
    return animation_count


def validate_panel(panel):
    ids = [element.get("id") for element in panel.iter("*") if element.get("id")]
    if len(ids) != len(set(ids)):
        raise ValueError("The Tech Stack panel contains repeated SVG ids")
    if panel.findall(".//svg:script", NS) or panel.findall(".//svg:image", NS):
        raise ValueError("The panel must contain all icons directly without scripts or image references")
    for element in panel.iter("*"):
        for attribute, value in element.attrib.items():
            if etree.QName(attribute).localname == "href" and not value.startswith("#"):
                raise ValueError("The panel cannot reference an external resource")
    for name, _ in ANIMATED:
        group = panel.find(f"svg:g[@id='item-{name}']", NS)
        rules = [rule for style in group.findall(".//svg:style", NS) for rule in tinycss2.parse_stylesheet(style.text or "", skip_comments=True, skip_whitespace=True)]
        animations = [rule for rule in rules if rule.type == "at-rule" and rule.lower_at_keyword.endswith("keyframes")]
        if not animations:
            raise ValueError(f"Missing animation for {name}")
        for rule in rules:
            if rule.type == "qualified-rule" and not tinycss2.serialize(rule.prelude).lstrip().startswith(f"#item-{name} "):
                raise ValueError(f"The {name} stylesheet must be scoped to its icon")


def build_panel():
    panel = etree.Element(f"{{{SVG}}}svg", nsmap={None: SVG}, width=str(WIDTH), height=str(HEIGHT), viewBox=f"0 0 {WIDTH} {HEIGHT}", role="img")
    title = add_element(panel, "title")
    title.text = "Tech Stack: Python, JavaScript, TypeScript, React, C++, C#, Java, Linux, Git, Markdown, PyTorch, TensorFlow, Django, SQLite, Next.js, Node.js, Unity, Unreal Engine, Adobe Premiere Pro, Adobe Audition, Adobe Photoshop"
    description = add_element(panel, "desc")
    description.text = "Five animated technology icons above sixteen static icons, on a dark background."
    add_element(panel, "rect", x=1, y=1, width=WIDTH - 2, height=HEIGHT - 2, rx=24, fill="#0d1117", stroke="#30363d", stroke_width=2)
    for index, (name, label) in enumerate(ANIMATED):
        cx = 160 + index * 220
        count = add_source(panel, name, cx - 55, 32, 110, 110)
        if count == 0:
            raise ValueError(f"The {name} source does not contain an animation")
        text = add_element(panel, "text", x=cx, y=166, fill="#e6edf3", font_size=18, font_family="Arial, Helvetica, sans-serif", font_weight=500, text_anchor="middle")
        text.text = label
    add_element(panel, "line", x1=40, y1=188, x2=1160, y2=188, stroke="#30363d", stroke_width=1)
    add_source(panel, "static", 160, 212, 880, 208)
    validate_panel(panel)
    ASSETS.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(etree.tostring(panel, encoding="utf-8", xml_declaration=True, pretty_print=True))
    reparsed = parse_svg(OUTPUT)
    validate_panel(reparsed)
    print(f"Built {OUTPUT.relative_to(ROOT)}: {WIDTH} × {HEIGHT}; 5 animated icons; 16 static icons; self-contained SVG")


def write_sources():
    lines = ["# Tech Stack 素材来源", "", "原始 SVG 保存在 `sources/`。`panel.svg` 由 `scripts/build_tech_stack.py` 生成。", "", "| 文件 | 来源 | SHA-256 |", "| --- | --- | --- |"]
    for name, url in SOURCE_URLS.items():
        filename = f"{name}.svg"
        digest = hashlib.sha256((SOURCES / filename).read_bytes()).hexdigest()
        lines.append(f"| `{filename}` | [原始 SVG]({url}) | `{digest}` |")
    (ASSETS / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Build the animated Tech Stack panel")
    parser.add_argument("--download", action="store_true", help="Fetch original SVG assets before building")
    args = parser.parse_args()
    if args.download:
        download_sources()
    build_panel()
    write_sources()


if __name__ == "__main__":
    main()
