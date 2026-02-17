from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.change import ChangeCategory, ChangeDirection
from app.models.entity import EntityType


class ChangeIngest(BaseModel):
    category: ChangeCategory
    stat_name: str
    ability_slot: Optional[str] = None
    old_value: Any
    new_value: Any
    delta_value: Optional[float] = None
    delta_percent: Optional[float] = None
    direction: ChangeDirection
    impact_weight: Optional[float] = None
    impact_score: Optional[float] = None
    tags: Optional[List[str]] = None

    @field_validator("stat_name")
    @classmethod
    def validate_stat_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("stat_name cannot be empty")
        return cleaned

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> Optional[List[str]]:
        if value is None:
            return None

        raw_tags: List[str] = []
        if isinstance(value, list):
            raw_tags = [str(tag) for tag in value]
        elif isinstance(value, dict):
            # Backward compatibility for old {"tag": true} payloads.
            raw_tags = [str(tag) for tag, enabled in value.items() if enabled]
        else:
            raw_tags = [str(value)]

        normalized: List[str] = []
        seen = set()
        for tag in raw_tags:
            cleaned = tag.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)

        return normalized or None

    @model_validator(mode="after")
    def infer_numeric_delta(self):
        if self.delta_value is None and isinstance(self.old_value, (int, float)) and isinstance(
            self.new_value, (int, float)
        ):
            self.delta_value = float(self.new_value) - float(self.old_value)
        return self


class EntityIngest(BaseModel):
    name: str
    entity_type: EntityType
    primary_role: Optional[str] = None
    changes: List[ChangeIngest] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("entity name cannot be empty")
        return cleaned


class PatchIngestPayload(BaseModel):
    version: str
    release_date: date
    raw_notes: str
    entities: List[EntityIngest] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("version cannot be empty")
        return cleaned

    @field_validator("raw_notes")
    @classmethod
    def validate_raw_notes(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("raw_notes cannot be empty")
        return cleaned

