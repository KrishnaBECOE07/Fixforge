import unittest

from scheduling import billable_minutes, slots_overlap, unique_guests


class SchedulingTests(unittest.TestCase):
    def test_overlapping_meetings(self):
        self.assertTrue(slots_overlap((10, 20), (15, 25)))

    def test_separate_meetings(self):
        self.assertFalse(slots_overlap((10, 20), (21, 30)))

    def test_partial_billing_increment(self):
        self.assertEqual(billable_minutes(16), 30)

    def test_invalid_billing_increment(self):
        with self.assertRaises(ValueError):
            billable_minutes(16, 0)

    def test_duplicate_addresses_with_identical_spelling(self):
        self.assertEqual(unique_guests(["one@example.com", "one@example.com", "two@example.com"]),
                         ["one@example.com", "two@example.com"])
