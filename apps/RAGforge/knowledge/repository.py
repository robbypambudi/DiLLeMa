"""Transactional graph publication, durable leases, scoped graph traversal."""

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4, uuid5

import sqlalchemy as sa

from app.models.collections import Collections
from app.models.files import Files
from knowledge import tables as t
from knowledge.contracts import (
    KnowledgeProfile,
    entity_id,
    normalize,
    validate_extraction,
)


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StaleJob(ValueError):
    pass


class KnowledgeRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def _collection(self, session, collection_id):
        row = (
            session.execute(
                sa.select(Collections.__table__)
                .where(Collections.id == collection_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not row:
            raise LookupError("Collection not found")
        return row

    def get_profile(self, collection_id) -> KnowledgeProfile:
        with self.session_factory() as session:
            row = (
                session.execute(
                    sa.select(t.profiles).where(
                        t.profiles.c.collection_id == collection_id
                    )
                )
                .mappings()
                .first()
            )
            return (
                KnowledgeProfile.model_validate(row["config"])
                if row
                else KnowledgeProfile()
            )

    def save_profile(self, collection_id, profile: KnowledgeProfile):
        with self.session_factory() as session:
            self._collection(session, collection_id)
            session.execute(
                t.profiles.delete().where(t.profiles.c.collection_id == collection_id)
            )
            session.execute(
                t.profiles.insert().values(
                    collection_id=collection_id,
                    revision=profile.revision,
                    config=profile.model_dump(),
                )
            )
            session.commit()
        return profile

    def enqueue(self, collection_id, file_id):
        with self.session_factory() as session:
            self._collection(session, collection_id)
            file = (
                session.execute(
                    sa.select(Files.__table__)
                    .where(Files.id == file_id, Files.collection_id == collection_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if not file:
                raise LookupError("File not found in collection")
            if file["status"] != "completed":
                raise ValueError("Finish document indexing before extracting knowledge")
            row = (
                session.execute(
                    sa.select(t.profiles).where(
                        t.profiles.c.collection_id == collection_id
                    )
                )
                .mappings()
                .first()
            )
            if not row or not row["config"]["enabled"]:
                raise ValueError("Enable a knowledge profile for this collection first")
            existing = (
                session.execute(sa.select(t.jobs).where(t.jobs.c.file_id == file_id))
                .mappings()
                .first()
            )
            if (
                existing
                and existing["schema_revision"] == row["revision"]
                and existing["status"] in ("queued", "running")
            ):
                return dict(existing)
            job = dict(
                file_id=file_id,
                id=uuid4(),
                collection_id=collection_id,
                status="queued",
                profile=row["config"],
                schema_revision=row["revision"],
                attempts=0,
                checkpoint={},
                error=None,
                lease_token=None,
                lease_until=None,
                updated_at=now(),
            )
            session.execute(t.jobs.delete().where(t.jobs.c.file_id == file_id))
            session.execute(t.jobs.insert().values(**job))
            session.commit()
            return job

    def list_jobs(self, collection_id):
        with self.session_factory() as session:
            columns = [
                t.jobs.c[k]
                for k in ("id", "file_id", "status", "attempts", "error", "updated_at")
            ]
            rows = session.execute(
                sa.select(*columns, Files.file_name)
                .join(Files, Files.id == t.jobs.c.file_id)
                .where(t.jobs.c.collection_id == collection_id)
                .order_by(t.jobs.c.updated_at.desc())
                .limit(100)
            ).mappings()
            return [dict(row) for row in rows]

    def claim_job(self, lease_seconds=300, max_attempts=3):
        with self.session_factory() as session:
            expired = sa.and_(
                t.jobs.c.status == "running", t.jobs.c.lease_until < now()
            )
            session.execute(
                t.jobs.update()
                .where(expired, t.jobs.c.attempts >= max_attempts)
                .values(
                    status="failed",
                    error="Worker lease expired; retry extraction",
                    updated_at=now(),
                )
            )
            available = sa.or_(t.jobs.c.status == "queued", expired)
            row = (
                session.execute(
                    sa.select(t.jobs)
                    .where(available, t.jobs.c.attempts < max_attempts)
                    .order_by(t.jobs.c.updated_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if not row:
                session.commit()
                return None
            token = uuid4()
            values = dict(
                status="running",
                lease_token=token,
                lease_until=now() + timedelta(seconds=lease_seconds),
                attempts=row["attempts"] + 1,
                updated_at=now(),
            )
            changed = session.execute(
                t.jobs.update()
                .where(t.jobs.c.id == row["id"], available)
                .values(**values)
            )
            session.commit()
            return {**row, **values} if changed.rowcount else None

    def file_for_job(self, job):
        with self.session_factory() as session:
            file = (
                session.execute(
                    sa.select(Files.__table__).where(
                        Files.id == job["file_id"],
                        Files.collection_id == job["collection_id"],
                        Files.status == "completed",
                    )
                )
                .mappings()
                .first()
            )
            if not file:
                raise StaleJob("Source file no longer active")
            return dict(file)

    def checkpoint(self, job, checkpoint, lease_seconds=300):
        with self.session_factory() as session:
            changed = session.execute(
                t.jobs.update()
                .where(
                    t.jobs.c.id == job["id"],
                    t.jobs.c.status == "running",
                    t.jobs.c.lease_token == job["lease_token"],
                    t.jobs.c.lease_until >= now(),
                )
                .values(
                    checkpoint=checkpoint,
                    lease_until=now() + timedelta(seconds=lease_seconds),
                    updated_at=now(),
                )
            )
            session.commit()
            if not changed.rowcount:
                raise StaleJob("Extraction lease lost or job replaced")

    def fail(self, job, message):
        with self.session_factory() as session:
            session.execute(
                t.jobs.update()
                .where(
                    t.jobs.c.id == job["id"], t.jobs.c.lease_token == job["lease_token"]
                )
                .values(
                    status="failed",
                    error=message[:1000],
                    lease_token=None,
                    lease_until=None,
                    updated_at=now(),
                )
            )
            session.commit()

    def publish(self, job, content_hash, source_chunks, results, provenance):
        profile = KnowledgeProfile.model_validate(job["profile"])
        # Defense in depth: publication never trusts persisted model responses.
        if len(source_chunks) != len(results):
            raise ValueError("Incomplete extraction")
        for chunk, extraction in zip(source_chunks, results):
            validate_extraction(extraction, chunk, profile)
        with self.session_factory() as session:
            self._collection(session, job["collection_id"])
            file = session.execute(
                sa.select(Files.id)
                .where(
                    Files.id == job["file_id"],
                    Files.collection_id == job["collection_id"],
                    Files.status == "completed",
                )
                .with_for_update()
            ).first()
            current = (
                session.execute(
                    sa.select(t.jobs).where(t.jobs.c.id == job["id"]).with_for_update()
                )
                .mappings()
                .first()
            )
            revision = session.execute(
                sa.select(t.profiles.c.revision).where(
                    t.profiles.c.collection_id == job["collection_id"]
                )
            ).scalar_one_or_none()
            if (
                not file
                or not current
                or current["status"] != "running"
                or current["lease_token"] != job["lease_token"]
                or current["lease_until"] < now()
                or revision != job["schema_revision"]
            ):
                raise StaleJob(
                    "Source, profile, or extraction lease changed before publication"
                )
            session.execute(
                t.documents.delete().where(t.documents.c.file_id == job["file_id"])
            )
            session.execute(
                t.documents.insert().values(
                    file_id=job["file_id"],
                    collection_id=job["collection_id"],
                    run_id=job["id"],
                    schema_revision=revision,
                    content_hash=content_hash,
                    provenance=provenance,
                )
            )
            for chunk, extraction in zip(source_chunks, results):
                session.execute(
                    t.chunks.insert().values(
                        file_id=job["file_id"], **chunk.model_dump()
                    )
                )
                ids = {}
                for entity in extraction.entities:
                    key = entity_id(
                        job["collection_id"], job["file_id"], entity, profile
                    )
                    ids[entity.key] = key
                    if not session.execute(
                        sa.select(t.entities.c.id).where(t.entities.c.id == key)
                    ).first():
                        session.execute(
                            t.entities.insert().values(
                                id=key,
                                collection_id=job["collection_id"],
                                name=entity.name,
                                type=entity.type,
                            )
                        )
                    for alias in entity.aliases:
                        where = sa.and_(
                            t.aliases.c.entity_id == key,
                            t.aliases.c.file_id == job["file_id"],
                            t.aliases.c.name == alias,
                        )
                        if not session.execute(
                            sa.select(t.aliases).where(where)
                        ).first():
                            session.execute(
                                t.aliases.insert().values(
                                    entity_id=key, file_id=job["file_id"], name=alias
                                )
                            )
                for index, claim in enumerate(extraction.claims):
                    start = chunk.text.index(claim.evidence_quote)
                    session.execute(
                        t.claims.insert().values(
                            id=uuid5(job["id"], f"{chunk.id}:{index}"),
                            file_id=job["file_id"],
                            chunk_id=chunk.id,
                            subject_id=ids[claim.subject],
                            object_id=ids[claim.object],
                            predicate=claim.predicate,
                            statement=claim.statement,
                            qualifiers=claim.qualifiers.model_dump(),
                            quote=claim.evidence_quote,
                            quote_start=start,
                            quote_end=start + len(claim.evidence_quote),
                            status="pending",
                        )
                    )
            session.execute(
                t.jobs.update()
                .where(t.jobs.c.id == job["id"])
                .values(
                    status="completed",
                    checkpoint={},
                    error=None,
                    lease_token=None,
                    lease_until=None,
                    updated_at=now(),
                )
            )
            session.commit()

    def _active_claims(self, collection_id):
        subject, obj = t.entities.alias("subject"), t.entities.alias("object")
        return (
            sa.select(
                t.claims,
                t.chunks.c.text,
                t.chunks.c.page,
                t.chunks.c.section,
                Files.file_name,
                subject.c.name.label("subject_name"),
                obj.c.name.label("object_name"),
            )
            .select_from(
                t.claims.join(t.documents, t.documents.c.file_id == t.claims.c.file_id)
                .join(t.chunks, t.chunks.c.id == t.claims.c.chunk_id)
                .join(Files, Files.id == t.documents.c.file_id)
                .join(
                    t.profiles,
                    t.profiles.c.collection_id == t.documents.c.collection_id,
                )
                .join(subject, subject.c.id == t.claims.c.subject_id)
                .join(obj, obj.c.id == t.claims.c.object_id)
            )
            .where(
                t.documents.c.collection_id == collection_id,
                t.profiles.c.revision == t.documents.c.schema_revision,
                Files.collection_id == collection_id,
                Files.status == "completed",
            )
        )

    def list_claims(self, collection_id, status="pending", offset=0, limit=50):
        with self.session_factory() as session:
            query = self._active_claims(collection_id)
            if status:
                query = query.where(t.claims.c.status == status)
            return [
                dict(row)
                for row in session.execute(
                    query.order_by(t.claims.c.id).offset(offset).limit(limit)
                ).mappings()
            ]

    def review(self, collection_id, claim_id, status, reviewer_id, note=""):
        if status not in ("approved", "rejected"):
            raise ValueError("Invalid review decision")
        with self.session_factory() as session:
            self._collection(session, collection_id)
            row = session.execute(
                self._active_claims(collection_id).where(t.claims.c.id == claim_id)
            ).first()
            if not row:
                raise LookupError("Claim not found in the current collection version")
            session.execute(
                t.claims.update()
                .where(t.claims.c.id == claim_id)
                .values(
                    status=status,
                    reviewer_id=reviewer_id,
                    reviewed_at=now(),
                    review_note=note,
                )
            )
            session.commit()

    def retrieve(self, collection_id, question, seed_file_ids=(), hops=2, limit=8):
        if not self.get_profile(collection_id).enabled:
            return []
        normalized_question = normalize(question)
        with self.session_factory() as session:
            active = self._active_claims(collection_id).where(
                t.claims.c.status == "approved"
            )
            # Limit inspection to entities participating in visible, approved claims.
            base = active.subquery()
            visible = sa.union(
                sa.select(base.c.subject_id), sa.select(base.c.object_id)
            )
            names = sa.union(
                sa.select(t.entities.c.id, t.entities.c.name).where(
                    t.entities.c.id.in_(visible)
                ),
                sa.select(t.aliases.c.entity_id.label("id"), t.aliases.c.name).where(
                    t.aliases.c.entity_id.in_(visible),
                    t.aliases.c.file_id.in_(sa.select(base.c.file_id)),
                ),
            ).subquery()
            entity_rows = session.execute(
                sa.select(names).order_by(names.c.id, names.c.name).limit(2000)
            ).mappings()
            frontier = {
                row["id"]
                for row in entity_rows
                if re.search(
                    r"(?<!\w)" + re.escape(normalize(row["name"])) + r"(?!\w)",
                    normalized_question,
                )
            }
            if not frontier and seed_file_ids:
                seeds = session.execute(
                    active.where(t.claims.c.file_id.in_(list(seed_file_ids)[:10]))
                    .order_by(t.claims.c.id)
                    .limit(20)
                ).mappings()
                frontier = {
                    row[key] for row in seeds for key in ("subject_id", "object_id")
                }
            seen_entities, found = set(), {}
            for _ in range(min(max(hops, 1), 3)):
                if not frontier:
                    break
                rows = (
                    session.execute(
                        active.where(
                            sa.or_(
                                t.claims.c.subject_id.in_(frontier),
                                t.claims.c.object_id.in_(frontier),
                            )
                        )
                        .order_by(t.claims.c.id)
                        .limit(64)
                    )
                    .mappings()
                    .all()
                )
                seen_entities.update(frontier)
                frontier = set()
                for row in rows:
                    found.setdefault(row["id"], dict(row))
                    frontier.update(
                        {row["subject_id"], row["object_id"]} - seen_entities
                    )
            # Return candidates for downstream reranking; each carries original evidence.
            return list(found.values())[:limit]
