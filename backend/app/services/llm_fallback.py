import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from app.config import (
    get_gemini_settings,
    get_llm_settings,
    get_ollama_settings,
    get_openai_settings,
)
from app.models.change import ChangeCategory, ChangeDirection

ALLOWED_TAGS = {
    "mobility",
    "burst",
    "waveclear",
    "sustain",
    "durability",
    "cc",
    "utility",
    "jungle",
    "mana",
    "cooldown",
}
MAX_CHANGES_PER_LINE = 3


@dataclass
class LLMChangeCandidate:
    source_line_index: int
    category: str
    stat_name: str
    old_value: Any
    new_value: Any
    direction: str
    ability_slot: Optional[str]
    tags: List[str]


def _system_prompt() -> str:
    return (
        "You convert ambiguous League patch-note lines into structured change objects. "
        "Return JSON only. Use only these categories: damage,cooldown,base_stat,scaling,cost,mechanic. "
        "Use only these directions: buff,nerf,adjustment. "
        "Tags must be a subset of: mobility,burst,waveclear,sustain,durability,cc,utility,jungle,mana,cooldown."
    )


def _user_prompt(entity_name: str, lines: List[str]) -> str:
    indexed_lines = "\n".join(f"{i}: {line}" for i, line in enumerate(lines))
    return (
        "Entity: "
        + entity_name
        + "\nExtract only lines with an actual gameplay/stat change. "
        + "If line has no clear change, skip it.\n"
        + "Output schema:\n"
        + '{ "changes": ['
        + '{"source_line_index":0,"category":"damage","stat_name":"...","old_value":"...","new_value":"...",'
        + '"direction":"buff","ability_slot":null,"tags":["burst"]}'
        + "] }\n\n"
        + "Input lines:\n"
        + indexed_lines
    )


def _normalize_tags(raw_tags: Any) -> List[str]:
    if raw_tags is None:
        return []
    if not isinstance(raw_tags, list):
        raw_tags = [raw_tags]

    tags: List[str] = []
    seen = set()
    for tag in raw_tags:
        cleaned = str(tag).strip().lower()
        if not cleaned or cleaned in seen or cleaned not in ALLOWED_TAGS:
            continue
        seen.add(cleaned)
        tags.append(cleaned)
    return tags


def _validate_candidates(raw_changes: Any, line_count: int) -> List[LLMChangeCandidate]:
    if not isinstance(raw_changes, list):
        return []

    category_values = {value.value for value in ChangeCategory}
    direction_values = {value.value for value in ChangeDirection}
    per_line_counts: Dict[int, int] = {}
    validated: List[LLMChangeCandidate] = []

    for raw in raw_changes:
        if not isinstance(raw, dict):
            continue

        source_line_index = raw.get("source_line_index")
        if not isinstance(source_line_index, int):
            continue
        if source_line_index < 0 or source_line_index >= line_count:
            continue

        per_line_counts[source_line_index] = per_line_counts.get(source_line_index, 0) + 1
        if per_line_counts[source_line_index] > MAX_CHANGES_PER_LINE:
            continue

        category = str(raw.get("category", "")).strip().lower()
        direction = str(raw.get("direction", "")).strip().lower()
        stat_name = str(raw.get("stat_name", "")).strip()

        if category not in category_values or direction not in direction_values or not stat_name:
            continue

        ability_slot = raw.get("ability_slot")
        if ability_slot is not None:
            ability_slot = str(ability_slot).strip() or None

        validated.append(
            LLMChangeCandidate(
                source_line_index=source_line_index,
                category=category,
                stat_name=stat_name,
                old_value=raw.get("old_value"),
                new_value=raw.get("new_value"),
                direction=direction,
                ability_slot=ability_slot,
                tags=_normalize_tags(raw.get("tags")),
            )
        )

    return validated


def _sanitize_json_text(value: Optional[str]) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return text or "{}"


def _parse_payload_from_text(value: Optional[str]) -> Dict[str, Any]:
    text = _sanitize_json_text(value)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _coverage(candidates: List[LLMChangeCandidate], total_lines: int) -> float:
    if total_lines <= 0:
        return 1.0
    line_indexes = {candidate.source_line_index for candidate in candidates}
    return len(line_indexes) / float(total_lines)


def _should_try_gemini_fallback(
    candidates: List[LLMChangeCandidate],
    total_lines: int,
) -> bool:
    min_coverage = float(os.getenv("LLM_LOW_CONFIDENCE_MIN_COVERAGE", "0.45"))
    has_api_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
    enabled = os.getenv("LLM_ENABLE_GEMINI_FALLBACK", "true").strip().lower() in {"1", "true", "yes"}
    if not enabled or not has_api_key:
        return False
    return _coverage(candidates, total_lines) < min_coverage


def _call_openai(entity_name: str, lines: List[str]) -> Dict[str, Any]:
    from openai import OpenAI

    settings = get_openai_settings()
    client = OpenAI(api_key=settings.api_key)
    response = client.chat.completions.create(
        model=settings.model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(entity_name, lines)},
        ],
    )
    return _parse_payload_from_text(response.choices[0].message.content)


def _call_ollama(entity_name: str, lines: List[str]) -> Dict[str, Any]:
    settings = get_ollama_settings()
    url = f"{settings.base_url}/api/chat"
    body = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(entity_name, lines)},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    try:
        response = requests.post(url, json=body, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            "Ollama request failed. Make sure Ollama is running and the model is available. "
            "Try: `ollama serve` and `ollama pull llama3.1:8b`."
        ) from exc

    raw = response.json()
    message_content = (
        raw.get("message", {}).get("content")
        if isinstance(raw.get("message"), dict)
        else raw.get("response", "{}")
    )
    return _parse_payload_from_text(message_content)


def _call_gemini(entity_name: str, lines: List[str]) -> Dict[str, Any]:
    import google.generativeai as genai

    settings = get_gemini_settings()
    genai.configure(api_key=settings.api_key)
    model = genai.GenerativeModel(settings.model)
    response = model.generate_content(
        f"{_system_prompt()}\n\n{_user_prompt(entity_name, lines)}",
        generation_config={
            "temperature": 0,
            "response_mime_type": "application/json",
        },
    )
    return _parse_payload_from_text(getattr(response, "text", "{}"))


def infer_changes_for_lines(entity_name: str, lines: List[str]) -> List[LLMChangeCandidate]:
    if not lines:
        return []

    llm_settings = get_llm_settings()
    line_count = len(lines)

    if llm_settings.provider == "openai":
        payload = _call_openai(entity_name, lines)
        return _validate_candidates(payload.get("changes"), line_count)

    if llm_settings.provider == "gemini":
        payload = _call_gemini(entity_name, lines)
        return _validate_candidates(payload.get("changes"), line_count)

    ollama_payload = _call_ollama(entity_name, lines)
    ollama_candidates = _validate_candidates(ollama_payload.get("changes"), line_count)
    if not _should_try_gemini_fallback(ollama_candidates, line_count):
        return ollama_candidates

    try:
        gemini_payload = _call_gemini(entity_name, lines)
        gemini_candidates = _validate_candidates(gemini_payload.get("changes"), line_count)
    except Exception:
        return ollama_candidates

    ollama_coverage = _coverage(ollama_candidates, line_count)
    gemini_coverage = _coverage(gemini_candidates, line_count)
    if gemini_coverage > ollama_coverage:
        return gemini_candidates
    if gemini_coverage == ollama_coverage and len(gemini_candidates) > len(ollama_candidates):
        return gemini_candidates
    return ollama_candidates
