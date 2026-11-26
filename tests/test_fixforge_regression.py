import unittest

from scheduling import billable_minutes


class BillingBoundaryTests(unittest.TestCase):
    def test_exact_multiples_are_preserved(self):
        self.assertEqual(billable_minutes(30, 15), 30)
        self.assertEqual(billable_minutes(20, 10), 20)

    def test_zero_minutes_stays_zero(self):
        self.assertEqual(billable_minutes(0, 15), 0)

    def test_partial_increments_still_round_up(self):
        self.assertEqual(billable_minutes(31, 15), 45)

    def test_invalid_durations_and_increments_are_rejected(self):
        with self.assertRaises(ValueError):
            billable_minutes(-1, 15)
        with self.assertRaises(ValueError):
            billable_minutes(30, 0)
