import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

SECTION_HEADER_BLACKLIST = {
    "base stats",
    "all abilities rescripted",
    "calibrum",
    "severum",
    "gravitum",
    "infernum",
    "crescendum",
}


def patch_version_to_slug(version: str) -> str:
    return version.replace(".", "-")


def default_url_for_version(version: str) -> str:
    slug = patch_version_to_slug(version)
    return f"https://www.leagueoflegends.com/en-us/news/game-updates/patch-{slug}-notes/"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _notes_root(soup: BeautifulSoup):
    return soup.find("article") or soup.find("main")


def extract_notes_text(soup: BeautifulSoup) -> str:
    root = _notes_root(soup)
    if not root:
        return ""

    paragraphs = [p.get_text(" ", strip=True) for p in root.find_all("p")]
    joined = " ".join(text for text in paragraphs if text)
    return _normalize_text(joined)


def parse_release_date(soup: BeautifulSoup) -> Optional[str]:
    time_tag = soup.find("time")
    if time_tag and time_tag.has_attr("datetime"):
        return str(time_tag["datetime"])[:10]
    return None


def _infer_section_type(header_text: str) -> Optional[str]:
    lowered = header_text.lower()
    if "champion" in lowered:
        return "champion"
    if "item" in lowered:
        return "item"
    if any(
        keyword in lowered
        for keyword in [
            "system",
            "rune",
            "summoner spell",
            "jungle",
            "objective",
            "bounty",
            "aram",
            "mode",
            "gameplay",
            "balance",
            "adjustment",
            "shard",
            "drake",
            "dragon",
            "rift herald",
            "baron",
            "tower",
            "minion",
            "lane",
        ]
    ):
        return "system"
    return None


def _is_likely_entity_header(text: str) -> bool:
    if not text:
        return False
    if ":" in text:
        return False
    if re.search(r"(?:⇒|=>|->)", text):
        return False
    if re.search(r"^(Passive|Q|W|E|R)\s*[-–—]\s*", text):
        return False
    # Ability-specific headings can appear as QQ/WW/EE/RR - Ability Name.
    if re.search(r"^(?:P|Q|W|E|R){1,3}\s*[-–—]\s*", text, re.IGNORECASE):
        return False
    if text.startswith(">"):
        return False
    if re.search(
        r"^>?\s*(?:Passive|Q|W|E|R)(?:\s*\+\s*(?:Passive|Q|W|E|R))+\s*[-–—]\s+",
        text,
        re.IGNORECASE,
    ):
        return False
    if any(ch in text for ch in [".", ",", "?", "!", "\""]):
        return False
    words = text.split()
    if len(words) == 0 or len(words) > 6:
        return False
    if text.lower() in SECTION_HEADER_BLACKLIST:
        return False
    return True


def extract_structured_change_lines(soup: BeautifulSoup) -> Tuple[str, Dict[str, str], Dict[str, int]]:
    root = _notes_root(soup)
    if not root:
        return "", {}, {}

    by_entity: Dict[str, Dict[str, List[str]]] = {}
    entity_order: List[str] = []
    section_type: Optional[str] = None
    current_entity: Optional[str] = None

    for node in root.find_all(["h2", "h3", "h4", "h5", "p", "li"]):
        tag = node.name.lower()
        text = _normalize_text(node.get_text(" ", strip=True))
        if not text:
            continue

        if tag.startswith("h"):
            inferred_type = _infer_section_type(text)
            if inferred_type:
                section_type = inferred_type
                current_entity = None
                continue
            if section_type and _is_likely_entity_header(text):
                current_entity = text
                if current_entity not in by_entity:
                    by_entity[current_entity] = {"type": section_type, "lines": []}
                    entity_order.append(current_entity)
                continue

        if not section_type or not current_entity:
            continue
        if text == current_entity:
            continue
        by_entity[current_entity]["lines"].append(text)

    output_lines: List[str] = []
    entity_types: Dict[str, str] = {}
    line_counts: Dict[str, int] = {}
    for entity_name in entity_order:
        entity_type = str(by_entity[entity_name]["type"])
        lines = [line for line in by_entity[entity_name]["lines"] if line]
        deduped_lines = list(dict.fromkeys(lines))
        if not deduped_lines:
            continue
        output_lines.append(f"[{entity_type}] {entity_name}")
        output_lines.extend(f"  {line}" for line in deduped_lines)
        output_lines.append("")
        entity_types[entity_name] = entity_type
        line_counts[entity_name] = len(deduped_lines)

    return "\n".join(output_lines).strip(), entity_types, line_counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Riot patch notes and create normalized JSON scaffold")
    parser.add_argument("--version", required=True, help="Patch version, e.g. 14.2")
    parser.add_argument("--url", help="Optional custom Riot patch notes URL")
    parser.add_argument(
        "--out",
        help="Output JSON file path. Defaults to backend/data/raw/<version>.json",
    )
    parser.add_argument(
        "--changes-out",
        help="Optional output text path for auto-extracted structured change lines.",
    )
    args = parser.parse_args()

    url = args.url or default_url_for_version(args.version)
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    raw_notes = extract_notes_text(soup)
    if not raw_notes:
        raw_notes = f"TODO: parse patch notes content for {args.version}"

    parsed_date = parse_release_date(soup) or date.today().isoformat()
    structured_lines, entity_types, line_counts = extract_structured_change_lines(soup)

    payload = {
        "version": args.version,
        "release_date": parsed_date,
        "raw_notes": raw_notes,
        "entities": [],
    }
    output_path = Path(args.out) if args.out else Path("data/raw") / f"{args.version}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote normalized scaffold to {output_path}")

    if args.changes_out:
        changes_out = Path(args.changes_out)
        changes_out.parent.mkdir(parents=True, exist_ok=True)
        changes_out.write_text(structured_lines, encoding="utf-8")
        print(
            "Wrote auto-extracted changes to "
            f"{changes_out} (entities={len(entity_types)}, total_lines={sum(line_counts.values())})"
        )


if __name__ == "__main__":
    main()

