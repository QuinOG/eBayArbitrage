import unittest
from unittest import mock

import app
import prices
from tests.test_scoring import FIXTURE


class ApiTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(prices.PRICES, FIXTURE, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        self.client = app.app.test_client()

    def test_price_cpu(self):
        response = self.client.post("/api/price", json={"part": "cpu", "text": "i7-8700"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["model"], "Core i7-8700")
        self.assertEqual(response.get_json()["value"], 60.0)

    def test_price_invalid_part(self):
        response = self.client.post("/api/price", json={"part": "psu", "text": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_price_unidentified_cpu(self):
        response = self.client.post("/api/price", json={"part": "cpu", "text": "nothing here"})
        self.assertEqual(response.status_code, 400)

    def test_evaluate_empty_title(self):
        response = self.client.post("/api/evaluate", json={"title": ""})
        self.assertEqual(response.status_code, 400)

    def test_evaluate_cpu(self):
        response = self.client.post("/api/evaluate", json={"title": "Intel Core i7-8700", "price": 40, "shipping": 10})
        self.assertEqual(response.status_code, 200)
        listing = response.get_json()["listing"]
        self.assertIsInstance(listing["profit"], (int, float))
        self.assertEqual(listing["parts"][0]["model"], "Core i7-8700")

    def assertBadRequest(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_evaluate_nan_price(self):
        self.assertBadRequest(self.client.post("/api/evaluate", json={"title": "Intel Core i7-8700", "price": "NaN"}))

    def test_evaluate_infinite_price(self):
        self.assertBadRequest(self.client.post("/api/evaluate", json={"title": "Intel Core i7-8700", "price": "Infinity"}))

    def test_evaluate_negative_price(self):
        self.assertBadRequest(self.client.post("/api/evaluate", json={"title": "Intel Core i7-8700", "price": -5}))

    def test_evaluate_bad_shipping(self):
        response = self.client.post("/api/evaluate", json={"title": "Intel Core i7-8700", "price": 40, "shipping": "abc"})
        self.assertBadRequest(response)
        self.assertIn("shipping", response.get_json()["error"].lower())

    def test_evaluate_array_body(self):
        self.assertBadRequest(self.client.post("/api/evaluate", json=[1, 2]))

    def test_evaluate_number_title(self):
        self.assertBadRequest(self.client.post("/api/evaluate", json={"title": 123}))

    def test_evaluate_number_link_does_not_call_ebay(self):
        with mock.patch("app.get_item") as get_item:
            response = self.client.post("/api/evaluate", json={"link": 123456789012})
        self.assertBadRequest(response)
        get_item.assert_not_called()

    def test_price_number_text(self):
        self.assertBadRequest(self.client.post("/api/price", json={"part": "cpu", "text": 8700}))

    def test_price_array_body(self):
        self.assertBadRequest(self.client.post("/api/price", json=["cpu"]))

    def test_evaluate_string_numbers_and_blank_shipping_still_work(self):
        response = self.client.post("/api/evaluate", json={"title": "Intel Core i7-8700", "price": "40", "shipping": ""})
        self.assertEqual(response.status_code, 200)

    def test_evaluate_missing_price_defaults_to_zero(self):
        response = self.client.post("/api/evaluate", json={"title": "Intel Core i7-8700"})
        self.assertEqual(response.status_code, 200)
