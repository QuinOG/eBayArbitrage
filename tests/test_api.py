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
