import os
from dataclasses import dataclass
from typing import List, Optional

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Change, ChangeEmbedding, Entity, Patch


@dataclass
class EmbedSummary:
    embedded: int
    skipped: int


def _get_ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")


def _get_embedding_model() -> str:
    return os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text").strip() or "nomic-embed-text"


def _build_search_text(change: Change, entity_name: str, patch_version: str) -> str:
    tags = ", ".join(change.tags or [])
    return " | ".join(
        [
            f"patch {patch_version}",
            f"entity {entity_name}",
            f"ability {change.ability_slot or 'none'}",
            f"direction {change.direction.value}",
            f"category {change.category.value}",
            f"stat {change.stat_name}",
            f"old {change.old_value}",
            f"new {change.new_value}",
            f"delta {change.delta_value}",
            f"tags {tags}",
        ]
    )


def embed_text(text: str) -> List[float]:
    body = {"model": _get_embedding_model(), "input": text}
    base_url = _get_ollama_base_url()

    # OpenAI-compatible endpoint
    response = requests.post(f"{base_url}/v1/embeddings", json=body, timeout=60)
    if response.status_code < 400:
        payload = response.json()
        data = payload.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            vector = data[0].get("embedding")
            if isinstance(vector, list):
                return [float(v) for v in vector]

    # Newer Ollama: /api/embed
    response = requests.post(f"{base_url}/api/embed", json=body, timeout=60)
    if response.status_code == 404:
        # Older Ollama: /api/embeddings
        response = requests.post(f"{base_url}/api/embeddings", json=body, timeout=60)
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload.get("embedding"), list):
        return [float(v) for v in payload["embedding"]]

    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings or not isinstance(embeddings[0], list):
        raise RuntimeError("Ollama embedding response missing embedding vector.")
    return [float(v) for v in embeddings[0]]


def embed_changes(db: Session, patch_version: Optional[str] = None) -> EmbedSummary:
    query = (
        select(Change, Entity.name, Patch.version)
        .join(Entity, Entity.id == Change.entity_id)
        .join(Patch, Patch.id == Change.patch_id)
    )
    if patch_version:
        query = query.where(Patch.version == patch_version)

    rows = db.execute(query).all()
    embedded = 0
    skipped = 0
    model = _get_embedding_model()

    for change, entity_name, version in rows:
        search_text = _build_search_text(change, entity_name, version)
        existing = db.execute(
            select(ChangeEmbedding).where(ChangeEmbedding.change_id == change.id)
        ).scalar_one_or_none()

        if existing and existing.search_text == search_text and existing.model == model:
            skipped += 1
            continue

        vector = embed_text(search_text)
        if existing:
            existing.embedding = vector
            existing.search_text = search_text
            existing.provider = "ollama"
            existing.model = model
        else:
            db.add(
                ChangeEmbedding(
                    change_id=change.id,
                    embedding=vector,
                    search_text=search_text,
                    provider="ollama",
                    model=model,
                )
            )
        embedded += 1

    return EmbedSummary(embedded=embedded, skipped=skipped)
