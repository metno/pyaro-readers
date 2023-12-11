import unittest
from geocoder_reverse_natural_earth import (
    Geocoder_Reverse_NE,
    Geocoder_Reverse_Exception,
)


class TestGeocoderRevereseNE(unittest.TestCase):
    def test_lookup(self):
        geo = Geocoder_Reverse_NE()
        self.assertEqual(geo.lookup(60, 10)["ISO_A2_EH"], "NO")
        self.assertEqual(geo.lookup(78, 15)["ISO_A2_EH"], "NO")
        with self.assertRaises(Geocoder_Reverse_Exception):
            geo.lookup(78.2361926, 15.3692614)

    def test_lookup(self):
        geo = Geocoder_Reverse_NE()
        self.assertEqual(geo.lookup_nearest(78.2361926, 15.3692614)["ISO_A2_EH"], "NO")
