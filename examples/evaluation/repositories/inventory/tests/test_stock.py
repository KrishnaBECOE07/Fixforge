import unittest

from stock import restock_queue, shipment_count


class StockTests(unittest.TestCase):
    def test_exact_shipment(self):
        self.assertEqual(shipment_count(12, 4), 3)

    def test_empty_shipment(self):
        self.assertEqual(shipment_count(0, 4), 0)

    def test_invalid_capacity(self):
        with self.assertRaises(ValueError):
            shipment_count(4, 0)

    def test_queue_sorts_by_descending_priority(self):
        items = [("cable", 1), ("sensor", 5), ("board", 3)]
        self.assertEqual(restock_queue(items), [("sensor", 5), ("board", 3), ("cable", 1)])
