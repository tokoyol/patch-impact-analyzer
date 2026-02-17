import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import SessionLocal
from app.services.ingest_patch import ingest_patch_payload, load_payload_from_file
from fetch_riot_patch import (
    default_url_for_version,
    extract_notes_text,
    extract_structured_change_lines,
    parse_release_date,
)
from paste_changes_into_patch import apply_llm_fallback, merge_into_patch_json, parse_raw_changes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Riot patch notes, auto-extract changes, and ingest in one command."
    )
    parser.add_argument("--version", required=True, help="Patch version, e.g. 26.4")
    parser.add_argument("--url", help="Optional custom Riot patch notes URL")
    parser.add_argument("--patch-json", help="Output patch JSON path. Defaults to data/raw/<version>.json")
    parser.add_argument(
        "--changes-out",
        help="Output auto-extracted changes text path. Defaults to data/raw/<version>.changes.auto.txt",
    )
    parser.add_argument(
        "--entity-type",
        default="champion",
        choices=["champion", "item", "system"],
        help="Default entity_type for untyped parsed headers.",
    )
    parser.add_argument(
        "--replace-entities",
        action="store_true",
        help="Replace entities in patch JSON with freshly extracted entities.",
    )
    parser.add_argument(
        "--use-llm-fallback",
        action="store_true",
        help="Use LLM fallback to infer unresolved lines.",
    )
    parser.add_argument(
        "--llm-max-lines",
        type=int,
        default=40,
        help="Maximum unresolved lines sent to LLM per entity.",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Generate parsed JSON only; skip database ingest.",
    )
    return parser.parse_args()


def _fetch_patch_html(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def _build_scaffold(version: str, soup: BeautifulSoup) -> Dict[str, Any]:
    raw_notes = extract_notes_text(soup)
    if not raw_notes:
        raw_notes = f"Auto-import scaffold for patch {version}."
    return {
        "version": version,
        "release_date": parse_release_date(soup) or date.today().isoformat(),
        "raw_notes": raw_notes,
        "entities": [],
    }


def _ipv4_db_url(db_url: str) -> str:
    return db_url.replace("@localhost:", "@127.0.0.1:")


def _ingest_with_local_session(payload, patch_json_path: Path):
    db = SessionLocal()
    try:
        summary = ingest_patch_payload(db, payload)
        db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ingest_with_ipv4_fallback(payload, patch_json_path: Path):
    configured_url = os.getenv("DATABASE_URL", "").strip()
    default_url = "postgresql+psycopg2://postgres:postgres@localhost:5432/patchdb"
    source_url = configured_url or default_url
    fallback_url = _ipv4_db_url(source_url)
    if fallback_url == source_url:
        raise RuntimeError("No localhost host found in DATABASE_URL for IPv4 fallback.")

    print(
        "Primary DB connection failed. Retrying once with IPv4 host "
        f"for ingest: {patch_json_path}"
    )
    engine = create_engine(fallback_url, pool_pre_ping=True)
    fallback_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = fallback_session()
    try:
        summary = ingest_patch_payload(db, payload)
        db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    args = parse_args()
    patch_json_path = Path(args.patch_json) if args.patch_json else Path("data/raw") / f"{args.version}.json"
    changes_out_path = (
        Path(args.changes_out)
        if args.changes_out
        else Path("data/raw") / f"{args.version}.changes.auto.txt"
    )

    url = args.url or default_url_for_version(args.version)
    print(f"Fetching patch notes from: {url}")
    html = _fetch_patch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    scaffold = _build_scaffold(args.version, soup)
    patch_json_path.parent.mkdir(parents=True, exist_ok=True)
    patch_json_path.write_text(json.dumps(scaffold, indent=2), encoding="utf-8")
    print(f"Wrote scaffold JSON: {patch_json_path}")

    structured_lines, _entity_types, line_counts = extract_structured_change_lines(soup)
    if not structured_lines:
        raise SystemExit(
            "Unable to auto-extract structured entities from this patch page. "
            "Try a custom --url or use manual parser input."
        )

    changes_out_path.parent.mkdir(parents=True, exist_ok=True)
    changes_out_path.write_text(structured_lines, encoding="utf-8")
    print(
        f"Wrote auto changes text: {changes_out_path} "
        f"(entities={len(line_counts)}, total_lines={sum(line_counts.values())})"
    )

    parse_result = parse_raw_changes(structured_lines)
    parsed_changes = parse_result.parsed_changes
    rule_based_change_count = sum(len(changes) for changes in parsed_changes.values())
    unresolved_line_count = sum(len(lines) for lines in parse_result.unresolved_by_entity.values())
    llm_applied: List[Dict[str, Any]] = []

    if args.use_llm_fallback:
        llm_applied = apply_llm_fallback(
            parsed_changes=parsed_changes,
            unresolved_by_entity=parse_result.unresolved_by_entity,
            max_lines_per_entity=args.llm_max_lines,
        )

    merge_into_patch_json(
        patch_json_path=patch_json_path,
        parsed_changes=parsed_changes,
        default_entity_type=args.entity_type,
        replace_entities=args.replace_entities,
        entity_type_by_entity=parse_result.entity_type_by_entity,
    )
    total_changes = sum(len(changes) for changes in parsed_changes.values())
    print(
        f"Parsed entities={len(parsed_changes)} changes={total_changes} "
        f"(rule_based={rule_based_change_count}, unresolved_lines={unresolved_line_count}, "
        f"llm_added={len(llm_applied)})"
    )

    if args.skip_ingest:
        print("Skipping ingest (--skip-ingest).")
        return

    payload = load_payload_from_file(patch_json_path)
    try:
        summary = _ingest_with_local_session(payload, patch_json_path)
    except OperationalError:
        summary = _ingest_with_ipv4_fallback(payload, patch_json_path)
    print(
        f"Ingest completed: version={summary.version}, entities={summary.entities}, changes={summary.changes}"
    )


if __name__ == "__main__":
    main()
