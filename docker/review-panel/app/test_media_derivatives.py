from pathlib import Path
from tempfile import TemporaryDirectory
import base64
import io
import os
import unittest
from unittest import mock

from PIL import Image

import app as review


def media_id(relative):
    return base64.urlsafe_b64encode(relative.encode()).decode().rstrip("=")


class MediaDerivativeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.photo_root = root / "photo"
        self.photo_root.mkdir()
        self.derivative_root = root / "derivatives"
        self.originals = {
            "PHOTO_ROOT": review.PHOTO_ROOT,
            "DERIVATIVE_ROOT": review.DERIVATIVE_ROOT,
        }
        self.section_root = review.MEDIA_SECTIONS["photo"]["root"]
        review.PHOTO_ROOT = self.photo_root
        review.DERIVATIVE_ROOT = self.derivative_root
        review.MEDIA_SECTIONS["photo"]["root"] = self.photo_root
        self.source = self.photo_root / "large.JPG"
        Image.new("RGB", (3200, 2400), (160, 80, 40)).save(
            self.source, format="JPEG", quality=95
        )
        self.original = self.source.read_bytes()
        self.client = review.app.test_client()

    def tearDown(self):
        review.PHOTO_ROOT = self.originals["PHOTO_ROOT"]
        review.DERIVATIVE_ROOT = self.originals["DERIVATIVE_ROOT"]
        review.MEDIA_SECTIONS["photo"]["root"] = self.section_root
        self.temporary.cleanup()

    def test_gallery_and_viewer_use_bounded_cached_images(self):
        item = review.media_item_from_path("photo", self.source, Path("large.JPG"))
        self.assertNotEqual(item["thumbnail_url"], item["preview_url"])

        for url, maximum in (
            (item["thumbnail_url"], 640),
            (item["preview_url"], 2400),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn("immutable", response.headers["Cache-Control"])
            with Image.open(io.BytesIO(response.data)) as image:
                self.assertLessEqual(max(image.size), maximum)
            response.close()

        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(len(list(self.derivative_root.glob("*.jpg"))), 2)

    def test_unknown_variant_is_not_served(self):
        response = self.client.get(
            f"/api/media-image/original/photo/{media_id('large.JPG')}"
        )
        self.assertEqual(response.status_code, 404)

    def test_raw_derivatives_use_embedded_preview_and_apply_orientation(self):
        raw = self.photo_root / "vertical.NEF"
        raw.write_bytes(b"untouched raw")
        embedded = Path(self.temporary.name) / "embedded.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (1200, 800), "navy").save(
            embedded, format="JPEG", exif=exif
        )
        item = review.media_item_from_path("photo", raw, Path(raw.name))

        with mock.patch.object(
            review, "extract_raw_preview", return_value=embedded
        ) as extract:
            response = self.client.get(item["thumbnail_url"])
            self.assertEqual(response.status_code, 200)
            with Image.open(io.BytesIO(response.data)) as image:
                self.assertEqual(image.size, (427, 640))
            response.close()
            cached = self.client.get(item["thumbnail_url"])
            self.assertEqual(cached.status_code, 200)
            cached.close()

        extract.assert_called_once()
        self.assertEqual(raw.read_bytes(), b"untouched raw")

    def test_cache_limit_removes_oldest_files_first(self):
        cache = Path(self.temporary.name) / "limited-cache"
        cache.mkdir()
        files = []
        for index in range(3):
            path = cache / f"{index}.jpg"
            path.write_bytes(bytes([index]) * 10)
            path.touch()
            files.append(path)
        for index, path in enumerate(files):
            path.touch()
            os.utime(path, ns=(index + 1, index + 1))

        self.assertEqual(review.trim_cache(cache, 20), 1)
        self.assertFalse(files[0].exists())
        self.assertTrue(files[1].exists())
        self.assertTrue(files[2].exists())


if __name__ == "__main__":
    unittest.main()
