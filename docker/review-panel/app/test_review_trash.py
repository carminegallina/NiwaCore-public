# Copyright (c) 2026 Carmine Gallina - https://github.com/carminegallina
from pathlib import Path
from tempfile import TemporaryDirectory
import base64
import io
import json
import os
import threading
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import app as review


def file_id(relative):
    return base64.urlsafe_b64encode(relative.encode("utf-8")).decode("ascii").rstrip("=")


class ReviewTrashTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.storage = root / "storage"
        self.data = root / "data"
        self.photo = self.storage / "photo"
        self.photo.mkdir(parents=True)
        self.data.mkdir()

        self.originals = {
            name: getattr(review, name)
            for name in (
                "STORAGE_ROOT", "TRASH_ROOT", "TRASH_FILE", "PHOTO_ROOT",
                "REVIEW_INDEX_FILE", "CACHE_ROOT", "DERIVATIVE_ROOT",
                "VIDEO_CACHE_ROOT",
            )
        }
        self.section_roots = {
            section: config["root"] for section, config in review.MEDIA_SECTIONS.items()
        }
        review.STORAGE_ROOT = self.storage
        review.TRASH_ROOT = self.storage / ".niwa_trash"
        review.TRASH_FILE = self.data / "review_trash.json"
        review.PHOTO_ROOT = self.photo
        review.REVIEW_INDEX_FILE = self.data / "review_index.json"
        review.CACHE_ROOT = self.storage / ".niwa_cache" / "review_previews"
        review.DERIVATIVE_ROOT = self.storage / ".niwa_cache" / "review_media"
        review.VIDEO_CACHE_ROOT = self.storage / ".niwa_cache" / "review_video_thumbs"
        for section, config in review.MEDIA_SECTIONS.items():
            config["root"] = self.storage / section

        self.files = {
            "imports/day1/DSC_1.NEF": b"raw-one",
            "imports/day1/DSC_1.xmp": b"<x:xmpmeta/>",
            "imports/day1/DSC_2.NEF": b"raw-two",
            "imports/day2/DSC_3.JPG": b"jpeg-three",
        }
        for relative, content in self.files.items():
            path = self.photo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.client = review.app.test_client()

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(review, name, value)
        for section, root in self.section_roots.items():
            review.MEDIA_SECTIONS[section]["root"] = root
        self.temporary_directory.cleanup()

    def trash(self, *relatives):
        response = self.client.post(
            "/api/media/photo/trash",
            json={"ids": [file_id(relative) for relative in relatives]},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def deleted_paths(self):
        return json.loads(review.TRASH_FILE.read_text(encoding="utf-8"))["deleted_paths"]

    def test_raw_jpg_download_is_separate_from_original(self):
        raw_id = file_id("imports/day1/DSC_1.NEF")
        jpg_id = file_id("imports/day2/DSC_3.JPG")
        export = self.storage / "export.jpg"
        export.write_bytes(b"\xff\xd8jpg\xff\xd9")
        with mock.patch.object(review, "render_raw_jpg", return_value=export) as render:
            response = self.client.get(f"/api/download-jpg/photo/{raw_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, export.read_bytes())
        self.assertIn("DSC_1.jpg", response.headers["Content-Disposition"])
        render.assert_called_once()
        response.close()
        self.assertEqual(
            self.client.get(f"/api/download-jpg/photo/{jpg_id}").status_code,
            404,
        )
        original = self.client.get(f"/api/download/photo/{raw_id}")
        self.assertEqual(original.data, b"raw-one")
        original.close()

    def test_trash_moves_media_and_sidecar_then_removes_empty_folders(self):
        result = self.trash("imports/day1/DSC_1.NEF", "imports/day1/DSC_2.NEF")

        self.assertEqual(result["moved"], 2)
        # day1 lost every file, sidecar included, so the folder is gone too.
        self.assertFalse((self.photo / "imports" / "day1").exists())
        self.assertTrue((self.photo / "imports" / "day2" / "DSC_3.JPG").is_file())
        self.assertTrue(self.photo.is_dir())
        trashed = sorted(path.name for path in review.TRASH_ROOT.rglob("*") if path.is_file())
        self.assertEqual(trashed, ["DSC_1.NEF", "DSC_1.xmp", "DSC_2.NEF"])
        # Paths as NIWA Import records them, so it never imports them again.
        self.assertEqual(
            self.deleted_paths(),
            ["photo/imports/day1/DSC_1.NEF", "photo/imports/day1/DSC_2.NEF"],
        )
        listing = self.client.get("/api/trash").get_json()
        self.assertEqual(listing["count"], 2)
        self.assertEqual({item["folder"] for item in listing["items"]}, {"photo/imports/day1"})

    def test_trash_lists_media_in_the_same_order_as_the_gallery(self):
        (self.photo / "imports/day2/DSC_4.JPG").write_bytes(b"jpeg-four")
        # Capture times out of creation order, plus a burst within one second.
        captured = {
            "imports/day1/DSC_1.NEF": 1_700_000_300,
            "imports/day1/DSC_2.NEF": 1_700_000_100,
            "imports/day2/DSC_3.JPG": 1_700_000_200,
            "imports/day2/DSC_4.JPG": 1_700_000_200,
        }
        for relative, stamp in captured.items():
            os.utime(self.photo / relative, (stamp, stamp))
        review.rebuild_review_index()
        gallery = [
            item["relative_path"]
            for item in self.client.get("/api/media/photo").get_json()["items"]
        ]
        self.assertEqual(gallery, [
            "imports/day1/DSC_1.NEF",
            "imports/day2/DSC_4.JPG",
            "imports/day2/DSC_3.JPG",
            "imports/day1/DSC_2.NEF",
        ])

        # Deleted in two batches, in an order unrelated to the gallery.
        self.trash("imports/day2/DSC_3.JPG", "imports/day1/DSC_2.NEF")
        self.trash("imports/day1/DSC_1.NEF", "imports/day2/DSC_4.JPG")

        trash = [
            item["relative_path"]
            for item in self.client.get("/api/trash").get_json()["items"]
        ]
        self.assertEqual(trash, gallery)

    def test_keeps_a_folder_that_still_holds_other_files(self):
        (self.photo / "imports" / "day1" / "notes.txt").write_text("keep me")
        self.trash("imports/day1/DSC_1.NEF", "imports/day1/DSC_2.NEF")
        self.assertTrue((self.photo / "imports" / "day1" / "notes.txt").is_file())

    def test_restore_brings_back_folder_sidecar_and_drops_the_tombstone(self):
        self.trash("imports/day1/DSC_1.NEF", "imports/day1/DSC_2.NEF")
        items = {item["name"]: item["id"] for item in self.client.get("/api/trash").get_json()["items"]}

        restored = self.client.post("/api/trash/restore", json={"ids": [items["DSC_1.NEF"]]}).get_json()

        self.assertEqual(restored["restored"], 1)
        self.assertEqual((self.photo / "imports/day1/DSC_1.NEF").read_bytes(), b"raw-one")
        self.assertEqual((self.photo / "imports/day1/DSC_1.xmp").read_bytes(), b"<x:xmpmeta/>")
        self.assertEqual(self.deleted_paths(), ["photo/imports/day1/DSC_2.NEF"])

        everything = self.client.post("/api/trash/restore", json={"all": True}).get_json()
        self.assertEqual(everything["restored"], 1)
        self.assertEqual(self.deleted_paths(), [])
        self.assertEqual(self.client.get("/api/trash").get_json()["count"], 0)

    def test_empty_trash_needs_confirmation_and_keeps_tombstones(self):
        self.trash("imports/day1/DSC_2.NEF")

        refused = self.client.post("/api/trash/empty", json={})
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(self.client.get("/api/trash").get_json()["count"], 1)

        emptied = self.client.post("/api/trash/empty", json={"confirm": True}).get_json()
        self.assertEqual(emptied["removed"], 1)
        self.assertFalse(review.TRASH_ROOT.exists())
        self.assertEqual(self.client.get("/api/trash").get_json()["count"], 0)
        # Purged for good: still recorded, so the camera cannot bring it back.
        self.assertEqual(self.deleted_paths(), ["photo/imports/day1/DSC_2.NEF"])

    def test_download_streams_a_flat_zip_with_sidecars(self):
        response = self.client.post(
            "/api/media/photo/download",
            data={"ids": [file_id("imports/day1/DSC_1.NEF"), file_id("imports/day2/DSC_3.JPG")]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        with zipfile.ZipFile(io.BytesIO(response.get_data())) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                ["DSC_1.NEF", "DSC_1.xmp", "DSC_3.JPG"],
            )
            self.assertEqual(archive.read("DSC_3.JPG"), b"jpeg-three")

    def test_download_by_day_keeps_only_one_folder_level_and_renames_collisions(self):
        other = self.photo / "imports/day2/DSC_1.NEF"
        other.write_bytes(b"raw-other")
        for relative in ("imports/day1/DSC_1.NEF", "imports/day2/DSC_1.NEF"):
            path = self.photo / relative
            os.utime(path, (1725832800, 1725832800))
        response = self.client.post("/api/media/photo/download", data={
            "ids": [file_id("imports/day1/DSC_1.NEF"), file_id("imports/day2/DSC_1.NEF")],
            "by_day": "1",
        })
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.get_data())) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 3)
            self.assertTrue(all(name.count("/") == 1 for name in names))
            self.assertEqual(len(set(name.casefold() for name in names)), 3)
            self.assertIn(b"raw-one", [archive.read(name) for name in names])
            self.assertIn(b"raw-other", [archive.read(name) for name in names])

    def test_rejects_paths_outside_the_library(self):
        response = self.client.post("/api/media/photo/trash", json={"ids": [file_id("../secret.NEF")]})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(review.TRASH_FILE.exists())

    def test_recovers_a_moved_file_if_trash_json_save_is_interrupted(self):
        relative = "imports/day1/DSC_1.NEF"
        with mock.patch.object(review, "save_trash", side_effect=OSError("power loss")):
            with self.assertRaises(OSError):
                review.trash_media("photo", [file_id(relative)])

        self.assertFalse((self.photo / relative).exists())
        self.assertEqual(len(list(review.TRASH_ROOT.glob(f"*/{review.TRASH_JOURNAL_NAME}"))), 1)
        listing = self.client.get("/api/trash").get_json()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(self.deleted_paths(), [f"photo/{relative}"])
        restored = self.client.post("/api/trash/restore", json={"all": True}).get_json()
        self.assertEqual(restored["restored"], 1)
        self.assertTrue((self.photo / relative).is_file())

    def test_rolls_back_a_sidecar_if_media_move_is_interrupted(self):
        relative = "imports/day1/DSC_1.NEF"
        media = self.photo / relative
        real_replace = os.replace

        def interrupted_replace(source, destination):
            if Path(source) == media:
                raise OSError("power loss")
            return real_replace(source, destination)

        with mock.patch.object(review.os, "replace", side_effect=interrupted_replace):
            with self.assertRaises(OSError):
                review.trash_media("photo", [file_id(relative)])

        listing = self.client.get("/api/trash").get_json()
        self.assertEqual(listing["count"], 0)
        self.assertTrue(media.is_file())
        self.assertTrue(media.with_suffix(".xmp").is_file())

    def test_index_rebuilds_are_serialized(self):
        active = 0
        maximum = 0
        guard = threading.Lock()

        def slow_scan(_section, _kind):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.01)
            with guard:
                active -= 1
            return []

        with mock.patch.object(review, "scan_media_filesystem", side_effect=slow_scan):
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(lambda _value: review.rebuild_review_index(), range(2)))
        self.assertEqual(maximum, 1)


if __name__ == "__main__":
    unittest.main()
