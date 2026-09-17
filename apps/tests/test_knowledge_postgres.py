"""Opt-in PostgreSQL tests. Every test owns a random schema in a test database."""

import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

import test_knowledge as fixtures
from app.models.collections import Collections
from app.models.files import Files
from app.models.users import Users
from knowledge import tables as t
from knowledge.contracts import KnowledgeProfile
from knowledge.documents import parse_document
from knowledge.repository import KnowledgeRepository, StaleJob


@unittest.skipUnless(
    os.environ.get("KG_TEST_DATABASE_URL"),
    "Set KG_TEST_DATABASE_URL to disposable PostgreSQL",
)
class PostgresTests(fixtures.DatabaseTests):
    """Run the persistence regressions plus real row-lock/concurrency checks."""

    def setUp(self):
        url = sa.engine.make_url(os.environ["KG_TEST_DATABASE_URL"])
        if url.get_backend_name() != "postgresql":
            raise ValueError("KG_TEST_DATABASE_URL must reference PostgreSQL")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.schema = "kg_test_" + uuid4().hex
        admin_engine = sa.create_engine(url)
        self.addCleanup(admin_engine.dispose)
        with admin_engine.begin() as connection:
            connection.execute(sa.schema.CreateSchema(self.schema))

        def drop_owned_schema():
            with admin_engine.begin() as connection:
                connection.execute(sa.schema.DropSchema(self.schema, cascade=True))

        self.addCleanup(drop_owned_schema)
        self.engine = sa.create_engine(
            url,
            connect_args={
                "options": f"-csearch_path={self.schema} -capplication_name={self.schema} -clock_timeout=10000 -cstatement_timeout=15000"
            },
        )
        self.addCleanup(self.engine.dispose)
        self.migration_config = Config()
        self.migration_config.set_main_option(
            "script_location", str(Path(__file__).parents[1] / "migrations")
        )
        with self.engine.begin() as connection:
            self.migration_config.attributes["connection"] = connection
            command.upgrade(self.migration_config, "head")
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
        # addCleanup also runs if setup or a test fails.
        pass

    def test_concurrent_workers_claim_only_once(self):
        self.repo.enqueue(self.collection, self.add_file())
        barrier = Barrier(2)

        def claim():
            barrier.wait(timeout=5)
            return self.repo.claim_job()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: claim(), range(2)))
        self.assertEqual(sum(row is not None for row in results), 1)

    def test_locked_job_is_skipped(self):
        first, second = self.add_file(), self.add_file()
        self.repo.enqueue(self.collection, first)
        self.repo.enqueue(self.collection, second)
        with self.engine.begin() as connection:
            connection.execute(
                sa.select(t.jobs).where(t.jobs.c.file_id == first).with_for_update()
            ).all()
            claimed = self.repo.claim_job()
            self.assertEqual(claimed["file_id"], second)

    def test_concurrent_publication_has_one_winner(self):
        file_id = self.add_file()
        self.repo.enqueue(self.collection, file_id)
        job = self.repo.claim_job()
        file = self.repo.file_for_job(job)
        fingerprint, chunks = parse_document(
            file["file_path"], file["file_type"], file_id
        )
        barrier = Barrier(2)

        def publish():
            barrier.wait(timeout=5)
            try:
                self.repo.publish(job, fingerprint, chunks, [fixtures.extraction()], {})
                return "published"
            except StaleJob:
                return "stale"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: publish(), range(2)))
        self.assertCountEqual(results, ["published", "stale"])
        self.assertEqual(len(self.repo.list_claims(self.collection)), 1)

    def test_concurrent_enqueue_reuses_one_generation(self):
        file_id = self.add_file()
        barrier = Barrier(2)

        def enqueue():
            barrier.wait(timeout=5)
            return self.repo.enqueue(self.collection, file_id)["id"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: enqueue(), range(2)))
        self.assertEqual(results[0], results[1])

    def publish_after_locked_change(self, change):
        file_id = self.add_file()
        self.repo.enqueue(self.collection, file_id)
        job = self.repo.claim_job()
        file = self.repo.file_for_job(job)
        fingerprint, chunks = parse_document(
            file["file_path"], file["file_type"], file_id
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.engine.begin() as connection:
                change(connection, file_id)
                future = pool.submit(
                    self.repo.publish,
                    job,
                    fingerprint,
                    chunks,
                    [fixtures.extraction()],
                    {},
                )
                # Observe actual PostgreSQL contention before committing the change.
                with self.engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as monitor:
                    deadline = time.monotonic() + 5
                    while not monitor.execute(
                        sa.text(
                            "SELECT count(*) FROM pg_stat_activity WHERE application_name=:name AND pid <> pg_backend_pid() AND wait_event_type='Lock'"
                        ),
                        {"name": self.schema},
                    ).scalar_one():
                        if future.done() or time.monotonic() >= deadline:
                            self.fail("Publisher did not reach the expected row lock")
                        time.sleep(0.02)
            with self.assertRaises(StaleJob):
                future.result(timeout=10)
        self.assertEqual(self.repo.list_claims(self.collection), [])

    def test_delete_race_fences_waiting_publisher(self):
        self.publish_after_locked_change(
            lambda connection, file_id: connection.execute(
                Files.__table__.delete().where(Files.id == file_id)
            )
        )

    def test_schema_race_fences_waiting_publisher(self):
        def change(connection, file_id):
            connection.execute(
                sa.select(Collections.id)
                .where(Collections.id == self.collection)
                .with_for_update()
            ).all()
            revised = self.profile.model_copy(
                update={"instructions": "Updated while publishing"}
            )
            connection.execute(
                t.profiles.update()
                .where(t.profiles.c.collection_id == self.collection)
                .values(revision=revised.revision, config=revised.model_dump())
            )

        self.publish_after_locked_change(change)

    def test_graph_migration_round_trip_on_postgres(self):
        with self.engine.begin() as connection:
            self.migration_config.attributes["connection"] = connection
            command.downgrade(self.migration_config, "a1b2c3d4e5f6")
            names = sa.inspect(connection).get_table_names(schema=self.schema)
            self.assertFalse(any(table.name in names for table in t.TABLES))
            command.upgrade(self.migration_config, "head")
            names = sa.inspect(connection).get_table_names(schema=self.schema)
            self.assertTrue(all(table.name in names for table in t.TABLES))


if __name__ == "__main__":
    unittest.main()
