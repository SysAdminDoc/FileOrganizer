"""Tests for fileorganizer/embeddings_classifier.py.

The classifier degrades cleanly when no embedding backend (fastembed,
model2vec, sentence_transformers) is installed — these tests verify that
graceful degradation, the singleton contract, and the cosine math for the
pure-Python path.  Live model loading is not exercised in CI.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fileorganizer import embeddings_classifier as ec


class CosineMath(unittest.TestCase):
    def test_orthogonal_vectors(self):
        self.assertAlmostEqual(ec._cosine([1, 0, 0], [0, 1, 0]), 0.0)

    def test_identical_vectors(self):
        self.assertAlmostEqual(ec._cosine([0.5, 0.5, 0.0], [0.5, 0.5, 0.0]), 1.0,
                               places=6)

    def test_opposite_vectors(self):
        self.assertAlmostEqual(ec._cosine([1, 0], [-1, 0]), -1.0, places=6)

    def test_zero_vector_is_not_nan(self):
        self.assertEqual(ec._cosine([0, 0], [1, 1]), 0.0)

    def test_mismatched_dim_is_zero(self):
        self.assertEqual(ec._cosine([1, 1], [1, 1, 1]), 0.0)


class EmbeddingsSingleton(unittest.TestCase):
    def test_instance_is_singleton(self):
        a = ec.EmbeddingsClassifier.instance()
        b = ec.EmbeddingsClassifier.instance()
        self.assertIs(a, b)


class GracefulDegradation(unittest.TestCase):
    """When no embedding backend is installed, classify() must return None
    rather than raise — so the caller silently falls through to AI."""

    def test_classify_one_returns_none_when_unavailable(self):
        clf = ec.EmbeddingsClassifier.instance()
        clf._initialized = False
        clf._backend = ""
        clf._anchors = {}

        # Force every backend loader to claim "not available".
        original = (clf._load_fastembed, clf._load_model2vec,
                    clf._load_sentence_transformers)
        clf._load_fastembed             = lambda: False
        clf._load_model2vec             = lambda: False
        clf._load_sentence_transformers = lambda: False
        try:
            result = clf.classify("Some Asset Name", ["After Effects - Other"])
            self.assertIsNone(result)
            self.assertEqual(clf.backend, "none")
            self.assertFalse(clf.available)
        finally:
            (clf._load_fastembed, clf._load_model2vec,
             clf._load_sentence_transformers) = original
            clf._initialized = False
            clf._backend = ""

    def test_module_classify_one_returns_none_when_unavailable(self):
        clf = ec.EmbeddingsClassifier.instance()
        clf._initialized = False
        clf._backend = ""
        clf._anchors = {}
        original = (clf._load_fastembed, clf._load_model2vec,
                    clf._load_sentence_transformers)
        clf._load_fastembed             = lambda: False
        clf._load_model2vec             = lambda: False
        clf._load_sentence_transformers = lambda: False
        try:
            self.assertIsNone(ec.classify_one("X", ["After Effects - Other"]))
        finally:
            (clf._load_fastembed, clf._load_model2vec,
             clf._load_sentence_transformers) = original
            clf._initialized = False
            clf._backend = ""


class FakeBackend(unittest.TestCase):
    """Drive the classifier with hand-rolled vectors to check the gating
    rules (top1 >= MIN_TOP1 AND margin >= MIN_MARGIN)."""

    def _install_fake(self, embedder_func) -> ec.EmbeddingsClassifier:
        clf = ec.EmbeddingsClassifier.instance()
        clf._initialized = True
        clf._backend = "fake"
        clf._model_name = "fake-test-model"
        clf._dim = 3
        clf._embedder = None
        clf._anchors = {}
        # Replace _embed with a deterministic mapping the test controls.
        clf._embed = embedder_func
        return clf

    def tearDown(self):
        # Reset shared singleton state so other tests start clean.
        clf = ec.EmbeddingsClassifier.instance()
        clf._initialized = False
        clf._backend = ""
        clf._model_name = ""
        clf._anchors = {}
        clf._embed = ec.EmbeddingsClassifier._embed.__get__(clf)

    def test_high_score_high_margin_returns_hit(self):
        # Anchors pointing along distinct unit axes; query aligned with first.
        anchors = {
            "After Effects - Logo Reveal":   [1.0, 0.0, 0.0],
            "Photoshop - Patterns & Textures":[0.0, 1.0, 0.0],
            "Illustrator - Icons & UI Kits": [0.0, 0.0, 1.0],
        }
        def fake_embed(texts):
            return [[1.0, 0.0, 0.0] for _ in texts]
        clf = self._install_fake(fake_embed)
        # Pre-load anchors directly to skip persistence path.
        clf._anchors = anchors

        result = clf.classify("Anything", list(anchors.keys()))
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "After Effects - Logo Reveal")
        self.assertEqual(result["confidence"], ec.HIT_CONF)
        self.assertGreaterEqual(result["top1"], ec.MIN_TOP1)
        self.assertGreaterEqual(result["margin"], ec.MIN_MARGIN)

    def test_low_top1_returns_none(self):
        anchors = {
            "Cat A": [1.0, 0.0, 0.0],
            "Cat B": [0.0, 1.0, 0.0],
        }
        # Query barely aligned with anything — top1 ≈ 0.5
        def fake_embed(texts):
            return [[0.5, 0.5, 0.7071] for _ in texts]
        clf = self._install_fake(fake_embed)
        clf._anchors = anchors
        result = clf.classify("ambiguous", list(anchors.keys()))
        self.assertIsNone(result)

    def test_thin_margin_returns_none(self):
        # Two anchors very close together; query equidistant.
        anchors = {
            "Cat A": [1.0, 0.0, 0.0],
            "Cat B": [0.99, 0.01, 0.0],
        }
        def fake_embed(texts):
            return [[1.0, 0.0, 0.0] for _ in texts]
        clf = self._install_fake(fake_embed)
        clf._anchors = anchors
        result = clf.classify("close call", list(anchors.keys()))
        self.assertIsNone(result, f"margin too thin should reject; got {result}")


class TextBuilder(unittest.TestCase):
    def test_includes_extensions_and_marketplace(self):
        text = ec.EmbeddingsClassifier._build_text(
            "Modern Logo Reveal",
            ext_set=["aep", "mp4"],
            marketplace="videohive",
        )
        self.assertIn("Modern Logo Reveal", text)
        self.assertIn("aep", text)
        self.assertIn("mp4", text)
        self.assertIn("videohive", text)

    def test_no_extras_is_just_name(self):
        text = ec.EmbeddingsClassifier._build_text("Plain Asset", None, None)
        self.assertEqual(text, "Plain Asset")


if __name__ == "__main__":
    unittest.main()
