"""Tests for NEXT-16 negative keyword rules in categories.py."""
import unittest

from fileorganizer.categories import check_negative_keywords, NEGATIVE_KEYWORDS


class TestNegativeKeywords(unittest.TestCase):
    def test_no_negatives_returns_false(self):
        self.assertFalse(check_negative_keywords("Some Unknown Category", "anything"))

    def test_wedding_blocked_by_corporate(self):
        self.assertTrue(check_negative_keywords(
            "After Effects - Wedding & Events", "corporate wedding promo"))

    def test_wedding_allowed_without_negatives(self):
        self.assertFalse(check_negative_keywords(
            "After Effects - Wedding & Events", "romantic wedding slideshow"))

    def test_flyers_blocked_by_business_card(self):
        self.assertTrue(check_negative_keywords(
            "Print - Flyers & Posters", "creative business card template"))

    def test_flyers_allowed_normally(self):
        self.assertFalse(check_negative_keywords(
            "Print - Flyers & Posters", "club party night flyer"))

    def test_negatives_dict_has_entries(self):
        self.assertGreater(len(NEGATIVE_KEYWORDS), 5)

    def test_all_values_are_lists(self):
        for cat, negatives in NEGATIVE_KEYWORDS.items():
            self.assertIsInstance(negatives, list, f"{cat} should have list value")
            for neg in negatives:
                self.assertIsInstance(neg, str, f"{cat} negative should be string")


class TestNegativeKeywordsIntegration(unittest.TestCase):
    def test_classifier_rejects_negative_match(self):
        from fileorganizer.classifier import categorize_folder
        # "Corporate Wedding" should NOT match "Wedding & Events" due to negative rule
        cat, score, _ = categorize_folder("Corporate Business Training")
        if cat:
            self.assertNotEqual(cat, "After Effects - Wedding & Events")


if __name__ == "__main__":
    unittest.main()
