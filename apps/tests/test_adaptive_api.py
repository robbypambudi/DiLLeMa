"""Real FastAPI dispatch/auth/validation plus the real bounded orchestrator."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from dependency_injector import providers
from fastapi.testclient import TestClient

from app.application import create_app
from app.api.v1.endpoints.answer import get_runtime, with_disconnect
from app.core.container import Container
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.services.adaptive.orchestrator import AdaptiveAnswerService
from app.services.adaptive.resilience import BoundedWorker
from tests.test_adaptive_rag import FakeGenerator, FakeRetriever, config, doc


class AdaptiveAPITests(unittest.TestCase):
    def setUp(self):
        self.container = Container()
        self.addCleanup(self.container.unwire)
        for name in ("db", "auth_service", "qdrant_client", "embedding_model"):
            getattr(self.container, name).override(providers.Object(Mock()))
        self.app = create_app(self.container)
        self.user = SimpleNamespace(id=uuid4(), role="user")
        self.collection_id = uuid4()
        self.collections, self.conversations = Mock(), Mock()
        self.collections.read_by_id.return_value = SimpleNamespace(
            vectordb_collection_name="resolved-physical-name"
        )
        self.conversations.answer_scope.return_value = {
            "collection_id": self.collection_id
        }
        self.cfg = config()
        self.service = AdaptiveAnswerService(self.cfg, FakeRetriever(), FakeGenerator())
        self.worker = BoundedWorker(2)
        self.addCleanup(self.worker.close)
        self.runtime = SimpleNamespace(
            config=self.cfg,
            service=self.service,
            db=self.worker,
            container=SimpleNamespace(
                collections_repository=lambda: self.collections,
                conversations_repository=lambda: self.conversations,
            ),
        )
        self.app.dependency_overrides[get_runtime] = lambda: self.runtime

    def login(self):
        self.app.dependency_overrides[get_current_user] = lambda: self.user

    def test_authentication_is_required(self):
        with TestClient(self.app) as client:
            result = client.post("/v1/answer", json={"query": "Write a thank you note"})
        self.assertEqual(result.status_code, 401)
        self.assertTrue(result.headers["X-Request-ID"])

    def test_rag_endpoint_returns_structured_answer(self):
        self.login()
        with TestClient(self.app) as client:
            result = client.post(
                "/v1/answer",
                json={
                    "query": "What is the policy deadline?",
                    "filters": {"collection_id": str(self.collection_id)},
                },
            )
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertEqual(body["strategy"], "rag")
        self.assertIn("14 May", body["answer"])
        self.assertEqual(body["metadata"]["request_id"], result.headers["X-Request-ID"])
        self.assertEqual(body["sources"][0]["id"], "S1")
        self.collections.read_by_id.assert_called_once_with(self.collection_id)

    def test_direct_endpoint_needs_no_collection(self):
        self.login()
        with TestClient(self.app) as client:
            result = client.post(
                "/v1/answer", json={"query": "Rewrite politely", "text": "send report"}
            )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["strategy"], "direct")
        self.collections.read_by_id.assert_not_called()

    def test_agentic_escalation_runs_end_to_end(self):
        self.login()
        self.service.retriever = FakeRetriever(
            [[doc("Policy exists.", 0.1)], [doc(identity="2")]]
        )
        with TestClient(self.app) as client:
            result = client.post(
                "/v1/answer",
                json={
                    "query": "What is the policy deadline?",
                    "filters": {"collection_id": str(self.collection_id)},
                },
            )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["strategy"], "agentic_rag")
        self.assertEqual(result.json()["metadata"]["retrieval_calls"], 2)

    def test_unknown_filters_cannot_be_silently_ignored(self):
        self.login()
        with TestClient(self.app) as client:
            result = client.post(
                "/v1/answer",
                json={"query": "policy?", "filters": {"tenant_id": "another-tenant"}},
            )
        self.assertEqual(result.status_code, 422)
        self.collections.read_by_id.assert_not_called()

    def test_conversation_scope_checks_owner_and_collection(self):
        self.login()
        conversation_id = uuid4()
        with TestClient(self.app) as client:
            result = client.post(
                "/v1/answer",
                json={
                    "query": "policy?",
                    "conversation_id": str(conversation_id),
                    "filters": {"collection_id": str(uuid4())},
                },
            )
        self.assertEqual(result.status_code, 422)
        self.conversations.answer_scope.assert_called_once_with(
            conversation_id, self.user.id
        )
        self.collections.read_by_id.assert_not_called()

    def test_another_users_conversation_stays_not_found(self):
        self.login()
        self.conversations.answer_scope.side_effect = NotFoundError(
            "Conversation not found"
        )
        with TestClient(self.app) as client:
            result = client.post(
                "/v1/answer", json={"query": "policy?", "conversation_id": str(uuid4())}
            )
        self.assertEqual(result.status_code, 404)

    def test_database_failure_is_sanitized(self):
        self.login()
        self.collections.read_by_id.side_effect = RuntimeError("password=secret")
        with TestClient(self.app) as client:
            result = client.post(
                "/v1/answer",
                json={
                    "query": "policy?",
                    "filters": {"collection_id": str(self.collection_id)},
                },
            )
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("secret", result.text)

    def test_metrics_require_admin_and_use_fixed_labels(self):
        self.login()
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/v1/metrics").status_code, 403)
            self.user.role = "admin"
            client.post("/v1/answer", json={"query": "Write a thank you note"})
            result = client.get("/v1/metrics")
        self.assertEqual(result.status_code, 200)
        self.assertIn('route="direct"', result.text)
        self.assertNotIn("thank you", result.text)


class DisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_cancels_the_operation(self):
        cancelled = asyncio.Event()

        async def operation():
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()

        async def disconnected():
            await asyncio.sleep(0.01)
            return True

        with self.assertRaises(asyncio.CancelledError):
            await with_disconnect(
                SimpleNamespace(is_disconnected=disconnected), operation(), 10
            )
        self.assertTrue(cancelled.is_set())


if __name__ == "__main__":
    unittest.main()
