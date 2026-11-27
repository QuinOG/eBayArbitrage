import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import requests

import ebay_api


class RetryTest(unittest.TestCase):
    def setUp(self):
        request_patch = mock.patch("ebay_api.requests.request")
        sleep_patch = mock.patch("ebay_api.time.sleep")
        self.request = request_patch.start()
        self.sleep = sleep_patch.start()
        self.addCleanup(request_patch.stop)
        self.addCleanup(sleep_patch.stop)

    def test_returns_last_503_without_sleeping_after_it(self):
        responses = [SimpleNamespace(status_code=503, headers={}) for _ in range(3)]
        self.request.side_effect = responses

        self.assertIs(ebay_api.request_with_retry("GET", ebay_api.BROWSE_URL), responses[-1])
        self.assertEqual(self.request.call_count, 3)
        self.assertEqual(self.sleep.call_args_list, [mock.call(3), mock.call(6)])

    def test_search_retries_401_with_fresh_token(self):
        unauthorized = SimpleNamespace(status_code=401, headers={})
        ok = SimpleNamespace(status_code=200, headers={}, json=lambda: {"itemSummaries": []})
        self.request.side_effect = [unauthorized, ok]

        with mock.patch.dict(ebay_api.TOKEN_CACHE, token="t1"), mock.patch(
            "ebay_api.get_ebay_oauth_token", side_effect=["t1", "t2"]
        ):
            self.assertEqual(ebay_api.search_listings("164"), [])
            self.assertIsNone(ebay_api.TOKEN_CACHE["token"])

        self.assertEqual(self.request.call_count, 2)
        self.assertEqual(self.request.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer t2")

    def test_honors_retry_after_on_429(self):
        self.check_retry_after("2", 2)

    def test_caps_retry_after_on_429(self):
        self.check_retry_after("600", 10)

    def check_retry_after(self, header, expected_wait):
        limited = SimpleNamespace(status_code=429, headers={"Retry-After": header})
        ok = SimpleNamespace(status_code=200, headers={})
        self.request.side_effect = [limited, ok]

        self.assertIs(ebay_api.request_with_retry("GET", ebay_api.BROWSE_URL), ok)
        self.sleep.assert_called_once_with(expected_wait)

    def test_retries_server_errors(self):
        for status in (500, 502, 504):
            with self.subTest(status=status):
                ok = SimpleNamespace(status_code=200, headers={})
                self.request.side_effect = [SimpleNamespace(status_code=status, headers={}), ok]

                self.assertIs(ebay_api.request_with_retry("GET", ebay_api.BROWSE_URL), ok)

    def test_returns_404_immediately(self):
        missing = SimpleNamespace(status_code=404, headers={})
        self.request.side_effect = [missing]

        self.assertIs(ebay_api.request_with_retry("GET", ebay_api.BROWSE_URL), missing)
        self.request.assert_called_once()
        self.sleep.assert_not_called()

    def test_raises_after_three_connection_errors(self):
        self.request.side_effect = [requests.ConnectionError("offline") for _ in range(3)]

        with self.assertRaisesRegex(Exception, "No response from .* after 3 attempts"):
            ebay_api.request_with_retry("GET", ebay_api.BROWSE_URL)

        self.assertEqual(self.request.call_count, 3)
        self.assertEqual(self.sleep.call_args_list, [mock.call(3), mock.call(6)])


class CacheTest(unittest.TestCase):
    def test_search_does_not_cache_results(self):
        ok = SimpleNamespace(status_code=200, headers={}, json=lambda: {"itemSummaries": []})
        with mock.patch("ebay_api.requests.request", return_value=ok) as request, mock.patch(
            "ebay_api.get_ebay_oauth_token", return_value="t"
        ):
            ebay_api.search_listings("164")
            ebay_api.search_listings("164")

        self.assertEqual(request.call_count, 2)

    def test_save_details_cache_drops_stale_entries(self):
        now = time.time()
        entries = {
            "fresh": (now, {"specifics": [], "description": []}),
            "stale": (0, {"specifics": [], "description": []}),
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            ebay_api, "DETAILS_CACHE_FILE", os.path.join(tmp, "details_cache.json")
        ), mock.patch.dict(ebay_api.DETAILS_CACHE, entries, clear=True):
            ebay_api.save_details_cache()
            self.assertEqual(set(ebay_api.DETAILS_CACHE), {"fresh"})
