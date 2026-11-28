import unittest

from stock import restock_queue


class RestockAcceptance(unittest.TestCase):
    def test_equal_priorities_keep_input_order(self):
        items = [("bearing", 2), ("washer", 4), ("gear", 2), ("bolt", 4), ("seal", 1)]
        self.assertEqual(restock_queue(items), [items[i] for i in (1, 3, 0, 2, 4)])

    def test_repeated_item_records_are_preserved(self):
        self.assertEqual(restock_queue([("seal", 2), ("seal", 2)]), [("seal", 2), ("seal", 2)])

    def test_input_remains_unchanged(self):
        items = [("motor", 1), ("belt", 3)]
        restock_queue(items)
        self.assertEqual(items, [("motor", 1), ("belt", 3)])
