import json
import unittest
from unittest.mock import patch
from io import BytesIO
from email.message import Message

from jarvis_aiba_summary import fetch_aiba_summary

URL = "https://aiba-technologies-preview.onrender.com/api/integrations/jarvis/summary"
TOKEN = "z" * 40

class FakeResponse:
    status = 200
    headers = Message()
    headers["Content-Type"] = "application/json"
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def read(self, size):
        return json.dumps({"service":"AIBA","leads_by_status":{"nuevo":3}}).encode()

class TestAibaSummary(unittest.TestCase):
    def test_read_only_aggregate(self):
        class FakeOpener:
            def open(self, req, timeout):
                assert req.get_method() == "GET"
                assert timeout == 10
                return FakeResponse()
        with patch("jarvis_aiba_summary.urllib.request.build_opener", return_value=FakeOpener()):
            self.assertEqual(fetch_aiba_summary(URL, TOKEN)["leads_by_status"]["nuevo"], 3)

    def test_reject_untrusted_hosts(self):
        for url in ("http://aiba-technologies-preview.onrender.com/api/integrations/jarvis/summary",
                    "https://example.org/api/integrations/jarvis/summary",
                    "https://aiba-technologies-preview.onrender.com/redirect"):
            with self.assertRaises(ValueError):
                fetch_aiba_summary(url, TOKEN)

    def test_missing_key(self):
        with self.assertRaises(ValueError):
            fetch_aiba_summary(URL, "")

if __name__ == "__main__":
    unittest.main()
