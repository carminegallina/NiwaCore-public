from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import base64
import io
import json
import socket
import struct
import threading
import unittest

from PIL import Image

import app as review


def media_id(relative):
    return base64.urlsafe_b64encode(relative.encode()).decode().rstrip("=")


class FakeSelphy(BaseHTTPRequestHandler):
    """Answers like the CP1500: Print-Job, Get-Job-Attributes, Get-Printer-Attributes."""
    printer = None  # the test case, which holds the replies and records requests

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        operation = struct.unpack(">H", body[2:4])[0]
        _status, attributes = review.ipp_parse(body)
        test = self.printer
        reply = b"\x01" + review.ipp_attribute(0x47, "attributes-charset", "utf-8")
        status = 0
        if operation == 0x0002:
            document = body[body.index(b"\x03\xff\xd8") + 1:]
            test.printed.append((attributes, document))
            reply += b"\x02" + review.ipp_integer("job-id", 7)
        elif operation == 0x0009:
            status = test.job_status
            reply += b"\x02" + review.ipp_attribute(0x23, "job-state", struct.pack(">i", test.job_state))
        elif operation == 0x000B:
            reply += b"\x04" + review.ipp_attribute(0x41, "printer-make-and-model", "Canon SELPHY CP1500 HTTP")
            for index, reason in enumerate(test.reasons):
                reply += review.ipp_attribute(0x44, "" if index else "printer-state-reasons", reason)
        message = struct.pack(">BBHI", 2, 0, status, 1) + reply + b"\x03"
        self.send_response(200)
        self.send_header("Content-Type", "application/ipp")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)

    def log_message(self, *args):
        pass


class DirectPrintTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.photo_root = root / "photo"
        self.photo_root.mkdir()
        names = ("PHOTO_ROOT", "PRINT_FRAME_ROOT", "PRINT_EXPORT_ROOT",
                 "EDITOR_PREVIEW_ROOT", "PRINTER_FILE", "PRINTER_PORT")
        self.originals = {name: getattr(review, name) for name in names}
        review.PHOTO_ROOT = self.photo_root
        review.MEDIA_SECTIONS["photo"]["root"] = self.photo_root
        review.PRINT_FRAME_ROOT = root / "frames"
        review.PRINT_EXPORT_ROOT = root / "exports"
        review.EDITOR_PREVIEW_ROOT = root / "previews"
        review.PRINTER_FILE = root / "selphy_printer.json"
        Image.new("RGB", (1600, 1200), "red").save(self.photo_root / "TEST.JPG", quality=95)

        self.printed, self.job_state, self.job_status, self.reasons = [], 5, 0, ["none"]
        FakeSelphy.printer = self
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSelphy)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        review.PRINTER_PORT = self.server.server_address[1]
        self.client = review.app.test_client()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for name, value in self.originals.items():
            setattr(review, name, value)
        review.MEDIA_SECTIONS["photo"]["root"] = self.originals["PHOTO_ROOT"]
        self.temporary.cleanup()

    def print_photo(self, **extra):
        payload = {"id": media_id("TEST.JPG"), "preset": "P", "orientation": "landscape", **extra}
        return self.client.post("/api/print/print", json=payload)

    def test_print_finds_the_printer_sends_the_page_and_follows_the_job(self):
        with mock.patch.object(review, "scan_printer_ports", return_value=["127.0.0.1"]):
            response = self.print_photo()
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        result = response.get_json()
        self.assertEqual(result["job_id"], 7)
        self.assertEqual(result["beside_original"], "TEST_stampa-P.jpg")
        self.assertEqual(json.loads(review.PRINTER_FILE.read_text()), {"host": "127.0.0.1"},
                         "the printer found by the scan is remembered")

        attributes, document = self.printed[0]
        self.assertEqual(attributes["document-format"], ["image/jpeg"])
        self.assertEqual(attributes["print-scaling"], ["fill"])
        media = attributes["media-col"][0]
        self.assertEqual(media["media-size"], [{"x-dimension": [10000], "y-dimension": [14800]}])
        self.assertEqual([media[f"media-{side}-margin"] for side in ("top", "bottom", "left", "right")],
                         [[0]] * 4, "borderless")
        with Image.open(io.BytesIO(document)) as page:
            self.assertEqual(page.size, (1872, 1248), "the SELPHY's whole page")

        self.assertEqual(self.client.get("/api/print/jobs/7").get_json(),
                         {"done": False, "ok": False, "state": 5, "message": "In stampa."})
        self.job_state = 9
        report = self.client.get("/api/print/jobs/7").get_json()
        self.assertEqual((report["done"], report["ok"], report["message"]), (True, True, "Stampata."))

    def test_printer_problems_are_explained(self):
        review.PRINTER_FILE.write_text(json.dumps({"host": "127.0.0.1"}))
        self.job_state, self.reasons = 8, ["media-empty-error", "marker-supply-low-warning"]
        report = self.client.get("/api/print/jobs/7").get_json()
        self.assertEqual((report["done"], report["ok"]), (True, False))
        self.assertEqual(report["message"], "Stampa interrotta: carta finita, inchiostro quasi finito.")
        self.job_status = 0x0404  # what the real CP1500 answers for a forgotten job
        report = self.client.get("/api/print/jobs/7").get_json()
        self.assertEqual((report["done"], report["ok"]), (True, None), "the SELPHY forgets older jobs")
        self.assertEqual(self.print_photo(preset="L").status_code, 400, "only P is measured")

    def test_unreachable_printer_fails_before_saving_anything(self):
        with socket.socket() as probe:  # a port nobody listens on
            probe.bind(("127.0.0.1", 0))
            review.PRINTER_PORT = probe.getsockname()[1]
        review.PRINTER_FILE.write_text(json.dumps({"host": "127.0.0.1"}))
        with mock.patch.object(review, "scan_printer_ports", return_value=[]):
            response = self.print_photo()
        self.assertEqual(response.status_code, 503)
        self.assertIn("Stampante non trovata", response.get_json()["error"])
        self.assertFalse(review.PRINT_EXPORT_ROOT.exists())
        self.assertEqual(sorted(path.name for path in self.photo_root.iterdir()), ["TEST.JPG"])
        report = self.client.get("/api/print/jobs/7").get_json()
        self.assertFalse(report["done"], "a missed status poll is retried")


if __name__ == "__main__":
    unittest.main()
