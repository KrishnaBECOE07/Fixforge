import unittest

from scheduling import slots_overlap


class MeetingBoundaryTests(unittest.TestCase):
    def test_touching_intervals_in_either_order_are_disjoint(self):
        self.assertFalse(slots_overlap((10, 20), (20, 30)))
        self.assertFalse(slots_overlap((20, 30), (10, 20)))

    def test_intervals_sharing_minutes_overlap(self):
        self.assertTrue(slots_overlap((10, 21), (20, 30)))
