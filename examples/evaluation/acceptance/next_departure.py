import unittest

from routing import next_departure


class DepartureAcceptance(unittest.TestCase):
    def test_order_can_catch_a_departure_at_its_ready_hour(self):
        self.assertEqual(next_departure(14, [21, 9, 14, 14]), 14)

    def test_midnight_and_end_of_day_are_inclusive(self):
        self.assertEqual(next_departure(0, [6, 0]), 0)
        self.assertEqual(next_departure(23, [20, 23]), 23)

    def test_invalid_values_are_rejected(self):
        for ready, hours in [(24, [7]), (7, [-1]), (-1, [7])]:
            with self.subTest(ready=ready, hours=hours), self.assertRaises(ValueError):
                next_departure(ready, hours)
