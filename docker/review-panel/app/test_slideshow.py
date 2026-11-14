# Copyright (c) 2026 Carmine Gallina - https://github.com/carminegallina
from pathlib import Path
from tempfile import TemporaryDirectory
import base64
import json
import unittest

import app as review


def file_id(relative):
    return base64.urlsafe_b64encode(relative.encode("utf-8")).decode("ascii").rstrip("=")


class SlideshowTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.storage = root / "storage"
        self.data = root / "data"
        self.data.mkdir()

        self.originals = {
            name: getattr(review, name)
            for name in (
                "STORAGE_ROOT", "TRASH_ROOT", "TRASH_FILE", "PHOTO_ROOT",
                "REVIEW_INDEX_FILE", "CACHE_ROOT", "DERIVATIVE_ROOT",
                "VIDEO_CACHE_ROOT", "SLIDESHOW_FILE",
            )
        }
        self.section_roots = {
            section: config["root"] for section, config in review.MEDIA_SECTIONS.items()
        }
        review.STORAGE_ROOT = self.storage
        review.TRASH_ROOT = self.storage / ".niwa_trash"
        review.TRASH_FILE = self.data / "review_trash.json"
        review.PHOTO_ROOT = self.storage / "photo"
        review.REVIEW_INDEX_FILE = self.data / "review_index.json"
        review.CACHE_ROOT = self.storage / ".niwa_cache" / "review_previews"
        review.DERIVATIVE_ROOT = self.storage / ".niwa_cache" / "review_media"
        review.VIDEO_CACHE_ROOT = self.storage / ".niwa_cache" / "review_video_thumbs"
        review.SLIDESHOW_FILE = self.data / "review_slideshow.json"
        for section, config in review.MEDIA_SECTIONS.items():
            config["root"] = self.storage / section

        for relative in ("photo/day1/DSC_1.NEF", "photo/day1/DSC_2.JPG", "video/clip.MP4"):
            path = self.storage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"media")
        self.client = review.app.test_client()

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(review, name, value)
        for section, root in self.section_roots.items():
            review.MEDIA_SECTIONS[section]["root"] = root
        self.temporary_directory.cleanup()

    def choose(self, section, relative, selected=True):
        return self.client.post(
            f"/api/slideshow/{section}/{file_id(relative)}", json={"selected": selected}
        )

    def shown(self):
        return [item["name"] for item in self.client.get("/api/slideshow").get_json()["items"]]

    def test_only_chosen_photos_are_shown_and_flagged(self):
        self.assertEqual(self.shown(), [])
        self.assertEqual(self.choose("photo", "day1/DSC_1.NEF").get_json()["selected"], True)

        self.assertEqual(self.shown(), ["DSC_1.NEF"])
        item = self.client.get("/api/slideshow").get_json()["items"][0]
        self.assertTrue(item["preview_url"].startswith("/api/media-image/viewer/photo/"))
        self.assertEqual((item["section"], item["slideshow"]), ("photo", True))
        flags = {
            item["name"]: item["slideshow"]
            for item in self.client.get("/api/media/photo").get_json()["items"]
        }
        self.assertEqual(flags, {"DSC_1.NEF": True, "DSC_2.JPG": False})
        saved = json.loads(review.SLIDESHOW_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["items"], ["photo/day1/DSC_1.NEF"])

        self.choose("photo", "day1/DSC_1.NEF", selected=False)
        self.assertEqual(self.shown(), [])

    def test_videos_and_missing_files_are_refused(self):
        self.assertEqual(self.choose("video", "clip.MP4").status_code, 400)
        self.assertEqual(self.choose("photo", "day1/missing.NEF").status_code, 404)
        self.assertFalse(review.SLIDESHOW_FILE.exists())

    def test_trashed_photo_leaves_the_show(self):
        self.choose("photo", "day1/DSC_2.JPG")
        self.assertEqual(self.shown(), ["DSC_2.JPG"])
        self.client.post("/api/media/photo/trash", json={"ids": [file_id("day1/DSC_2.JPG")]})
        self.assertEqual(self.shown(), [])

    def test_page_is_served(self):
        response = self.client.get("/slideshow")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/api/slideshow", response.data)
        response.close()


if __name__ == "__main__":
    unittest.main()
