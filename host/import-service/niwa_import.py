#!/usr/bin/env python3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlrequest
from urllib.parse import urlsplit
import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import traceback


APP_VERSION = "0.3.0"
PORT = int(os.environ.get("NIWA_IMPORT_PORT", "5057"))
PROJECT_ROOT = Path(os.environ.get("NIWA_PROJECT_ROOT", "/home/niwa/niwa"))
DATA_ROOT = Path(os.environ.get("NIWA_DATA_ROOT", str(PROJECT_ROOT / "data")))
STORAGE_ROOT = Path(os.environ.get("NIWA_STORAGE_ROOT", "/mnt/niwa-storage"))
MOUNT_ROOT = Path(os.environ.get("NIWA_IMPORT_MOUNT_ROOT", "/mnt/niwa-import"))
STAGING_ROOT = STORAGE_ROOT / ".niwa_import_staging"
BRIDGE_STAGING_ROOT = STORAGE_ROOT / ".niwa_bridge_staging"
STAGING_RETENTION_SECONDS = int(os.environ.get("NIWA_IMPORT_STAGING_RETENTION_SECONDS", str(24 * 3600)))
STAGING_CLEANUP_INTERVAL_SECONDS = int(os.environ.get("NIWA_IMPORT_STAGING_CLEANUP_INTERVAL_SECONDS", str(3600)))
BRIDGE_MAX_FILE_SIZE = int(os.environ.get("NIWA_BRIDGE_MAX_FILE_SIZE", str(2 * 1024 * 1024 * 1024)))
BRIDGE_MAX_CHUNK_SIZE = int(os.environ.get("NIWA_BRIDGE_MAX_CHUNK_SIZE", str(512 * 1024)))
BRIDGE_STAGING_RETENTION_SECONDS = int(
    os.environ.get("NIWA_BRIDGE_STAGING_RETENTION_SECONDS", str(7 * 24 * 3600))
)
BRIDGE_MAX_ACTIVE_SESSIONS = int(
    os.environ.get("NIWA_BRIDGE_MAX_ACTIVE_SESSIONS", "8")
)
BRIDGE_MAX_SESSION_OBJECTS = int(
    os.environ.get("NIWA_BRIDGE_MAX_SESSION_OBJECTS", "2000")
)
BRIDGE_MAX_SESSION_HISTORY = int(
    os.environ.get("NIWA_BRIDGE_MAX_SESSION_HISTORY", "100")
)
BRIDGE_MIN_FREE_BYTES = int(
    os.environ.get("NIWA_BRIDGE_MIN_FREE_BYTES", str(256 * 1024 * 1024))
)
BRIDGE_SOCKET_TIMEOUT_SECONDS = int(
    os.environ.get("NIWA_BRIDGE_SOCKET_TIMEOUT_SECONDS", "30")
)
BRIDGE_TOKEN = os.environ.get("NIWA_BRIDGE_TOKEN", "").strip()

CONFIG_FILE = DATA_ROOT / "import_sources.json"
JOBS_FILE = DATA_ROOT / "import_jobs.json"
HASHES_FILE = DATA_ROOT / "import_hashes.json"
BRIDGE_SESSIONS_FILE = DATA_ROOT / "bridge_sessions.json"
BRIDGE_TOKEN_FILE = DATA_ROOT / "bridge_token"
# Written by NIWA Review, only read here: media the user deleted in Review.
REVIEW_TRASH_FILE = DATA_ROOT / "review_trash.json"

DEFAULT_CONFIG = {
    "version": 1,
    "storage_root": str(STORAGE_ROOT),
    "mount_root": str(MOUNT_ROOT),
    "excluded_uuids": ["7ca9f987-1382-4e77-85d9-84a6424c7425"],
    "excluded_serials": ["41RB806NKFU2"],
    "sources": [],
}

RAW_EXTENSIONS = {
    ".3fr", ".arw", ".cr2", ".cr3", ".dng", ".erf", ".fff",
    ".gpr", ".iiq", ".kdc", ".mos", ".mrw", ".nef", ".nrw", ".orf",
    ".pef", ".raf", ".raw", ".rwl", ".rw2", ".srw", ".x3f",
}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".heif"}
VIDEO_EXTENSIONS = {
    ".avi", ".braw", ".crm", ".m2ts", ".m4v", ".mov", ".mp4", ".mts", ".mxf",
}
IGNORED_EXTENSIONS = {".lrv", ".thm"}
IGNORED_DIRECTORIES = {
    "$RECYCLE.BIN", ".Spotlight-V100", ".Trashes", "System Volume Information",
}
PROFILES = {"camera", "gopro"}
BRIDGE_ALLOWED_EXTENSIONS = {".nef", ".jpg", ".jpeg"}
BRIDGE_CONTENT_RANGE = re.compile(r"^bytes ([0-9]+)-([0-9]+)/([0-9]+)$")
BRIDGE_ROUTE_ID = r"([A-Za-z0-9_-]{8,96})"

STATE_LOCK = threading.Lock()
JOBS_LOCK = threading.Lock()
INGEST_LOCK = threading.Lock()
BRIDGE_LOCK = threading.RLock()
ACTIVE_JOB = None
LAST_SCAN_ERROR = None
SEEN_APPROVED_DEVICES = set()


class ApiError(RuntimeError):
    def __init__(self, message, status=400, **details):
        super().__init__(message)
        self.status = status
        self.details = details


def now_label():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def iso_job_id(device_id):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{device_id[:8]}"


def fsync_directory(path):
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_json_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)
    fsync_directory(path.parent)


def load_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError):
        return fallback
    return payload


def load_config():
    payload = load_json(CONFIG_FILE, {})
    config = dict(DEFAULT_CONFIG)
    if isinstance(payload, dict):
        config.update(payload)
    if not isinstance(config.get("sources"), list):
        config["sources"] = []
    return config


def save_config(config):
    atomic_json_write(CONFIG_FILE, config)


def load_jobs():
    payload = load_json(JOBS_FILE, {"version": 1, "jobs": []})
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        return {"version": 1, "jobs": []}
    return payload


def save_job(job):
    with JOBS_LOCK:
        payload = load_jobs()
        jobs = payload["jobs"]
        for index, existing in enumerate(jobs):
            if existing.get("id") == job["id"]:
                jobs[index] = dict(job)
                break
        else:
            jobs.insert(0, dict(job))
        payload["jobs"] = jobs[:80]
        atomic_json_write(JOBS_FILE, payload)


def load_hashes():
    payload = load_json(HASHES_FILE, {"version": 3, "files": {}, "sources": {}})
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
        return {"version": 3, "files": {}, "sources": {}}
    if not isinstance(payload.get("sources"), dict):
        payload["sources"] = {}
    payload["version"] = 3
    return payload


def user_deleted_paths():
    """Storage paths the user deleted in NIWA Review, in its trash or purged."""
    try:
        payload = json.loads(REVIEW_TRASH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    paths = payload.get("deleted_paths") if isinstance(payload, dict) else None
    if not isinstance(paths, list):
        return frozenset()
    return frozenset(path for path in paths if isinstance(path, str))


def deleted_by_user(destination, deleted):
    """True when a recorded destination is gone because the user deleted it."""
    if not destination or not deleted:
        return False
    path = Path(destination)
    try:
        relative = path.relative_to(STORAGE_ROOT).as_posix()
    except ValueError:
        return False
    return relative in deleted and not path.exists()


def inventory_deleted(cached, signature, deleted):
    """True when this card file was imported before and then deleted in Review."""
    return (
        isinstance(cached, dict)
        and cached.get("size") == signature["size"]
        and cached.get("mtime_ns") == signature["mtime_ns"]
        and cached.get("quick_hash") == signature["quick_hash"]
        and deleted_by_user(cached.get("destination"), deleted)
    )


def save_hashes(payload):
    atomic_json_write(HASHES_FILE, payload)


def command_json(command):
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=8,
    )
    return json.loads(result.stdout)


def flatten_blocks(nodes, parent=None):
    for node in nodes:
        yield node, parent
        yield from flatten_blocks(node.get("children", []), node)


def list_mountpoints(node):
    mountpoints = node.get("mountpoints")
    if isinstance(mountpoints, list):
        return [value for value in mountpoints if value]
    mountpoint = node.get("mountpoint")
    return [mountpoint] if mountpoint else []


def stable_device_id(node, parent):
    parts = [
        str(node.get("uuid") or ""),
        str((parent or node).get("serial") or ""),
        str(node.get("label") or ""),
        str(node.get("size") or ""),
        str(node.get("path") or node.get("name") or ""),
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def fallback_signature(node, parent):
    reader = parent or node
    serial = str(reader.get("serial") or "")
    model = str(reader.get("model") or "")
    hctl = str(reader.get("hctl") or "")
    lun = hctl.rsplit(":", 1)[-1] if ":" in hctl else hctl
    size = str(node.get("size") or "")
    fstype = str(node.get("fstype") or "")
    label = str(node.get("label") or "")
    partition_number = str(node.get("partn") or "")
    if not serial or not size or not fstype:
        return None
    parts = [serial, model, lun, size, fstype, label, partition_number]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def source_match(device, config):
    for source in config.get("sources", []):
        if not source.get("approved"):
            continue
        if source.get("uuid") and source["uuid"] == device.get("uuid"):
            return source
        if (
            source.get("fallback_signature")
            and source["fallback_signature"] == device.get("fallback_signature")
        ):
            return source
        if (
            source.get("allow_serial_match")
            and source.get("serial")
            and source["serial"] == device.get("serial")
        ):
            return source
    return None


def ignored_reasons(node, parent, config):
    reasons = []
    path = str(node.get("path") or "")
    parent_path = str((parent or {}).get("path") or "")
    mountpoints = list_mountpoints(node)
    uuid = str(node.get("uuid") or "")
    serial = str((parent or node).get("serial") or "")
    fstype = str(node.get("fstype") or "").lower()

    if path.startswith("/dev/mmcblk") or parent_path.startswith("/dev/mmcblk"):
        reasons.append("Scheda di sistema Raspberry")
    if path.startswith("/dev/zram") or fstype == "swap":
        reasons.append("Volume virtuale o swap")
    if uuid and uuid in set(config.get("excluded_uuids", [])):
        reasons.append("SSD media NIWA escluso per UUID")
    if serial and serial in set(config.get("excluded_serials", [])):
        reasons.append("SSD media NIWA escluso per seriale")
    if any(value in {"/", "/boot", "/boot/firmware", str(STORAGE_ROOT)} for value in mountpoints):
        reasons.append("Volume di sistema o storage NIWA")
    return reasons


def scan_devices(include_ignored=True):
    global LAST_SCAN_ERROR
    config = load_config()
    try:
        payload = command_json([
            "lsblk", "-J", "-b",
            "-o", "NAME,KNAME,PATH,TYPE,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS,RM,HOTPLUG,RO,TRAN,MODEL,SERIAL,VENDOR,PKNAME,HCTL,PARTN",
        ])
    except Exception as error:
        LAST_SCAN_ERROR = str(error)
        return []

    LAST_SCAN_ERROR = None
    devices = []
    for node, parent in flatten_blocks(payload.get("blockdevices", [])):
        if node.get("type") not in {"disk", "part"}:
            continue
        if not node.get("fstype"):
            continue

        reasons = ignored_reasons(node, parent, config)
        device = {
            "id": stable_device_id(node, parent),
            "device": node.get("path") or f"/dev/{node.get('name')}",
            "parent": (parent or {}).get("path"),
            "name": node.get("name"),
            "fstype": node.get("fstype"),
            "label": node.get("label") or "Senza etichetta",
            "uuid": node.get("uuid"),
            "size": int(node.get("size") or 0),
            "model": ((parent or node).get("model") or "").strip(),
            "serial": ((parent or node).get("serial") or "").strip(),
            "slot": str((parent or node).get("hctl") or "").rsplit(":", 1)[-1],
            "vendor": ((parent or node).get("vendor") or "").strip(),
            "transport": (parent or node).get("tran"),
            "removable": bool((parent or node).get("rm")),
            "hotplug": bool((parent or node).get("hotplug")),
            "readonly": bool(node.get("ro")),
            "mountpoints": list_mountpoints(node),
            "ignored_reasons": reasons,
            "fallback_signature": fallback_signature(node, parent),
        }
        source = source_match(device, config)
        device["source"] = source
        if reasons:
            device["status"] = "ignored"
        elif source:
            device["status"] = "approved"
            device["profile"] = source.get("profile", "camera")
            device["auto_import"] = bool(source.get("auto_import"))
        else:
            device["status"] = "unknown"
            device["profile"] = None
            device["auto_import"] = False

        if include_ignored or device["status"] != "ignored":
            devices.append(device)

    return devices


def human_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def source_mountpoint(device):
    return MOUNT_ROOT / device["id"][:16]


def mount_readonly(device):
    existing = [Path(value) for value in device.get("mountpoints", []) if value]
    own_mountpoint = source_mountpoint(device)
    if existing:
        if own_mountpoint in existing and os.path.ismount(own_mountpoint):
            return own_mountpoint, False
        raise RuntimeError("La scheda risulta gia montata altrove. Smontala e riprova.")

    own_mountpoint.mkdir(parents=True, exist_ok=True)
    options = ["ro", "nosuid", "nodev", "noexec"]
    if str(device.get("fstype", "")).lower() in {"ext2", "ext3", "ext4"}:
        options.append("noload")

    subprocess.run(
        ["mount", "-o", ",".join(options), device["device"], str(own_mountpoint)],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return own_mountpoint, True


def safe_unmount(mountpoint):
    if not mountpoint:
        return
    try:
        mounted = os.path.ismount(mountpoint)
    except OSError:
        mounted = False
    if mounted:
        subprocess.run(
            ["umount", str(mountpoint)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    try:
        Path(mountpoint).rmdir()
    except OSError:
        pass


def classify_media(path, profile):
    suffix = path.suffix.lower()
    if suffix in IGNORED_EXTENSIONS:
        return None
    if suffix in RAW_EXTENSIONS:
        return ("gopro" if profile == "gopro" else "photo", "raw")
    if suffix in PHOTO_EXTENSIONS:
        return ("gopro" if profile == "gopro" else "photo", "photo")
    if suffix in VIDEO_EXTENSIONS:
        return ("gopro" if profile == "gopro" else "video", "video")
    return None


def walk_error(error):
    raise error


def find_media_files(root, profile):
    files = []
    for current_root, directories, filenames in os.walk(root, onerror=walk_error):
        directories[:] = [
            value for value in directories
            if not value.startswith(".") and value not in IGNORED_DIRECTORIES
        ]
        current_path = Path(current_root)
        for filename in filenames:
            path = current_path / filename
            classification = classify_media(path, profile)
            if not classification:
                continue
            relative = path.relative_to(root)
            files.append((path, relative, classification[0], classification[1]))
    files.sort(key=lambda value: str(value[1]).lower())
    return files


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def quick_fingerprint(path):
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(stat.st_size).encode("ascii"))
    chunk_size = 64 * 1024
    offsets = {0}
    if stat.st_size > chunk_size:
        offsets.add(max(0, (stat.st_size // 2) - (chunk_size // 2)))
        offsets.add(max(0, stat.st_size - chunk_size))
    with open(path, "rb") as handle:
        for offset in sorted(offsets):
            handle.seek(offset)
            digest.update(handle.read(chunk_size))
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "quick_hash": digest.hexdigest(),
    }


def inventory_source_key(device):
    identity = device.get("uuid") or device.get("fallback_signature") or device["id"]
    return hashlib.sha1(str(identity).encode("utf-8")).hexdigest()


def inventory_file_key(category, relative):
    return f"{category}|{str(relative).replace(os.sep, '/')}"


def known_destinations_by_relative(hashes):
    destinations = {}
    for digest, path_string in hashes.get("files", {}).items():
        path = Path(path_string)
        try:
            relative = path.relative_to(STORAGE_ROOT)
        except ValueError:
            continue
        parts = relative.parts
        if len(parts) < 4 or parts[1] != "imports":
            continue
        key = inventory_file_key(parts[0], Path(*parts[3:]))
        destinations.setdefault(key, []).append((path, digest))
    return destinations


def cached_duplicate(source_path, key, source_inventory, destinations):
    signature = quick_fingerprint(source_path)
    cached = source_inventory.get(key)
    if (
        cached
        and cached.get("size") == signature["size"]
        and cached.get("mtime_ns") == signature["mtime_ns"]
    ):
        destination = Path(cached.get("destination", ""))
        digest = cached.get("digest")
        if (
            destination.exists()
            and cached.get("quick_hash") == signature["quick_hash"]
            and isinstance(digest, str)
            and sha256_file(destination) == digest
        ):
            return signature, destination, digest

    for destination, digest in destinations.get(key, []):
        try:
            if (
                destination.exists()
                and quick_fingerprint(destination)["quick_hash"]
                == signature["quick_hash"]
                and sha256_file(destination) == digest
            ):
                return signature, destination, digest
        except OSError:
            continue

    return signature, None, None


def remember_source_file(source_inventory, key, signature, digest, destination):
    source_inventory[key] = {
        **signature,
        "digest": digest,
        "destination": str(destination),
    }


def copy_and_verify(source, staged_path):
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = staged_path.with_suffix(staged_path.suffix + ".partial")
    digest = hashlib.sha256()
    total = 0
    with open(source, "rb") as input_handle, open(partial_path, "wb") as output_handle:
        while True:
            chunk = input_handle.read(1024 * 1024)
            if not chunk:
                break
            output_handle.write(chunk)
            digest.update(chunk)
            total += len(chunk)
        output_handle.flush()
        os.fsync(output_handle.fileno())
    shutil.copystat(source, partial_path)
    expected_hash = digest.hexdigest()
    copied_hash = sha256_file(partial_path)
    if expected_hash != copied_hash:
        raise RuntimeError(f"Checksum non valido per {source.name}")
    os.replace(partial_path, staged_path)
    fsync_directory(staged_path.parent)
    return expected_hash, total


def unique_destination(destination, digest):
    if not destination.exists():
        return destination, False
    if sha256_file(destination) == digest:
        return destination, True
    conflict = destination.with_name(
        f"{destination.stem}_conflict_{digest[:8]}{destination.suffix}"
    )
    if not conflict.exists():
        return conflict, False
    if sha256_file(conflict) == digest:
        return conflict, True
    for index in range(2, 1000):
        numbered = destination.with_name(
            f"{destination.stem}_conflict_{digest[:8]}_{index}{destination.suffix}"
        )
        if not numbered.exists():
            return numbered, False
        if sha256_file(numbered) == digest:
            return numbered, True
    raise RuntimeError(f"Troppi conflitti di nome per {destination.name}")


def publish_verified_file(staged_path, destination, digest):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination, duplicate = unique_destination(destination, digest)
    if duplicate:
        staged_path.unlink(missing_ok=True)
        return destination, True
    os.replace(staged_path, destination)
    fsync_directory(destination.parent)
    return destination, False


def review_rebuild():
    try:
        req = urlrequest.Request("http://127.0.0.1:5052/api/index/rebuild", method="POST")
        with urlrequest.urlopen(req, timeout=45) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def cleanup_old_staging(max_age_seconds=STAGING_RETENTION_SECONDS, active_job_id=None):
    if not STAGING_ROOT.exists():
        return 0
    cutoff = time.time() - max_age_seconds
    removed = 0
    for child in STAGING_ROOT.iterdir():
        try:
            if (
                child.is_dir()
                and child.name != active_job_id
                and child.stat().st_mtime < cutoff
            ):
                shutil.rmtree(child)
                removed += 1
        except OSError:
            pass
    return removed


def cleanup_completed_staging(staging_job):
    try:
        if staging_job.exists():
            shutil.rmtree(staging_job)
    except OSError:
        pass


def staging_cleanup_loop():
    while True:
        with STATE_LOCK:
            active_job_id = ACTIVE_JOB.get("id") if ACTIVE_JOB else None
        cleanup_old_staging(active_job_id=active_job_id)
        cleanup_old_bridge_staging()
        time.sleep(STAGING_CLEANUP_INTERVAL_SECONDS)


def run_import(device, profile, trigger):
    with INGEST_LOCK:
        return run_import_locked(device, profile, trigger)


def run_import_locked(device, profile, trigger):
    global ACTIVE_JOB
    job = {
        "id": iso_job_id(device["id"]),
        "device_id": device["id"],
        "device": device["device"],
        "label": device["label"],
        "profile": profile,
        "trigger": trigger,
        "status": "running",
        "started": now_label(),
        "finished": None,
        "message": "Preparazione importazione.",
        "total_files": 0,
        "processed_files": 0,
        "published_files": 0,
        "duplicate_files": 0,
        "fast_skipped_files": 0,
        "deleted_files": 0,
        "bytes_copied": 0,
        "review_rebuild": False,
        "errors": [],
    }
    with STATE_LOCK:
        ACTIVE_JOB = job
    save_job(job)

    mountpoint = None
    staging_job = STAGING_ROOT / job["id"]
    session = f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{device['id'][:8]}"
    staged_files = []
    hashes = load_hashes()
    source_inventory = hashes["sources"].setdefault(inventory_source_key(device), {})
    destinations = known_destinations_by_relative(hashes)
    deleted = user_deleted_paths()

    try:
        STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        mountpoint, _mounted_now = mount_readonly(device)
        job["message"] = "Scansione ricorsiva della scheda."
        save_job(job)
        files = find_media_files(mountpoint, profile)
        job["total_files"] = len(files)
        if not files:
            job["status"] = "completed"
            job["message"] = "Nessun RAW, JPG o video compatibile trovato."
            return

        for source_path, relative, category, kind in files:
            key = inventory_file_key(category, relative)
            signature, known_destination, known_digest = cached_duplicate(
                source_path,
                key,
                source_inventory,
                destinations,
            )
            if known_destination:
                remember_source_file(
                    source_inventory,
                    key,
                    signature,
                    known_digest,
                    known_destination,
                )
                job["processed_files"] += 1
                job["duplicate_files"] += 1
                job["fast_skipped_files"] += 1
                job["message"] = f"Gia verificato, salto rapido: {relative}"
                save_job(job)
                continue

            if inventory_deleted(source_inventory.get(key), signature, deleted):
                job["processed_files"] += 1
                job["deleted_files"] += 1
                job["message"] = f"Eliminato in Review, non reimportato: {relative}"
                save_job(job)
                continue

            job["message"] = f"Copia e checksum: {relative}"
            save_job(job)
            staged_path = staging_job / category / "imports" / session / relative
            digest, copied_bytes = copy_and_verify(source_path, staged_path)
            job["processed_files"] += 1
            job["bytes_copied"] += copied_bytes
            staged_files.append({
                "staged": staged_path,
                "destination": STORAGE_ROOT / category / "imports" / session / relative,
                "digest": digest,
                "relative": str(relative),
                "kind": kind,
                "inventory_key": key,
                "signature": signature,
            })
            save_job(job)

        job["message"] = "Pubblicazione atomica dei file verificati."
        save_job(job)
        for item in staged_files:
            known = hashes["files"].get(item["digest"])
            known_path = Path(known) if known else None
            if (
                known_path
                and known_path.is_file()
                and sha256_file(known_path) == item["digest"]
            ):
                item["staged"].unlink(missing_ok=True)
                job["duplicate_files"] += 1
                remember_source_file(
                    source_inventory,
                    item["inventory_key"],
                    item["signature"],
                    item["digest"],
                    known_path,
                )
                continue
            if deleted_by_user(known, deleted):
                # Same content as a file the user deleted in Review.
                item["staged"].unlink(missing_ok=True)
                job["deleted_files"] += 1
                remember_source_file(
                    source_inventory,
                    item["inventory_key"],
                    item["signature"],
                    item["digest"],
                    known_path,
                )
                continue
            destination, duplicate = publish_verified_file(
                item["staged"],
                item["destination"],
                item["digest"],
            )
            if duplicate:
                job["duplicate_files"] += 1
            else:
                hashes["files"][item["digest"]] = str(destination)
                job["published_files"] += 1
            remember_source_file(
                source_inventory,
                item["inventory_key"],
                item["signature"],
                item["digest"],
                destination,
            )

        save_hashes(hashes)
        if hasattr(os, "sync"):
            os.sync()
        job["review_rebuild"] = review_rebuild()
        job["status"] = "completed"
        job["message"] = (
            f"Importazione completata: {job['published_files']} file nuovi, "
            f"{job['duplicate_files']} duplicati saltati, "
            f"{job['fast_skipped_files']} riconosciuti senza ricopia."
        )
        if job["deleted_files"]:
            job["message"] += (
                f" {job['deleted_files']} eliminati in Review, non reimportati."
            )
        cleanup_completed_staging(staging_job)
    except Exception as error:
        job["status"] = "interrupted"
        job["errors"].append(str(error))
        job["message"] = (
            "Importazione interrotta. La libreria Review non contiene file "
            "parziali; controlla la scheda e riprova."
        )
    finally:
        safe_unmount(mountpoint)
        job["finished"] = now_label()
        save_job(job)
        with STATE_LOCK:
            ACTIVE_JOB = None


def bridge_auth_required():
    return bool(BRIDGE_TOKEN)


def bridge_validate_token(token):
    if (
        not isinstance(token, str)
        or len(token) < 32
        or len(token) > 256
        or any(character.isspace() or ord(character) < 33 for character in token)
    ):
        raise RuntimeError(
            "NIWA bridge token non valido: usa almeno 32 caratteri senza spazi."
        )
    return token


def ensure_bridge_token():
    global BRIDGE_TOKEN
    with BRIDGE_LOCK:
        if BRIDGE_TOKEN:
            return bridge_validate_token(BRIDGE_TOKEN)
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        if BRIDGE_TOKEN_FILE.is_symlink():
            raise RuntimeError("Il file token bridge non puo essere un link simbolico.")
        try:
            token = BRIDGE_TOKEN_FILE.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            token = secrets.token_hex(32)
            temporary = BRIDGE_TOKEN_FILE.with_name(
                f".{BRIDGE_TOKEN_FILE.name}.{os.getpid()}.{secrets.token_hex(4)}"
            )
            descriptor = os.open(
                str(temporary),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(token + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    temporary.unlink()
                except OSError:
                    pass
                raise
            os.replace(temporary, BRIDGE_TOKEN_FILE)
            fsync_directory(BRIDGE_TOKEN_FILE.parent)
        except OSError as error:
            raise RuntimeError(f"Impossibile leggere il token bridge: {error}") from error
        token = bridge_validate_token(token)
        try:
            os.chmod(BRIDGE_TOKEN_FILE, 0o600)
        except OSError as error:
            raise RuntimeError(
                f"Impossibile proteggere il file token bridge: {error}"
            ) from error
        BRIDGE_TOKEN = token
        return token


def bridge_authorization_valid(header_value):
    if not bridge_auth_required():
        return True
    prefix = "Bearer "
    if not isinstance(header_value, str) or not header_value.startswith(prefix):
        return False
    supplied = header_value[len(prefix):].strip()
    return bool(supplied) and hmac.compare_digest(supplied, BRIDGE_TOKEN)


def bridge_loopback_address(address):
    try:
        return ipaddress.ip_address(str(address).split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def bridge_load_sessions():
    payload = load_json(BRIDGE_SESSIONS_FILE, {"version": 1, "sessions": {}})
    if not isinstance(payload, dict) or not isinstance(payload.get("sessions"), dict):
        return {"version": 1, "sessions": {}}
    payload["version"] = 1
    return payload


def bridge_save_sessions(payload):
    sessions = payload.get("sessions", {})
    if isinstance(sessions, dict) and len(sessions) > BRIDGE_MAX_SESSION_HISTORY:
        active = {
            session_id: session
            for session_id, session in sessions.items()
            if session.get("status") in {"active", "completing"}
        }
        terminal = [
            (session_id, session)
            for session_id, session in sessions.items()
            if session_id not in active
        ]
        terminal.sort(
            key=lambda value: value[1].get("updated_at", ""),
            reverse=True,
        )
        remaining = max(0, BRIDGE_MAX_SESSION_HISTORY - len(active))
        payload["sessions"] = {
            **active,
            **dict(terminal[:remaining]),
        }
    atomic_json_write(BRIDGE_SESSIONS_FILE, payload)


def bridge_path_is_within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError):
        return False


def bridge_text(value, label, required=True, maximum=180):
    if value is None and not required:
        return ""
    if not isinstance(value, (str, int)):
        raise ApiError(f"{label} non valido.")
    text = str(value).strip()
    if required and not text:
        raise ApiError(f"{label} mancante.")
    if len(text) > maximum or any(ord(character) < 32 for character in text):
        raise ApiError(f"{label} non valido.")
    return text


def bridge_sha256(value, required=False):
    if (value is None or value == "") and not required:
        return None
    digest = bridge_text(value, "SHA-256", maximum=64).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ApiError("SHA-256 non valido.")
    return digest


def bridge_file_size(value):
    if isinstance(value, bool):
        raise ApiError("Dimensione file non valida.")
    try:
        size = int(value)
    except (TypeError, ValueError):
        raise ApiError("Dimensione file non valida.") from None
    if size <= 0:
        raise ApiError("La dimensione del file deve essere maggiore di zero.")
    if size > BRIDGE_MAX_FILE_SIZE:
        raise ApiError(
            "File oltre il limite configurato.",
            status=413,
            max_file_size=BRIDGE_MAX_FILE_SIZE,
        )
    return size


def bridge_filename(value):
    filename = bridge_text(value, "Nome file", maximum=220)
    if filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise ApiError("Il nome file deve essere un nome semplice, senza cartelle.")
    if Path(filename).suffix.lower() not in BRIDGE_ALLOWED_EXTENSIONS:
        raise ApiError("Formato non supportato: sono ammessi NEF, JPG e JPEG.")
    return filename


def bridge_ptp_datetime(value, label):
    text = bridge_text(
        value,
        label,
        required=False,
        maximum=32,
    )
    if not text:
        return None
    match = re.fullmatch(
        r"([0-9]{8}T[0-9]{6})(?:\.[0-9]+)?Z?",
        text,
    )
    if not match:
        raise ApiError(
            f"{label} non valido: usa YYYYMMDDThhmmss[.frazione][Z]."
        )
    normalized = match.group(1)
    try:
        datetime.strptime(normalized, "%Y%m%dT%H%M%S")
    except ValueError:
        raise ApiError(f"{label} non valido: data inesistente.") from None
    return normalized


def bridge_apply_item_mtime(path, item):
    ptp_timestamp = item.get("captured_at") or item.get("modified_at")
    if not ptp_timestamp:
        return
    timestamp = datetime.strptime(ptp_timestamp, "%Y%m%dT%H%M%S").timestamp()
    stat = path.stat()
    os.utime(path, (stat.st_atime, timestamp))


def bridge_staged_path(session, item):
    staged_name = item.get("staged_name")
    if not staged_name:
        raise ApiError("Nome staging mancante.", status=500)
    path = BRIDGE_STAGING_ROOT / session["id"] / staged_name
    if not bridge_path_is_within(path, BRIDGE_STAGING_ROOT):
        raise ApiError("Percorso staging non valido.", status=500)
    if path.exists():
        return path
    upload_id = item.get("upload_id")
    if upload_id:
        for suffix in (".partial", ".verified"):
            candidate = BRIDGE_STAGING_ROOT / session["id"] / f"{upload_id}{suffix}"
            if (
                candidate != path
                and bridge_path_is_within(candidate, BRIDGE_STAGING_ROOT)
                and candidate.is_file()
            ):
                item["staged_name"] = candidate.name
                return candidate
    return path


def bridge_published_candidate(wanted, digest):
    candidates = [
        wanted,
        wanted.with_name(
            f"{wanted.stem}_conflict_{digest[:8]}{wanted.suffix}"
        ),
    ]
    candidates.extend(
        wanted.with_name(
            f"{wanted.stem}_conflict_{digest[:8]}_{index}{wanted.suffix}"
        )
        for index in range(2, 1000)
    )
    for candidate in candidates:
        if (
            bridge_path_is_within(candidate, STORAGE_ROOT)
            and candidate.is_file()
            and sha256_file(candidate) == digest
        ):
            return candidate
    return None


def bridge_destination_for_api(path_string):
    path = Path(path_string)
    try:
        return str(path.relative_to(STORAGE_ROOT)).replace(os.sep, "/")
    except ValueError:
        return None


def bridge_inventory_source_key(session):
    identity = f"bridge|{session.get('source_id', '')}"
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()


def bridge_inventory_file_key(source_key):
    digest = hashlib.sha1(source_key.encode("utf-8")).hexdigest()
    return f"photo|bridge|{digest}"


def bridge_existing_destination(hashes, digest):
    destination_string = hashes.get("files", {}).get(digest)
    if not destination_string:
        return None
    destination = Path(destination_string)
    if (
        bridge_path_is_within(destination, STORAGE_ROOT)
        and destination.is_file()
        and sha256_file(destination) == digest
    ):
        return destination
    return None


def bridge_inventory_match(hashes, session, source_key, size, quick_hash):
    """Inventory record of this camera object, if size and quick hash match."""
    if not quick_hash:
        return None
    source_inventory = hashes.get("sources", {}).get(
        bridge_inventory_source_key(session),
        {},
    )
    if not isinstance(source_inventory, dict):
        return None
    cached = source_inventory.get(bridge_inventory_file_key(source_key))
    if not isinstance(cached, dict) or cached.get("source_key") != source_key:
        return None
    try:
        cached_size = int(cached.get("size", -1))
    except (TypeError, ValueError):
        return None
    if cached_size != size or cached.get("quick_hash") != quick_hash:
        return None
    return cached


def bridge_deleted_source(hashes, session, source_key, size, quick_hash, expected_sha256):
    """Where this camera object was published, if the user deleted it in Review."""
    deleted = user_deleted_paths()
    if not deleted:
        return None
    candidates = []
    if expected_sha256:
        candidates.append(hashes.get("files", {}).get(expected_sha256))
    cached = bridge_inventory_match(hashes, session, source_key, size, quick_hash)
    if cached:
        candidates.append(cached.get("destination"))
    for candidate in candidates:
        if deleted_by_user(candidate, deleted):
            return candidate
    return None


def bridge_quick_duplicate(hashes, session, source_key, size, quick_hash):
    cached = bridge_inventory_match(hashes, session, source_key, size, quick_hash)
    if not cached:
        return None, None
    try:
        digest = bridge_sha256(cached.get("digest"), required=False)
    except ApiError:
        return None, None
    destination_string = cached.get("destination")
    if not digest or not destination_string:
        return None, None
    destination = Path(destination_string)
    if (
        bridge_path_is_within(destination, STORAGE_ROOT)
        and destination.is_file()
        and sha256_file(destination) == digest
    ):
        return destination, digest
    return None, None


def bridge_remember_source(hashes, session, item, digest, destination):
    quick_hash = item.get("quick_hash")
    source_key = item.get("source_key")
    if not quick_hash or not source_key:
        return
    inventory = hashes["sources"].setdefault(
        bridge_inventory_source_key(session),
        {},
    )
    inventory[bridge_inventory_file_key(source_key)] = {
        "size": item["size"],
        "mtime_ns": 0,
        "quick_hash": quick_hash,
        "digest": digest,
        "destination": str(destination),
        "source_key": source_key,
        "filename": item["filename"],
        "updated_at": now_label(),
    }


def bridge_public_item(item):
    return {
        "object_id": item["object_id"],
        "source_key": item["source_key"],
        "filename": item["filename"],
        "size": item["size"],
        "quick_hash": item.get("quick_hash"),
        "captured_at": item.get("captured_at"),
        "modified_at": item.get("modified_at"),
        "sha256": item.get("digest") or item.get("expected_sha256"),
        "upload_id": item.get("upload_id"),
        "offset": item.get("received", 0),
        "status": item["status"],
        "duplicate": bool(item.get("duplicate")),
        "destination": bridge_destination_for_api(item.get("destination", ""))
        if item.get("destination")
        else None,
    }


def bridge_public_session(session, include_objects=True):
    objects = list(session.get("objects", {}).values())
    payload = {
        "id": session["id"],
        "status": session["status"],
        "source_id": session["source_id"],
        "camera_model": session.get("camera_model"),
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "finished_at": session.get("finished_at"),
        "total_objects": len(objects),
        "published_objects": sum(
            item.get("status") == "published" for item in objects
        ),
        "duplicate_objects": sum(
            item.get("status") in {"skipped", "duplicate"} for item in objects
        ),
        "deleted_objects": sum(
            item.get("status") == "deleted" for item in objects
        ),
        "verified_objects": sum(
            item.get("status") == "verified" for item in objects
        ),
        "uploading_objects": sum(
            item.get("status") == "uploading" for item in objects
        ),
        "review_rebuild": session.get("review_rebuild"),
        "last_error": session.get("last_error"),
    }
    if include_objects:
        payload["objects"] = [bridge_public_item(item) for item in objects]
    return payload


def bridge_create_session(payload):
    source_id = (
        payload.get("source_id")
        or payload.get("camera_serial")
        or payload.get("device_id")
        or payload.get("camera_model")
        or "nikon-z6ii"
    )
    source_id = bridge_text(source_id, "Identificativo sorgente", maximum=180)
    camera_model = bridge_text(
        payload.get("camera_model", "Nikon Z6 II"),
        "Modello camera",
        required=False,
        maximum=120,
    )
    client_id = bridge_text(
        payload.get("client_id", ""),
        "Identificativo client",
        required=False,
        maximum=120,
    )
    with BRIDGE_LOCK:
        sessions = bridge_load_sessions()
        resumable = [
            session
            for session in sessions["sessions"].values()
            if (
                session.get("status") in {"active", "completing"}
                and session.get("source_id") == source_id
                and session.get("client_id", "") == client_id
            )
        ]
        if resumable:
            session = max(
                resumable,
                key=lambda value: value.get("created_at", ""),
            )
            if session.get("status") == "completing":
                session["status"] = "active"
                session["updated_at"] = now_label()
                session["last_error"] = (
                    "Sessione ripresa dopo un'interruzione durante la pubblicazione."
                )
                bridge_save_sessions(sessions)
            return {
                "ok": True,
                "session_id": session["id"],
                "status": session["status"],
                "resumed": True,
                "chunk_size": BRIDGE_MAX_CHUNK_SIZE,
                "max_file_size": BRIDGE_MAX_FILE_SIZE,
            }
        active_sessions = sum(
            session.get("status") in {"active", "completing"}
            for session in sessions["sessions"].values()
        )
        if active_sessions >= BRIDGE_MAX_ACTIVE_SESSIONS:
            raise ApiError(
                "Troppe sessioni bridge attive.",
                status=429,
                max_active_sessions=BRIDGE_MAX_ACTIVE_SESSIONS,
            )
        session_id = (
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{secrets.token_hex(4)}"
        )
        session = {
            "id": session_id,
            "status": "active",
            "source_id": source_id,
            "camera_model": camera_model,
            "client_id": client_id,
            "created_at": now_label(),
            "updated_at": now_label(),
            "finished_at": None,
            "folder": f"esp32-{session_id}",
            "objects": {},
            "review_rebuild": None,
            "last_error": None,
        }
        sessions["sessions"][session_id] = session
        BRIDGE_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        (BRIDGE_STAGING_ROOT / session_id).mkdir(parents=True, exist_ok=False)
        fsync_directory(BRIDGE_STAGING_ROOT)
        bridge_save_sessions(sessions)
        return {
            "ok": True,
            "session_id": session_id,
            "status": "active",
            "resumed": False,
            "chunk_size": BRIDGE_MAX_CHUNK_SIZE,
            "max_file_size": BRIDGE_MAX_FILE_SIZE,
        }


def bridge_get_session(session_id):
    with BRIDGE_LOCK:
        session = bridge_load_sessions()["sessions"].get(session_id)
        if not session:
            raise ApiError("Sessione bridge non trovata.", status=404)
        return {"ok": True, "session": bridge_public_session(session)}


def bridge_find_upload(sessions, upload_id):
    for session in sessions.get("sessions", {}).values():
        for item in session.get("objects", {}).values():
            if item.get("upload_id") == upload_id:
                return session, item
    raise ApiError("Upload bridge non trovato.", status=404)


def bridge_upload_response(session, item):
    staged_path = bridge_staged_path(session, item)
    offset = staged_path.stat().st_size if staged_path.exists() else 0
    return {
        "ok": True,
        "action": "upload",
        "session_id": session["id"],
        "object_id": item["object_id"],
        "upload_id": item["upload_id"],
        "offset": offset,
        "size": item["size"],
        "chunk_size": BRIDGE_MAX_CHUNK_SIZE,
    }


def bridge_skip_response(session, item, reason="duplicate"):
    return {
        "ok": True,
        "action": "skip",
        "reason": reason,
        "session_id": session["id"],
        "object_id": item["object_id"],
        "size": item["size"],
        "sha256": item.get("digest"),
        "destination": bridge_destination_for_api(item.get("destination", ""))
        if item.get("destination")
        else None,
    }


def bridge_reserved_upload_bytes(sessions):
    reserved = 0
    for session in sessions.get("sessions", {}).values():
        if session.get("status") not in {"active", "completing"}:
            continue
        for item in session.get("objects", {}).values():
            if item.get("status") != "uploading":
                continue
            try:
                staged_path = bridge_staged_path(session, item)
                received = staged_path.stat().st_size if staged_path.exists() else 0
                reserved += max(0, int(item["size"]) - received)
            except (ApiError, OSError, TypeError, ValueError):
                reserved += max(0, int(item.get("size") or 0))
    return reserved


def bridge_require_upload_space(sessions, requested_size):
    try:
        free_bytes = shutil.disk_usage(STORAGE_ROOT).free
    except OSError as error:
        raise ApiError(
            f"Spazio storage non verificabile: {error}",
            status=503,
        ) from error
    reserved_bytes = bridge_reserved_upload_bytes(sessions)
    required_bytes = requested_size + reserved_bytes + BRIDGE_MIN_FREE_BYTES
    if free_bytes < required_bytes:
        raise ApiError(
            "Spazio SSD insufficiente per il nuovo upload.",
            status=507,
            free_bytes=free_bytes,
            reserved_bytes=reserved_bytes,
            requested_bytes=requested_size,
            minimum_free_bytes=BRIDGE_MIN_FREE_BYTES,
        )


def bridge_preflight(session_id, payload):
    object_id = bridge_text(payload.get("object_id"), "Object ID", maximum=128)
    source_key = bridge_text(
        payload.get("source_key") or object_id,
        "Source key",
        maximum=300,
    )
    filename = bridge_filename(payload.get("filename"))
    size = bridge_file_size(payload.get("size"))
    quick_hash = bridge_sha256(payload.get("quick_hash"), required=False)
    expected_sha256 = bridge_sha256(payload.get("sha256"), required=False)
    captured_at = bridge_ptp_datetime(payload.get("captured_at"), "captured_at")
    modified_at = bridge_ptp_datetime(payload.get("modified_at"), "modified_at")

    with INGEST_LOCK:
        with BRIDGE_LOCK:
            sessions = bridge_load_sessions()
            session = sessions["sessions"].get(session_id)
            if not session:
                raise ApiError("Sessione bridge non trovata.", status=404)
            if session.get("status") != "active":
                raise ApiError("La sessione bridge non e attiva.", status=409)

            existing = session.get("objects", {}).get(object_id)
            if existing:
                if (
                    existing.get("filename") != filename
                    or existing.get("size") != size
                    or existing.get("source_key") != source_key
                    or existing.get("captured_at") != captured_at
                    or existing.get("modified_at") != modified_at
                ):
                    raise ApiError(
                        "Object ID gia usato con metadati differenti.",
                        status=409,
                    )
                if expected_sha256 and existing.get("expected_sha256") not in {
                    None,
                    expected_sha256,
                }:
                    raise ApiError(
                        "Object ID gia usato con SHA-256 differente.",
                        status=409,
                    )
                if (
                    quick_hash
                    and existing.get("quick_hash")
                    and existing.get("quick_hash") != quick_hash
                ):
                    raise ApiError(
                        "Object ID gia usato con quick hash differente.",
                        status=409,
                    )
                if existing.get("status") == "deleted":
                    return bridge_skip_response(
                        session,
                        existing,
                        reason="deleted_by_user",
                    )
                if existing.get("status") in {"skipped", "published", "duplicate"}:
                    return bridge_skip_response(session, existing)
                if existing.get("status") == "verified":
                    return bridge_skip_response(
                        session,
                        existing,
                        reason="verified_waiting_session_complete",
                    )
                response = bridge_upload_response(session, existing)
                session["updated_at"] = now_label()
                bridge_save_sessions(sessions)
                return response

            if len(session.get("objects", {})) >= BRIDGE_MAX_SESSION_OBJECTS:
                raise ApiError(
                    "Limite oggetti della sessione raggiunto.",
                    status=413,
                    max_session_objects=BRIDGE_MAX_SESSION_OBJECTS,
                )

            hashes = load_hashes()
            destination = None
            digest = None
            duplicate_reason = None
            if expected_sha256:
                destination = bridge_existing_destination(hashes, expected_sha256)
                if destination:
                    digest = expected_sha256
                    duplicate_reason = "sha256"
            if not destination and quick_hash:
                destination, digest = bridge_quick_duplicate(
                    hashes,
                    session,
                    source_key,
                    size,
                    quick_hash,
                )
                if destination:
                    duplicate_reason = "quick_hash"

            deleted_destination = None
            if not destination:
                # Never send again a photo the user deleted in Review: at Wi-Fi
                # speed a NEF costs over a minute, so decide before the upload.
                deleted_destination = bridge_deleted_source(
                    hashes,
                    session,
                    source_key,
                    size,
                    quick_hash,
                    expected_sha256,
                )
            done = destination or deleted_destination
            if not done:
                bridge_require_upload_space(sessions, size)
            if deleted_destination:
                status = "deleted"
            elif destination:
                status = "skipped"
            else:
                status = "uploading"
            item = {
                "object_id": object_id,
                "source_key": source_key,
                "filename": filename,
                "size": size,
                "quick_hash": quick_hash,
                "captured_at": captured_at,
                "modified_at": modified_at,
                "expected_sha256": expected_sha256,
                "digest": digest,
                "upload_id": None,
                "staged_name": None,
                "received": size if done else 0,
                "status": status,
                "duplicate": bool(destination),
                "duplicate_reason": duplicate_reason,
                "destination": str(done) if done else None,
                "created_at": now_label(),
                "updated_at": now_label(),
            }
            session["objects"][object_id] = item
            session["updated_at"] = now_label()

            if done:
                bridge_save_sessions(sessions)
                return bridge_skip_response(
                    session,
                    item,
                    reason="deleted_by_user" if deleted_destination else duplicate_reason,
                )

            for _attempt in range(8):
                upload_id = secrets.token_urlsafe(18).replace("-", "_")
                staged_name = f"{upload_id}.partial"
                staged_path = BRIDGE_STAGING_ROOT / session_id / staged_name
                try:
                    with open(staged_path, "xb") as handle:
                        handle.flush()
                        os.fsync(handle.fileno())
                    break
                except FileExistsError:
                    continue
            else:
                raise ApiError("Impossibile allocare lo staging.", status=500)

            item["upload_id"] = upload_id
            item["staged_name"] = staged_name
            fsync_directory(staged_path.parent)
            bridge_save_sessions(sessions)
            return bridge_upload_response(session, item)


def bridge_get_upload(upload_id):
    with BRIDGE_LOCK:
        sessions = bridge_load_sessions()
        session, item = bridge_find_upload(sessions, upload_id)
        public_item = bridge_public_item(item)
        if item["status"] == "uploading":
            staged_path = bridge_staged_path(session, item)
            public_item["offset"] = (
                staged_path.stat().st_size if staged_path.exists() else 0
            )
        return {
            "ok": True,
            "session_id": session["id"],
            "upload": public_item,
            "chunk_size": BRIDGE_MAX_CHUNK_SIZE,
        }


def bridge_receive_chunk(upload_id, start, end, total, data):
    if not isinstance(data, bytes):
        raise ApiError("Chunk non valido.")
    if len(data) > BRIDGE_MAX_CHUNK_SIZE:
        raise ApiError(
            "Chunk oltre il limite configurato.",
            status=413,
            max_chunk_size=BRIDGE_MAX_CHUNK_SIZE,
        )
    if start < 0 or end < start or total <= 0 or end + 1 > total:
        raise ApiError("Content-Range non valido.")
    if len(data) != end - start + 1:
        raise ApiError("Content-Length e Content-Range non coincidono.")

    with BRIDGE_LOCK:
        sessions = bridge_load_sessions()
        session, item = bridge_find_upload(sessions, upload_id)
        if session.get("status") != "active":
            raise ApiError("La sessione bridge non e attiva.", status=409)
        if item.get("status") != "uploading":
            if item.get("status") == "verified":
                return {
                    "ok": True,
                    "upload_id": upload_id,
                    "offset": item["size"],
                    "size": item["size"],
                    "complete": True,
                    "status": "verified",
                }
            raise ApiError("L'upload non accetta altri chunk.", status=409)
        if total != item["size"]:
            raise ApiError("La dimensione totale non coincide col preflight.", status=409)

        staged_path = bridge_staged_path(session, item)
        actual_offset = staged_path.stat().st_size if staged_path.exists() else 0
        if start != actual_offset:
            raise ApiError(
                "Offset non valido: riprendi dall'offset indicato.",
                status=409,
                expected_offset=actual_offset,
            )

        staged_path.parent.mkdir(parents=True, exist_ok=True)
        with open(staged_path, "r+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() != actual_offset:
                raise ApiError(
                    "Lo staging e cambiato durante l'upload.",
                    status=409,
                    expected_offset=handle.tell(),
                )
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        offset = end + 1
        return {
            "ok": True,
            "upload_id": upload_id,
            "offset": offset,
            "size": total,
            "complete": offset == total,
            "status": "uploading",
        }


def bridge_reset_staged_upload(staged_path, item, session, sessions, message):
    with open(staged_path, "wb") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    item["received"] = 0
    item["digest"] = None
    item["updated_at"] = now_label()
    item["last_error"] = message
    session["updated_at"] = now_label()
    bridge_save_sessions(sessions)
    raise ApiError(message, status=422, expected_offset=0)


def bridge_complete_upload(upload_id, payload):
    result = bridge_verify_upload(upload_id, payload)
    status = bridge_publish_ready_uploads(result.pop("session_id"), upload_id)
    if status:
        result["status"] = status
    return result


def bridge_verify_upload(upload_id, payload):
    supplied_sha256 = bridge_sha256(payload.get("sha256"), required=False)
    with BRIDGE_LOCK:
        sessions = bridge_load_sessions()
        session, item = bridge_find_upload(sessions, upload_id)
        if item.get("status") in {"verified", "published", "duplicate"}:
            return {
                "ok": True,
                "action": "verified",
                "upload_id": upload_id,
                "session_id": session["id"],
                "sha256": item.get("digest"),
                "status": item.get("status"),
            }
        if session.get("status") != "active" or item.get("status") != "uploading":
            raise ApiError("L'upload non puo essere completato.", status=409)
        expected_sha256 = item.get("expected_sha256")
        if (
            supplied_sha256
            and expected_sha256
            and supplied_sha256 != expected_sha256
        ):
            raise ApiError("SHA-256 dichiarato diverso dal preflight.", status=409)

        staged_path = bridge_staged_path(session, item)
        actual_size = staged_path.stat().st_size if staged_path.exists() else 0
        if actual_size != item["size"]:
            raise ApiError(
                "Upload incompleto.",
                status=409,
                expected_offset=actual_size,
                expected_size=item["size"],
            )

        digest = sha256_file(staged_path)
        authoritative_expected = supplied_sha256 or expected_sha256
        if authoritative_expected and digest != authoritative_expected:
            bridge_reset_staged_upload(
                staged_path,
                item,
                session,
                sessions,
                "Checksum SHA-256 non valido; upload azzerato.",
            )
        quick_hash = item.get("quick_hash")
        if quick_hash and quick_fingerprint(staged_path)["quick_hash"] != quick_hash:
            bridge_reset_staged_upload(
                staged_path,
                item,
                session,
                sessions,
                "Quick hash non valido; upload azzerato.",
            )

        bridge_apply_item_mtime(staged_path, item)
        with open(staged_path, "r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        item["received"] = item["size"]
        item["digest"] = digest
        item["status"] = "verified"
        item["last_error"] = None
        item["updated_at"] = now_label()
        session["updated_at"] = now_label()
        bridge_save_sessions(sessions)
        return {
            "ok": True,
            "action": "verified",
            "upload_id": upload_id,
            "session_id": session["id"],
            "sha256": digest,
            "size": item["size"],
            "status": "verified",
        }


def bridge_publish_ready_uploads(session_id, upload_id):
    """Move the verified uploads of an active session into photo/imports now.

    Runs after every verified upload, so each photo shows up on the Raspberry as
    soon as it lands instead of waiting for the session to close. If an SD-card
    import holds the ingest lock, publication is left to the next upload or to
    session completion: the verified copy stays safe in staging meanwhile.
    """
    if not INGEST_LOCK.acquire(timeout=5):
        return None
    try:
        with BRIDGE_LOCK:
            sessions = bridge_load_sessions()
            session = sessions["sessions"].get(session_id)
            if not session or session.get("status") != "active":
                return None
            hashes = load_hashes()
            published_any = False
            for item in session.get("objects", {}).values():
                if item.get("status") != "verified":
                    continue
                try:
                    bridge_publish_verified_item(session, item, hashes)
                except Exception as error:
                    item["last_error"] = f"Pubblicazione rimandata: {error}"
                    item["updated_at"] = now_label()
                    bridge_save_sessions(sessions)
                    continue
                published_any = published_any or item["status"] == "published"
                save_hashes(hashes)
                session["updated_at"] = now_label()
                bridge_save_sessions(sessions)
            _, current = bridge_find_upload(sessions, upload_id)
            status = current.get("status")
    finally:
        INGEST_LOCK.release()
    if published_any:
        # Off the request path: a slow Review panel must not hold the ESP32.
        threading.Thread(target=review_rebuild, daemon=True).start()
    return status


def bridge_publish_verified_item(session, item, hashes):
    """Publish one verified bridge upload and record it in the hash index."""
    digest = item.get("digest")
    if not digest:
        raise RuntimeError(f"Checksum mancante per {item['filename']}")
    staged_path = bridge_staged_path(session, item)
    wanted = (
        STORAGE_ROOT
        / "photo"
        / "imports"
        / session["folder"]
        / item["filename"]
    )
    known_destination = bridge_existing_destination(hashes, digest)
    recorded = hashes.get("files", {}).get(digest)
    if not known_destination and deleted_by_user(recorded, user_deleted_paths()):
        # Same content as a photo the user deleted in Review: never publish it.
        staged_path.unlink(missing_ok=True)
        item["destination"] = recorded
        item["duplicate"] = False
        item["status"] = "deleted"
        item["last_error"] = None
        item["updated_at"] = now_label()
        return
    if known_destination:
        staged_path.unlink(missing_ok=True)
        destination = known_destination
        duplicate = True
    elif staged_path.is_file():
        bridge_apply_item_mtime(staged_path, item)
        destination, duplicate = publish_verified_file(
            staged_path,
            wanted,
            digest,
        )
    else:
        recorded = Path(item.get("destination") or "")
        if (
            recorded.is_file()
            and bridge_path_is_within(recorded, STORAGE_ROOT)
            and sha256_file(recorded) == digest
        ):
            destination = recorded
            duplicate = bool(item.get("duplicate"))
        else:
            recovered = bridge_published_candidate(wanted, digest)
            if not recovered:
                raise RuntimeError(
                    f"Staging verificato mancante: {item['filename']}"
                )
            destination = recovered
            duplicate = bool(item.get("duplicate"))

    hashes["files"][digest] = str(destination)
    item["destination"] = str(destination)
    item["duplicate"] = duplicate
    item["status"] = "duplicate" if duplicate else "published"
    item["last_error"] = None
    item["updated_at"] = now_label()
    bridge_remember_source(hashes, session, item, digest, destination)


def bridge_complete_session(session_id):
    with INGEST_LOCK:
        with BRIDGE_LOCK:
            sessions = bridge_load_sessions()
            session = sessions["sessions"].get(session_id)
            if not session:
                raise ApiError("Sessione bridge non trovata.", status=404)
            if session.get("status") == "completed":
                return {
                    "ok": True,
                    "session": bridge_public_session(
                        session,
                        include_objects=False,
                    ),
                }
            if session.get("status") not in {"active", "completing"}:
                raise ApiError("La sessione bridge non puo essere completata.", status=409)

            incomplete = [
                item["object_id"]
                for item in session.get("objects", {}).values()
                if item.get("status")
                not in {"skipped", "verified", "published", "duplicate", "deleted"}
            ]
            if incomplete:
                raise ApiError(
                    "La sessione contiene upload non completati.",
                    status=409,
                    incomplete_objects=incomplete[:20],
                )

            session["status"] = "completing"
            session["updated_at"] = now_label()
            session["last_error"] = None
            bridge_save_sessions(sessions)
            hashes = load_hashes()

            try:
                for item in session.get("objects", {}).values():
                    if item["status"] in {"published", "duplicate", "deleted"}:
                        continue
                    digest = item.get("digest")
                    if not digest:
                        raise RuntimeError(
                            f"Checksum mancante per {item['filename']}"
                        )

                    if item["status"] == "skipped":
                        known_destination = bridge_existing_destination(
                            hashes,
                            digest,
                        )
                        destination = known_destination
                        if not destination:
                            recorded = Path(item.get("destination") or "")
                            if (
                                recorded.is_file()
                                and bridge_path_is_within(recorded, STORAGE_ROOT)
                                and sha256_file(recorded) == digest
                            ):
                                destination = recorded
                        if not destination:
                            raise ApiError(
                                "Il duplicato saltato non e piu valido. "
                                "Annulla questa sessione e avviane una nuova "
                                "per trasferire nuovamente il file.",
                                status=409,
                                restart_session=True,
                                object_id=item["object_id"],
                            )
                        item["destination"] = str(destination)
                        item["duplicate"] = True
                        bridge_remember_source(
                            hashes,
                            session,
                            item,
                            digest,
                            destination,
                        )
                        continue

                    bridge_publish_verified_item(session, item, hashes)
                    save_hashes(hashes)
                    session["updated_at"] = now_label()
                    bridge_save_sessions(sessions)

                save_hashes(hashes)
                if hasattr(os, "sync"):
                    os.sync()
                has_new_publications = any(
                    item.get("status") == "published"
                    for item in session.get("objects", {}).values()
                )
                session["review_rebuild"] = (
                    review_rebuild() if has_new_publications else False
                )
                session["status"] = "completed"
                session["finished_at"] = now_label()
                session["updated_at"] = now_label()
                session["last_error"] = None
                cleanup_completed_staging(BRIDGE_STAGING_ROOT / session_id)
                bridge_save_sessions(sessions)
                return {
                    "ok": True,
                    "session": bridge_public_session(
                        session,
                        include_objects=False,
                    ),
                }
            except Exception as error:
                session["status"] = "active"
                session["last_error"] = str(error)
                session["updated_at"] = now_label()
                bridge_save_sessions(sessions)
                raise


def bridge_abort_session(session_id):
    with BRIDGE_LOCK:
        sessions = bridge_load_sessions()
        session = sessions["sessions"].get(session_id)
        if not session:
            raise ApiError("Sessione bridge non trovata.", status=404)
        if session.get("status") == "completed":
            raise ApiError("Una sessione completata non puo essere annullata.", status=409)
        session["status"] = "aborted"
        session["finished_at"] = now_label()
        session["updated_at"] = now_label()
        cleanup_completed_staging(BRIDGE_STAGING_ROOT / session_id)
        bridge_save_sessions(sessions)
        return {
            "ok": True,
            "session": bridge_public_session(session, include_objects=False),
        }


def cleanup_old_bridge_staging(max_age_seconds=BRIDGE_STAGING_RETENTION_SECONDS):
    if not BRIDGE_STAGING_ROOT.exists():
        return 0
    cutoff = time.time() - max_age_seconds
    removed = 0
    with BRIDGE_LOCK:
        sessions = bridge_load_sessions()
        changed = False
        for directory in BRIDGE_STAGING_ROOT.iterdir():
            if not directory.is_dir():
                continue
            session = sessions["sessions"].get(directory.name)
            if session and session.get("status") in {"completed", "aborted", "expired"}:
                cleanup_completed_staging(directory)
                removed += int(not directory.exists())
                continue
            try:
                session_updated_at = (
                    datetime.strptime(
                        session.get("updated_at", ""),
                        "%Y-%m-%d %H:%M:%S",
                    ).timestamp()
                    if session
                    else directory.stat().st_mtime
                )
            except (OSError, TypeError, ValueError):
                try:
                    session_updated_at = directory.stat().st_mtime
                except OSError:
                    continue
            staging_updated_at = session_updated_at
            try:
                staging_updated_at = max(
                    [directory.stat().st_mtime]
                    + [
                        child.stat().st_mtime
                        for child in directory.iterdir()
                        if child.is_file()
                    ]
                )
            except OSError:
                pass
            updated_at = max(session_updated_at, staging_updated_at)
            if updated_at >= cutoff:
                continue
            cleanup_completed_staging(directory)
            if directory.exists():
                continue
            removed += 1
            if session and session.get("status") in {"active", "completing"}:
                session["status"] = "expired"
                session["finished_at"] = now_label()
                session["updated_at"] = now_label()
                session["last_error"] = (
                    "Sessione scaduta: staging inattivo rimosso automaticamente."
                )
                changed = True
        if changed:
            bridge_save_sessions(sessions)
    return removed


def bridge_status_payload():
    with BRIDGE_LOCK:
        sessions = list(bridge_load_sessions()["sessions"].values())
        sessions.sort(key=lambda value: value.get("created_at", ""), reverse=True)
        try:
            free_bytes = shutil.disk_usage(STORAGE_ROOT).free
        except OSError:
            free_bytes = None
        return {
            "ok": True,
            "service": "niwa-import-bridge",
            "version": APP_VERSION,
            "api_version": 1,
            "auth_required": bridge_auth_required(),
            "allowed_extensions": sorted(BRIDGE_ALLOWED_EXTENSIONS),
            "chunk_size": BRIDGE_MAX_CHUNK_SIZE,
            "max_file_size": BRIDGE_MAX_FILE_SIZE,
            "storage_free_bytes": free_bytes,
            "active_sessions": sum(
                session.get("status") in {"active", "completing"}
                for session in sessions
            ),
            "sessions": [
                bridge_public_session(session, include_objects=False)
                for session in sessions[:12]
            ],
        }


def start_import(device_id, profile=None, trigger="manual"):
    global ACTIVE_JOB
    devices = scan_devices(include_ignored=False)
    device = next((value for value in devices if value["id"] == device_id), None)
    if not device:
        raise RuntimeError("Scheda non disponibile o esclusa.")
    selected_profile = profile or device.get("profile")
    if selected_profile not in PROFILES:
        raise RuntimeError("Seleziona un profilo valido.")
    with STATE_LOCK:
        if ACTIVE_JOB:
            raise RuntimeError("Una importazione e gia in corso.")
        ACTIVE_JOB = {"id": "starting"}
    worker = threading.Thread(
        target=run_import,
        args=(device, selected_profile, trigger),
        daemon=True,
    )
    worker.start()


def approve_source(device_id, profile, auto_import):
    if profile not in PROFILES:
        raise RuntimeError("Profilo non valido.")
    devices = scan_devices(include_ignored=False)
    device = next((value for value in devices if value["id"] == device_id), None)
    if not device:
        raise RuntimeError("Scheda non disponibile o esclusa.")
    if not device.get("uuid") and not device.get("fallback_signature"):
        raise RuntimeError("La scheda non espone un identificativo stabile sufficiente per l'approvazione.")

    config = load_config()
    config["sources"] = [
        source for source in config.get("sources", [])
        if source.get("uuid") != device["uuid"]
    ]
    config["sources"].append({
        "id": device["id"],
        "approved": True,
        "uuid": device["uuid"],
        "fallback_signature": device.get("fallback_signature"),
        "identity_method": "filesystem_uuid" if device.get("uuid") else "reader_card_fingerprint",
        "label": device["label"],
        "model": device["model"],
        "serial": device["serial"],
        "profile": profile,
        "auto_import": bool(auto_import),
        "allow_serial_match": False,
        "approved_at": now_label(),
    })
    save_config(config)


def forget_source(device_id):
    config = load_config()
    before = len(config.get("sources", []))
    config["sources"] = [
        source for source in config.get("sources", [])
        if source.get("id") != device_id
    ]
    if len(config["sources"]) == before:
        raise RuntimeError("Sorgente approvata non trovata.")
    save_config(config)


def status_payload():
    with STATE_LOCK:
        active = dict(ACTIVE_JOB) if ACTIVE_JOB else None
    jobs = load_jobs().get("jobs", [])
    devices = scan_devices(include_ignored=True)
    for device in devices:
        device["size_label"] = human_size(device["size"])
    return {
        "service": "niwa-import",
        "version": APP_VERSION,
        "updated": now_label(),
        "scan_error": LAST_SCAN_ERROR,
        "storage_root": str(STORAGE_ROOT),
        "mount_root": str(MOUNT_ROOT),
        "devices": devices,
        "approved_sources": load_config().get("sources", []),
        "active_job": active,
        "jobs": jobs[:12],
        "bridge": {
            "auth_required": bridge_auth_required(),
            "active_sessions": bridge_status_payload()["active_sessions"],
        },
    }


def auto_import_loop():
    global SEEN_APPROVED_DEVICES
    time.sleep(4)
    while True:
        try:
            devices = scan_devices(include_ignored=False)
            present = {
                device["id"] for device in devices
                if device["status"] == "approved"
            }
            inserted = present - SEEN_APPROVED_DEVICES
            for device in devices:
                if (
                    device["id"] in inserted
                    and device["status"] == "approved"
                    and device.get("auto_import")
                ):
                    try:
                        start_import(device["id"], trigger="auto")
                    except RuntimeError:
                        pass
            SEEN_APPROVED_DEVICES = present
        except Exception:
            pass
        time.sleep(4)


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIWA Import</title>
<style>
:root{color-scheme:dark;--bg:#0f0d0d;--panel:#211918;--panel2:#151112;--line:rgba(203,144,124,.28);--text:#fff7f0;--muted:#c8afa4;--accent:#d59a84;--accent2:#f0b8a2;--ok:#22c55e;--warn:#facc15;--err:#ef4444}
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:radial-gradient(circle at 18% -5%,rgba(213,154,132,.22),transparent 34%),linear-gradient(180deg,#0e0c0c,#171211 46%,#0e0c0c);color:var(--text);padding:20px}h1,h2{letter-spacing:0;color:#fff4ec}h1{margin:0 0 6px;font-size:32px}h2{font-size:20px;margin:20px 0 10px}.topbar,.head,.actions{display:flex;gap:12px;align-items:center;justify-content:space-between}.brand{display:flex;gap:12px;align-items:center}.logo{width:52px;height:52px;border-radius:50%;border:1px solid rgba(213,154,132,.42);background:#f2dfcf}.subtitle,.muted,.meta{color:var(--muted);line-height:1.45}.button,button,select{background:rgba(64,45,42,.94);color:white;border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-height:40px}button{cursor:pointer}button:hover,.button:hover{background:rgba(87,61,56,.96)}button:disabled{opacity:.52;cursor:not-allowed}.button{text-decoration:none;display:inline-flex;align-items:center}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.card{background:linear-gradient(180deg,rgba(42,31,29,.94),rgba(18,14,14,.96));border:1px solid var(--line);border-radius:10px;padding:15px;box-shadow:0 18px 34px rgba(0,0,0,.22)}.hero{margin-top:16px}.pill{display:inline-flex;padding:5px 9px;border-radius:999px;border:1px solid rgba(255,255,255,.14);font-size:12px;font-weight:bold}.ok{color:#86efac;border-color:rgba(34,197,94,.38);background:rgba(34,197,94,.14)}.warning{color:#fde68a;border-color:rgba(250,204,21,.38);background:rgba(250,204,21,.14)}.error{color:#fecaca;border-color:rgba(239,68,68,.40);background:rgba(239,68,68,.14)}.info{color:#ffd9cb;border-color:var(--line);background:rgba(213,154,132,.12)}.device-name{font-weight:bold;margin-bottom:5px}.meta{font-size:13px}.actions{justify-content:flex-start;flex-wrap:wrap;margin-top:12px}.empty{color:var(--muted)}.progress{height:10px;margin-top:12px;border-radius:999px;overflow:hidden;background:#151112;border:1px solid rgba(203,144,124,.18)}.fill{height:100%;background:linear-gradient(90deg,#d59a84,#f0b8a2)}.job{display:grid;gap:6px}.job-message{color:#eadbd4;font-size:14px}.banner{display:none;margin-top:14px}.banner.visible{display:block}.checkbox{display:flex;align-items:center;gap:7px;color:#eadbd4;font-size:13px}input[type=checkbox]{width:18px;height:18px;accent-color:#d59a84}
@media(max-width:760px){body{padding:12px}.topbar{display:block}.logo{width:44px;height:44px}.topbar .button{margin-top:10px}.head{align-items:flex-start}.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">
    <img class="logo" src="/static/niwa-logo.png" alt="">
    <div><h1>NIWA Import</h1><div class="subtitle">Ingest locale verificato per schede camera e GoPro.</div></div>
  </div>
  <a class="button" id="dashboardLink" href="/">Dashboard</a>
</div>
<div class="card hero">
  <div class="head"><strong>Stato importazioni</strong><span class="pill info" id="serviceState">Controllo</span></div>
  <div class="muted" id="serviceMessage">Scansione dispositivi in corso.</div>
  <div id="activeJob"></div>
</div>
<div class="card banner" id="banner"></div>
<h2>Schede e dispositivi</h2>
<div class="grid" id="devices"><div class="card empty">Scansione in corso.</div></div>
<h2>Ultime importazioni</h2>
<div class="grid" id="jobs"><div class="card empty">Nessuna importazione registrata.</div></div>
<script>
document.getElementById('dashboardLink').href=`${location.protocol}//${location.hostname}:3000`;
let lastCompleted='';
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function pill(status,label){return `<span class="pill ${status}">${esc(label)}</span>`;}
function profileSelect(id,current='camera'){return `<select id="profile-${id}"><option value="camera"${current==='camera'?' selected':''}>Camera / universale</option><option value="gopro"${current==='gopro'?' selected':''}>GoPro</option></select>`;}
async function post(path,payload){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload||{})});const data=await res.json();if(!res.ok||data.error)throw new Error(data.error||`HTTP ${res.status}`);return data;}
async function approve(id){try{await post('/api/sources/approve',{device_id:id,profile:document.getElementById(`profile-${id}`).value,auto_import:document.getElementById(`auto-${id}`).checked});await load();}catch(e){alert(e.message);}}
async function forget(id){try{await post('/api/sources/forget',{device_id:id});await load();}catch(e){alert(e.message);}}
async function start(id){try{const select=document.getElementById(`profile-${id}`);await post('/api/imports/start',{device_id:id,profile:select?select.value:null});await load();}catch(e){alert(e.message);}}
function deviceCard(d){
  const status=d.status==='approved'?pill('ok','APPROVATA'):d.status==='ignored'?pill('info','ESCLUSA'):pill('warning','DA APPROVARE');
  const details=`${esc(d.device)} - ${esc(d.size_label)} - ${esc(d.fstype||'filesystem non noto')}<br>${esc(d.model||d.vendor||'lettore non identificato')}<br>${esc((d.mountpoints||[]).join(', ')||'non montata')}`;
  let actions='';
  if(d.status==='unknown')actions=`<div class="actions">${profileSelect(d.id)}<label class="checkbox"><input id="auto-${d.id}" type="checkbox" checked>Auto dopo approvazione</label><button onclick="approve('${d.id}')">Approva</button></div>`;
  if(d.status==='approved')actions=`<div class="actions">${profileSelect(d.id,d.profile)}<button onclick="start('${d.id}')">Importa ora</button><button onclick="forget('${d.source.id}')">Dimentica</button></div>`;
  if(d.status==='ignored')actions=`<div class="meta">${esc((d.ignored_reasons||[]).join(' - '))}</div>`;
  return `<div class="card"><div class="head"><div class="device-name">${esc(d.label)}</div>${status}</div><div class="meta">${details}</div>${actions}</div>`;
}
function jobCard(j){
  const status=j.status==='completed'?pill('ok','COMPLETATA'):j.status==='running'?pill('warning','IN CORSO'):pill('error','INTERROTTA');
  const progress=j.total_files?Math.round((j.processed_files/j.total_files)*100):0;
  return `<div class="card job"><div class="head"><strong>${esc(j.label||j.device)}</strong>${status}</div><div class="meta">${esc(j.started||'')} - profilo ${esc(j.profile||'')}</div><div class="job-message">${esc(j.message||'')}</div><div class="meta">${j.processed_files||0}/${j.total_files||0} file letti, ${j.published_files||0} pubblicati, ${j.duplicate_files||0} duplicati, ${j.fast_skipped_files||0} saltati rapidamente</div><div class="progress"><div class="fill" style="width:${progress}%"></div></div></div>`;
}
function notifyCompleted(jobs){
  const latest=(jobs||[]).find(j=>j.status==='completed');
  if(!latest||latest.id===lastCompleted)return;
  lastCompleted=latest.id;
  const banner=document.getElementById('banner');
  banner.className='card banner visible';
  banner.innerHTML=`<strong>Importazione completata</strong><div class="muted">${esc(latest.message)}</div>`;
}
async function load(){
  try{
    const res=await fetch('/api/status',{cache:'no-store'});const data=await res.json();
    document.getElementById('serviceState').className='pill ok';document.getElementById('serviceState').textContent='PRONTO';
    document.getElementById('serviceMessage').textContent=data.scan_error?`Errore scansione: ${data.scan_error}`:'Schede sconosciute in attesa di approvazione. Lo storage NIWA resta escluso.';
    document.getElementById('devices').innerHTML=data.devices.length?data.devices.map(deviceCard).join(''):'<div class="card empty">Nessuna scheda o unita compatibile rilevata.</div>';
    document.getElementById('jobs').innerHTML=data.jobs.length?data.jobs.map(jobCard).join(''):'<div class="card empty">Nessuna importazione registrata.</div>';
    document.getElementById('activeJob').innerHTML=data.active_job&&data.active_job.id!=='starting'?jobCard(data.active_job):'';
    notifyCompleted(data.jobs);
  }catch(e){document.getElementById('serviceState').className='pill error';document.getElementById('serviceState').textContent='ERRORE';document.getElementById('serviceMessage').textContent=e.message;}
}
load();setInterval(load,4000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(max(5, BRIDGE_SOCKET_TIMEOUT_SECONDS))

    def log_message(self, pattern, *args):
        print(f"[{now_label()}] {self.address_string()} {pattern % args}", flush=True)

    def send_json(self, payload, status=200, headers=None, cors=True):
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Content-Range")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, body):
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            raise ApiError("Content-Length non valido.") from None
        if length < 0:
            raise ApiError("Content-Length non valido.")
        if length > 1024 * 64:
            raise ApiError("Richiesta troppo grande.", status=413)
        raw = self.rfile.read(length) if length else b"{}"
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Payload non valido.")
        return payload

    def require_bridge_auth(self):
        if not bridge_authorization_valid(self.headers.get("Authorization", "")):
            raise ApiError("Token bridge mancante o non valido.", status=401)

    def send_error_payload(self, error):
        status = error.status if isinstance(error, ApiError) else 400
        payload = {"error": str(error)}
        if isinstance(error, ApiError):
            payload.update(error.details)
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        self.send_json(payload, status, headers=headers)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Content-Range")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path.startswith("/api/bridge/v1/"):
                if path == "/api/bridge/v1/provision/token":
                    if not bridge_loopback_address(self.client_address[0]):
                        raise ApiError(
                            "Provisioning token disponibile solo via loopback.",
                            status=403,
                        )
                    self.send_json(
                        {
                            "ok": True,
                            "token": ensure_bridge_token(),
                        },
                        headers={"Cache-Control": "no-store"},
                        cors=False,
                    )
                    return
                self.require_bridge_auth()
                if path == "/api/bridge/v1/status":
                    self.send_json(bridge_status_payload())
                    return
                match = re.fullmatch(
                    rf"/api/bridge/v1/sessions/{BRIDGE_ROUTE_ID}",
                    path,
                )
                if match:
                    self.send_json(bridge_get_session(match.group(1)))
                    return
                match = re.fullmatch(
                    rf"/api/bridge/v1/uploads/{BRIDGE_ROUTE_ID}",
                    path,
                )
                if match:
                    self.send_json(bridge_get_upload(match.group(1)))
                    return
                self.send_json({"error": "Endpoint bridge non trovato."}, 404)
                return
        except Exception as error:
            self.send_error_payload(error)
            return

        if path == "/":
            self.send_html(INDEX_HTML)
            return
        if path == "/api/health":
            self.send_json({"ok": True, "service": "niwa-import", "version": APP_VERSION})
            return
        if path == "/api/status":
            self.send_json(status_payload())
            return
        if path == "/static/niwa-logo.png":
            logo = Path(__file__).resolve().parent / "static" / "niwa-logo.png"
            if logo.exists():
                payload = logo.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.end_headers()
            return
        self.send_json({"error": "Endpoint non trovato."}, 404)

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            if path.startswith("/api/bridge/v1/"):
                self.require_bridge_auth()
            payload = self.read_json()
            if path.startswith("/api/bridge/v1/"):
                if path == "/api/bridge/v1/sessions":
                    self.send_json(bridge_create_session(payload), 201)
                    return
                match = re.fullmatch(
                    rf"/api/bridge/v1/sessions/{BRIDGE_ROUTE_ID}/objects/preflight",
                    path,
                )
                if match:
                    self.send_json(bridge_preflight(match.group(1), payload))
                    return
                match = re.fullmatch(
                    rf"/api/bridge/v1/uploads/{BRIDGE_ROUTE_ID}/complete",
                    path,
                )
                if match:
                    self.send_json(bridge_complete_upload(match.group(1), payload))
                    return
                match = re.fullmatch(
                    rf"/api/bridge/v1/sessions/{BRIDGE_ROUTE_ID}/complete",
                    path,
                )
                if match:
                    self.send_json(bridge_complete_session(match.group(1)))
                    return
                match = re.fullmatch(
                    rf"/api/bridge/v1/sessions/{BRIDGE_ROUTE_ID}/abort",
                    path,
                )
                if match:
                    self.send_json(bridge_abort_session(match.group(1)))
                    return
                self.send_json({"error": "Endpoint bridge non trovato."}, 404)
                return

            if path == "/api/sources/approve":
                approve_source(
                    payload.get("device_id", ""),
                    payload.get("profile", ""),
                    bool(payload.get("auto_import")),
                )
                self.send_json({"ok": True})
                return
            if path == "/api/sources/forget":
                forget_source(payload.get("device_id", ""))
                self.send_json({"ok": True})
                return
            if path == "/api/imports/start":
                start_import(
                    payload.get("device_id", ""),
                    payload.get("profile"),
                    trigger="manual",
                )
                self.send_json({"ok": True})
                return
            self.send_json({"error": "Endpoint non trovato."}, 404)
        except Exception as error:
            self.send_error_payload(error)

    def do_PUT(self):
        try:
            path = urlsplit(self.path).path
            match = re.fullmatch(
                rf"/api/bridge/v1/uploads/{BRIDGE_ROUTE_ID}",
                path,
            )
            if not match:
                self.send_json({"error": "Endpoint non trovato."}, 404)
                return
            self.require_bridge_auth()
            content_range = self.headers.get("Content-Range", "")
            range_match = BRIDGE_CONTENT_RANGE.fullmatch(content_range)
            if not range_match:
                raise ApiError("Header Content-Range mancante o non valido.")
            start, end, total = (int(value) for value in range_match.groups())
            try:
                content_length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                raise ApiError("Header Content-Length mancante o non valido.") from None
            expected_length = end - start + 1
            if content_length != expected_length:
                raise ApiError("Content-Length e Content-Range non coincidono.")
            if content_length < 1 or content_length > BRIDGE_MAX_CHUNK_SIZE:
                raise ApiError(
                    "Chunk oltre il limite configurato.",
                    status=413,
                    max_chunk_size=BRIDGE_MAX_CHUNK_SIZE,
                )
            chunks = []
            remaining = content_length
            while remaining:
                chunk = self.rfile.read(min(remaining, 64 * 1024))
                if not chunk:
                    raise ApiError("Corpo del chunk incompleto.")
                chunks.append(chunk)
                remaining -= len(chunk)
            response = bridge_receive_chunk(
                match.group(1),
                start,
                end,
                total,
                b"".join(chunks),
            )
            self.send_json(response)
        except Exception as error:
            self.send_error_payload(error)


def serve():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    MOUNT_ROOT.mkdir(parents=True, exist_ok=True)
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    BRIDGE_STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_bridge_token()
    cleanup_old_staging()
    cleanup_old_bridge_staging()
    monitor = threading.Thread(target=auto_import_loop, daemon=True)
    monitor.start()
    staging_cleanup = threading.Thread(target=staging_cleanup_loop, daemon=True)
    staging_cleanup.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"NIWA Import {APP_VERSION} listening on 0.0.0.0:{PORT}", flush=True)
    print(
        "NIWA Bridge API /api/bridge/v1 "
        "(token required; local provisioning on /api/bridge/v1/provision/token)",
        flush=True,
    )
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="NIWA Import removable media assistant")
    parser.add_argument("--scan-once", action="store_true", help="print detected storage devices and exit")
    arguments = parser.parse_args()
    if arguments.scan_once:
        print(json.dumps(status_payload(), indent=2, ensure_ascii=True))
        return
    serve()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        raise
