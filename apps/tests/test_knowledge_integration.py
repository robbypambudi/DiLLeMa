import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import test_knowledge as fixtures
from test_knowledge import TEXT


class KnowledgeApiTests(unittest.TestCase):
    add_file = fixtures.DatabaseTests.add_file
    process = fixtures.DatabaseTests.process

    def setUp(self):
        fixtures.DatabaseTests.setUp(self)
        from dependency_injector import providers
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.endpoints.knowledge import router
        from app.core.config import settings
        from app.core.container import Container
        from app.core.dependencies import get_current_user

        self.settings = patch.object(settings, "KG_ENABLED", True)
        self.settings.start()
        self.container = Container()
        self.container.knowledge_repository.override(providers.Object(self.repo))
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        self.user_dependency = get_current_user
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=self.admin, role="admin"
        )
        self.client = TestClient(self.app)
        self.base = f"/api/v1/knowledge/{self.collection}"

    def tearDown(self):
        self.client.close()
        self.container.unwire()
        self.settings.stop()
        fixtures.DatabaseTests.tearDown(self)

    def test_api_enqueue_review_and_graph(self):
        file_id = self.add_file()
        response = self.client.post(f"{self.base}/files/{file_id}/extract")
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(self.process(file_id), "completed")
        claims = self.client.get(f"{self.base}/claims").json()["data"]
        self.assertEqual(len(claims), 1)
        self.assertEqual(self.client.get(f"{self.base}/graph").json()["edges"], [])
        response = self.client.patch(
            f"{self.base}/claims/{claims[0]['id']}", json={"status": "approved"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        graph = self.client.get(f"{self.base}/graph").json()
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(graph["edges"][0]["quote"], TEXT)

    def test_non_admin_cannot_modify_knowledge(self):
        self.app.dependency_overrides[self.user_dependency] = lambda: SimpleNamespace(
            id=self.admin, role="user"
        )
        response = self.client.put(
            f"{self.base}/profile", json=self.profile.model_dump()
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_schema_is_rejected(self):
        payload = self.profile.model_dump()
        payload["relations"][0]["subject_types"] = ["DoesNotExist"]
        self.assertEqual(
            self.client.put(f"{self.base}/profile", json=payload).status_code, 422
        )

    def test_feature_disabled_does_not_query_new_tables(self):
        from app.core.config import settings

        with (
            patch.object(settings, "KG_ENABLED", False),
            patch.object(
                self.repo, "get_profile", side_effect=AssertionError("must not query")
            ),
        ):
            response = self.client.get(f"{self.base}/profile")
            self.assertFalse(response.json()["available"])
            self.assertEqual(
                self.client.post(f"{self.base}/files/{uuid4()}/extract").status_code,
                503,
            )


class QuestionIntegrationTests(unittest.TestCase):
    def setUp(self):
        from app.services.question_service import QuestionsService
        from app.schema.question_schema import CreateQuestion
        from rag.llm.chat_model import OpenAIChat

        self.payload = CreateQuestion(
            question_id="test",
            question_text="Program A",
            collection_id=uuid4(),
            using_augment_query=False,
        )
        self.questions = Mock()
        self.questions.create.side_effect = lambda question: question
        self.collection = Mock()
        self.collection.read_by_id.return_value = SimpleNamespace(
            vectordb_collection_name="pilot"
        )
        self.vectors = Mock()
        self.vectors.search.return_value = [
            SimpleNamespace(
                id=1,
                score=0.9,
                payload={
                    "document": "Program A",
                    "file_name": "source.txt",
                    "file_id": str(uuid4()),
                },
            )
        ]
        self.vectors.client.search.return_value = self.vectors.search.return_value
        self.embedding = Mock()
        self.embedding.encode.return_value = SimpleNamespace(tolist=lambda: [0.1])
        self.reranker = Mock()
        self.reranker.rank.side_effect = (
            lambda pairs, top_results, min_score=None: pairs[:top_results]
        )
        self.chat = Mock()
        self.chat.format_sources = OpenAIChat.format_sources
        self.chat.source_items = OpenAIChat.source_items
        self.chat.chat.return_value = "Jawaban [S1]"

        async def stream(**_):
            yield "Jawaban "
            yield "[S1]"

        self.chat.chat_with_stream = stream
        self.graph = Mock()
        self.graph.retrieve.return_value = []
        self.service = QuestionsService(
            self.questions,
            self.collection,
            self.vectors,
            Mock(),
            self.graph,
            self.embedding,
            self.reranker,
            self.chat,
        )

    def test_stream_saved_answer_equals_sent_content(self):
        from app.core.config import settings

        cited = []

        async def collect():
            text = []
            async for item in self.service.question_stream(self.payload):
                (cited if item.get("event") == "sources" else text).append(item["data"])
            return "".join(text)

        with patch.object(settings, "KG_ENABLED", False):
            answer = asyncio.run(collect())
        self.assertEqual(self.questions.create.call_args.args[0].answer, answer)
        self.assertIn("Jawaban [S1]", answer)
        # The file reaches the client as citation metadata, not as answer text.
        self.assertNotIn("source.txt", answer)
        self.assertEqual(json.loads(cited[0])[0]["file_name"], "source.txt")

    def test_graph_evidence_reaches_generation_with_qualifiers(self):
        from app.core.config import settings

        self.graph.retrieve.return_value = [
            {
                "id": uuid4(),
                "statement": "A rule",
                "qualifiers": {"negated": True},
                "quote": TEXT,
                "text": TEXT,
                "page": 3,
                "file_name": "rules.pdf",
            }
        ]
        # Only sources the answer cites are reported, so the claim has to be
        # the one the answer points at.
        self.chat.chat.return_value = "Jawaban [S1] dan aturannya [S2]"
        with patch.object(settings, "KG_ENABLED", True):
            result = self.service.question_no_stream(self.payload)
        pairs = self.chat.chat.call_args.kwargs["context_pairs"]
        self.assertIn('"negated": true', pairs[1][1])
        self.assertEqual(pairs[1][2]["page"], 3)
        self.assertIn("rules.pdf, halaman 3", result.answer)

    def test_graph_failure_falls_back_to_vector_evidence(self):
        from app.core.config import settings

        self.graph.retrieve.side_effect = RuntimeError("unavailable")
        with patch.object(settings, "KG_ENABLED", True):
            self.service.question_no_stream(self.payload)
        self.assertEqual(len(self.chat.chat.call_args.kwargs["context_pairs"]), 1)

    def test_empty_retrieval_does_not_call_generation(self):
        from app.core.config import settings

        self.vectors.search.return_value = []
        self.vectors.client.search.return_value = []
        with patch.object(settings, "KG_ENABLED", False):
            result = self.service.question_no_stream(self.payload)
        self.chat.chat.assert_not_called()
        self.assertIn("tidak memiliki informasi", result.answer)

    def test_source_markup_is_escaped(self):
        from rag.llm.chat_model import OpenAIChat

        sources = OpenAIChat.format_sources(
            [["q", "text", {"file_name": "<script>x</script>", "quote": "<img src=x>"}]]
        )
        self.assertNotIn("<script>", sources)
        self.assertNotIn("<img", sources)

    def test_reranker_preserves_provenance_and_scores_only_text(self):
        from rag.llm.re_rank import ReRanking

        reranker = object.__new__(ReRanking)
        reranker.model = Mock()
        reranker.model.predict.return_value = [0.1, 0.9]
        pairs = [
            ["question", "first", {"file_name": "first.pdf"}],
            ["question", "second", {"file_name": "second.pdf"}],
        ]
        self.assertEqual(
            reranker.rank(top_results=1, pairs=pairs)[0][2]["file_name"], "second.pdf"
        )
        reranker.model.predict.assert_called_once_with(
            [["question", "first"], ["question", "second"]]
        )


class IngestionIntegrationTests(unittest.TestCase):
    def test_upload_queues_extraction_after_completed_status(self):
        from app.core.config import settings
        from app.pipeline.pipeline_service import PipelineService
        from rag.nlp.doc_parse import Section

        files = Mock()
        files.get_collection_name.return_value = "Pilot"
        files.get_vectordb_collection_name.return_value = "pilot"
        chunks = SimpleNamespace(
            chunk_sections=lambda sections, file_name="": [
                {
                    "text": TEXT,
                    "page": 1,
                    "page_label": None,
                    "section": "",
                    "quote": TEXT[:350],
                    "page_text": TEXT,
                }
            ],
            chunk_size=1000,
            chunk_overlap=100,
        )
        knowledge = Mock()
        knowledge.get_profile.return_value = SimpleNamespace(enabled=True)
        model, vectors = Mock(), Mock()
        source = SimpleNamespace(
            id=uuid4(),
            collection_id=uuid4(),
            file_path="fixture.txt",
            file_type="text/plain",
            file_name="fixture.txt",
        )
        pipeline = PipelineService(files, vectors, knowledge, model, chunks)

        def enqueue(collection_id, file_id):
            self.assertEqual(
                files.update_fields.call_args.args[1]["status"], "completed"
            )

        knowledge.enqueue.side_effect = enqueue
        with (
            patch.object(settings, "KG_ENABLED", True),
            patch(
                "app.pipeline.pipeline_service.read_sections",
                return_value=[Section(1, "", TEXT)],
            ),
        ):
            pipeline.run_pipeline(source)
        knowledge.enqueue.assert_called_once_with(source.collection_id, source.id)
        # Partial file updates must not overwrite file identity, path or collection.
        self.assertNotIn("file_path", files.update_fields.call_args.args[1])
        self.assertNotIn("collection_id", files.update_fields.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
