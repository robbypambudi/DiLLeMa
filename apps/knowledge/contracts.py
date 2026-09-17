"""Versioned extraction contracts. No model downloads or application imports."""

import hashlib
import json
import unicodedata
from typing import Annotated, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

PIPELINE_VERSION = "knowledge-v2.1"


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Relation(Contract):
    name: str = Field(min_length=1, max_length=80)
    subject_types: list[str] = Field(min_length=1)
    object_types: list[str] = Field(min_length=1)
    description: str = Field(min_length=1, max_length=1000)


class KnowledgeProfile(Contract):
    enabled: bool = False
    entity_types: list[str] = Field(
        default_factory=lambda: [
            "Person",
            "Organization",
            "Program",
            "Procedure",
            "Requirement",
            "Concept",
        ],
        min_length=1,
        max_length=50,
    )
    relations: list[Relation] = Field(
        default_factory=lambda: [
            Relation(
                name="REQUIRES",
                subject_types=["Program", "Procedure"],
                object_types=["Requirement"],
                description="Explicit requirement, retaining all conditions.",
            ),
            Relation(
                name="MANAGED_BY",
                subject_types=["Program", "Procedure"],
                object_types=["Person", "Organization"],
                description="Explicit responsible party.",
            ),
            Relation(
                name="HAS_PROCEDURE",
                subject_types=["Program"],
                object_types=["Procedure"],
                description="Procedure for a program.",
            ),
        ],
        min_length=1,
        max_length=100,
    )
    # Exact names only; opt-in per type. People never merge merely by name.
    merge_by_name: list[str] = Field(default_factory=list)
    instructions: str = Field(
        default="Extract only explicit knowledge from the supplied source.",
        max_length=4000,
    )

    @model_validator(mode="after")
    def validate_types(self):
        types = set(self.entity_types)
        if len(types) != len(self.entity_types) or any(not t.strip() for t in types):
            raise ValueError("Entity types must be non-empty and unique")
        if len({r.name for r in self.relations}) != len(self.relations):
            raise ValueError("Relation names must be unique")
        for relation in self.relations:
            if not set(relation.subject_types + relation.object_types) <= types:
                raise ValueError("Relation endpoints must use declared entity types")
        if not set(self.merge_by_name) <= types or "Person" in self.merge_by_name:
            raise ValueError(
                "Invalid merge_by_name types; Person requires explicit resolution"
            )
        return self

    @property
    def revision(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(), sort_keys=True).encode()
        ).hexdigest()


class SourceChunk(Contract):
    id: UUID
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    section: str = ""
    ordinal: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=1)


class Entity(Contract):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=80)
    mention: str = Field(min_length=1, max_length=1000)
    aliases: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        default_factory=list, max_length=20
    )


class Qualifiers(Contract):
    # Preserve logical expressions as source language until a rule evaluator exists.
    conditions: str | None = None
    exceptions: str | None = None
    actor_scope: str | None = None
    negated: bool = False
    modality: Literal[
        "asserted", "required", "permitted", "prohibited", "recommended"
    ] = "asserted"
    value: str | None = None
    unit: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None


class Claim(Contract):
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    statement: str = Field(min_length=1, max_length=3000)
    evidence_quote: str = Field(min_length=1, max_length=6000)
    qualifiers: Qualifiers = Field(default_factory=Qualifiers)


class Extraction(Contract):
    entities: list[Entity] = Field(default_factory=list, max_length=100)
    claims: list[Claim] = Field(default_factory=list, max_length=100)


class ExtractionContractError(ValueError):
    """Detailed repair feedback stays separate from the public job error."""

    def __init__(self, details):
        super().__init__(
            "Extraction does not match source evidence or collection ontology"
        )
        self.details = details


def validate_extraction(
    result: Extraction, chunk: SourceChunk, profile: KnowledgeProfile
) -> None:
    """Reject unsupported spans and invalid topology; semantic review remains required."""
    entities = {entity.key: entity for entity in result.entities}
    if len(entities) != len(result.entities):
        raise ValueError("Duplicate entity keys")
    for entity in entities.values():
        if entity.type not in profile.entity_types or entity.mention not in chunk.text:
            raise ValueError("Entity type or mention is not supported by the source")
        if any(
            not a or normalize(a) not in normalize(chunk.text) for a in entity.aliases
        ):
            raise ValueError("Entity alias is not present in the source")
    relations = {relation.name: relation for relation in profile.relations}
    errors = []
    for index, claim in enumerate(result.claims):
        if claim.subject not in entities or claim.object not in entities:
            errors.append(
                {
                    "location": ["claims", index],
                    "type": "unknown_entity_key",
                    "message": "Use entity.key, not entity.name, for both endpoints",
                    "allowed_keys": list(entities),
                }
            )
            continue
        relation = relations.get(claim.predicate)
        if (
            not relation
            or entities[claim.subject].type not in relation.subject_types
            or entities[claim.object].type not in relation.object_types
        ):
            errors.append(
                {
                    "location": ["claims", index],
                    "type": "relation_direction_or_type",
                    "message": "Correct subject/object direction and types to match the ontology; do not invent predicates",
                    "subject_type": entities[claim.subject].type,
                    "object_type": entities[claim.object].type,
                    "expected_subject_types": (
                        relation.subject_types if relation else []
                    ),
                    "expected_object_types": relation.object_types if relation else [],
                    "allowed_predicates": list(relations),
                }
            )
        if claim.evidence_quote not in chunk.text:
            errors.append(
                {
                    "location": ["claims", index, "evidence_quote"],
                    "type": "non_verbatim_quote",
                    "message": "Copy one contiguous exact substring of source, including original newlines",
                }
            )
    if errors:
        raise ExtractionContractError(errors)


def entity_id(
    collection_id: UUID, file_id: UUID, entity: Entity, profile: KnowledgeProfile
) -> UUID:
    scope = "collection" if entity.type in profile.merge_by_name else str(file_id)
    return uuid5(
        collection_id,
        f"{profile.revision}:{scope}:{entity.type}:{normalize(entity.name)}",
    )
