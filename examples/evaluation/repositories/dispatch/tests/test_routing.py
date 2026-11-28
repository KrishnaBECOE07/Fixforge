import unittest

from routing import next_departure, normalize_zone


class RoutingTests(unittest.TestCase):
    def test_simple_zone(self):
        self.assertEqual(normalize_zone(" north west "), "NORTH-WEST")

    def test_blank_zone(self):
        with self.assertRaises(ValueError):
            normalize_zone("   ")

    def test_next_departure_uses_time_not_input_order(self):
        self.assertEqual(next_departure(8, [19, 7, 12]), 12)

    def test_no_suitable_departure(self):
        self.assertIsNone(next_departure(20, [8, 19]))
