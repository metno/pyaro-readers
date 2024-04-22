import unittest
from src.pyaro_readers.harpreader.harpreader import *


class TestHARPReader(unittest.TestCase):
    def test_parse_unit_str(self):
        with self.assertRaises(ValueError):
            extract_unit_information("test")

        with self.assertRaises(ValueError):
            extract_unit_information("days snice ")

        self.assertEquals(
            extract_unit_information("days since 2001-01-01"),
            UnitsInformation(np.datetime64("2001-01-01"), "days"),
        )
