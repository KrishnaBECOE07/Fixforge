import unittest

from routing import normalize_zone


class ZoneAcceptance(unittest.TestCase):
    def test_mixed_whitespace_uses_one_separator(self):
        self.assertEqual(normalize_zone("\tSouth  \tWest\nCoast  "), "SOUTH-WEST-COAST")

    def test_existing_hyphens_are_preserved(self):
        self.assertEqual(normalize_zone("district-7   loading-bay"), "DISTRICT-7-LOADING-BAY")

    def test_mixed_whitespace_alone_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_zone(" \t\n")
