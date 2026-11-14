# Copyright (c) 2026 Carmine Gallina - https://github.com/carminegallina
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
        self.assertEqual((data["channel"], data["ok"], data["pending"]), ("1", True, ""))

    def test_away_from_home_is_not_an_alarm_but_a_missing_hotspot_is(self):
        def statuses(ips):
            return {check["id"]: (check["status"], check["detail"]) for check in system.network_checks(ips)}

        away = statuses(["10.42.0.1", "172.17.0.1"])
        self.assertEqual({status for status, _detail in away.values()}, {"ok"})
        self.assertIn("fuori casa", away["lan_ip"][1])
        self.assertIn("192.168.1.101", statuses(["192.168.1.101", "10.42.0.1"])["lan_ip"][1])
        self.assertEqual(statuses(["192.168.1.101"])["hotspot_ip"][0], "error")

    def test_scan_recommends_the_least_crowded_channel(self):
        (system.HOTSPOT_DIR / "status.json").write_text('{"channel":"1","ok":true}')
        (system.HOTSPOT_DIR / "scan.json").write_text(
            '{"ok":true,"updated":"now","networks":['
            '{"channel":1,"signal":-40},{"channel":2,"signal":-60},'
            '{"channel":6,"signal":-85},{"channel":11,"signal":-70},{"channel":11,"signal":-75}]}'
        )
        scan = self.client.get("/api/hotspot").get_json()["scan"]
        self.assertEqual(scan["recommended"], "6")
        self.assertEqual(scan["channels"]["1"]["networks"], 2)
        self.assertEqual(scan["channels"]["6"]["strongest"], -60)  # channel 2 still overlaps 6

    def test_scan_tie_keeps_the_current_channel(self):
        (system.HOTSPOT_DIR / "status.json").write_text('{"channel":"11","ok":true}')
        (system.HOTSPOT_DIR / "scan.json").write_text('{"ok":true,"updated":"now","networks":[]}')
        self.assertEqual(self.client.get("/api/hotspot").get_json()["scan"]["recommended"], "11")

    def test_scan_request_is_queued_once(self):
        first = self.client.post("/api/hotspot/scan", json={})
        self.assertEqual(first.status_code, 202)
        self.assertEqual((system.HOTSPOT_DIR / "request").read_text(), "scan")
        self.assertEqual(first.get_json()["pending"], "scan")
        self.assertEqual(self.client.post("/api/hotspot/scan", json={}).status_code, 409)


if __name__ == "__main__":
    unittest.main()
