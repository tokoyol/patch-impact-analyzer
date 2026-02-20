import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


ARROW_PATTERN = r"(?:⇒|=>|->)"
CHANGE_RE = re.compile(
    rf"^\s*(?:[-*]\s*)?(?P<stat>[^:]+):\s*(?P<old>.+?)\s*{ARROW_PATTERN}\s*(?P<new>.+?)\s*$"
)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
ENTITY_TYPED_HEADER_RE = re.compile(r"^\[(champion|item|system)\]\s+(.+?)\s*$", re.IGNORECASE)
ABILITY_COMBO_HEADER_RE = re.compile(
    r"^>?\s*(?:Passive|Q|W|E|R)(?:\s*\+\s*(?:Passive|Q|W|E|R))+\s*[-–—]\s+",
    re.IGNORECASE,
)
SECTION_HEADERS = {
    "base stats",
    "all abilities rescripted",
    "calibrum",
    "severum",
    "gravitum",
    "infernum",
    "crescendum",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Paste raw change lines and merge into patch JSON entities."
    )
    parser.add_argument(
        "--patch-json",
        required=True,
        help="Path to patch JSON file, e.g. data/raw/26.3.json",
    )
    parser.add_argument(
        "--input-file",
        help="Optional text file containing raw pasted changes. If omitted, reads from stdin.",
    )
    parser.add_argument(
        "--entity-type",
        default="champion",
        choices=["champion", "item", "system"],
        help="Default entity_type for newly created entities.",
    )
    parser.add_argument(
        "--replace-entities",
        action="store_true",
        help="Replace all existing entities in patch JSON with parsed entities.",
    )
    parser.add_argument(
        "--use-llm-fallback",
        action="store_true",
        help="Use LLM fallback for unresolved lines (provider from LLM_PROVIDER).",
    )
    parser.add_argument(
        "--llm-max-lines",
        type=int,
        default=40,
        help="Maximum unresolved lines sent to the LLM per entity.",
    )
    parser.add_argument(
        "--llm-dry-run",
        action="store_true",
        help="Print LLM suggestions without writing patch JSON.",
    )
    return parser.parse_args()


@dataclass
class ParseResult:
    parsed_changes: Dict[str, List[Dict[str, Any]]]
    unresolved_by_entity: Dict[str, List[str]]
    entity_type_by_entity: Dict[str, str]


def infer_category(stat_name: str) -> str:
    s = stat_name.lower()
    if "cooldown" in s:
        return "cooldown"
    if "damage" in s:
        return "damage"
    if any(k in s for k in ["health", "armor", "resist", "mr", "attack speed", "ad", "mana"]):
        return "base_stat"
    if any(k in s for k in ["ratio", "scaling", "% ap", "% ad", "ap", "ad scaling"]):
        return "scaling"
    if any(k in s for k in ["cost", "energy", "mana cost"]):
        return "cost"
    return "mechanic"


def first_number(value: str) -> Optional[float]:
    match = NUMBER_RE.search(value)
    if not match:
        return None
    return float(match.group())


def maybe_numeric(value: str) -> Any:
    cleaned = value.strip()
    if re.fullmatch(r"-?\d+", cleaned):
        return int(cleaned)
    if re.fullmatch(r"-?\d+\.\d+", cleaned):
        return float(cleaned)
    return cleaned


def _repair_compact_slash_values(stat_name: str, old_text: str, new_text: str) -> str:
    # Riot notes occasionally drop a slash in multi-rank values (e.g. 105155/...).
    repaired = re.sub(
        r"\b(\d{2,3})(\d{2,3})(/\d{2,3}(?:/\d{2,3})*)\b",
        r"\1/\2\3",
        new_text,
    )

    # Guard for two-rank compact values like 105110 where no later slash exists.
    if repaired == new_text:
        stat_lower = stat_name.lower()
        if "damage" in stat_lower and "/" in old_text:
            repaired = re.sub(
                r"\b(\d{2,3})(\d{2,3})(?=\s*(?:\(|%|x|\b))",
                r"\1/\2",
                repaired,
            )
    return repaired


def infer_direction(stat_name: str, old_text: str, new_text: str) -> str:
    old_num = first_number(old_text)
    new_num = first_number(new_text)
    if old_num is None or new_num is None:
        return "adjustment"

    inverse = any(k in stat_name.lower() for k in ["cooldown", "cost", "mana cost", "energy"])
    if inverse:
        if new_num < old_num:
            return "buff"
        if new_num > old_num:
            return "nerf"
        return "adjustment"

    if new_num > old_num:
        return "buff"
    if new_num < old_num:
        return "nerf"
    return "adjustment"


def infer_tags(stat_name: str, old_text: str, new_text: str) -> List[str]:
    haystack = f"{stat_name} {old_text} {new_text}".lower()
    tags: List[str] = []

    def add(tag: str) -> None:
        if tag not in tags:
            tags.append(tag)

    if "cooldown" in haystack:
        add("cooldown")

    if any(k in haystack for k in ["mana", "energy", "cost"]):
        add("mana")

    if any(k in haystack for k in ["move speed", "movement speed", "dash", "blink", "leap", "speed"]):
        add("mobility")

    if any(k in haystack for k in ["damage", "execute", "burst", "initial hit"]):
        add("burst")

    if any(k in haystack for k in ["minion", "wave", "lane clear", "clear speed"]):
        add("waveclear")

    if any(k in haystack for k in ["heal", "healing", "shield", "regen", "lifesteal", "omnivamp"]):
        add("sustain")

    if any(
        k in haystack
        for k in ["health", "armor", "magic resist", "mr", "resist", "durability", "tank", "hp"]
    ):
        add("durability")

    if any(
        k in haystack
        for k in [
            "stun",
            "root",
            "slow",
            "charm",
            "fear",
            "taunt",
            "silence",
            "knockup",
            "knock up",
            "knockback",
            "knock back",
            "suppress",
            "snare",
        ]
    ):
        add("cc")

    if any(k in haystack for k in ["vision", "reveal", "stealth", "camouflage", "invisible", "ward"]):
        add("utility")

    if any(k in haystack for k in ["monster", "jungle", "camp", "smite", "epic monster"]):
        add("jungle")

    return tags


def is_entity_header(stripped: str) -> bool:
    if ":" in stripped:
        return False
    if re.search(ARROW_PATTERN, stripped):
        return False

    lowered = stripped.lower()
    if lowered in SECTION_HEADERS:
        return False
    if stripped.startswith("/"):
        return False
    if stripped.startswith(">"):
        return False
    if re.match(r"^(Passive|Q|W|E|R)\s*[-–—]\s*", stripped):
        return False
    if ABILITY_COMBO_HEADER_RE.match(stripped):
        return False
    if " - " in stripped:
        first_part = stripped.split(" - ", 1)[0].strip()
        if len(first_part) <= 10:
            return False

    # Treat long prose/sentences as commentary, not entity headers.
    words = stripped.split()
    if len(words) > 5:
        return False
    if any(ch in stripped for ch in [".", ",", "?", "!", "\""]):
        return False
    return True


def is_valid_entity_name(name: str) -> bool:
    stripped = name.strip()
    if not stripped:
        return False
    if stripped.startswith(">"):
        return False
    if ABILITY_COMBO_HEADER_RE.match(stripped):
        return False
    if re.search(r"^(?:P|Q|W|E|R){1,3}\s*[-–—]\s*", stripped, re.IGNORECASE):
        return False
    return True


def should_skip_colon_line_without_arrow(stripped: str) -> bool:
    lowered = stripped.lower()
    if "unchanged" in lowered:
        return True
    if lowered.startswith("initial hit"):
        return True
    if lowered.startswith("subsequent hits"):
        return True
    return False


def is_potential_change_line(stripped: str) -> bool:
    lowered = stripped.lower()
    if ":" in stripped:
        return True
    if re.search(r"\d", stripped) and any(
        keyword in lowered
        for keyword in [
            "cooldown",
            "damage",
            "cost",
            "mana",
            "energy",
            "shield",
            "healing",
            "armor",
            "resist",
            "ratio",
            "increased",
            "decreased",
        ]
    ):
        return True
    return False


def parse_raw_changes(raw_text: str) -> ParseResult:
    parsed: Dict[str, List[Dict[str, Any]]] = {}
    unresolved_by_entity: Dict[str, List[str]] = {}
    entity_type_by_entity: Dict[str, str] = {}
    current_entity: Optional[str] = None
    saw_typed_headers = False

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        typed_header_match = ENTITY_TYPED_HEADER_RE.match(stripped)
        if typed_header_match:
            entity_type = typed_header_match.group(1).strip().lower()
            entity_name = typed_header_match.group(2).strip()
            if is_valid_entity_name(entity_name):
                saw_typed_headers = True
                current_entity = entity_name
                parsed.setdefault(current_entity, [])
                unresolved_by_entity.setdefault(current_entity, [])
                entity_type_by_entity[current_entity] = entity_type
                continue

        match = CHANGE_RE.match(line)
        if match:
            if not current_entity:
                raise ValueError(f"Found change line before entity header: {line}")

            stat_name = match.group("stat").strip()
            old_text = match.group("old").strip()
            new_text = _repair_compact_slash_values(
                stat_name=stat_name,
                old_text=old_text,
                new_text=match.group("new").strip(),
            )

            old_num = first_number(old_text)
            new_num = first_number(new_text)
            delta_value = None
            if old_num is not None and new_num is not None:
                delta_value = new_num - old_num

            parsed[current_entity].append(
                {
                    "category": infer_category(stat_name),
                    "stat_name": stat_name,
                    "old_value": maybe_numeric(old_text),
                    "new_value": maybe_numeric(new_text),
                    "delta_value": delta_value,
                    "direction": infer_direction(stat_name, old_text, new_text),
                    "tags": infer_tags(stat_name, old_text, new_text),
                }
            )
            continue

        if ":" in stripped and not re.search(ARROW_PATTERN, stripped):
            if should_skip_colon_line_without_arrow(stripped):
                continue
            if current_entity and is_potential_change_line(stripped):
                unresolved_by_entity.setdefault(current_entity, []).append(stripped)
            continue

        if is_entity_header(stripped):
            if saw_typed_headers and current_entity:
                continue
            if not is_valid_entity_name(stripped):
                continue
            current_entity = stripped
            parsed.setdefault(current_entity, [])
            unresolved_by_entity.setdefault(current_entity, [])
            continue

        if current_entity and is_potential_change_line(stripped):
            unresolved_by_entity.setdefault(current_entity, []).append(stripped)
        continue

    return ParseResult(
        parsed_changes=parsed,
        unresolved_by_entity=unresolved_by_entity,
        entity_type_by_entity=entity_type_by_entity,
    )


def apply_llm_fallback(
    parsed_changes: Dict[str, List[Dict[str, Any]]],
    unresolved_by_entity: Dict[str, List[str]],
    max_lines_per_entity: int,
) -> List[Dict[str, Any]]:
    from app.services.llm_fallback import infer_changes_for_lines

    applied: List[Dict[str, Any]] = []
    for entity, unresolved_lines in unresolved_by_entity.items():
        if not unresolved_lines:
            continue

        lines_for_llm = unresolved_lines[: max(0, max_lines_per_entity)]
        if not lines_for_llm:
            continue

        candidates = infer_changes_for_lines(entity, lines_for_llm)
        for candidate in candidates:
            old_value = candidate.old_value
            new_value = candidate.new_value
            old_num = first_number(str(old_value)) if old_value is not None else None
            new_num = first_number(str(new_value)) if new_value is not None else None
            delta_value = None
            if old_num is not None and new_num is not None:
                delta_value = new_num - old_num

            normalized_tags = candidate.tags or infer_tags(
                candidate.stat_name,
                str(old_value) if old_value is not None else "",
                str(new_value) if new_value is not None else "",
            )
            change = {
                "category": candidate.category,
                "stat_name": candidate.stat_name,
                "ability_slot": candidate.ability_slot,
                "old_value": old_value,
                "new_value": new_value,
                "delta_value": delta_value,
                "direction": candidate.direction,
                "tags": normalized_tags,
            }
            parsed_changes.setdefault(entity, []).append(change)
            applied.append(
                {
                    "entity": entity,
                    "source_line": lines_for_llm[candidate.source_line_index],
                    "change": change,
                }
            )

    return applied


def merge_into_patch_json(
    patch_json_path: Path,
    parsed_changes: Dict[str, List[Dict[str, Any]]],
    default_entity_type: str,
    replace_entities: bool,
    entity_type_by_entity: Optional[Dict[str, str]] = None,
) -> None:
    raw_file = patch_json_path.read_text(encoding="utf-8")
    try:
        patch_data = json.loads(raw_file)
    except json.JSONDecodeError:
        version_match = re.search(r'"version"\s*:\s*"([^"]+)"', raw_file)
        release_date_match = re.search(r'"release_date"\s*:\s*"([^"]+)"', raw_file)
        raw_notes_match = re.search(r'"raw_notes"\s*:\s*"([^"]*)"', raw_file)
        patch_data = {
            "version": version_match.group(1) if version_match else "unknown",
            "release_date": release_date_match.group(1) if release_date_match else "1970-01-01",
            "raw_notes": raw_notes_match.group(1) if raw_notes_match else "",
            "entities": [],
        }
        print(
            "Warning: patch JSON was invalid. Rebuilt a valid base using metadata fields and replaced entities."
        )
    entities = [] if replace_entities else patch_data.get("entities", [])
    if not str(patch_data.get("raw_notes", "")).strip():
        patch_data["raw_notes"] = (
            f"Imported structured changes for patch {patch_data.get('version', 'unknown')}."
        )
    existing_by_name = {e.get("name", "").lower(): e for e in entities if isinstance(e, dict)}

    for name, changes in parsed_changes.items():
        key = name.lower()
        resolved_entity_type = (
            (entity_type_by_entity or {}).get(name, default_entity_type).strip().lower()
        )
        existing = existing_by_name.get(key)
        if existing:
            existing["changes"] = changes
            existing["entity_type"] = resolved_entity_type
            if "primary_role" not in existing:
                existing["primary_role"] = None
        else:
            entities.append(
                {
                    "name": name,
                    "entity_type": resolved_entity_type,
                    "primary_role": None,
                    "changes": changes,
                }
            )

    patch_data["entities"] = entities
    patch_json_path.write_text(json.dumps(patch_data, indent=2), encoding="utf-8")


def read_raw_input(input_file: Optional[str]) -> str:
    if input_file:
        return Path(input_file).read_text(encoding="utf-8")

    print("Paste raw changes. End input with Ctrl+Z then Enter (Windows).")
    print("Example:")
    print("Mel")
    print("  Health per Level: 93 => 99")
    print()

    lines: List[str] = []
    try:
        while True:
            lines.append(input())
    except EOFError:
        pass
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    patch_json_path = Path(args.patch_json)
    raw_text = read_raw_input(args.input_file)

    parse_result = parse_raw_changes(raw_text)
    parsed_changes = parse_result.parsed_changes
    rule_based_change_count = sum(len(changes) for changes in parsed_changes.values())
    llm_applied: List[Dict[str, Any]] = []
    if args.use_llm_fallback:
        try:
            llm_applied = apply_llm_fallback(
                parsed_changes=parsed_changes,
                unresolved_by_entity=parse_result.unresolved_by_entity,
                max_lines_per_entity=args.llm_max_lines,
            )
        except RuntimeError as exc:
            raise SystemExit(f"LLM fallback failed: {exc}") from exc

    if args.llm_dry_run:
        print(
            json.dumps(
                {
                    "entities": len(parsed_changes),
                    "rule_based_changes": rule_based_change_count,
                    "unresolved_line_count": sum(
                        len(lines) for lines in parse_result.unresolved_by_entity.values()
                    ),
                    "llm_suggestions_count": len(llm_applied),
                    "llm_suggestions_preview": llm_applied[:20],
                },
                indent=2,
                ensure_ascii=True,
            )
        )
        return

    merge_into_patch_json(
        patch_json_path,
        parsed_changes,
        args.entity_type,
        args.replace_entities,
        parse_result.entity_type_by_entity,
    )

    total_changes = sum(len(changes) for changes in parsed_changes.values())
    print(
        f"Updated {patch_json_path} with {len(parsed_changes)} entities and {total_changes} changes."
    )
    if args.use_llm_fallback:
        print(f"LLM fallback added {len(llm_applied)} changes from unresolved lines.")


if __name__ == "__main__":
    main()

