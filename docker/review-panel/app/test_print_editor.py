# Copyright (c) 2026 Carmine Gallina - https://github.com/carminegallina
from pathlib import Path
from tempfile import TemporaryDirectory
import base64
import io
import unittest
from unittest import mock

from PIL import Image, ImageDraw

import app as review


def media_id(relative):
    return base64.urlsafe_b64encode(relative.encode()).decode().rstrip("=")


class PrintEditorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.photo_root = root / "photo"
        self.photo_root.mkdir()
        self.frame_root = root / "frames"
        self.export_root = root / "exports"
        self.preview_root = root / "previews"
        self.originals = {
            name: getattr(review, name)
            for name in ("PHOTO_ROOT", "PRINT_FRAME_ROOT", "PRINT_EXPORT_ROOT", "EDITOR_PREVIEW_ROOT")
        }
        review.PHOTO_ROOT = self.photo_root
        review.MEDIA_SECTIONS["photo"]["root"] = self.photo_root
        review.PRINT_FRAME_ROOT = self.frame_root
        review.PRINT_EXPORT_ROOT = self.export_root
        review.EDITOR_PREVIEW_ROOT = self.preview_root
        self.source = self.photo_root / "TEST.JPG"
        image = Image.new("RGB", (1600, 1200), "red")
        image.paste("blue", (800, 0, 1600, 1200))
        image.save(self.source, format="JPEG", quality=95)
        self.original_bytes = self.source.read_bytes()
        self.client = review.app.test_client()

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(review, name, value)
        review.MEDIA_SECTIONS["photo"]["root"] = self.originals["PHOTO_ROOT"]
        self.temporary.cleanup()

    def frame_png(self, size=(1748, 1181), transparent=True):
        image = Image.new("RGBA", size, (0, 180, 0, 255))
        if transparent:
            image.paste((0, 0, 0, 0), (55, 55, size[0] - 55, size[1] - 55))
        output = io.BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        return output

    def upload(self, image=None, preset="P", orientation="landscape"):
        return self.client.post("/api/print/frames", data={
            "name": "Cornice prova", "collection": "Fiera",
            "preset": preset, "orientation": orientation,
            "file": (image or self.frame_png(), "frame.png"),
        }, content_type="multipart/form-data")

    def test_frame_upload_validation_gallery_and_delete(self):
        self.assertEqual(self.upload(self.frame_png((1200, 1200))).status_code, 400)
        self.assertEqual(self.upload(self.frame_png(transparent=False)).status_code, 400)
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        frame = response.get_json()
        self.assertEqual(frame["preset"], "P")
        self.assertEqual(frame["collection"], "Fiera")
        self.assertEqual(len(self.client.get("/api/print/frames").get_json()["frames"]), 1)
        image_response = self.client.get(frame["url"])
        self.assertEqual(image_response.status_code, 200)
        image_response.close()
        thumbnail_response = self.client.get(frame["thumbnail_url"])
        self.assertEqual(thumbnail_response.status_code, 200)
        with Image.open(io.BytesIO(thumbnail_response.data)) as image:
            self.assertLessEqual(max(image.size), 280)
        thumbnail_response.close()
        self.assertEqual(self.client.delete(f"/api/print/frames/{frame['id']}").status_code, 200)
        self.assertEqual(self.client.get("/api/print/frames").get_json()["frames"], [])

    def test_export_jpg_png_and_original_preserved(self):
        frame = self.upload().get_json()
        payload = {
            "id": media_id("TEST.JPG"), "preset": "P",
            "orientation": "landscape", "frame_id": frame["id"],
            "zoom": 1, "offset_x": 0, "offset_y": 0,
            "rotation": 0, "exposure": 0.2, "contrast": 15,
            "temperature": 10, "tint": -5, "vibrance": 20,
            "saturation": 10, "luminance_noise": 25,
        }
        for file_type in ("jpg", "png"):
            response = self.client.post("/api/print/export", json={**payload, "file_type": file_type})
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            result = response.get_json()
            self.assertEqual((self.export_root / result["name"]).is_file(), True,
                             "print exports have no collection subfolder")
            download = self.client.get(result["download_url"])
            self.assertEqual(download.status_code, 200)
            with Image.open(io.BytesIO(download.data)) as image:
                self.assertEqual(image.size, (1872, 1248), "the SELPHY's whole page")
                self.assertEqual(image.getpixel((0, 0))[1] > 120, True)
                self.assertEqual(image.getpixel((1200, 600))[2] > 50, True)
            download.close()
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_jpg_export_is_kept_beside_the_photo(self):
        payload = {"id": media_id("TEST.JPG"), "preset": "P",
                   "orientation": "landscape", "file_type": "jpg"}
        beside = self.photo_root / "TEST_stampa-P.jpg"
        first = self.client.post("/api/print/export", json=payload).get_json()
        self.assertEqual(first["beside_original"], beside.name)
        download = self.client.get(first["download_url"])
        self.assertEqual(beside.read_bytes(), download.data)
        download.close()
        self.assertEqual(beside.stat().st_mtime_ns, self.source.stat().st_mtime_ns,
                         "the gallery lists it beside the photo")

        second = self.client.post("/api/print/export", json={**payload, "exposure": 1}).get_json()
        self.assertEqual(second["beside_original"], beside.name)
        download = self.client.get(second["download_url"])
        self.assertEqual(beside.read_bytes(), download.data, "the latest export wins")
        download.close()
        png = self.client.post("/api/print/export", json={**payload, "file_type": "png"}).get_json()
        self.assertIsNone(png["beside_original"])
        self.assertEqual(sorted(path.name for path in self.photo_root.iterdir()),
                         ["TEST.JPG", "TEST_stampa-P.jpg"])
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_framed_filter_only_marks_confirmed_framed_copies(self):
        frame = self.upload().get_json()
        payload = {"id": media_id("TEST.JPG"), "preset": "P", "orientation": "landscape"}
        response = self.client.post("/api/print/export", json={**payload, "frame_id": frame["id"]})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        items = review.scan_media_filesystem("photo")
        framed = [item for item in items if item["framed"]]
        self.assertEqual([item["name"] for item in framed], ["TEST_stampa-P.jpg"])
        with mock.patch.object(review, "scan_media", return_value=items), \
             mock.patch.object(review, "get_review_index", return_value={"sections": {}}):
            result = self.client.get("/api/media/photo?frame=1").get_json()
            self.assertEqual([item["name"] for item in result["items"]], ["TEST_stampa-P.jpg"])
        unframed = self.client.post("/api/print/export", json=payload)
        self.assertEqual(unframed.status_code, 200)
        self.assertFalse(any(item["framed"] for item in review.scan_media_filesystem("photo")),
                         "a new unframed export replaces the old framed copy")

    def test_export_rejects_mismatch_and_uncovered_photo(self):
        frame = self.upload().get_json()
        base = {"id": media_id("TEST.JPG"), "preset": "P", "orientation": "landscape"}
        mismatch = self.client.post("/api/print/export", json={**base, "frame_id": frame["id"], "preset": "C"})
        self.assertEqual(mismatch.status_code, 400)
        uncovered = self.client.post("/api/print/export", json={**base, "zoom": 1, "offset_x": 0.4})
        self.assertEqual(uncovered.status_code, 400)
        self.assertIn("copre", uncovered.get_json()["error"])
        invalid = self.client.post("/api/print/export", json={**base, "zoom": "nan"})
        self.assertEqual(invalid.status_code, 400)
        for field, value in (("contrast", 101), ("temperature", -101),
                             ("luminance_noise", 101)):
            invalid = self.client.post("/api/print/export", json={**base, field: value})
            self.assertEqual(invalid.status_code, 400)

    def test_no_frame_original_format_preserves_photo_ratio(self):
        response = self.client.post("/api/print/export", json={
            "id": media_id("TEST.JPG"), "preset": "original",
            "orientation": "landscape", "file_type": "jpg",
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        result = response.get_json()
        self.assertEqual((result["width"], result["height"]), (1600, 1200))
        download = self.client.get(result["download_url"])
        with Image.open(io.BytesIO(download.data)) as image:
            self.assertEqual(image.size, (1600, 1200))
        download.close()

        rejected_frame = self.upload(preset="original")
        self.assertEqual(rejected_frame.status_code, 400)

    def test_color_and_luminance_controls_change_only_the_export(self):
        source = Image.new("RGB", (40, 40))
        for y in range(40):
            for x in range(40):
                value = 120 if (x + y) % 2 else 136
                source.putpixel((x, y), (value, value, value))
        reduced = review.reduce_luminance_noise(source, 1)
        before = abs(source.getpixel((20, 20))[0] - source.getpixel((21, 20))[0])
        after = abs(reduced.getpixel((20, 20))[0] - reduced.getpixel((21, 20))[0])
        self.assertLess(after, before / 2)
        self.assertEqual(source.getpixel((20, 20)), (136, 136, 136))
        colored = review.apply_color_controls(Image.new("RGB", (1, 1), (100, 100, 100)),
                                              0, 1, 0, 0, 0)
        self.assertGreater(colored.getpixel((0, 0))[0], colored.getpixel((0, 0))[2])

    def test_selphy_page_puts_the_card_between_the_measured_perforations(self):
        card = Image.new("RGB", (1748, 1181), (30, 60, 220))
        ImageDraw.Draw(card).rectangle((0, 0, 1747, 1180), outline=(220, 30, 30), width=30)
        page = review.selphy_page(card, "P", "landscape")
        self.assertEqual(page.size, (1872, 1248))
        mm = 300 / 25.4
        left, right = round(3.5 * mm), 1872 - round(5.0 * mm)
        red = lambda x, y: page.getpixel((x, y))[0] > 150
        self.assertTrue(red(left - 20, 624), "the torn-off bleed continues the border")
        self.assertTrue(red(left + 10, 624) and not red(left + 50, 624), "card edge at 3.5 mm")
        self.assertTrue(red(right - 10, 624) and not red(right - 50, 624), "card edge at 5 mm")
        self.assertTrue(red(936, round(2.5 * mm) + 10) and not red(936, round(2.5 * mm) + 50))
        self.assertIs(review.selphy_page(card, "C", "landscape"), card, "unmeasured paper stays as is")
        portrait = review.selphy_page(card.rotate(90, expand=True), "P", "portrait")
        self.assertEqual(portrait.size, (1248, 1872))
        top, bottom = round(3.5 * mm), 1872 - round(5.0 * mm)
        red = lambda x, y: portrait.getpixel((x, y))[0] > 150
        self.assertTrue(red(624, top + 10) and not red(624, top + 50), "perforation 3.5 mm from the top")
        self.assertTrue(red(624, bottom - 10) and not red(624, bottom - 50), "perforation 5 mm from the bottom")
        direct = review.selphy_page(card, "P", "landscape", direct=True)
        left, right = round(4.5 * mm), 1872 - round(6.0 * mm)
        red = lambda x, y: direct.getpixel((x, y))[0] > 150
        self.assertTrue(red(left + 10, 624) and not red(left + 50, 624), "direct print: 4.5 mm")
        self.assertTrue(red(right - 10, 624) and not red(right - 50, 624), "direct print: 6 mm")

    def test_rotation_keeps_the_photo_covering_the_print(self):
        base = {"id": media_id("TEST.JPG"), "preset": "P", "orientation": "portrait"}
        uncovered = self.client.post("/api/print/export", json={**base, "rotation": 45, "zoom": 1})
        self.assertEqual(uncovered.status_code, 400)
        response = self.client.post("/api/print/export", json={**base, "rotation": 45, "zoom": 1.2})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        response = self.client.post("/api/print/export", json={**base, "rotation": 90, "zoom": 1})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        download = self.client.get(response.get_json()["download_url"])
        with Image.open(io.BytesIO(download.data)) as image:
            self.assertEqual(image.size, (1248, 1872))
            # A clockwise quarter turn brings the red left half to the top.
            top, bottom = image.getpixel((624, 150)), image.getpixel((624, 1720))
        download.close()
        self.assertGreater(top[0], top[2])
        self.assertGreater(bottom[2], bottom[0])

    def test_frame_border_allows_movement_without_changing_zoom(self):
        frame = self.upload().get_json()
        base = {
            "id": media_id("TEST.JPG"), "preset": "P", "orientation": "landscape",
            "frame_id": frame["id"], "zoom": 1,
        }
        shifted = self.client.post("/api/print/export", json={**base, "offset_x": 0.02})
        self.assertEqual(shifted.status_code, 200, shifted.get_data(as_text=True))
        too_far = self.client.post("/api/print/export", json={**base, "offset_x": 0.1})
        self.assertEqual(too_far.status_code, 400)

    def test_high_zoom_allows_larger_pan_but_still_rejects_uncovered_photo(self):
        base = {"id": media_id("TEST.JPG"), "preset": "P", "orientation": "landscape",
                "zoom": 4}
        shifted = self.client.post("/api/print/export", json={**base, "offset_x": 0.8})
        self.assertEqual(shifted.status_code, 200, shifted.get_data(as_text=True))
        uncovered = self.client.post("/api/print/export", json={**base, "offset_x": 3})
        self.assertEqual(uncovered.status_code, 400)


if __name__ == "__main__":
    unittest.main()
