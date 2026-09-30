from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import os
import time
import unittest


MODULE_PATH = Path(__file__).with_name("niwa_import.py")
SPEC = importlib.util.spec_from_file_location("niwa_import", MODULE_PATH)
niwa_import = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(niwa_import)


class NiwaImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source"
        self.storage = self.root / "storage"
        self.data = self.root / "data"
        self.mount = self.root / "mount"
        self.source.mkdir()
        self.storage.mkdir()
        self.data.mkdir()
        self.mount.mkdir()

        self.originals = {
            "DATA_ROOT": niwa_import.DATA_ROOT,
            "STORAGE_ROOT": niwa_import.STORAGE_ROOT,
            "MOUNT_ROOT": niwa_import.MOUNT_ROOT,
            "STAGING_ROOT": niwa_import.STAGING_ROOT,
            "BRIDGE_STAGING_ROOT": niwa_import.BRIDGE_STAGING_ROOT,
            "CONFIG_FILE": niwa_import.CONFIG_FILE,
            "JOBS_FILE": niwa_import.JOBS_FILE,
            "HASHES_FILE": niwa_import.HASHES_FILE,
            "BRIDGE_SESSIONS_FILE": niwa_import.BRIDGE_SESSIONS_FILE,
            "BRIDGE_TOKEN_FILE": niwa_import.BRIDGE_TOKEN_FILE,
            "BRIDGE_TOKEN": niwa_import.BRIDGE_TOKEN,
            "BRIDGE_MIN_FREE_BYTES": niwa_import.BRIDGE_MIN_FREE_BYTES,
            "mount_readonly": niwa_import.mount_readonly,
            "safe_unmount": niwa_import.safe_unmount,
            "review_rebuild": niwa_import.review_rebuild,
            "copy_and_verify": niwa_import.copy_and_verify,
            "command_json": niwa_import.command_json,
            "bridge_save_sessions": niwa_import.bridge_save_sessions,
        }
        niwa_import.DATA_ROOT = self.data
        niwa_import.STORAGE_ROOT = self.storage
        niwa_import.MOUNT_ROOT = self.mount
        niwa_import.STAGING_ROOT = self.storage / ".niwa_import_staging"
        niwa_import.BRIDGE_STAGING_ROOT = self.storage / ".niwa_bridge_staging"
        niwa_import.CONFIG_FILE = self.data / "import_sources.json"
        niwa_import.JOBS_FILE = self.data / "import_jobs.json"
        niwa_import.HASHES_FILE = self.data / "import_hashes.json"
        niwa_import.BRIDGE_SESSIONS_FILE = self.data / "bridge_sessions.json"
        niwa_import.BRIDGE_TOKEN_FILE = self.data / "bridge_token"
        niwa_import.BRIDGE_TOKEN = ""
        niwa_import.BRIDGE_MIN_FREE_BYTES = 1024
        niwa_import.mount_readonly = lambda _device: (self.source, False)
        niwa_import.safe_unmount = lambda _mountpoint: None
        niwa_import.review_rebuild = lambda: True

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(niwa_import, name, value)
        self.temporary_directory.cleanup()

    def device(self):
        return {
            "id": "abc12345abc12345abc12345abc12345abc12345",
            "device": "/dev/sdz1",
            "label": "TESTCARD",
        }

    def write_source(self, relative, content):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def test_camera_import_routes_media_and_ignores_gopro_proxy_files(self):
        self.write_source("DCIM/100NZ6_2/DSC_0001.NEF", b"raw")
        self.write_source("DCIM/100NZ6_2/DSC_0001.JPG", b"jpg")
        self.write_source("PRIVATE/VIDEO_001.MOV", b"video")
        self.write_source("DCIM/100GOPRO/GX010001.LRV", b"proxy")
        self.write_source("DCIM/100GOPRO/GX010001.THM", b"thumb")

        niwa_import.run_import(self.device(), "camera", "test")

        jobs = niwa_import.load_jobs()["jobs"]
        self.assertEqual(jobs[0]["status"], "completed")
        self.assertEqual(jobs[0]["published_files"], 3)
        self.assertEqual(len(list((self.storage / "photo").rglob("*.NEF"))), 1)
        self.assertEqual(len(list((self.storage / "photo").rglob("*.JPG"))), 1)
        self.assertEqual(len(list((self.storage / "video").rglob("*.MOV"))), 1)
        self.assertEqual(len(list(self.storage.rglob("*.LRV"))), 0)
        self.assertEqual(len(list(self.storage.rglob("*.THM"))), 0)

    def test_repeated_import_skips_matching_checksums(self):
        self.write_source("DCIM/100NZ6_2/DSC_0001.NEF", b"raw")

        niwa_import.run_import(self.device(), "camera", "test")
        calls = []
        original_copy = niwa_import.copy_and_verify

        def track_copy(source, staged_path):
            calls.append((source, staged_path))
            return original_copy(source, staged_path)

        niwa_import.copy_and_verify = track_copy
        niwa_import.run_import(self.device(), "camera", "test")

        jobs = niwa_import.load_jobs()["jobs"]
        self.assertEqual(jobs[0]["status"], "completed")
        self.assertEqual(jobs[0]["published_files"], 0)
        self.assertEqual(jobs[0]["duplicate_files"], 1)
        self.assertEqual(jobs[0]["fast_skipped_files"], 1)
        self.assertEqual(jobs[0]["bytes_copied"], 0)
        self.assertEqual(calls, [])
        self.assertEqual(len(list((self.storage / "photo").rglob("*.NEF"))), 1)

    def test_repeated_import_recopies_when_cached_destination_was_corrupted(self):
        relative = Path("DCIM/100NZ6_2/DSC_0002.NEF")
        source_content = bytearray(b"A" * (512 * 1024))
        self.write_source(relative, bytes(source_content))
        niwa_import.run_import(self.device(), "camera", "test")
        first_destination = next((self.storage / "photo").rglob("DSC_0002.NEF"))
        corrupted = bytearray(source_content)
        corrupted[100000] = ord("B")
        first_destination.write_bytes(corrupted)
        self.assertEqual(
            niwa_import.quick_fingerprint(self.source / relative)["quick_hash"],
            niwa_import.quick_fingerprint(first_destination)["quick_hash"],
        )

        niwa_import.run_import(self.device(), "camera", "test")

        job = niwa_import.load_jobs()["jobs"][0]
        digest = niwa_import.sha256_file(self.source / relative)
        repaired = Path(niwa_import.load_hashes()["files"][digest])
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["fast_skipped_files"], 0)
        self.assertEqual(job["published_files"], 1)
        self.assertEqual(repaired.read_bytes(), bytes(source_content))
        self.assertNotEqual(repaired, first_destination)

    def test_existing_hash_index_bootstraps_fast_skip_without_copy(self):
        relative = Path("DCIM/100GOPRO/GX010001.MP4")
        self.write_source(relative, b"video")
        destination = self.storage / "gopro" / "imports" / "old-session" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"video")
        digest = niwa_import.sha256_file(destination)
        niwa_import.save_hashes({"version": 1, "files": {digest: str(destination)}})

        def fail_copy(_source, _staged_path):
            raise AssertionError("existing verified file should not be copied again")

        niwa_import.copy_and_verify = fail_copy
        niwa_import.run_import(self.device(), "gopro", "test")

        job = niwa_import.load_jobs()["jobs"][0]
        hashes = niwa_import.load_hashes()
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["fast_skipped_files"], 1)
        self.assertEqual(job["bytes_copied"], 0)
        self.assertTrue(hashes["sources"])

    def test_card_import_does_not_discard_staging_for_corrupt_hash_index_target(self):
        relative = Path("DCIM/100NZ6_2/DSC_0099.NEF")
        good_content = b"good-nef-content"
        corrupt_content = b"bad!-nef-content"
        self.assertEqual(len(good_content), len(corrupt_content))
        self.write_source(relative, good_content)
        digest = niwa_import.sha256_file(self.source / relative)
        corrupt = self.storage / "photo" / "imports" / "old-session" / relative
        corrupt.parent.mkdir(parents=True, exist_ok=True)
        corrupt.write_bytes(corrupt_content)
        niwa_import.save_hashes({
            "version": 3,
            "files": {digest: str(corrupt)},
            "sources": {},
        })

        niwa_import.run_import(self.device(), "camera", "test")

        job = niwa_import.load_jobs()["jobs"][0]
        indexed = Path(niwa_import.load_hashes()["files"][digest])
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["published_files"], 1)
        self.assertNotEqual(indexed, corrupt)
        self.assertEqual(indexed.read_bytes(), good_content)
        self.assertEqual(corrupt.read_bytes(), corrupt_content)

    def test_interrupted_copy_never_publishes_partial_media(self):
        self.write_source("DCIM/100NZ6_2/DSC_0001.NEF", b"raw")

        def fail_copy(_source, _staged_path):
            raise OSError("simulated card removal")

        niwa_import.copy_and_verify = fail_copy
        niwa_import.run_import(self.device(), "camera", "test")

        jobs = niwa_import.load_jobs()["jobs"]
        self.assertEqual(jobs[0]["status"], "interrupted")
        self.assertEqual(len(list((self.storage / "photo").rglob("*.NEF"))), 0)

    def test_cleanup_removes_only_expired_inactive_staging(self):
        old_job = self.storage / ".niwa_import_staging" / "old-job"
        active_job = self.storage / ".niwa_import_staging" / "active-job"
        recent_job = self.storage / ".niwa_import_staging" / "recent-job"
        for directory in (old_job, active_job, recent_job):
            directory.mkdir(parents=True)
            (directory / "partial.tmp").write_bytes(b"partial")

        old_time = time.time() - 7200
        os.utime(old_job, (old_time, old_time))
        os.utime(active_job, (old_time, old_time))

        removed = niwa_import.cleanup_old_staging(
            max_age_seconds=3600,
            active_job_id="active-job",
        )

        self.assertEqual(removed, 1)
        self.assertFalse(old_job.exists())
        self.assertTrue(active_job.exists())
        self.assertTrue(recent_job.exists())

    def test_scan_excludes_niwa_storage_and_keeps_unknown_card_pending(self):
        niwa_import.command_json = lambda _command: {
            "blockdevices": [
                {
                    "name": "sda",
                    "path": "/dev/sda",
                    "type": "disk",
                    "size": 240000000000,
                    "serial": "41RB806NKFU2",
                    "children": [
                        {
                            "name": "sda1",
                            "path": "/dev/sda1",
                            "type": "part",
                            "size": 240000000000,
                            "fstype": "ext4",
                            "uuid": "7ca9f987-1382-4e77-85d9-84a6424c7425",
                            "mountpoints": ["/mnt/niwa-storage"],
                        }
                    ],
                },
                {
                    "name": "sdb",
                    "path": "/dev/sdb",
                    "type": "disk",
                    "size": 64000000000,
                    "serial": "reader-card",
                    "children": [
                        {
                            "name": "sdb1",
                            "path": "/dev/sdb1",
                            "type": "part",
                            "size": 64000000000,
                            "fstype": "exfat",
                            "uuid": "camera-card-uuid",
                            "mountpoints": [],
                        }
                    ],
                },
                {
                    "name": "zram0",
                    "path": "/dev/zram0",
                    "type": "disk",
                    "size": 2000000000,
                    "fstype": "swap",
                    "uuid": "swap-uuid",
                    "mountpoints": ["[SWAP]"],
                },
            ]
        }

        devices = niwa_import.scan_devices(include_ignored=True)
        by_device = {device["device"]: device for device in devices}
        self.assertEqual(by_device["/dev/sda1"]["status"], "ignored")
        self.assertEqual(by_device["/dev/sdb1"]["status"], "unknown")
        self.assertEqual(by_device["/dev/zram0"]["status"], "ignored")

    def test_card_without_uuid_can_be_approved_with_reader_fingerprint(self):
        niwa_import.command_json = lambda _command: {
            "blockdevices": [
                {
                    "name": "sdb",
                    "path": "/dev/sdb",
                    "type": "disk",
                    "size": 64000000000,
                    "model": "SDDR-A631",
                    "serial": "reader-card",
                    "hctl": "1:0:0:0",
                    "children": [
                        {
                            "name": "sdb1",
                            "path": "/dev/sdb1",
                            "type": "part",
                            "partn": 1,
                            "size": 64000000000,
                            "fstype": "exfat",
                            "uuid": None,
                            "mountpoints": [],
                        }
                    ],
                },
            ]
        }

        devices = niwa_import.scan_devices(include_ignored=False)
        niwa_import.approve_source(devices[0]["id"], "gopro", True)
        approved = niwa_import.scan_devices(include_ignored=False)[0]

        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["profile"], "gopro")
        self.assertTrue(approved["auto_import"])
        self.assertEqual(approved["source"]["identity_method"], "reader_card_fingerprint")

    def test_bridge_resumes_verifies_then_publishes_atomically(self):
        content = (b"NEF-test-block-" * 12000) + b"end"
        sample = self.root / "sample.NEF"
        sample.write_bytes(content)
        quick_hash = niwa_import.quick_fingerprint(sample)["quick_hash"]
        digest = niwa_import.sha256_file(sample)

        created = niwa_import.bridge_create_session({
            "source_id": "nikon-test",
            "camera_model": "Nikon Z6 II",
            "client_id": "esp32-s3",
        })
        session_id = created["session_id"]
        preflight = niwa_import.bridge_preflight(session_id, {
            "object_id": "1001",
            "source_key": "storage-1:1001:DSC_0001.NEF",
            "filename": "DSC_0001.NEF",
            "size": len(content),
            "quick_hash": quick_hash,
        })
        self.assertEqual(preflight["action"], "upload")
        upload_id = preflight["upload_id"]

        split = 70000
        first = niwa_import.bridge_receive_chunk(
            upload_id,
            0,
            split - 1,
            len(content),
            content[:split],
        )
        self.assertEqual(first["offset"], split)
        resumed = niwa_import.bridge_get_upload(upload_id)
        self.assertEqual(resumed["upload"]["offset"], split)
        with self.assertRaises(niwa_import.ApiError) as conflict:
            niwa_import.bridge_receive_chunk(
                upload_id,
                0,
                9,
                len(content),
                content[:10],
            )
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(conflict.exception.details["expected_offset"], split)

        niwa_import.bridge_receive_chunk(
            upload_id,
            split,
            len(content) - 1,
            len(content),
            content[split:],
        )
        verified = niwa_import.bridge_complete_upload(
            upload_id,
            {"sha256": digest},
        )
        self.assertEqual(verified["sha256"], digest)
        self.assertEqual(list((self.storage / "photo").rglob("*.NEF")), [])

        completed = niwa_import.bridge_complete_session(session_id)
        self.assertEqual(completed["session"]["status"], "completed")
        self.assertNotIn("objects", completed["session"])
        published = list((self.storage / "photo").rglob("DSC_0001.NEF"))
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].read_bytes(), content)
        self.assertEqual(niwa_import.load_hashes()["files"][digest], str(published[0]))
        source_entries = [
            entry
            for inventory in niwa_import.load_hashes()["sources"].values()
            for entry in inventory.values()
        ]
        self.assertTrue(any(entry.get("quick_hash") == quick_hash for entry in source_entries))

    def test_bridge_recovers_verified_rename_before_json_save(self):
        content = b"legacy-power-loss" * 4000
        digest = niwa_import.hashlib.sha256(content).hexdigest()
        created = niwa_import.bridge_create_session({"source_id": "camera-a"})
        preflight = niwa_import.bridge_preflight(created["session_id"], {
            "object_id": "1101",
            "source_key": "camera-a:1101",
            "filename": "DSC_1101.NEF",
            "size": len(content),
        })
        niwa_import.bridge_receive_chunk(
            preflight["upload_id"],
            0,
            len(content) - 1,
            len(content),
            content,
        )
        sessions = niwa_import.bridge_load_sessions()
        session = sessions["sessions"][created["session_id"]]
        item = session["objects"]["1101"]
        partial = niwa_import.bridge_staged_path(session, item)
        legacy_verified = partial.with_suffix(".verified")
        os.replace(partial, legacy_verified)

        verified = niwa_import.bridge_complete_upload(
            preflight["upload_id"],
            {"sha256": digest},
        )

        self.assertEqual(verified["status"], "verified")
        repaired = niwa_import.bridge_load_sessions()["sessions"][
            created["session_id"]
        ]["objects"]["1101"]
        self.assertEqual(repaired["staged_name"], legacy_verified.name)
        completed = niwa_import.bridge_complete_session(created["session_id"])
        self.assertEqual(completed["session"]["status"], "completed")
        published = list((self.storage / "photo").rglob("DSC_1101.NEF"))
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0].read_bytes(), content)

    def test_bridge_recovers_destination_rename_before_index_and_session_save(self):
        content = b"publish-power-loss" * 4000
        digest = niwa_import.hashlib.sha256(content).hexdigest()
        created = niwa_import.bridge_create_session({"source_id": "camera-a"})
        preflight = niwa_import.bridge_preflight(created["session_id"], {
            "object_id": "1201",
            "source_key": "camera-a:1201",
            "filename": "DSC_1201.JPG",
            "size": len(content),
        })
        niwa_import.bridge_receive_chunk(
            preflight["upload_id"],
            0,
            len(content) - 1,
            len(content),
            content,
        )
        niwa_import.bridge_complete_upload(
            preflight["upload_id"],
            {"sha256": digest},
        )
        sessions = niwa_import.bridge_load_sessions()
        session = sessions["sessions"][created["session_id"]]
        item = session["objects"]["1201"]
        staged = niwa_import.bridge_staged_path(session, item)
        wanted = (
            self.storage
            / "photo"
            / "imports"
            / session["folder"]
            / item["filename"]
        )
        wanted.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, wanted)

        completed = niwa_import.bridge_complete_session(created["session_id"])

        self.assertEqual(completed["session"]["status"], "completed")
        repaired = niwa_import.bridge_load_sessions()["sessions"][
            created["session_id"]
        ]["objects"]["1201"]
        self.assertEqual(repaired["status"], "published")
        self.assertEqual(Path(repaired["destination"]), wanted)
        self.assertEqual(niwa_import.load_hashes()["files"][digest], str(wanted))
        self.assertEqual(wanted.read_bytes(), content)

    def test_bridge_complete_response_stays_compact_with_many_objects(self):
        created = niwa_import.bridge_create_session({"source_id": "camera-a"})
        sessions = niwa_import.bridge_load_sessions()
        session = sessions["sessions"][created["session_id"]]
        session["objects"] = {
            str(index): {
                "object_id": str(index),
                "source_key": f"camera-a:{index}",
                "filename": f"DSC_{index:04d}.JPG",
                "size": 1,
                "status": "duplicate",
                "duplicate": True,
                "received": 1,
                "digest": "0" * 64,
                "upload_id": None,
                "staged_name": None,
                "destination": None,
            }
            for index in range(250)
        }
        niwa_import.bridge_save_sessions(sessions)

        completed = niwa_import.bridge_complete_session(created["session_id"])

        self.assertNotIn("objects", completed["session"])
        self.assertEqual(completed["session"]["total_objects"], 250)
        self.assertEqual(completed["session"]["duplicate_objects"], 250)
        self.assertFalse(completed["session"]["review_rebuild"])

    def test_bridge_quick_hash_preflight_skips_existing_verified_file(self):
        content = b"same-photo" * 9000
        sample = self.root / "same.JPG"
        sample.write_bytes(content)
        quick_hash = niwa_import.quick_fingerprint(sample)["quick_hash"]
        digest = niwa_import.sha256_file(sample)

        first_session = niwa_import.bridge_create_session({"source_id": "nikon-test"})
        first = niwa_import.bridge_preflight(first_session["session_id"], {
            "object_id": "2001",
            "source_key": "first-source-key",
            "filename": "DSC_2001.JPG",
            "size": len(content),
            "quick_hash": quick_hash,
        })
        niwa_import.bridge_receive_chunk(
            first["upload_id"],
            0,
            len(content) - 1,
            len(content),
            content,
        )
        niwa_import.bridge_complete_upload(first["upload_id"], {"sha256": digest})
        niwa_import.bridge_complete_session(first_session["session_id"])

        rebuild_calls = []
        niwa_import.review_rebuild = lambda: rebuild_calls.append(True) or True
        second_session = niwa_import.bridge_create_session({"source_id": "nikon-test"})
        second = niwa_import.bridge_preflight(second_session["session_id"], {
            "object_id": "2002",
            "source_key": "first-source-key",
            "filename": "DSC_2001.JPG",
            "size": len(content),
            "quick_hash": quick_hash,
        })
        self.assertEqual(second["action"], "skip")
        self.assertEqual(second["reason"], "quick_hash")
        self.assertEqual(second["sha256"], digest)
        completed = niwa_import.bridge_complete_session(second_session["session_id"])
        self.assertEqual(completed["session"]["duplicate_objects"], 1)
        self.assertFalse(completed["session"]["review_rebuild"])
        self.assertEqual(rebuild_calls, [])
        self.assertEqual(len(list((self.storage / "photo").rglob("*.JPG"))), 1)

    def test_bridge_rejects_unsafe_filename_and_checks_optional_token(self):
        session = niwa_import.bridge_create_session({"source_id": "nikon-test"})
        with self.assertRaises(niwa_import.ApiError):
            niwa_import.bridge_preflight(session["session_id"], {
                "object_id": "3001",
                "filename": "../escape.NEF",
                "size": 100,
            })

        niwa_import.BRIDGE_TOKEN = "runtime-secret"
        self.assertFalse(niwa_import.bridge_authorization_valid(""))
        self.assertFalse(niwa_import.bridge_authorization_valid("Bearer wrong"))
        self.assertTrue(
            niwa_import.bridge_authorization_valid("Bearer runtime-secret")
        )

    def test_bridge_generates_and_reuses_persistent_root_only_token(self):
        first = niwa_import.ensure_bridge_token()
        self.assertGreaterEqual(len(first), 32)
        self.assertEqual(
            niwa_import.BRIDGE_TOKEN_FILE.read_text(encoding="utf-8").strip(),
            first,
        )
        if os.name == "posix":
            self.assertEqual(
                niwa_import.BRIDGE_TOKEN_FILE.stat().st_mode & 0o077,
                0,
            )

        niwa_import.BRIDGE_TOKEN = ""
        second = niwa_import.ensure_bridge_token()

        self.assertEqual(second, first)
        self.assertTrue(niwa_import.bridge_loopback_address("127.0.0.1"))
        self.assertTrue(niwa_import.bridge_loopback_address("::1"))
        self.assertFalse(niwa_import.bridge_loopback_address("10.42.0.103"))

    def test_bridge_session_creation_resumes_same_source_and_client(self):
        first = niwa_import.bridge_create_session({
            "source_id": "camera-a",
            "client_id": "esp32-a",
        })
        resumed = niwa_import.bridge_create_session({
            "source_id": "camera-a",
            "client_id": "esp32-a",
        })
        sessions = niwa_import.bridge_load_sessions()
        sessions["sessions"][first["session_id"]]["status"] = "completing"
        niwa_import.bridge_save_sessions(sessions)
        recovered = niwa_import.bridge_create_session({
            "source_id": "camera-a",
            "client_id": "esp32-a",
        })
        different = niwa_import.bridge_create_session({
            "source_id": "camera-a",
            "client_id": "esp32-b",
        })

        self.assertFalse(first["resumed"])
        self.assertTrue(resumed["resumed"])
        self.assertEqual(resumed["session_id"], first["session_id"])
        self.assertTrue(recovered["resumed"])
        self.assertEqual(recovered["status"], "active")
        self.assertEqual(
            niwa_import.bridge_load_sessions()["sessions"][
                first["session_id"]
            ]["status"],
            "active",
        )
        usable = niwa_import.bridge_preflight(recovered["session_id"], {
            "object_id": "resume-check",
            "filename": "RESUME.JPG",
            "size": 1,
        })
        self.assertEqual(usable["action"], "upload")
        self.assertNotEqual(different["session_id"], first["session_id"])

    def test_bridge_preserves_ptp_capture_time_only_for_new_publication(self):
        content = b"photo-with-capture-time" * 5000
        digest = niwa_import.hashlib.sha256(content).hexdigest()
        captured_at = "20260723T123337"
        expected_mtime = niwa_import.datetime.strptime(
            captured_at,
            "%Y%m%dT%H%M%S",
        ).timestamp()
        first = niwa_import.bridge_create_session({
            "source_id": "camera-a",
            "client_id": "esp32-a",
        })
        upload = niwa_import.bridge_preflight(first["session_id"], {
            "object_id": "3301",
            "source_key": "camera-a:3301",
            "filename": "DSC_3301.JPG",
            "size": len(content),
            "captured_at": captured_at,
            "modified_at": "20260723T123400",
        })
        niwa_import.bridge_receive_chunk(
            upload["upload_id"],
            0,
            len(content) - 1,
            len(content),
            content,
        )
        niwa_import.bridge_complete_upload(
            upload["upload_id"],
            {"sha256": digest},
        )
        niwa_import.bridge_complete_session(first["session_id"])
        published = next((self.storage / "photo").rglob("DSC_3301.JPG"))
        self.assertAlmostEqual(published.stat().st_mtime, expected_mtime, delta=2)
        original_mtime = published.stat().st_mtime

        second = niwa_import.bridge_create_session({
            "source_id": "camera-b",
            "client_id": "esp32-b",
        })
        skipped = niwa_import.bridge_preflight(second["session_id"], {
            "object_id": "3302",
            "source_key": "camera-b:3302",
            "filename": "RENAMED.JPG",
            "size": len(content),
            "sha256": digest,
            "captured_at": "20000101T000000",
        })
        self.assertEqual(skipped["action"], "skip")
        niwa_import.bridge_complete_session(second["session_id"])
        self.assertEqual(published.stat().st_mtime, original_mtime)

        third = niwa_import.bridge_create_session({
            "source_id": "camera-c",
            "client_id": "esp32-c",
        })
        with self.assertRaises(niwa_import.ApiError):
            niwa_import.bridge_preflight(third["session_id"], {
                "object_id": "3303",
                "filename": "INVALID.JPG",
                "size": 100,
                "captured_at": "20261399T999999",
            })

    def test_bridge_normalizes_ptp_fraction_and_utc_suffix(self):
        expected = "20260723T123456"
        self.assertEqual(
            niwa_import.bridge_ptp_datetime(
                "20260723T123456.0",
                "captured_at",
            ),
            expected,
        )
        self.assertEqual(
            niwa_import.bridge_ptp_datetime(
                "20260723T123456Z",
                "captured_at",
            ),
            expected,
        )
        self.assertEqual(
            niwa_import.bridge_ptp_datetime(
                "20260723T123456.123Z",
                "modified_at",
            ),
            expected,
        )

    def test_bridge_chunk_and_status_do_not_rewrite_session_json(self):
        content = b"one-durable-chunk"
        created = niwa_import.bridge_create_session({"source_id": "camera-a"})
        preflight = niwa_import.bridge_preflight(created["session_id"], {
            "object_id": "3101",
            "source_key": "camera-a:3101",
            "filename": "DSC_3101.JPG",
            "size": len(content),
        })
        writes = []
        original_save = niwa_import.bridge_save_sessions
        niwa_import.bridge_save_sessions = lambda payload: writes.append(payload)
        try:
            uploaded = niwa_import.bridge_receive_chunk(
                preflight["upload_id"],
                0,
                len(content) - 1,
                len(content),
                content,
            )
            status = niwa_import.bridge_get_upload(preflight["upload_id"])
        finally:
            niwa_import.bridge_save_sessions = original_save

        self.assertEqual(uploaded["offset"], len(content))
        self.assertEqual(status["upload"]["offset"], len(content))
        self.assertEqual(writes, [])

    def test_bridge_preflight_rejects_insufficient_free_space(self):
        created = niwa_import.bridge_create_session({"source_id": "camera-a"})
        original_disk_usage = niwa_import.shutil.disk_usage
        niwa_import.shutil.disk_usage = lambda _path: type(
            "Usage",
            (),
            {"free": niwa_import.BRIDGE_MIN_FREE_BYTES + 9},
        )()
        try:
            with self.assertRaises(niwa_import.ApiError) as failure:
                niwa_import.bridge_preflight(created["session_id"], {
                    "object_id": "3201",
                    "source_key": "camera-a:3201",
                    "filename": "DSC_3201.NEF",
                    "size": 10,
                })
        finally:
            niwa_import.shutil.disk_usage = original_disk_usage

        self.assertEqual(failure.exception.status, 507)

    def test_bridge_cleanup_expires_only_inactive_old_staging(self):
        created = niwa_import.bridge_create_session({"source_id": "nikon-test"})
        session_id = created["session_id"]
        sessions = niwa_import.bridge_load_sessions()
        sessions["sessions"][session_id]["updated_at"] = "2000-01-01 00:00:00"
        niwa_import.bridge_save_sessions(sessions)
        old_time = time.time() - 7200
        os.utime(
            niwa_import.BRIDGE_STAGING_ROOT / session_id,
            (old_time, old_time),
        )

        removed = niwa_import.cleanup_old_bridge_staging(max_age_seconds=3600)

        self.assertEqual(removed, 1)
        self.assertFalse((niwa_import.BRIDGE_STAGING_ROOT / session_id).exists())
        expired = niwa_import.bridge_load_sessions()["sessions"][session_id]
        self.assertEqual(expired["status"], "expired")

    def test_bridge_ignores_malformed_quick_hash_inventory_digest(self):
        destination = self.storage / "photo" / "imports" / "old" / "known.JPG"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"known")
        quick_hash = niwa_import.quick_fingerprint(destination)["quick_hash"]
        session = niwa_import.bridge_create_session({"source_id": "nikon-test"})
        stored_session = niwa_import.bridge_load_sessions()["sessions"][
            session["session_id"]
        ]
        source_key = "malformed-entry"
        niwa_import.save_hashes({
            "version": 3,
            "files": {},
            "sources": {
                niwa_import.bridge_inventory_source_key(stored_session): {
                    niwa_import.bridge_inventory_file_key(source_key): {
                        "size": destination.stat().st_size,
                        "quick_hash": quick_hash,
                        "digest": "not-a-sha256",
                        "destination": str(destination),
                        "source_key": source_key,
                    },
                },
            },
        })

        result = niwa_import.bridge_preflight(session["session_id"], {
            "object_id": "4001",
            "source_key": source_key,
            "filename": "KNOWN.JPG",
            "size": destination.stat().st_size,
            "quick_hash": quick_hash,
        })

        self.assertEqual(result["action"], "upload")

    def test_bridge_never_quick_skips_a_new_source_with_sample_collision(self):
        size = 512 * 1024
        first_content = bytearray(b"A" * size)
        second_content = bytearray(first_content)
        second_content[100000] = ord("B")
        first_sample = self.root / "first.NEF"
        second_sample = self.root / "second.NEF"
        first_sample.write_bytes(first_content)
        second_sample.write_bytes(second_content)
        first_quick = niwa_import.quick_fingerprint(first_sample)["quick_hash"]
        second_quick = niwa_import.quick_fingerprint(second_sample)["quick_hash"]
        self.assertEqual(first_quick, second_quick)
        self.assertNotEqual(
            niwa_import.sha256_file(first_sample),
            niwa_import.sha256_file(second_sample),
        )

        first_session = niwa_import.bridge_create_session({"source_id": "camera-a"})
        first = niwa_import.bridge_preflight(first_session["session_id"], {
            "object_id": "5001",
            "source_key": "same-looking-key",
            "filename": "COLLIDE.NEF",
            "size": size,
            "quick_hash": first_quick,
        })
        niwa_import.bridge_receive_chunk(
            first["upload_id"],
            0,
            size - 1,
            size,
            bytes(first_content),
        )
        niwa_import.bridge_complete_upload(first["upload_id"], {})
        niwa_import.bridge_complete_session(first_session["session_id"])

        second_session = niwa_import.bridge_create_session({"source_id": "camera-b"})
        second = niwa_import.bridge_preflight(second_session["session_id"], {
            "object_id": "5001",
            "source_key": "same-looking-key",
            "filename": "COLLIDE.NEF",
            "size": size,
            "quick_hash": second_quick,
        })

        self.assertEqual(second["action"], "upload")

    def test_bridge_does_not_skip_corrupt_sha256_index_target(self):
        good_content = b"verified-photo-content" * 5000
        sample = self.root / "verified.JPG"
        sample.write_bytes(good_content)
        digest = niwa_import.sha256_file(sample)
        corrupt = self.storage / "photo" / "imports" / "old" / "DSC_6001.JPG"
        corrupt.parent.mkdir(parents=True)
        corrupt.write_bytes(b"X" * len(good_content))
        niwa_import.save_hashes({
            "version": 3,
            "files": {digest: str(corrupt)},
            "sources": {},
        })
        session = niwa_import.bridge_create_session({"source_id": "camera-a"})

        preflight = niwa_import.bridge_preflight(session["session_id"], {
            "object_id": "6001",
            "source_key": "camera-a:6001",
            "filename": "DSC_6001.JPG",
            "size": len(good_content),
            "sha256": digest,
        })

        self.assertEqual(preflight["action"], "upload")
        niwa_import.bridge_receive_chunk(
            preflight["upload_id"],
            0,
            len(good_content) - 1,
            len(good_content),
            good_content,
        )
        niwa_import.bridge_complete_upload(
            preflight["upload_id"],
            {"sha256": digest},
        )
        niwa_import.bridge_complete_session(session["session_id"])
        indexed = Path(niwa_import.load_hashes()["files"][digest])
        self.assertNotEqual(indexed, corrupt)
        self.assertEqual(indexed.read_bytes(), good_content)
        self.assertEqual(corrupt.read_bytes(), b"X" * len(good_content))

    def test_bridge_rejects_skip_if_destination_corrupts_before_session_complete(self):
        content = b"valid-before-skip" * 5000
        destination = (
            self.storage
            / "photo"
            / "imports"
            / "old"
            / "DSC_7001.JPG"
        )
        destination.parent.mkdir(parents=True)
        destination.write_bytes(content)
        digest = niwa_import.sha256_file(destination)
        quick_hash = niwa_import.quick_fingerprint(destination)["quick_hash"]
        created = niwa_import.bridge_create_session({"source_id": "camera-a"})
        stored_session = niwa_import.bridge_load_sessions()["sessions"][
            created["session_id"]
        ]
        source_key = "camera-a:7001"
        niwa_import.save_hashes({
            "version": 3,
            "files": {digest: str(destination)},
            "sources": {
                niwa_import.bridge_inventory_source_key(stored_session): {
                    niwa_import.bridge_inventory_file_key(source_key): {
                        "size": len(content),
                        "quick_hash": quick_hash,
                        "digest": digest,
                        "destination": str(destination),
                        "source_key": source_key,
                    },
                },
            },
        })
        skipped = niwa_import.bridge_preflight(created["session_id"], {
            "object_id": "7001",
            "source_key": source_key,
            "filename": "DSC_7001.JPG",
            "size": len(content),
            "quick_hash": quick_hash,
        })
        self.assertEqual(skipped["action"], "skip")
        destination.write_bytes(b"X" * len(content))

        with self.assertRaises(niwa_import.ApiError) as failure:
            niwa_import.bridge_complete_session(created["session_id"])

        self.assertEqual(failure.exception.status, 409)
        self.assertTrue(failure.exception.details["restart_session"])
        self.assertEqual(
            niwa_import.bridge_load_sessions()["sessions"][
                created["session_id"]
            ]["status"],
            "active",
        )


if __name__ == "__main__":
    unittest.main()
