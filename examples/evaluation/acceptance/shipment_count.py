import unittest

from stock import shipment_count


class ShipmentAcceptance(unittest.TestCase):
    def test_partial_first_shipment(self):
        self.assertEqual(shipment_count(1, 20), 1)

    def test_partial_last_shipment(self):
        self.assertEqual(shipment_count(101, 10), 11)

    def test_very_large_counts_keep_integer_precision(self):
        self.assertEqual(shipment_count(10**24 + 1, 10), 10**23 + 1)

    def test_negative_units_are_rejected(self):
        with self.assertRaises(ValueError):
            shipment_count(-1, 3)
