"""Durable chat history, ownership, streaming failures and HTTP contracts."""

import asyncio
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import anyio
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from dependency_injector import providers
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_DB", "test")

from app.application import create_app
from app.core.container import Container
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import create_access_token
from app.models.collections import Collections
from app.models.conversations import Conversations, ConversationTurns, utcnow
from app.models.users import Users
from app.repositories.conversations_repository import ConversationsRepository
from app.repositories.users_repository import UsersRepository
from app.schema.question_schema import CreateQuestion
from app.services.question_service import QuestionsService


class HistoryFixture(unittest.TestCase):
    def create_engine(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.engine = sa.create_engine("sqlite:///" + temp.name + "/history.db")
        self.addCleanup(self.engine.dispose)

        @sa.event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        SQLModel.metadata.create_all(self.engine)

    def setUp(self):
        self.create_engine()
        self.owner, self.other, self.collection = uuid4(), uuid4(), uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                Users.__table__.insert(),
                [
                    {
                        "id": self.owner,
                        "email": "owner@example.test",
                        "password_hash": "unused",
                        "role": "user",
                    },
                    {
                        "id": self.other,
                        "email": "other@example.test",
                        "password_hash": "unused",
                        "role": "admin",
                    },
                ],
            )
            connection.execute(
                Collections.__table__.insert().values(
                    id=self.collection,
                    collection_name="Documents",
                    vectordb_collection_name="documents",
                )
            )

        @contextmanager
        def sessions():
            with Session(self.engine) as session:
                yield session

        self.sessions = sessions
        self.repo = ConversationsRepository(sessions)
        self.conversation = self.repo.create(self.owner, self.collection)["id"]
        self.payload = CreateQuestion(
            question_id="q1",
            question_text="What is the project?",
            collection_id=self.collection,
            conversation_id=self.conversation,
        )
        self.legacy = Mock()
        self.retrieval = Mock()
        self.retrieval.retrieve.return_value = [("context", "source")]
        self.chat = Mock()
        self.chat.chat.return_value = "The answer."
        self.chat.format_sources.return_value = "\nSource: document.pdf"
        self.chat.source_items.return_value = [
            {
                "index": 1,
                "file_id": "3f1f0d4c-6b3e-4a1c-9e2f-2f1d6b0a7c55",
                "file_name": "document.pdf",
                "pages": [4],
                "quote": "A cited sentence.",
                "snippets": [{"page": 4, "quote": "A cited sentence."}],
            }
        ]

        async def stream(**_):
            yield "The "
            yield "answer."

        self.chat.chat_with_stream = stream
        self.service = QuestionsService(
            self.legacy,
            Mock(),
            Mock(),
            Mock(),
            openai_chat=self.chat,
            retrieval_service=self.retrieval,
            conversations_repository=self.repo,
        )

    def start(self, **updates):
        return self.service.start_turn(
            self.payload.model_copy(update=updates), SimpleNamespace(id=self.owner)
        )

    def detail(self):
        return self.repo.get(self.conversation, self.owner)


class HistoryRepositoryTests(HistoryFixture):
    def test_reopen_persists_order_title_and_answer_across_repository_instances(self):
        first = self.start(question_text="  What\n is the project?  ")
        self.repo.finish_turn(first, "First answer", "completed")
        second = self.start(question_id="q2", question_text="Follow up")
        self.repo.finish_turn(second, "Second answer", "completed")
        saved = ConversationsRepository(self.sessions).get(
            self.conversation, self.owner
        )
        self.assertEqual(saved["title"], "What is the project?")
        self.assertEqual([turn["sequence"] for turn in saved["turns"]], [1, 2])
        self.assertEqual(
            [turn["answer"] for turn in saved["turns"]],
            ["First answer", "Second answer"],
        )
        self.assertEqual(self.repo.list(self.owner, 0, 1)["total"], 1)
        self.assertEqual(self.repo.list(self.owner, 1, 1)["data"], [])

    def test_another_owner_including_admin_cannot_read_write_or_delete(self):
        self.assertEqual(self.repo.list(self.other, 0, 50), {"data": [], "total": 0})
        for operation in (
            lambda: self.repo.get(self.conversation, self.other),
            lambda: self.repo.delete(self.conversation, self.other),
            lambda: self.repo.begin_turn(self.conversation, self.other, self.payload),
        ):
            with self.assertRaises(NotFoundError):
                operation()
        self.assertEqual(self.detail()["turns"], [])

    def test_duplicate_and_parallel_requests_do_not_add_turns(self):
        turn_id = self.start()
        with self.assertRaises(ConflictError):
            self.start(question_id="another")
        self.repo.finish_turn(turn_id, "Done", "completed")
        with self.assertRaises(ConflictError):
            self.start()
        self.assertEqual(len(self.detail()["turns"]), 1)

    def test_missing_or_mismatched_collection_is_rejected(self):
        with self.assertRaises(NotFoundError):
            self.repo.create(self.owner, uuid4())
        with self.assertRaises(ConflictError):
            self.start(collection_id=uuid4())

    def test_server_restart_expires_stale_turn_and_allows_next_question(self):
        first = self.start()
        with self.engine.begin() as conn:
            conn.execute(
                sa.update(ConversationTurns)
                .where(ConversationTurns.id == first)
                .values(updated_at=utcnow() - timedelta(minutes=11))
            )
        self.assertEqual(self.detail()["turns"][0]["status"], "interrupted")
        self.start(question_id="q2")
        self.assertEqual(len(self.detail()["turns"]), 2)

    def test_deleting_collection_preserves_readable_history(self):
        self.repo.finish_turn(self.start(), "Keep this answer", "completed")
        with self.engine.begin() as conn:
            conn.execute(
                sa.delete(Collections).where(Collections.id == self.collection)
            )
        saved = self.detail()
        self.assertIsNone(saved["collection_id"])
        self.assertEqual(saved["collection_name"], "Documents")
        self.assertEqual(saved["turns"][0]["answer"], "Keep this answer")
        with self.assertRaises(ConflictError):
            self.start(question_id="q2")

    def test_delete_removes_turns_and_late_completion_does_not_recreate(self):
        turn = self.start()
        self.repo.delete(self.conversation, self.owner)
        self.repo.finish_turn(turn, "Late answer", "completed")
        with self.sessions() as session:
            self.assertEqual(session.query(ConversationTurns).count(), 0)
        self.assertEqual(self.repo.list(self.owner, 0, 50)["total"], 0)


class HistoryGenerationTests(HistoryFixture):
    def test_sync_answer_is_saved_and_legacy_requests_still_work(self):
        answer = self.service.question_no_stream(self.payload, self.start())
        self.assertEqual(self.detail()["turns"][0]["answer"], answer.answer)
        self.legacy.create.assert_not_called()
        public = self.payload.model_copy(update={"conversation_id": None})
        self.assertIsNone(self.service.start_turn(public, None))
        self.service.question_no_stream(public)
        self.legacy.create.assert_called_once()

    def test_tracked_question_requires_authenticated_owner(self):
        with self.assertRaises(UnauthorizedError):
            self.service.start_turn(self.payload, None)
        self.assertEqual(self.detail()["turns"], [])

    def test_sync_failure_preserves_question_with_failed_status(self):
        turn = self.start()
        self.retrieval.retrieve.side_effect = RuntimeError("Retrieval failed")
        with self.assertRaises(RuntimeError):
            self.service.question_no_stream(self.payload, turn)
        self.assertEqual(self.detail()["turns"][0]["status"], "failed")

    def test_stream_saves_completed_answer_and_sources(self):
        turn = self.start()

        async def consume():
            return [
                item async for item in self.service.question_stream(self.payload, turn)
            ]

        events = asyncio.run(consume())
        chunks = [item["data"] for item in events if "event" not in item]
        cited = [item for item in events if item.get("event") == "sources"]
        saved = self.detail()["turns"][0]
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["answer"], "".join(chunks))
        # Citation metadata travels beside the answer, not inside it, so the
        # rendered source list is not repeated in the answer text.
        self.assertNotIn("Source: document.pdf", saved["answer"])
        self.assertNotIn("Sumber konteks", saved["answer"])
        self.assertEqual(
            json.loads(cited[0]["data"]), self.chat.source_items.return_value
        )
        self.assertEqual(saved["sources"], self.chat.source_items.return_value)

    def test_stream_falls_back_to_a_rendered_list_without_citation_metadata(self):
        self.chat.source_items.return_value = []
        turn = self.start()

        async def consume():
            return [
                item async for item in self.service.question_stream(self.payload, turn)
            ]

        events = asyncio.run(consume())
        saved = self.detail()["turns"][0]
        self.assertIn("Source: document.pdf", saved["answer"])
        self.assertEqual([item for item in events if "event" in item], [])

    def test_model_failure_keeps_partial_answer(self):
        async def failing(**_):
            yield "Partial answer"
            raise RuntimeError("Model unavailable")

        self.chat.chat_with_stream = failing
        turn = self.start()

        async def consume():
            return [
                item async for item in self.service.question_stream(self.payload, turn)
            ]

        asyncio.run(consume())
        saved = self.detail()["turns"][0]
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["answer"], "Partial answer")

    def test_disconnect_keeps_partial_answer(self):
        turn = self.start()

        async def disconnect():
            generator = self.service.question_stream(self.payload, turn)
            await anext(generator)
            await generator.aclose()

        asyncio.run(disconnect())
        saved = self.detail()["turns"][0]
        self.assertEqual((saved["status"], saved["answer"]), ("interrupted", "The "))

    def test_cancelled_request_shields_final_save(self):
        turn = self.start()

        async def cancel():
            with anyio.CancelScope() as scope:
                generator = self.service.question_stream(self.payload, turn)
                await anext(generator)
                scope.cancel()
                await generator.aclose()

        anyio.run(cancel)
        self.assertEqual(self.detail()["turns"][0]["status"], "interrupted")


class HistoryApiTests(HistoryFixture):
    def setUp(self):
        super().setUp()
        container = Container()
        self.addCleanup(container.unwire)
        for name, dependency in (
            ("db", Mock()),
            ("auth_service", Mock()),
            ("qdrant_client", Mock()),
            ("embedding_model", Mock()),
            ("conversations_repository", self.repo),
            ("users_repository", UsersRepository(self.sessions)),
            ("question_service", self.service),
        ):
            getattr(container, name).override(providers.Object(dependency))
        self.app = create_app(container)
        self.client = self.enterContext(TestClient(self.app))
        self.owner_headers = self.headers(self.owner, "user")

    @staticmethod
    def headers(user_id, role):
        return {
            "Authorization": "Bearer " + create_access_token(user_id=user_id, role=role)
        }

    def test_authentication_is_required_for_history_and_tracked_generation(self):
        self.assertEqual(self.client.get("/api/v1/conversations").status_code, 401)
        response = self.client.post(
            "/api/v1/questions/stream", data=self.payload.model_dump(mode="json")
        )
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.detail()["turns"], [])

    def test_create_stream_reopen_and_delete_as_regular_user(self):
        created = self.client.post(
            "/api/v1/conversations",
            json={"collection_id": str(self.collection)},
            headers=self.owner_headers,
        )
        self.assertEqual(created.status_code, 201, created.text)
        data = created.json()["data"]
        self.assertTrue(data["created_at"].endswith("+00:00"))
        conversation_id = data["id"]
        payload = self.payload.model_dump(mode="json") | {
            "conversation_id": conversation_id
        }
        response = self.client.post(
            "/api/v1/questions/stream", data=payload, headers=self.owner_headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn("data: The ", response.text)
        reopened = self.client.get(
            f"/api/v1/conversations/{conversation_id}", headers=self.owner_headers
        ).json()["data"]
        self.assertEqual(reopened["turns"][0]["status"], "completed")
        self.assertIn("The answer.", reopened["turns"][0]["answer"])
        listed = self.client.get(
            "/api/v1/conversations?limit=1", headers=self.owner_headers
        ).json()
        self.assertEqual(listed["total"], 2)
        self.assertEqual(listed["data"][0]["id"], conversation_id)
        self.assertEqual(
            self.client.delete(
                f"/api/v1/conversations/{conversation_id}", headers=self.owner_headers
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/conversations/{conversation_id}", headers=self.owner_headers
            ).status_code,
            404,
        )

    def test_ownership_errors_are_returned_before_stream_starts(self):
        headers = self.headers(self.other, "admin")
        self.assertEqual(
            self.client.get("/api/v1/conversations", headers=headers).json()["data"], []
        )
        path = f"/api/v1/conversations/{self.conversation}"
        self.assertEqual(self.client.get(path, headers=headers).status_code, 404)
        self.assertEqual(self.client.delete(path, headers=headers).status_code, 404)
        response = self.client.post(
            "/api/v1/questions/stream",
            data=self.payload.model_dump(mode="json"),
            headers=headers,
        )
        self.assertEqual(response.status_code, 404, response.text)
        self.assertNotIn("text/event-stream", response.headers["content-type"])

    def test_invalid_token_does_not_save_as_guest(self):
        response = self.client.post(
            "/api/v1/questions/stream",
            data=self.payload.model_dump(mode="json"),
            headers={"Authorization": "Bearer invalid"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.detail()["turns"], [])

    def test_duplicate_submission_returns_conflict_before_stream(self):
        self.start()
        response = self.client.post(
            "/api/v1/questions/stream",
            data=self.payload.model_dump(mode="json"),
            headers=self.owner_headers,
        )
        self.assertEqual(response.status_code, 409)


class HistoryMigrationTests(unittest.TestCase):
    def test_upgrade_and_downgrade_preserve_existing_tables(self):
        def load(name):
            path = Path(__file__).parents[1] / "migrations/versions" / name
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        # The tables are built by one revision and extended by the next; the
        # models must match the end of that chain, not its first step.
        chain = [
            load("c3d4e5f6a702_conversation_history.py"),
            load("d4e5f6a70311_turn_sources.py"),
        ]
        engine = sa.create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as conn:
            Users.__table__.create(conn)
            Collections.__table__.create(conn)
            owner = uuid4()
            conn.execute(
                Users.__table__.insert().values(
                    id=owner, email="keep@example.test", password_hash="unused"
                )
            )
            with Operations.context(MigrationContext.configure(conn)):
                for migration in chain:
                    migration.upgrade()
                for model in (Conversations, ConversationTurns):
                    self.assertEqual(
                        {
                            column["name"]
                            for column in sa.inspect(conn).get_columns(
                                model.__tablename__
                            )
                        },
                        set(model.__table__.columns.keys()),
                    )
                for migration in reversed(chain):
                    migration.downgrade()
                self.assertEqual(
                    set(sa.inspect(conn).get_table_names()), {"users", "collections"}
                )
                self.assertEqual(conn.execute(sa.select(Users.id)).scalar_one(), owner)


if __name__ == "__main__":
    unittest.main()
