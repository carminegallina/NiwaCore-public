from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
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
            "CONFIG_FILE": niwa_import.CONFIG_FILE,
            "JOBS_FILE": niwa_import.JOBS_FILE,
            "HASHES_FILE": niwa_import.HASHES_FILE,
            "mount_readonly": niwa_import.mount_readonly,
            "safe_unmount": niwa_import.safe_unmount,
            "review_rebuild": niwa_import.review_rebuild,
            "copy_and_verify": niwa_import.copy_and_verify,
            "command_json": niwa_import.command_json,
        }
        niwa_import.DATA_ROOT = self.data
        niwa_import.STORAGE_ROOT = self.storage
        niwa_import.MOUNT_ROOT = self.mount
        niwa_import.STAGING_ROOT = self.storage / ".niwa_import_staging"
        niwa_import.CONFIG_FILE = self.data / "import_sources.json"
        niwa_import.JOBS_FILE = self.data / "import_jobs.json"
        niwa_import.HASHES_FILE = self.data / "import_hashes.json"
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
        niwa_import.run_import(self.device(), "camera", "test")

        jobs = niwa_import.load_jobs()["jobs"]
        self.assertEqual(jobs[0]["status"], "completed")
        self.assertEqual(jobs[0]["published_files"], 0)
        self.assertEqual(jobs[0]["duplicate_files"], 1)
        self.assertEqual(len(list((self.storage / "photo").rglob("*.NEF"))), 1)

    def test_interrupted_copy_never_publishes_partial_media(self):
        self.write_source("DCIM/100NZ6_2/DSC_0001.NEF", b"raw")

        def fail_copy(_source, _staged_path):
            raise OSError("simulated card removal")

        niwa_import.copy_and_verify = fail_copy
        niwa_import.run_import(self.device(), "camera", "test")

        jobs = niwa_import.load_jobs()["jobs"]
        self.assertEqual(jobs[0]["status"], "interrupted")
        self.assertEqual(len(list((self.storage / "photo").rglob("*.NEF"))), 0)

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


if __name__ == "__main__":
    unittest.main()
