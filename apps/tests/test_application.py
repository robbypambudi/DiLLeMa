"""HTTP compatibility and resource lifetime without external services or models."""

import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from dependency_injector import providers
from fastapi.testclient import TestClient

os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_DB", "test")

from app.application import create_app
from app.core.container import Container
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.container = Container()
        self.addCleanup(self.container.unwire)
        self.db = Mock()
        self.auth = Mock()
        self.collections = Mock()
        self.files = Mock()
        self.pipeline = Mock()
        for name, dependency in (
            ("db", self.db),
            ("auth_service", self.auth),
            ("collection_service", self.collections),
            ("files_service", self.files),
            ("pipeline_service", self.pipeline),
            ("qdrant_client", Mock()),
            ("embedding_model", Mock()),
        ):
            getattr(self.container, name).override(providers.Object(dependency))
        self.app = create_app(self.container)

    def test_startup_and_shutdown_manage_resources(self):
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.auth.seed_admin_if_empty.assert_called_once()
            self.db.close.assert_not_called()
        self.db.close.assert_called_once()

    def test_failed_startup_still_closes_database(self):
        self.auth.seed_admin_if_empty.side_effect = RuntimeError("startup failed")
        with self.assertRaisesRegex(RuntimeError, "startup failed"):
            with TestClient(self.app):
                pass
        self.db.close.assert_called_once()

    def test_public_list_runs_outside_event_loop_and_keeps_response_contract(self):
        thread_ids = {}

        @self.app.middleware("http")
        async def capture_event_loop(request, call_next):
            thread_ids["event_loop"] = threading.get_ident()
            return await call_next(request)

        def list_collections(_query):
            thread_ids["service"] = threading.get_ident()
            return {
                "data": [],
                "metadata": {"total_count": 0, "page": 1, "page_size": 100},
            }

        self.collections.list_collections.side_effect = list_collections
        with TestClient(self.app) as client:
            response = client.get("/api/v1/collection?page=1&page_size=100")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"], [])
        self.assertEqual(response.json()["status"], "success")
        self.assertNotEqual(thread_ids["event_loop"], thread_ids["service"])

    def test_collection_writes_require_an_admin(self):
        with TestClient(self.app) as client:
            self.assertEqual(
                client.post(
                    "/api/v1/collection", json={"collection_name": "test"}
                ).status_code,
                401,
            )
            self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
                id=uuid4(), role="user"
            )
            self.assertEqual(
                client.post(
                    "/api/v1/collection", json={"collection_name": "test"}
                ).status_code,
                403,
            )
        self.collections.create.assert_not_called()

    def test_validation_keeps_field_and_message_response(self):
        with TestClient(self.app) as client:
            response = client.post("/api/v1/auth/login", json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            {error["field"] for error in response.json()["errors"]},
            {"email", "password"},
        )
        self.auth.login.assert_not_called()

    def test_file_upload_dispatches_background_pipeline(self):
        collection_id = uuid4()
        document = SimpleNamespace(
            id=uuid4(),
            collection_id=collection_id,
            file_name="source.txt",
            file_type="text/plain",
            file_path="unused",
            file_size=7,
            status="pending",
            processing_started_at=None,
            processing_ended_at=None,
        )
        self.files.create.return_value = document
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=uuid4(), role="admin"
        )
        with TestClient(self.app) as client:
            response = client.post(
                "/api/v1/files",
                data={"collection_id": str(collection_id)},
                files={"file": ("source.txt", b"content", "text/plain")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["status"], "pending")
        self.pipeline.run_pipeline.assert_called_once_with(document)

    def test_cited_document_is_served_inline_for_the_source_panel(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "renstra.pdf"
        path.write_bytes(b"%PDF-1.7\nbody")
        file_id = uuid4()
        self.files.get_stored_file.return_value = SimpleNamespace(
            id=file_id,
            file_name="renstra.pdf",
            file_path=str(path),
            file_type="application/pdf",
        )
        with TestClient(self.app) as client:
            response = client.get(f"/api/v1/files/{file_id}/raw")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"%PDF-1.7\nbody")
        self.assertEqual(response.headers["content-type"], "application/pdf")
        # Inline, so the viewer renders it instead of the browser downloading it.
        self.assertIn("inline", response.headers["content-disposition"])
        self.files.get_stored_file.assert_called_once_with(file_id)

    def test_missing_cited_document_is_not_confused_with_its_metadata_route(self):
        self.files.get_stored_file.side_effect = NotFoundError(
            detail="The stored document is no longer available."
        )
        with TestClient(self.app) as client:
            response = client.get(f"/api/v1/files/{uuid4()}/raw")
        self.assertEqual(response.status_code, 404)
        self.files.get_by_id.assert_not_called()


if __name__ == "__main__":
    unittest.main()
