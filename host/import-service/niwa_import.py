#!/usr/bin/env python3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlrequest
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import traceback


APP_VERSION = "0.2.0"
PORT = int(os.environ.get("NIWA_IMPORT_PORT", "5057"))
PROJECT_ROOT = Path(os.environ.get("NIWA_PROJECT_ROOT", "/home/niwa/niwa"))
DATA_ROOT = Path(os.environ.get("NIWA_DATA_ROOT", str(PROJECT_ROOT / "data")))
STORAGE_ROOT = Path(os.environ.get("NIWA_STORAGE_ROOT", "/mnt/niwa-storage"))
MOUNT_ROOT = Path(os.environ.get("NIWA_IMPORT_MOUNT_ROOT", "/mnt/niwa-import"))
STAGING_ROOT = STORAGE_ROOT / ".niwa_import_staging"
STAGING_RETENTION_SECONDS = int(os.environ.get("NIWA_IMPORT_STAGING_RETENTION_SECONDS", str(24 * 3600)))
STAGING_CLEANUP_INTERVAL_SECONDS = int(os.environ.get("NIWA_IMPORT_STAGING_CLEANUP_INTERVAL_SECONDS", str(3600)))

CONFIG_FILE = DATA_ROOT / "import_sources.json"
JOBS_FILE = DATA_ROOT / "import_jobs.json"
HASHES_FILE = DATA_ROOT / "import_hashes.json"

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

STATE_LOCK = threading.Lock()
JOBS_LOCK = threading.Lock()
ACTIVE_JOB = None
LAST_SCAN_ERROR = None
SEEN_APPROVED_DEVICES = set()


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
    payload = load_json(HASHES_FILE, {"version": 2, "files": {}, "sources": {}})
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
        return {"version": 2, "files": {}, "sources": {}}
    if not isinstance(payload.get("sources"), dict):
        payload["sources"] = {}
    payload["version"] = 2
    return payload


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
        if (
            destination.exists()
            and cached.get("quick_hash") == signature["quick_hash"]
        ):
            return signature, destination, cached.get("digest")

    for destination, digest in destinations.get(key, []):
        try:
            if destination.exists() and quick_fingerprint(destination)["quick_hash"] == signature["quick_hash"]:
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
    return destination.with_name(f"{destination.stem}_conflict_{digest[:8]}{destination.suffix}"), False


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
        time.sleep(STAGING_CLEANUP_INTERVAL_SECONDS)


def run_import(device, profile, trigger):
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
            if known and Path(known).exists():
                item["staged"].unlink(missing_ok=True)
                job["duplicate_files"] += 1
                remember_source_file(
                    source_inventory,
                    item["inventory_key"],
                    item["signature"],
                    item["digest"],
                    Path(known),
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
    def log_message(self, pattern, *args):
        print(f"[{now_label()}] {self.address_string()} {pattern % args}", flush=True)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
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
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 1024 * 64:
            raise RuntimeError("Richiesta troppo grande.")
        raw = self.rfile.read(length) if length else b"{}"
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Payload non valido.")
        return payload

    def do_GET(self):
        if self.path == "/":
            self.send_html(INDEX_HTML)
            return
        if self.path == "/api/health":
            self.send_json({"ok": True, "service": "niwa-import", "version": APP_VERSION})
            return
        if self.path == "/api/status":
            self.send_json(status_payload())
            return
        if self.path == "/static/niwa-logo.png":
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
            payload = self.read_json()
            if self.path == "/api/sources/approve":
                approve_source(
                    payload.get("device_id", ""),
                    payload.get("profile", ""),
                    bool(payload.get("auto_import")),
                )
                self.send_json({"ok": True})
                return
            if self.path == "/api/sources/forget":
                forget_source(payload.get("device_id", ""))
                self.send_json({"ok": True})
                return
            if self.path == "/api/imports/start":
                start_import(
                    payload.get("device_id", ""),
                    payload.get("profile"),
                    trigger="manual",
                )
                self.send_json({"ok": True})
                return
            self.send_json({"error": "Endpoint non trovato."}, 404)
        except Exception as error:
            self.send_json({"error": str(error)}, 400)


def serve():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    MOUNT_ROOT.mkdir(parents=True, exist_ok=True)
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    cleanup_old_staging()
    monitor = threading.Thread(target=auto_import_loop, daemon=True)
    monitor.start()
    staging_cleanup = threading.Thread(target=staging_cleanup_loop, daemon=True)
    staging_cleanup.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"NIWA Import {APP_VERSION} listening on 0.0.0.0:{PORT}", flush=True)
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
