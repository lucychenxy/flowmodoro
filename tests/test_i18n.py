import unittest

from flowmo.i18n import category_from_label, category_label, normalize_language, text


class I18nTests(unittest.TestCase):
    def test_category_labels_are_translated_without_changing_internal_value(self) -> None:
        self.assertEqual(category_label("en", "阅读"), "Reading")
        self.assertEqual(category_label("de", "阅读"), "Lesen")
        self.assertEqual(category_label("zh", "阅读"), "阅读")
        self.assertEqual(category_from_label("de", "Lesen"), "阅读")

    def test_unknown_language_falls_back_to_english(self) -> None:
        self.assertEqual(normalize_language("fr"), "en")
        self.assertEqual(text("fr", "recent"), "Recent")


if __name__ == "__main__":
    unittest.main()
