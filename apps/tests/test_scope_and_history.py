"""The scope gate stops what the corpus cannot answer; history keeps follow-ups."""

import unittest
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock, patch
from uuid import uuid4

from agents.standalone_question import clean_question
from app.schema.question_schema import CreateQuestion
from app.services.conversation_context import contextual_query, is_followup
from app.services.retrieval_service import RetrievalService
from app.services.scope_gate import trivial_reason
from rag.llm.chat_model import OpenAIChat

HISTORY = [("Bagaimana cara mendaftar beasiswa KIP?", "Pendaftaran dibuka [S1].")]


class SyntacticGateTests(unittest.TestCase):
    def test_utterances_without_a_question_are_named(self):
        self.assertEqual(trivial_reason("halo"), "small_talk")
        self.assertEqual(trivial_reason("Terima kasih!"), "small_talk")
        self.assertEqual(trivial_reason("p"), "too_short")
        self.assertEqual(trivial_reason("???"), "no_words")

    def test_a_bare_keyword_is_still_a_search(self):
        # Evidence decides this one, not its length.
        self.assertIsNone(trivial_reason("beasiswa"))
        self.assertIsNone(trivial_reason("Apa syarat pendaftaran?"))


class FollowUpTests(unittest.TestCase):
    def test_elliptic_questions_borrow_the_earlier_topic(self):
        for question in ("Berapa lama prosesnya?", "Kalau untuk S2 bagaimana?"):
            self.assertTrue(is_followup(question))
            self.assertEqual(
                contextual_query(question, HISTORY),
                f"{HISTORY[0][0]} {question}",
            )

    def test_a_self_contained_question_is_left_alone(self):
        question = "Apa syarat IPK minimum pendaftaran beasiswa KIP tahun 2026?"
        self.assertFalse(is_followup(question))
        self.assertEqual(contextual_query(question, HISTORY), question)

    def test_the_first_question_has_nothing_to_borrow(self):
        self.assertEqual(contextual_query("Berapa lamanya?", []), "Berapa lamanya?")


class ScopeProbeTests(unittest.TestCase):
    def build(self, probe_score):
        rerank = Mock()
        rerank.best_score.return_value = probe_score
        rerank.rank.side_effect = lambda pairs, **kw: [
            [pair[0], pair[1], {**pair[2], "rerank_score": probe_score}]
            for pair in pairs
        ]
        collections = Mock()
        collections.read_by_id.return_value = SimpleNamespace(
            vectordb_collection_name="pilot", collection_name="pilot"
        )
        vectors = Mock()
        vectors.search.return_value = [
            SimpleNamespace(
                id=1,
                score=0.9,
                payload={"document": "teks", "file_id": str(uuid4()), "page": 1},
            )
        ]
        embedding = Mock()
        embedding.encode.return_value = SimpleNamespace(tolist=lambda: [0.1])
        augment = Mock()
        augment.augment.return_value = ["a", "b"]
        service = RetrievalService(
            collections, vectors, augment, None, embedding, rerank
        )
        payload = CreateQuestion(
            question_id="q", question_text="Siapa itu Jokowi", collection_id=uuid4()
        )
        return service, payload, augment, rerank

    def test_an_unanswerable_question_stops_before_the_rewrite_call(self):
        service, payload, augment, rerank = self.build(0.001)
        stages = []
        with patch(
            "app.services.retrieval_service.settings.SCOPE_GATE_MIN_SCORE", 0.02
        ):
            self.assertEqual(
                service.retrieve(payload, True, lambda s, **d: stages.append(s)), []
            )
        # The saving is the point: no LLM rewrite, no full rerank.
        augment.augment.assert_not_called()
        rerank.rank.assert_not_called()
        self.assertEqual(stages[-1], "out_of_scope")

    def test_a_covered_question_proceeds_untouched(self):
        service, payload, augment, rerank = self.build(0.9)
        with patch(
            "app.services.retrieval_service.settings.SCOPE_GATE_MIN_SCORE", 0.02
        ):
            self.assertEqual(len(service.retrieve(payload, True)), 1)
        augment.augment.assert_called_once()
        rerank.rank.assert_called_once()


class ConversationDecisionTests(unittest.TestCase):
    """Bare probe first, carried probe second, on scores measured for real.

    The pairs are (bare, carried) cross-encoder scores taken from
    bge-reranker-v2-m3 against a fixture passage, so the thresholds are
    exercised against the separation they were chosen for.
    """

    MEASURED: ClassVar[dict[str, tuple[float, float]]] = {
        "Berapa lama prosesnya?": (0.094, 0.958),
        "Kalau untuk S2 bagaimana?": (0.128, 0.988),
        "Kalau jadwal kuliahnya?": (0.733, 0.891),
        "Siapa itu Jokowi": (0.000, 0.182),
        "Berapa IPK minimum beasiswa KIP?": (0.989, 0.995),
    }

    def build(self, question):
        self.searched = []
        scores = self.MEASURED[question]
        rerank = Mock()
        rerank.best_score.side_effect = lambda pairs, query=None: (
            scores[0] if query == question else scores[1]
        )
        rerank.rank.side_effect = lambda pairs, **kw: [
            [pair[0], pair[1], {**pair[2], "rerank_score": 0.9}] for pair in pairs
        ]
        collections = Mock()
        collections.read_by_id.return_value = SimpleNamespace(
            vectordb_collection_name="pilot", collection_name="pilot"
        )
        vectors = Mock()

        def search(collection_name, query_vector, query_text=None, limit=20):
            self.searched.append(query_text)
            return [
                SimpleNamespace(
                    id=1,
                    score=0.9,
                    payload={"document": "teks", "file_id": str(uuid4()), "page": 1},
                )
            ]

        vectors.search.side_effect = search
        embedding = Mock()
        embedding.encode.return_value = SimpleNamespace(tolist=lambda: [0.1])
        augment = Mock()
        augment.augment.side_effect = lambda query: [query]
        rewriter = Mock()
        rewriter.rewrite.side_effect = lambda q, history: f"standalone: {q}"
        service = RetrievalService(
            collections, vectors, augment, None, embedding, rerank, rewriter
        )
        payload = CreateQuestion(
            question_id="q", question_text=question, collection_id=uuid4()
        )
        return service, payload, augment, rewriter

    def decide(self, question):
        service, payload, augment, rewriter = self.build(question)
        evidence = service.retrieve(payload, True, None, HISTORY)
        if not evidence:
            return "rejected", augment, rewriter
        return ("follow_up" if rewriter.rewrite.called else "standalone"), augment, rewriter

    def test_an_elliptic_question_is_rewritten_not_concatenated(self):
        for question in ("Berapa lama prosesnya?", "Kalau untuk S2 bagaimana?"):
            decision, augment, rewriter = self.decide(question)
            self.assertEqual(decision, "follow_up", question)
            # One rewrite call replaces the augmentation call, not adds to it.
            rewriter.rewrite.assert_called_once()
            augment.augment.assert_not_called()
            # The concatenation never reaches the search that feeds ranking.
            self.assertEqual(self.searched[-1], f"standalone: {question}")

    def test_a_topic_switch_keeps_its_own_words(self):
        decision, _, rewriter = self.decide("Kalau jadwal kuliahnya?")
        self.assertEqual(decision, "standalone")
        rewriter.rewrite.assert_not_called()
        # Nothing was searched with the old topic attached to it.
        self.assertNotIn(f"{HISTORY[0][0]} Kalau jadwal kuliahnya?", self.searched)

    def test_an_aside_is_rejected_although_history_would_carry_it(self):
        decision, augment, rewriter = self.decide("Siapa itu Jokowi")
        self.assertEqual(decision, "rejected")
        rewriter.rewrite.assert_not_called()
        augment.augment.assert_not_called()

    def test_a_self_contained_question_ignores_the_conversation(self):
        decision, augment, rewriter = self.decide("Berapa IPK minimum beasiswa KIP?")
        self.assertEqual(decision, "standalone")
        rewriter.rewrite.assert_not_called()
        augment.augment.assert_called_once()


class StandaloneRewriteTests(unittest.TestCase):
    def test_only_a_labelled_line_is_accepted(self):
        self.assertEqual(
            clean_question("Berapa lamanya?", "TANYA: Berapa lama proses KIP?"),
            "Berapa lama proses KIP?",
        )

    def test_an_answer_instead_of_a_rewrite_is_dropped(self):
        # An unlabelled reply is the model answering; the original is safer.
        self.assertEqual(
            clean_question("Berapa lamanya?", "Prosesnya 14 hari kerja."),
            "Berapa lamanya?",
        )

    def test_reasoning_before_the_label_is_ignored(self):
        self.assertEqual(
            clean_question("Berapa lamanya?", "<think>hmm</think>\nTANYA: Berapa lama?"),
            "Berapa lama?",
        )


class HistoryPromptTests(unittest.TestCase):
    def test_earlier_turns_reach_the_model_without_their_citations(self):
        chat = object.__new__(OpenAIChat)
        messages = chat._prepare_messages("Berapa lamanya?", [], HISTORY)
        replayed = [m.content for m in messages]
        self.assertIn(HISTORY[0][0], replayed)
        # The replayed answer sits just before this turn's evidence, and
        # [S1] pointed at that turn's sources, not at this turn's.
        self.assertIn("Pendaftaran dibuka", replayed[-2])
        self.assertNotIn("[S1]", replayed[-2])

    def test_the_evidence_stays_the_last_thing_the_model_reads(self):
        chat = object.__new__(OpenAIChat)
        messages = chat._prepare_messages("Berapa lamanya?", [], HISTORY)
        self.assertIn("PERTANYAAN: Berapa lamanya?", messages[-1].content)

    def test_without_history_the_prompt_is_unchanged(self):
        chat = object.__new__(OpenAIChat)
        self.assertEqual(
            [m.content for m in chat._prepare_messages("q", [])],
            [m.content for m in chat._prepare_messages("q", [], [])],
        )


if __name__ == "__main__":
    unittest.main()
