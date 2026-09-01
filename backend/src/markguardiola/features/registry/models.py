from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeatureDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    entity_grain: str
    sources: tuple[str, ...]
    computation: str
    window: str
    availability_rule: str
    null_strategy: str
    targets: tuple[str, ...]
    family: str
    tags: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_documentation(self) -> FeatureDefinition:
        for field_name in (
            "name",
            "description",
            "entity_grain",
            "computation",
            "window",
            "availability_rule",
            "null_strategy",
            "family",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError()
        if not self.sources or not self.targets:
            raise ValueError()
        return self


class FeatureRegistry:
    def __init__(self, definitions: tuple[FeatureDefinition, ...]) -> None:
        names = [definition.name for definition in definitions]
        if len(names) != len(set(names)):
            raise ValueError()
        self._definitions = definitions
        self._by_name = {definition.name: definition for definition in definitions}

    @classmethod
    def load(cls, path: Path | None = None) -> FeatureRegistry:
        registry_path = path or Path(__file__).with_name("features.json")
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError()
        return cls(tuple(FeatureDefinition.model_validate(item) for item in payload))

    @property
    def definitions(self) -> tuple[FeatureDefinition, ...]:
        return self._definitions

    def get(self, name: str) -> FeatureDefinition:
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError() from None

    def for_target(self, target: str) -> tuple[FeatureDefinition, ...]:
        return tuple(item for item in self._definitions if target in item.targets)
