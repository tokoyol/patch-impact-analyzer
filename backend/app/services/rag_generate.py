import json
import re
import warnings
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import get_gemini_settings, get_llm_settings, get_ollama_settings, get_openai_settings
from app.models import Change, Entity, Patch
from app.models.change import ChangeCategory, ChangeDirection
from app.models.entity import EntityType
from app.services.semantic_search import semantic_search_changes


def _build_prompt(
    query: str,
    retrieved_changes: List[Dict[str, Any]],
    relevant_patch_notes: List[Dict[str, str]],
) -> str:
    return (
        "User question:\n"
        f"{query}\n\n"
        "Here are the structured changes:\n"
        f"{json.dumps(retrieved_changes, indent=2, ensure_ascii=True)}\n\n"
        "Here are relevant patch notes:\n"
        f"{json.dumps(relevant_patch_notes, indent=2, ensure_ascii=True)}\n\n"
        "Explain likely meta impact with role-level effects. Return JSON only with keys:\n"
        "{"
        '"explanation": string,'
        '"impact_summary": [string],'
        '"reasoning": [string],'
        '"citations": [{"index": number, "entity": string, "patch_version": string}]'
        "}\n"
        "Rules:\n"
        "- Ground all claims in provided data and cite used retrieved items by their index in structured changes.\n"
        "- Mention uncertainty when evidence is sparse or conflicting.\n"
        "- Do not claim role winners/losers unless supporting tags/stats are present in retrieved changes.\n"
        "- If query asks about system changes, prioritize system entities over champion specifics."
    )


def _call_llm_for_rag(prompt: str) -> Dict[str, Any]:
    llm_settings = get_llm_settings()

    if llm_settings.provider == "openai":
        from openai import OpenAI

        settings = get_openai_settings()
        client = OpenAI(api_key=settings.api_key)
        response = client.chat.completions.create(
            model=settings.model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a grounded patch analysis assistant. Return strict JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    if llm_settings.provider == "gemini":
        settings = get_gemini_settings()
        requested_model = settings.model.strip()
        fallback_models = ["gemini-2.0-flash", "gemini-1.5-flash-latest"]
        candidate_models: List[str] = [requested_model] + [
            model_name for model_name in fallback_models if model_name != requested_model
        ]
        last_error: Optional[Exception] = None

        # Prefer the modern Gemini SDK if available.
        try:
            from google import genai

            client = genai.Client(api_key=settings.api_key)
            for model_name in candidate_models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents="You are a grounded patch analysis assistant. Return strict JSON.\n\n"
                        + prompt,
                        config={
                            "temperature": 0.2,
                            "response_mime_type": "application/json",
                        },
                    )
                    text = (
                        (getattr(response, "text", None) or getattr(response, "output_text", "{}") or "{}")
                        .strip()
                    )
                    if text.startswith("```"):
                        text = (
                            text.removeprefix("```json")
                            .removeprefix("```")
                            .removesuffix("```")
                            .strip()
                        )
                    return json.loads(text or "{}")
                except Exception as exc:
                    last_error = exc
        except Exception:
            pass

        # Backward-compat fallback to deprecated SDK.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                import google.generativeai as genai

            genai.configure(api_key=settings.api_key)
            for model_name in candidate_models:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(
                        "You are a grounded patch analysis assistant. Return strict JSON.\n\n" + prompt,
                        generation_config={
                            "temperature": 0.2,
                            "response_mime_type": "application/json",
                        },
                    )
                    text = (getattr(response, "text", "{}") or "{}").strip()
                    if text.startswith("```"):
                        text = (
                            text.removeprefix("```json")
                            .removeprefix("```")
                            .removesuffix("```")
                            .strip()
                        )
                    return json.loads(text or "{}")
                except Exception as exc:
                    last_error = exc
        except Exception as exc:
            last_error = exc

        if last_error is not None:
            raise last_error

    settings = get_ollama_settings()
    url = f"{settings.base_url}/api/chat"
    body = {
        "model": settings.model,
        "messages": [
            {
                "role": "system",
                "content": "You are a grounded patch analysis assistant. Return strict JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 450},
    }
    response = requests.post(url, json=body, timeout=240)
    response.raise_for_status()
    raw = response.json()
    message_content = (
        raw.get("message", {}).get("content")
        if isinstance(raw.get("message"), dict)
        else raw.get("response", "{}")
    )
    return json.loads(message_content or "{}")


def _collect_relevant_patch_notes(db: Session, versions: List[str]) -> List[Dict[str, str]]:
    if not versions:
        return []
    rows = db.query(Patch).filter(Patch.version.in_(versions)).all()
    notes: List[Dict[str, str]] = []
    for patch in rows:
        note_text = patch.raw_notes or ""
        notes.append(
            {
                "patch_version": patch.version,
                "raw_notes_excerpt": note_text[:800],
            }
        )
    return notes


def _normalize_text_key(value: str) -> str:
    lowered = value.strip().lower()
    lowered = lowered.replace("&", " and ")
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _infer_item_from_query(db: Session, query: str) -> Optional[str]:
    normalized_query = f" {_normalize_text_key(query)} "
    if len(normalized_query.strip()) < 2:
        return None

    item_names = [
        row[0]
        for row in db.query(Entity.name)
        .filter(Entity.entity_type == EntityType.item)
        .all()
    ]
    best_match: Optional[str] = None
    best_len = -1
    for item_name in item_names:
        normalized_item = _normalize_text_key(item_name)
        if not normalized_item:
            continue
        # Word boundary check prevents partial-token false positives.
        if f" {normalized_item} " in normalized_query and len(normalized_item) > best_len:
            best_match = item_name
            best_len = len(normalized_item)
    return best_match


def _fallback_retrieve_changes(
    db: Session,
    k: int,
    patch_version: Optional[str],
    entity_type: Optional[str],
    direction: Optional[str],
    category: Optional[str],
    tag: Optional[str],
    entity: Optional[str],
) -> List[Dict[str, Any]]:
    query = (
        db.query(Change, Entity.name.label("entity_name"), Entity.entity_type.label("entity_type_value"), Patch.version)
        .join(Entity, Entity.id == Change.entity_id)
        .join(Patch, Patch.id == Change.patch_id)
    )

    if patch_version:
        query = query.filter(Patch.version == patch_version.strip())
    if entity_type and entity_type != "all":
        query = query.filter(Entity.entity_type == EntityType(entity_type))
    if direction:
        query = query.filter(Change.direction == ChangeDirection(direction))
    if category:
        query = query.filter(Change.category == ChangeCategory(category))
    if tag:
        normalized_tag = tag.strip().lower()
        if normalized_tag:
            query = query.filter(Change.tags.isnot(None), Change.tags.contains([normalized_tag]))
    if entity:
        query = query.filter(Entity.name.ilike(f"%{entity.strip()}%"))

    rows = (
        query.order_by(desc(Change.impact_score), Patch.version.desc(), Entity.name.asc(), Change.id.asc())
        .limit(max(1, min(k, 100)))
        .all()
    )
    return [
        {
            "score": 0.0,
            "distance": None,
            "patch_version": version,
            "entity": entity_name,
            "entity_type": (
                entity_type_value.value if hasattr(entity_type_value, "value") else str(entity_type_value)
            ),
            "ability_slot": change.ability_slot,
            "direction": change.direction.value,
            "category": change.category.value,
            "stat_name": change.stat_name,
            "old_value": change.old_value,
            "new_value": change.new_value,
            "delta_value": change.delta_value,
            "impact_score": change.impact_score,
            "tags": change.tags or [],
            "embedding_model": "fallback-sql",
        }
        for change, entity_name, entity_type_value, version in rows
    ]


def _deterministic_rag_fallback(
    query: str,
    indexed_changes: List[Dict[str, Any]],
    relevant_notes: List[Dict[str, str]],
) -> Dict[str, Any]:
    if not indexed_changes:
        return {
            "query": query,
            "retrieved_count": 0,
            "retrieval_entity_type": "all",
            "retrieval_entity": None,
            "retrieved_items": [],
            "relevant_patch_notes": relevant_notes,
            "explanation": "No matching patch changes were found for this question.",
            "impact_summary": [],
            "reasoning": ["RAG fallback was used because LLM generation failed."],
            "citations": [],
        }

    top_items = indexed_changes[: min(5, len(indexed_changes))]
    patch_versions = sorted({item["patch_version"] for item in top_items})
    entities = [item["entity"] for item in top_items]
    explanation = (
        "LLM generation is temporarily unavailable, so this is a deterministic summary based on retrieved changes. "
        f"Top matches span patches {', '.join(patch_versions)} and focus on {', '.join(entities[:3])}."
    )
    impact_summary = [
        f"{item['entity']} {item['direction']} {item['stat_name']} (impact {float(item['impact_score'] or 0.0):.2f})"
        for item in top_items
    ]
    reasoning = [
        "Results are ordered from retrieved semantic/fallback matches.",
        "Use filters (patch, category, direction, entity) to narrow intent.",
    ]
    citations = [
        {
            "index": item["index"],
            "entity": item["entity"],
            "patch_version": item["patch_version"],
        }
        for item in top_items
    ]
    return {
        "query": query,
        "retrieved_count": len(indexed_changes),
        "retrieval_entity_type": "all",
        "retrieval_entity": None,
        "retrieved_items": indexed_changes,
        "relevant_patch_notes": relevant_notes,
        "explanation": explanation,
        "impact_summary": impact_summary,
        "reasoning": reasoning,
        "citations": citations,
    }


def rag_explain(
    db: Session,
    query: str,
    k: int = 12,
    patch_version: Optional[str] = None,
    entity_type: Optional[str] = None,
    direction: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    entity: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_entity_type = entity_type.strip().lower() if entity_type else None
    normalized_entity = entity.strip() if entity else None

    inferred_item_entity: Optional[str] = None
    if not normalized_entity:
        inferred_item_entity = _infer_item_from_query(db=db, query=query)
        if inferred_item_entity:
            normalized_entity = inferred_item_entity
            normalized_entity_type = "item"

    if not normalized_entity_type:
        query_lower = query.lower()
        if "system" in query_lower or "objective" in query_lower or "map" in query_lower:
            normalized_entity_type = "system"
        elif "item" in query_lower or "items" in query_lower:
            normalized_entity_type = "item"
        else:
            normalized_entity_type = "all"

    retrieved = semantic_search_changes(
        db=db,
        query_text=query,
        k=k,
        patch_version=patch_version,
        entity_type=normalized_entity_type,
        direction=direction,
        category=category,
        tag=tag,
        entity=normalized_entity,
    )
    if not retrieved:
        retrieved = _fallback_retrieve_changes(
            db=db,
            k=k,
            patch_version=patch_version,
            entity_type=normalized_entity_type,
            direction=direction,
            category=category,
            tag=tag,
            entity=normalized_entity,
        )
    indexed_changes = [
        {
            "index": index,
            "patch_version": item["patch_version"],
            "entity": item["entity"],
            "entity_type": item.get("entity_type"),
            "ability_slot": item["ability_slot"],
            "direction": item["direction"],
            "category": item["category"],
            "stat_name": item["stat_name"],
            "old_value": item["old_value"],
            "new_value": item["new_value"],
            "delta_value": item["delta_value"],
            "impact_score": item["impact_score"],
            "tags": item["tags"],
            "score": item["score"],
        }
        for index, item in enumerate(retrieved)
    ]
    patch_versions = sorted({item["patch_version"] for item in indexed_changes})
    relevant_notes = _collect_relevant_patch_notes(db, patch_versions)

    prompt = _build_prompt(query, indexed_changes, relevant_notes)
    try:
        generated = _call_llm_for_rag(prompt)
    except Exception:
        return _deterministic_rag_fallback(
            query=query,
            indexed_changes=indexed_changes,
            relevant_notes=relevant_notes,
        )

    explanation = str(generated.get("explanation", "")).strip()
    impact_summary = generated.get("impact_summary")
    reasoning = generated.get("reasoning")
    citations = generated.get("citations")

    if not isinstance(impact_summary, list):
        impact_summary = []
    if not isinstance(reasoning, list):
        reasoning = []
    if not isinstance(citations, list):
        citations = []

    return {
        "query": query,
        "retrieved_count": len(indexed_changes),
        "retrieval_entity_type": normalized_entity_type,
        "retrieval_entity": normalized_entity,
        "retrieved_items": indexed_changes,
        "relevant_patch_notes": relevant_notes,
        "explanation": explanation,
        "impact_summary": [str(line) for line in impact_summary],
        "reasoning": [str(line) for line in reasoning],
        "citations": citations,
    }
