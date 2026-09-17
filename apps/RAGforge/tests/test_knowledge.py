"""Offline integration coverage: real SQL transactions, fake model boundary only."""

import importlib.util
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_DB", "test")

from app.models.collections import Collections
from app.models.files import Files
from app.models.questions import Questions  # Register relationship metadata.
from app.models.users import Users
from knowledge import tables as t
from knowledge.contracts import (
    Claim,
    Entity,
    Extraction,
    KnowledgeProfile,
    Qualifiers,
    SourceChunk,
    entity_id,
    validate_extraction,
)
from knowledge.documents import (
    chunk_sections,
    chunks_fingerprint,
    markdown_sections,
    parse_document,
    read_sections,
)
from knowledge.extraction import ExtractionFailure, KnowledgeExtractor
from knowledge.smoke import check_expectations
from knowledge.repository import KnowledgeRepository, StaleJob, now
from knowledge.worker import KnowledgeWorker


TEXT = "Program A dikelola Organisasi B. Berlaku untuk mahasiswa reguler mulai 2026."


def extraction(text=TEXT, program="Program A"):
    return Extraction(
        entities=[
            Entity(key="p", name=program, type="Program", mention=program),
            Entity(
                key="o",
                name="Organisasi B",
                type="Organization",
                mention="Organisasi B",
            ),
        ],
        claims=[
            Claim(
                subject="p",
                predicate="MANAGED_BY",
                object="o",
                statement=f"{program} dikelola Organisasi B.",
                evidence_quote=text,
                qualifiers=Qualifiers(
                    actor_scope="mahasiswa reguler", valid_from="2026"
                ),
            )
        ],
    )


class FakeExtractor:
    model = "offline-fixture"
    max_tokens = 4096

    def extract(self, chunk, profile):
        program = "Program C" if "Program C" in chunk.text else "Program A"
        return extraction(chunk.text, program)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.profile = KnowledgeProfile(enabled=True)
        self.chunk = SourceChunk(
            id=uuid4(), text=TEXT, page=1, ordinal=0, start=0, end=len(TEXT)
        )

    def test_evidence_and_qualifiers_are_preserved(self):
        result = extraction()
        validate_extraction(result, self.chunk, self.profile)
        self.assertEqual(result.claims[0].qualifiers.actor_scope, "mahasiswa reguler")

    def test_fabricated_quote_rejected(self):
        result = extraction()
        result.claims[0].evidence_quote = "Semua mahasiswa wajib magang."
        with self.assertRaises(ValueError):
            validate_extraction(result, self.chunk, self.profile)

    def test_wrong_relation_endpoint_rejected(self):
        result = extraction()
        result.entities[0].type = "Person"
        with self.assertRaises(ValueError):
            validate_extraction(result, self.chunk, self.profile)

    def test_unknown_reference_rejected(self):
        result = extraction()
        result.claims[0].subject = "missing"
        with self.assertRaises(ValueError):
            validate_extraction(result, self.chunk, self.profile)

    def test_duplicate_keys_and_invented_alias_rejected(self):
        for mutate in (
            lambda r: r.entities.append(r.entities[0]),
            lambda r: r.entities[0].aliases.append("Unmentioned alias"),
        ):
            result = extraction()
            mutate(result)
            with self.assertRaises(ValueError):
                validate_extraction(result, self.chunk, self.profile)

    def test_name_merging_is_opt_in_and_scoped(self):
        collection, first, second = uuid4(), uuid4(), uuid4()
        entity = extraction().entities[0]
        self.assertNotEqual(
            entity_id(collection, first, entity, self.profile),
            entity_id(collection, second, entity, self.profile),
        )
        self.profile.merge_by_name = ["Program"]
        self.assertEqual(
            entity_id(collection, first, entity, self.profile),
            entity_id(collection, second, entity, self.profile),
        )
        self.assertNotEqual(
            entity_id(collection, first, entity, self.profile),
            entity_id(uuid4(), first, entity, self.profile),
        )
        with self.assertRaises(ValueError):
            KnowledgeProfile(merge_by_name=["Person"])

    def test_schema_revision_is_deterministic(self):
        self.assertEqual(
            self.profile.revision,
            KnowledgeProfile.model_validate(self.profile.model_dump()).revision,
        )
        changed = self.profile.model_copy(
            update={"instructions": "Different extraction policy"}
        )
        self.assertNotEqual(changed.revision, self.profile.revision)

    def test_chunk_boundaries_preserve_original_text_and_page(self):
        file_id = uuid4()
        text = "Program A membutuhkan data.\n" * 30
        chunks = chunk_sections(
            [(1, "", text), (2, "", TEXT)], file_id, "hash", size=200, overlap=30
        )
        for chunk in chunks:
            source = text if chunk.page == 1 else TEXT
            self.assertEqual(source[chunk.start : chunk.end], chunk.text)
        self.assertEqual(chunks[-1].page, 2)
        self.assertEqual(
            chunks,
            chunk_sections(
                [(1, "", text), (2, "", TEXT)], file_id, "hash", size=200, overlap=30
            ),
        )

    def test_scanned_pdf_fails_explicitly(self):
        with patch(
            "pypdf.PdfReader",
            return_value=SimpleNamespace(pages=[Mock(extract_text=lambda: "")]),
        ):
            with self.assertRaisesRegex(ValueError, "OCR"):
                read_sections("test.pdf", "application/pdf")

    def test_markdown_heading_context_and_code_fences(self):
        text = "Intro\n# Program A\nInfo\n## Syarat\n80 SKS\n```text\n# Not a heading\n```\n## Jadwal\n2026\n"
        sections = markdown_sections(text)
        self.assertEqual("".join(row[2] for row in sections), text)
        self.assertEqual(
            [row[1] for row in sections],
            ["", "Program A", "Program A / Syarat", "Program A / Jadwal"],
        )
        self.assertIn("# Not a heading", sections[2][2])

    def test_parsed_text_and_location_changes_invalidate_chunk_identity(self):
        file_id = uuid4()
        first = chunk_sections([(1, "Syarat", "80 SKS")], file_id, "same-source")
        second = chunk_sections([(1, "Syarat", "90 SKS")], file_id, "same-source")
        third = chunk_sections([(2, "Syarat", "80 SKS")], file_id, "same-source")
        self.assertNotEqual(first[0].id, second[0].id)
        self.assertNotEqual(first[0].id, third[0].id)
        self.assertNotEqual(chunks_fingerprint(first), chunks_fingerprint(second))

    def test_extractor_repairs_once_and_validates(self):
        client = Mock()

        def response(content):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop", message=SimpleNamespace(content=content)
                    )
                ]
            )

        client.chat.completions.create.side_effect = [
            response('{"wrong":true}'),
            response(extraction().model_dump_json()),
        ]
        result = KnowledgeExtractor(client, "model").extract(self.chunk, self.profile)
        self.assertEqual(len(result.claims), 1)
        self.assertEqual(client.chat.completions.create.call_count, 2)
        repair = client.chat.completions.create.call_args.kwargs["messages"][-1][
            "content"
        ]
        self.assertIn("extra_forbidden", repair)

    def test_failed_repair_has_local_diagnostics_but_safe_public_error(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content='{"private_source":"sensitive"}'),
                )
            ]
        )
        with self.assertRaises(ExtractionFailure) as caught:
            KnowledgeExtractor(client, "model").extract(self.chunk, self.profile)
        self.assertNotIn("sensitive", str(caught.exception))
        self.assertEqual(len(caught.exception.attempts), 2)
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_smoke_detects_missing_relations_and_qualifiers(self):
        rows = [{"extraction": extraction().model_dump()}]
        expected = [
            {
                "id": "manager",
                "subject": "Program A",
                "predicate": "MANAGED_BY",
                "object_contains": "Organisasi B",
                "qualifiers": {"actor_scope": "mahasiswa reguler"},
            }
        ]
        self.assertTrue(check_expectations(rows, expected)["passed"])
        expected[0]["qualifiers"]["valid_from"] = "2027"
        self.assertFalse(check_expectations(rows, expected)["passed"])
        expected[0]["predicate"] = "REQUIRES"
        self.assertFalse(check_expectations(rows, expected)["checks"][0]["claim_found"])

    def test_truncated_model_output_is_not_published(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="length")]
        )
        with self.assertRaisesRegex(ValueError, "incomplete"):
            KnowledgeExtractor(client, "model").extract(self.chunk, self.profile)

    def test_structured_output_uses_ontology_and_still_validates_source(self):
        client = Mock()
        invalid = extraction()
        invalid.claims[0].evidence_quote = "Invented quotation."
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=invalid.model_dump_json()),
                )
            ]
        )
        with self.assertRaises(ExtractionFailure):
            KnowledgeExtractor(client, "model", output_format="json_schema").extract(
                self.chunk, self.profile
            )
        schema = client.chat.completions.create.call_args.kwargs["response_format"][
            "json_schema"
        ]["schema"]
        self.assertEqual(
            schema["$defs"]["Entity"]["properties"]["type"]["enum"],
            self.profile.entity_types,
        )
        self.assertEqual(
            schema["$defs"]["Claim"]["properties"]["predicate"]["enum"],
            [r.name for r in self.profile.relations],
        )


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = sa.create_engine("sqlite:///" + self.temp.name + "/test.db")

        @sa.event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        t.metadata.create_all(self.engine)
        self.collection, self.admin = uuid4(), uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                Collections.__table__.insert().values(
                    id=self.collection,
                    collection_name="Pilot",
                    vectordb_collection_name="pilot",
                )
            )
            connection.execute(
                Users.__table__.insert().values(
                    id=self.admin,
                    email="review@example.test",
                    password_hash="unused",
                    role="admin",
                )
            )

        @contextmanager
        def sessions():
            with Session(self.engine) as session:
                yield session

        self.repo = KnowledgeRepository(sessions)
        self.profile = KnowledgeProfile(
            enabled=True, merge_by_name=["Program", "Organization"]
        )
        self.repo.save_profile(self.collection, self.profile)

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def add_file(self, text=TEXT, collection=None):
        file_id = uuid4()
        path = Path(self.temp.name) / f"{file_id}.txt"
        path.write_text(text)
        with self.engine.begin() as conn:
            conn.execute(
                Files.__table__.insert().values(
                    id=file_id,
                    collection_id=collection or self.collection,
                    file_name="fixture.txt",
                    file_path=str(path),
                    file_type="text/plain",
                    file_size=len(text),
                    status="completed",
                )
            )
        return file_id

    def process(self, file_id, extractor=None):
        self.repo.enqueue(self.collection, file_id)
        return KnowledgeWorker(self.repo, extractor or FakeExtractor()).process_next()

    def approve_all(self):
        for claim in self.repo.list_claims(self.collection):
            self.repo.review(self.collection, claim["id"], "approved", self.admin)

    def test_persistent_worker_and_review_gate(self):
        file_id = self.add_file()
        self.assertEqual(self.process(file_id), "completed")
        self.assertEqual(self.repo.retrieve(self.collection, "Program A"), [])
        self.approve_all()
        found = self.repo.retrieve(self.collection, "Program A")
        self.assertEqual(len(found), 1)
        row = found[0]
        self.assertEqual(
            row["text"][row["quote_start"] : row["quote_end"]], row["quote"]
        )
        self.assertEqual(self.repo.list_jobs(self.collection)[0]["status"], "completed")

    def test_multi_hop_across_documents(self):
        self.process(self.add_file())
        self.process(self.add_file(TEXT.replace("Program A", "Program C")))
        self.approve_all()
        self.assertEqual(
            len(self.repo.retrieve(self.collection, "Program A", hops=1)), 1
        )
        self.assertEqual(
            len(self.repo.retrieve(self.collection, "Program A", hops=2)), 2
        )

    def test_cross_collection_never_leaks_even_with_seed_file(self):
        file_id = self.add_file()
        self.process(file_id)
        self.approve_all()
        other = uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                Collections.__table__.insert().values(
                    id=other, collection_name="Other", vectordb_collection_name="other"
                )
            )
        self.repo.save_profile(other, self.profile)
        self.assertEqual(self.repo.retrieve(other, "Program A", [file_id]), [])
        claim = self.repo.list_claims(self.collection, "approved")[0]
        with self.assertRaises(LookupError):
            self.repo.review(other, claim["id"], "approved", self.admin)
        with self.assertRaises(LookupError):
            self.repo.enqueue(other, file_id)

    def test_delete_cascades_jobs_claims_and_evidence(self):
        file_id = self.add_file()
        self.process(file_id)
        self.approve_all()
        with self.engine.begin() as conn:
            conn.execute(Files.__table__.delete().where(Files.id == file_id))
        self.assertEqual(self.repo.retrieve(self.collection, "Program A"), [])
        with self.engine.connect() as conn:
            for table in (t.jobs, t.documents, t.chunks, t.claims):
                self.assertEqual(
                    conn.execute(
                        sa.select(sa.func.count()).select_from(table)
                    ).scalar(),
                    0,
                )

    def test_collection_deletion_and_shared_entity_support(self):
        first, second = self.add_file(), self.add_file()
        self.process(first)
        self.process(second)
        self.approve_all()
        with self.engine.begin() as conn:
            conn.execute(Files.__table__.delete().where(Files.id == first))
        self.assertEqual(len(self.repo.retrieve(self.collection, "Program A")), 1)
        with self.engine.begin() as conn:
            conn.execute(Files.__table__.delete().where(Files.id == second))
            conn.execute(
                Collections.__table__.delete().where(Collections.id == self.collection)
            )
        with self.engine.connect() as conn:
            for table in t.TABLES:
                self.assertEqual(
                    conn.execute(
                        sa.select(sa.func.count()).select_from(table)
                    ).scalar(),
                    0,
                )

    def test_schema_change_hides_previous_graph(self):
        self.process(self.add_file())
        self.approve_all()
        self.profile.instructions = "A new ontology instruction"
        self.repo.save_profile(self.collection, self.profile)
        self.assertEqual(self.repo.retrieve(self.collection, "Program A"), [])

    def test_queue_is_idempotent_and_lease_prevents_double_work(self):
        file_id = self.add_file()
        first = self.repo.enqueue(self.collection, file_id)
        self.assertEqual(first["id"], self.repo.enqueue(self.collection, file_id)["id"])
        self.assertIsNotNone(self.repo.claim_job())
        self.assertIsNone(self.repo.claim_job())

    def test_stale_worker_cannot_publish(self):
        file_id = self.add_file()
        self.repo.enqueue(self.collection, file_id)
        job = self.repo.claim_job()
        with self.engine.begin() as conn:
            conn.execute(
                t.jobs.update().values(lease_until=now() - timedelta(seconds=1))
            )
        self.repo.claim_job()
        file = self.repo.file_for_job(job)
        fingerprint, chunks = parse_document(
            file["file_path"], file["file_type"], file_id
        )
        with self.assertRaises(StaleJob):
            self.repo.publish(job, fingerprint, chunks, [extraction()], {})
        self.assertEqual(self.repo.list_claims(self.collection), [])

    def test_deleted_file_cannot_be_republished(self):
        file_id = self.add_file()
        self.repo.enqueue(self.collection, file_id)
        job = self.repo.claim_job()
        file = self.repo.file_for_job(job)
        fingerprint, chunks = parse_document(
            file["file_path"], file["file_type"], file_id
        )
        with self.engine.begin() as conn:
            conn.execute(Files.__table__.delete().where(Files.id == file_id))
        with self.assertRaises(StaleJob):
            self.repo.publish(job, fingerprint, chunks, [extraction()], {})

    def test_invalid_new_extraction_keeps_previous_graph(self):
        file_id = self.add_file()
        self.process(file_id)
        self.approve_all()
        invalid = FakeExtractor()
        invalid.extract = lambda *_: Extraction(entities=[], claims=extraction().claims)
        self.assertEqual(self.process(file_id, invalid), "failed")
        self.assertEqual(len(self.repo.retrieve(self.collection, "Program A")), 1)

    def test_reextraction_replaces_claims_and_resets_review(self):
        file_id = self.add_file()
        self.process(file_id)
        old_id = self.repo.list_claims(self.collection)[0]["id"]
        self.approve_all()
        self.process(file_id)
        self.assertEqual(len(self.repo.list_claims(self.collection)), 1)
        self.assertNotEqual(old_id, self.repo.list_claims(self.collection)[0]["id"])
        self.assertEqual(self.repo.retrieve(self.collection, "Program A"), [])

    def test_interrupted_worker_resumes_checkpoint(self):
        file_id = self.add_file((TEXT + "\n") * 100)
        self.repo.enqueue(self.collection, file_id)
        fake = FakeExtractor()
        calls = []

        def interrupted(chunk, profile):
            calls.append(chunk.id)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return Extraction()

        fake.extract = interrupted
        with self.assertRaises(KeyboardInterrupt):
            KnowledgeWorker(self.repo, fake).process_next()
        with self.engine.begin() as conn:
            conn.execute(
                t.jobs.update().values(lease_until=now() - timedelta(seconds=1))
            )
        resumed = []
        fake.extract = lambda chunk, profile: (resumed.append(chunk.id) or Extraction())
        self.assertEqual(KnowledgeWorker(self.repo, fake).process_next(), "completed")
        self.assertNotIn(calls[0], resumed)
        self.assertIn(calls[1], resumed)

    def test_archived_source_is_not_retrievable(self):
        file_id = self.add_file()
        self.process(file_id)
        self.approve_all()
        with self.engine.begin() as conn:
            conn.execute(
                Files.__table__.update()
                .where(Files.id == file_id)
                .values(status="archived")
            )
        self.assertEqual(self.repo.retrieve(self.collection, "Program A"), [])

    def test_parser_upgrade_invalidates_interrupted_checkpoint(self):
        file_id = self.add_file((TEXT + "\n") * 100)
        self.repo.enqueue(self.collection, file_id)
        fake, calls = FakeExtractor(), []

        def interrupted(chunk, profile):
            calls.append(chunk.id)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return Extraction()

        fake.extract = interrupted
        with self.assertRaises(KeyboardInterrupt):
            KnowledgeWorker(self.repo, fake).process_next()
        with self.engine.begin() as conn:
            conn.execute(
                t.jobs.update().values(lease_until=now() - timedelta(seconds=1))
            )
        resumed = []
        fake.extract = lambda chunk, profile: (resumed.append(chunk.id) or Extraction())
        with patch(
            "knowledge.worker.parser_provenance", return_value={"version": "new-parser"}
        ):
            self.assertEqual(
                KnowledgeWorker(self.repo, fake).process_next(), "completed"
            )
        self.assertIn(calls[0], resumed)

    def test_source_alias_can_seed_graph_and_is_removed_with_source(self):
        text = "Program A (PA) dikelola Organisasi B."
        file_id = self.add_file(text)
        fake = FakeExtractor()
        result = extraction(text)
        result.entities[0].aliases = ["PA"]
        fake.extract = lambda *_: result
        self.assertEqual(self.process(file_id, fake), "completed")
        self.approve_all()
        self.assertEqual(
            len(self.repo.retrieve(self.collection, "Siapa pengelola PA?")), 1
        )
        with self.engine.begin() as conn:
            conn.execute(Files.__table__.delete().where(Files.id == file_id))
        self.assertEqual(self.repo.retrieve(self.collection, "PA"), [])
        with self.engine.connect() as conn:
            self.assertEqual(
                conn.execute(
                    sa.select(sa.func.count()).select_from(t.aliases)
                ).scalar(),
                0,
            )

    def test_changed_schema_fences_running_worker(self):
        file_id = self.add_file()
        self.repo.enqueue(self.collection, file_id)
        job = self.repo.claim_job()
        file = self.repo.file_for_job(job)
        fingerprint, chunks = parse_document(
            file["file_path"], file["file_type"], file_id
        )
        self.profile.instructions = "Updated policy"
        self.repo.save_profile(self.collection, self.profile)
        with self.assertRaises(StaleJob):
            self.repo.publish(job, fingerprint, chunks, [extraction()], {})


class MigrationTests(unittest.TestCase):
    def test_frozen_migration_upgrade_and_downgrade(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        path = (
            Path(__file__).parents[1]
            / "migrations/versions/b2d3e4f5a601_knowledge_graph.py"
        )
        spec = importlib.util.spec_from_file_location("kg_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            for name in ("collections", "files", "users"):
                migration.metadata.tables[name].create(conn)
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
                names = sa.inspect(conn).get_table_names()
                self.assertTrue(all(table.name in names for table in t.TABLES))
                for live, frozen in zip(t.TABLES, migration.TABLES):
                    self.assertEqual(list(live.c.keys()), list(frozen.c.keys()))
                migration.downgrade()
                self.assertEqual(
                    set(sa.inspect(conn).get_table_names()),
                    {"collections", "files", "users"},
                )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
