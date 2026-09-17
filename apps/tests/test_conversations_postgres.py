"""Opt-in history tests in disposable PostgreSQL schemas, including row locks."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.core.exceptions import ConflictError
from app.models.conversations import ConversationTurns
import test_conversations as fixtures


@unittest.skipUnless(
    os.environ.get("CHAT_TEST_DATABASE_URL"),
    "Set CHAT_TEST_DATABASE_URL to disposable PostgreSQL",
)
class HistoryPostgresTests(fixtures.HistoryRepositoryTests):
    def create_engine(self):
        url = sa.engine.make_url(os.environ["CHAT_TEST_DATABASE_URL"])
        if url.get_backend_name() != "postgresql":
            raise ValueError("CHAT_TEST_DATABASE_URL must reference PostgreSQL")
        schema = "chat_test_" + uuid4().hex
        admin = sa.create_engine(url)
        self.addCleanup(admin.dispose)
        with admin.begin() as conn:
            conn.execute(sa.schema.CreateSchema(schema))

        def cleanup_schema():
            with admin.begin() as conn:
                conn.execute(sa.schema.DropSchema(schema, cascade=True))

        self.addCleanup(cleanup_schema)
        self.engine = sa.create_engine(
            url,
            connect_args={
                "options": f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000",
            },
        )
        self.addCleanup(self.engine.dispose)
        config = Config()
        config.set_main_option(
            "script_location", str(Path(__file__).parents[1] / "migrations")
        )
        with self.engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")

    def test_simultaneous_questions_have_only_one_winner(self):
        barrier = Barrier(2)

        def submit(question_id):
            barrier.wait(timeout=5)
            try:
                self.start(question_id=question_id)
                return "started"
            except ConflictError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, ["first", "second"]))
        self.assertCountEqual(results, ["started", "conflict"])
        self.assertEqual(len(self.detail()["turns"]), 1)

    def test_completion_racing_delete_does_not_deadlock_or_recreate(self):
        turn = self.start()
        barrier = Barrier(2)

        def complete():
            barrier.wait(timeout=5)
            self.repo.finish_turn(turn, "Answer", "completed")

        def delete():
            barrier.wait(timeout=5)
            self.repo.delete(self.conversation, self.owner)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(complete), pool.submit(delete)]
            for future in futures:
                future.result(timeout=10)
        self.assertEqual(self.repo.list(self.owner, 0, 50)["total"], 0)
        with self.sessions() as session:
            self.assertEqual(session.query(ConversationTurns).count(), 0)


if __name__ == "__main__":
    unittest.main()
