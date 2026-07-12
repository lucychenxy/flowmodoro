import unittest

from flowmo.db import CATEGORIES
from flowmo.i18n import LANGUAGES, category_from_label, category_label, normalize_language, text


class I18nTests(unittest.TestCase):
    def test_category_labels_are_translated_without_changing_internal_value(self) -> None:
        self.assertEqual(category_label("en", "阅读"), "Reading")
        self.assertEqual(category_label("de", "阅读"), "Lesen")
        self.assertEqual(category_label("zh", "阅读"), "阅读")
        self.assertEqual(category_from_label("de", "Lesen"), "阅读")

    def test_all_categories_have_labels_for_each_language(self) -> None:
        self.assertEqual(len(CATEGORIES), 7)
        self.assertIn("\u8bb2\u5ea7/\u7814\u8ba8", CATEGORIES)
        for language in LANGUAGES:
            for category in CATEGORIES:
                self.assertTrue(category_label(language, category))

        seminar_category = "\u8bb2\u5ea7/\u7814\u8ba8"
        self.assertEqual(category_label("en", seminar_category), "Seminars / Workshops")
        self.assertEqual(category_label("de", seminar_category), "Seminare / Workshops")
        self.assertEqual(category_label("zh", seminar_category), seminar_category)
        self.assertEqual(category_from_label("en", "Seminars / Workshops"), seminar_category)

    def test_unknown_language_falls_back_to_english(self) -> None:
        self.assertEqual(normalize_language("fr"), "en")
        self.assertEqual(text("fr", "recent"), "Recent")


if __name__ == "__main__":
    unittest.main()
