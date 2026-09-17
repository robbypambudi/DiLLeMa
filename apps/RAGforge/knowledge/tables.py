"""Canonical SQL graph. PostgreSQL in production, SQLite in contract tests."""

import sqlalchemy as sa
from sqlmodel import SQLModel

metadata = SQLModel.metadata

profiles = sa.Table(
    "kg_profiles",
    metadata,
    sa.Column(
        "collection_id",
        sa.Uuid(),
        sa.ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("revision", sa.String(64), nullable=False),
    sa.Column("config", sa.JSON(), nullable=False),
)
jobs = sa.Table(
    "kg_jobs",
    metadata,
    sa.Column(
        "file_id",
        sa.Uuid(),
        sa.ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("id", sa.Uuid(), nullable=False, unique=True),
    sa.Column(
        "collection_id",
        sa.Uuid(),
        sa.ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column("status", sa.String(20), nullable=False, index=True),
    sa.Column("profile", sa.JSON(), nullable=False),
    sa.Column("schema_revision", sa.String(64), nullable=False),
    sa.Column("attempts", sa.Integer(), nullable=False),
    sa.Column("lease_token", sa.Uuid(), nullable=True),
    sa.Column("lease_until", sa.DateTime(), nullable=True),
    sa.Column("checkpoint", sa.JSON(), nullable=False),
    sa.Column("error", sa.Text(), nullable=True),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
    sa.CheckConstraint(
        "status IN ('queued','running','completed','failed')", name="ck_kg_job_status"
    ),
)
documents = sa.Table(
    "kg_documents",
    metadata,
    sa.Column(
        "file_id",
        sa.Uuid(),
        sa.ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "collection_id",
        sa.Uuid(),
        sa.ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column("run_id", sa.Uuid(), nullable=False),
    sa.Column("schema_revision", sa.String(64), nullable=False),
    sa.Column("content_hash", sa.String(64), nullable=False),
    sa.Column("provenance", sa.JSON(), nullable=False),
)
chunks = sa.Table(
    "kg_chunks",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "file_id",
        sa.Uuid(),
        sa.ForeignKey("kg_documents.file_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("page", sa.Integer(), nullable=True),
    sa.Column("section", sa.Text(), nullable=False),
    sa.Column("ordinal", sa.Integer(), nullable=False),
    sa.Column("start", sa.Integer(), nullable=False),
    sa.Column("end", sa.Integer(), nullable=False),
)
entities = sa.Table(
    "kg_entities",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "collection_id",
        sa.Uuid(),
        sa.ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column("name", sa.String(255), nullable=False),
    sa.Column("type", sa.String(80), nullable=False),
)
claims = sa.Table(
    "kg_claims",
    metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column(
        "file_id",
        sa.Uuid(),
        sa.ForeignKey("kg_documents.file_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "chunk_id",
        sa.Uuid(),
        sa.ForeignKey("kg_chunks.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "subject_id",
        sa.Uuid(),
        sa.ForeignKey("kg_entities.id"),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "object_id",
        sa.Uuid(),
        sa.ForeignKey("kg_entities.id"),
        nullable=False,
        index=True,
    ),
    sa.Column("predicate", sa.String(80), nullable=False),
    sa.Column("statement", sa.Text(), nullable=False),
    sa.Column("qualifiers", sa.JSON(), nullable=False),
    sa.Column("quote", sa.Text(), nullable=False),
    sa.Column("quote_start", sa.Integer(), nullable=False),
    sa.Column("quote_end", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(20), nullable=False, index=True),
    sa.Column(
        "reviewer_id",
        sa.Uuid(),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    sa.Column("review_note", sa.Text(), nullable=True),
    sa.CheckConstraint(
        "status IN ('pending','approved','rejected')", name="ck_kg_claim_status"
    ),
)

aliases = sa.Table(
    "kg_aliases",
    metadata,
    sa.Column(
        "entity_id", sa.Uuid(), sa.ForeignKey("kg_entities.id"), primary_key=True
    ),
    sa.Column(
        "file_id",
        sa.Uuid(),
        sa.ForeignKey("kg_documents.file_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("name", sa.String(255), primary_key=True),
)

TABLES = (profiles, jobs, documents, chunks, entities, claims, aliases)
