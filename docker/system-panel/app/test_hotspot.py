import os
import tempfile
import unittest
from pathlib import Path

import app as system


class HotspotChannelTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        system.HOTSPOT_DIR = Path(self.temp.name)
        self.client = system.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_channel_drops_a_request_for_the_host(self):
        response = self.client.post("/api/hotspot/channel", json={"channel": "6"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual((system.HOTSPOT_DIR / "request").read_text(), "6")
        self.assertTrue(response.get_json()["pending"])

    def test_rejects_other_channels_and_non_json_posts(self):
        for body in ({"channel": "13"}, {"channel": "6; reboot"}, ["6"], {}):
            self.assertEqual(self.client.post("/api/hotspot/channel", json=body).status_code, 400)
        form = self.client.post("/api/hotspot/channel", data={"channel": "6"})
        self.assertEqual(form.status_code, 400)
        self.assertEqual(os.listdir(system.HOTSPOT_DIR), [])

    def test_reports_host_status(self):
        (system.HOTSPOT_DIR / "status.json").write_text(
            '{"channel":"1","ok":true,"message":"Canale 1 attivo","updated":"2026-10-05T01:00:00+02:00"}'
        )
        data = self.client.get("/api/hotspot").get_json()
        self.assertEqual((data["channel"], data["ok"], data["pending"]), ("1", True, False))


if __name__ == "__main__":
    unittest.main()
