import unittest
from unittest import mock

import config
import prices
import scanner

FIXTURE = {
    ("cpu", "Core i7-8700"): {"value": 60.0, "sales": 10, "confidence": "high", "kind": "exact"},
    ("cpu", "Core i5-8500"): {"value": 30.0, "sales": 10, "confidence": "high", "kind": "exact"},
    ("cpu", "Ryzen 5 3600"): {"value": 70.0, "sales": 10, "confidence": "high", "kind": "exact"},
    ("mobo", "MSI B450 TOMAHAWK MAX"): {"value": 80.0, "sales": 1, "confidence": "low", "kind": "exact"},
    ("mobo", "B660M"): {"value": 85.0, "sales": 5, "confidence": "high", "kind": "fallback"},
    ("ram", "DDR4 Desktop 16GB"): {"value": 50.0, "sales": 5, "confidence": "high", "kind": "fallback"},
    ("gpu", "RTX 3060 12GB"): {"value": 300.0, "sales": 20, "confidence": "high", "kind": "exact"},
    ("mobo", "B550"): {"value": 80.0, "sales": 30, "confidence": "high", "kind": "fallback"},
    ("cpu", "Ryzen 5 5600X"): {"value": 120.0, "sales": 10, "confidence": "high", "kind": "exact"},
}
SEARCH = {s["name"]: s for s in config.SEARCHES}


class ScoringTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.dict(prices.PRICES, FIXTURE, clear=True),
            mock.patch.object(config, "SALES_TAX_RATE", 0.10),
            mock.patch.object(config, "TAX_ON_SHIPPING", True),
            mock.patch.object(config, "MIN_PROFIT", 20.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def score(self, search, title, price, shipping, **extra):
        return scanner.score_listing({"title": title, "price": price, "shipping": shipping, **extra}, SEARCH[search])

    def test_profit_math(self):
        result = self.score("CPU", "Intel Core i7-8700 3.20GHz 6-Core LGA1151 Desktop Processor", 40, 10)
        self.assertEqual(result["tax"], 5.0)
        self.assertNotIn("total_cost", result)  # current behavior, see report
        self.assertEqual(result["price"] + result["shipping"] + result["tax"], 55.0)
        self.assertEqual(result["parts_value"], 60.0)
        self.assertEqual(result["profit"], 5.0)
        self.assertIs(result["is_deal"], False)
        self.assertEqual(result["confidence"], "high")

    def test_tax_without_shipping(self):
        with mock.patch.object(config, "TAX_ON_SHIPPING", False):
            result = self.score("CPU", "Intel Core i7-8700 3.20GHz 6-Core LGA1151 Desktop Processor", 40, 10)
        self.assertEqual(result["tax"], 4.0)

    def test_deal_threshold(self):
        result = self.score("CPU", "Intel Core i7-8700 3.20GHz 6-Core LGA1151 Desktop Processor", 20, 0)
        self.assertEqual(result["profit"], 38.0)
        self.assertIs(result["is_deal"], True)

    def test_lot_multiplier(self):
        result = self.score("CPU", "Lot of 5 Intel Core i5-8500 3.0GHz SR3XE LGA1151 CPU", 40, 0)
        self.assertEqual(result["parts_value"], 150.0)
        self.assertTrue(any("Lot of 5" in flag for flag in result["flags"]))

    def test_unknown_shipping(self):
        result = self.score("CPU", "Intel Core i7-8700 3.20GHz 6-Core LGA1151 Desktop Processor", 40, None)
        self.assertEqual(result["shipping"], 0.0)
        self.assertTrue(any("Shipping cost unknown" in flag for flag in result["flags"]))

    def test_unidentified_cpu(self):
        result = self.score("CPU", "Intel Core i5 10th Gen Processor Desktop CPU", 40, 0)
        self.assertEqual(result["parts"], [])
        self.assertEqual(result["parts_value"], 0)
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["missing"][0]["part"], "cpu")

    def test_low_confidence_part(self):
        result = self.score("Combo", "MSI B450 TOMAHAWK MAX + AMD Ryzen 5 3600 + 16GB DDR4 3200 Combo", 40, 0)
        board = next(part for part in result["parts"] if part["part"] == "mobo")
        self.assertEqual(board["value"], 80.0)
        self.assertEqual(result["confidence"], "low")

    def test_chipset_fallback(self):
        result = self.score("Combo", "Intel i5-12400F + B660M Motherboard + 16GB DDR4 Bundle", 40, 0)
        board = next(part for part in result["parts"] if part["part"] == "mobo")
        self.assertEqual(board["priced_as"], "B660M")
        self.assertEqual(board["kind"], "fallback")
        self.assertTrue(any("average B660M board" in flag for flag in result["flags"]))

    def test_gpu(self):
        result = self.score("Desktop", "Custom Gaming PC Ryzen 5 3600 RTX 3060 12GB 32GB DDR4", 40, 0)
        gpu = next(part for part in result["parts"] if part["part"] == "gpu")
        self.assertEqual(gpu["model"], "RTX 3060 12GB")
        self.assertEqual(gpu["value"], 300.0)

    def test_damaged_title(self):
        result = self.score("CPU", "Intel Core i7-8700 - Untested, For Parts", 40, 0)
        self.assertTrue(any("damaged or untested" in flag for flag in result["flags"]))
        self.assertEqual(result["confidence"], "low")

    def test_untested_for_parts_is_low(self):
        result = self.score("CPU", "Intel Core i7-8700 - Untested, For Parts", 20, 0)
        self.assertEqual(result["confidence"], "low")

    def test_missing_board_is_low(self):
        result = self.score("Combo", "AMD Ryzen 5 3600 CPU and 16GB DDR4 RAM Combo", 40, 0)
        self.assertIn("mobo", [part["part"] for part in result["missing"]])
        self.assertEqual(result["confidence"], "low")

    def test_unknown_shipping_is_low(self):
        result = self.score("CPU", "Intel Core i7-8700", 40, None)
        self.assertEqual(result["confidence"], "low")

    def test_lot_is_low(self):
        result = self.score("CPU", "Lot of 5 Intel Core i5-8500 3.0GHz SR3XE LGA1151 CPU", 40, 0)
        self.assertEqual(result["confidence"], "low")

    def test_chipset_fallback_is_low(self):
        result = self.score("Combo", "Intel i5-12400F + B660M Motherboard + 16GB DDR4 Bundle", 40, 0)
        self.assertEqual(result["confidence"], "low")

    def test_full_board_name_fallback_is_low(self):
        result = self.score("Combo", "MSI B550 GAMING PLUS Ryzen 5 5600X Combo", 40, 0)
        board = next(part for part in result["parts"] if part["part"] == "mobo")
        self.assertEqual(board["priced_as"], "B550")
        self.assertEqual(result["confidence"], "low")
        self.assertTrue(any("priced as an average B550 board" in flag for flag in result["flags"]))

    def test_description_junk_is_low(self):
        result = self.score("CPU", "Intel Core i7-8700", 40, 0, description=["Sold as-is"])
        self.assertEqual(result["confidence"], "low")

    def test_clean_listing_stays_high(self):
        result = self.score("CPU", "Intel Core i7-8700", 40, 5)
        self.assertEqual(result["confidence"], "high")

    def test_multiple_cpu_models(self):
        model, problem = scanner.find_part("cpu", "i7-8700 and i5-8500")
        self.assertIsNone(model)
        self.assertIn("several CPU models", problem)

    def test_price_lookup_fallback_and_unknown(self):
        row = prices.lookup("mobo", "MSI B660M MORTAR")
        self.assertEqual(row, {**FIXTURE[("mobo", "B660M")], "priced_as": "B660M"})
        self.assertIsNone(prices.lookup("cpu", "Core i9-99999"))
