from flask import Flask, Response, abort, jsonify, request, send_file
from pathlib import Path
import base64
import hashlib
import html
import io
import json
import math
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile

from werkzeug.exceptions import NotFound

app = Flask(__name__)

PHOTO_ROOT = Path("/storage/photo")
VIDEO_ROOT = Path("/storage/video")
GOPRO_ROOT = Path("/storage/gopro")
COMPANION_ROOT = Path("/storage/companion")
CACHE_ROOT = Path("/storage/.niwa_cache/review_previews")
DERIVATIVE_ROOT = Path("/storage/.niwa_cache/review_media")
JPG_EXPORT_ROOT = Path("/storage/.niwa_cache/review_jpg")
EDITOR_PREVIEW_ROOT = Path("/storage/.niwa_cache/review_editor")
PRINT_FRAME_ROOT = Path("/storage/.niwa_frames")
PRINT_EXPORT_ROOT = Path("/storage/exports/print")
VIDEO_CACHE_ROOT = Path("/storage/.niwa_cache/review_video_thumbs")
PREVIEW_STATE_FILE = CACHE_ROOT / "preview_state.json"
DATA_ROOT = Path("/data")
REVIEW_INDEX_FILE = DATA_ROOT / "review_index.json"
STORAGE_ROOT = Path("/storage")
TRASH_ROOT = STORAGE_ROOT / ".niwa_trash"
# NIWA Import reads deleted_paths from here so deleted media never come back.
TRASH_FILE = DATA_ROOT / "review_trash.json"
# Written by NIWA Import; Review only reads them to show RAWs still arriving.
BRIDGE_SESSIONS_FILE = DATA_ROOT / "bridge_sessions.json"
BRIDGE_STAGING_ROOT = Path("/storage/.niwa_bridge_staging")
INCOMING_ROOT = Path("/storage/.niwa_cache/review_incoming")
TRASH_ID_PATTERN = re.compile("[0-9a-f]{32}")
TRASH_JOURNAL_NAME = ".niwa-item.json"
TRASH_LOCK = threading.RLock()
JPG_EXPORT_LOCK = threading.Lock()
PRINT_FRAME_LOCK = threading.Lock()
EDITOR_PREVIEW_LOCK = threading.Lock()
INDEX_REBUILD_LOCK = threading.Lock()
INCOMING_LOCK = threading.Lock()

PRINT_PRESETS = {
    "original": {"label": "Originale"},
    "P": {"label": "P · Cartolina", "mm": [148, 100], "pixels": [1748, 1181]},
    "L": {"label": "L · Foto", "mm": [119, 89], "pixels": [1406, 1051]},
    "C": {"label": "C · Carta", "mm": [86, 54], "pixels": [1016, 638]},
    "1:1": {"label": "1:1", "ratio": [1, 1]},
    "3:2": {"label": "3:2", "ratio": [3, 2]},
    "4:3": {"label": "4:3", "ratio": [4, 3]},
    "4:5": {"label": "4:5", "ratio": [4, 5]},
    "9:16": {"label": "9:16", "ratio": [9, 16]},
}

INDEX_VERSION = 2
INDEX_SCAN_INTERVAL_SECONDS = 120
PREVIEW_SCAN_INTERVAL_SECONDS = 20
# Part of every RAW preview cache key: bump it to regenerate them all.
# 2: previews carry the RAW orientation, so vertical shots show upright.
RAW_PREVIEW_VERSION = 2
DERIVATIVE_VERSION = 1
DERIVATIVE_SIZES = {"thumb": 640, "viewer": 2400}
JPG_EXPORT_MAX_BYTES = 2 * 1024 * 1024 * 1024
PREVIEW_STABLE_SECONDS = 60
PREVIEW_RETRY_SECONDS = 300
# The worker rescans after this much work, so shots that arrived meanwhile
# (newest first) do not wait behind a long backlog.
PREVIEW_BATCH_SECONDS = 10
# A RAW's IFDs, which locate its embedded JPEGs, fit well inside this.
INCOMING_HEADER_BYTES = 256 * 1024
INCOMING_STALL_SECONDS = 120
EMBEDDED_JPEG_TAGS = ("JpgFromRaw", "PreviewImage", "OtherImage")
DEFAULT_PAGE_SIZE = 80
MAX_PAGE_SIZE = 220

RAW_EXTENSIONS = {
    ".3fr", ".arw", ".cr2", ".cr3", ".dng", ".erf", ".fff", ".gpr",
    ".iiq", ".kdc", ".mos", ".mrw", ".nef", ".nrw", ".orf", ".pef",
    ".raf", ".raw", ".rwl", ".rw2", ".srw", ".x3f",
}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}
VIDEO_EXTENSIONS = {".avi", ".braw", ".crm", ".m2ts", ".m4v", ".mov", ".mp4", ".mts", ".mxf"}
PHOTO_EXTENSIONS = RAW_EXTENSIONS | JPEG_EXTENSIONS
GOPRO_EXTENSIONS = JPEG_EXTENSIONS | VIDEO_EXTENSIONS | {".gpr"}

MEDIA_SECTIONS = {
    "photo": {
        "label": "Foto",
        "root": PHOTO_ROOT,
        "extensions": PHOTO_EXTENSIONS,
        "empty": "Nessun RAW o JPG trovato nella cartella photo.",
    },
    "video": {
        "label": "Video",
        "root": VIDEO_ROOT,
        "extensions": VIDEO_EXTENSIONS,
        "empty": "Nessun video trovato nella cartella video.",
    },
    "gopro": {
        "label": "GoPro",
        "root": GOPRO_ROOT,
        "extensions": GOPRO_EXTENSIONS,
        "empty": "Nessun JPG o MP4 trovato nella cartella gopro.",
    },
    "companion": {
        "label": "Companion",
        "root": COMPANION_ROOT,
        "extensions": JPEG_EXTENSIONS,
        "empty": "Nessuno scatto Companion trovato.",
    },
}

WORKER_LOCK = threading.Lock()
WORKER_STATE = {
    "running": False,
    "last_scan": None,
    "current": None,
    "queued": 0,
    "cached": 0,
    "processed": 0,
    "errors": 0,
    "message": "Worker non ancora avviato.",
}

INDEX_LOCK = threading.Lock()
INDEX_STATE = {
    "running": False,
    "last_scan": None,
    "duration_ms": 0,
    "items": 0,
    "errors": 0,
    "message": "Indice non ancora avviato.",
}

XMP_TEMPLATE = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:xmp="http://ns.adobe.com/xap/1.0/"
      xmp:Rating="{rating}" />
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""


def encode_id(relative_path):
    raw = str(relative_path).replace("\\", "/").encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_id(file_id):
    try:
        padded = file_id + "=" * (-len(file_id) % 4)
        value = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception:
        abort(400, "Invalid file id")

    if value.startswith("/") or ".." in Path(value).parts:
        abort(400, "Unsafe file path")

    return Path(value)


def section_config(section):
    config = MEDIA_SECTIONS.get(section)
    if not config:
        abort(404, "Unknown media section")
    return config


def resolve_media(root_path, file_id):
    relative = decode_id(file_id)
    path = (root_path / relative).resolve()
    root = root_path.resolve()

    try:
        path.relative_to(root)
    except ValueError:
        abort(400, "Path outside media root")

    if not path.exists() or not path.is_file():
        abort(404, "File not found")

    return path, relative


def resolve_photo(file_id):
    return resolve_media(PHOTO_ROOT, file_id)


def xmp_path_for(path):
    if path.suffix.lower() in RAW_EXTENSIONS:
        return path.with_suffix(".xmp")
    return path.with_name(f"{path.name}.xmp")


def read_rating(path):
    xmp_path = xmp_path_for(path)
    if not xmp_path.exists():
        return 0

    try:
        root = ET.parse(xmp_path).getroot()
    except Exception:
        return 0

    for element in root.iter():
        for key, value in element.attrib.items():
            if key.endswith("Rating"):
                try:
                    rating = int(value)
                except ValueError:
                    return 0
                return max(0, min(5, rating))

    return 0


def write_rating(path, rating):
    rating = max(0, min(5, int(rating)))
    xmp_path = xmp_path_for(path)

    if rating == 0:
        if xmp_path.exists():
            xmp_path.unlink()
        return

    xmp_path.write_text(XMP_TEMPLATE.format(rating=rating), encoding="utf-8")


def human_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def atomic_write_json(path, payload, **dump_options):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, **dump_options)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def media_kind(path):
    suffix = path.suffix.lower()
    if suffix in RAW_EXTENSIONS:
        return "raw"
    if suffix in JPEG_EXTENSIONS:
        return "photo"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return "file"


def iter_media_files(root_path, extensions):
    if not root_path.exists():
        return

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [
            directory for directory in dirs
            if not directory.startswith(".") and directory != ".niwa_cache"
        ]

        root_path_current = Path(root)
        for filename in files:
            path = root_path_current / filename
            if path.suffix.lower() not in extensions:
                continue

            try:
                relative = path.relative_to(root_path)
            except ValueError:
                continue

            yield path, relative


def iter_photo_files(extensions):
    yield from iter_media_files(PHOTO_ROOT, extensions)


def media_item_from_path(section, path, relative):
    suffix = path.suffix.lower()
    kind = media_kind(path)

    try:
        stat = path.stat()
    except OSError:
        return None

    file_id = encode_id(relative)
    cache_version = f"{stat.st_mtime_ns:x}-{stat.st_size:x}"
    thumbnail_url = (
        f"/api/media-image/thumb/{section}/{file_id}?v={cache_version}"
    )
    preview_url = (
        f"/api/video-thumb/{section}/{file_id}"
        if kind == "video" else
        f"/api/media-image/viewer/{section}/{file_id}?v={cache_version}"
    )

    return {
        "id": file_id,
        "section": section,
        "name": path.name,
        "relative_path": str(relative).replace("\\", "/"),
        "extension": suffix.upper().lstrip("."),
        "kind": kind,
        "size": stat.st_size,
        "size_label": human_size(stat.st_size),
        "mtime": stat.st_mtime,
        "mtime_ns": stat.st_mtime_ns,
        "mtime_label": time.strftime(
            "%Y-%m-%d %H:%M",
            time.localtime(stat.st_mtime)
        ),
        "thumbnail_url": thumbnail_url,
        "preview_url": preview_url,
        "media_url": f"/api/media-file/{section}/{file_id}",
        "download_url": f"/api/download/{section}/{file_id}",
        "download_jpg_url": (
            f"/api/download-jpg/{section}/{file_id}"
            if section == "photo" and suffix in RAW_EXTENSIONS else None
        ),
        "rating": read_rating(path),
    }


def filter_kind(items, kind_filter):
    if kind_filter == "all":
        return items

    filtered = []
    for item in items:
        kind = item.get("kind")
        if kind_filter == "photo" and kind == "video":
            continue
        if kind_filter == "video" and kind != "video":
            continue
        filtered.append(item)
    return filtered


def media_order(item):
    """Newest capture first. The path breaks ties, such as a burst shot within
    one second, so the gallery and the trash list media in the same order."""
    return item["mtime_ns"], item["relative_path"]


def scan_media_filesystem(section, kind_filter="all"):
    config = section_config(section)
    root_path = config["root"]
    items = []

    for path, relative in iter_media_files(root_path, config["extensions"]):
        item = media_item_from_path(section, path, relative)
        if not item:
            continue

        if kind_filter == "photo" and item["kind"] == "video":
            continue
        if kind_filter == "video" and item["kind"] != "video":
            continue

        items.append(item)

    items.sort(key=media_order, reverse=True)
    return items


def load_review_index():
    if not REVIEW_INDEX_FILE.exists():
        return None

    try:
        with open(REVIEW_INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    if data.get("version") != INDEX_VERSION:
        return None
    if not isinstance(data.get("sections"), dict):
        return None

    return data


def save_review_index(index):
    atomic_write_json(REVIEW_INDEX_FILE, index, indent=2)


def index_summary(index):
    sections = index.get("sections", {})
    total = 0
    summary = {}

    for section, payload in sections.items():
        items = payload.get("items", [])
        total += len(items)
        summary[section] = {
            "count": len(items),
            "exists": payload.get("exists", False),
            "root": payload.get("root", ""),
            "kind_counts": payload.get("kind_counts", {}),
        }

    return {
        "version": index.get("version"),
        "updated": index.get("updated"),
        "duration_ms": index.get("duration_ms", 0),
        "total_items": total,
        "sections": summary,
    }


def cleanup_orphan_raw_previews(raw_files):
    expected = set()
    expected_jpg = set()
    for path, relative in raw_files:
        try:
            expected.add(cache_path_for(path, relative).resolve())
            expected_jpg.add(jpg_export_path_for(path, relative).resolve())
        except OSError:
            continue

    removed = 0
    for directory, keep in ((CACHE_ROOT, expected),
                            (JPG_EXPORT_ROOT, expected_jpg)):
        if not directory.exists():
            continue
        for cache_file in directory.glob("*.jpg"):
            try:
                resolved = cache_file.resolve()
            except OSError:
                continue
            if resolved in keep:
                continue
            try:
                cache_file.unlink()
                removed += 1
            except OSError:
                pass

    return removed + trim_cache(JPG_EXPORT_ROOT, JPG_EXPORT_MAX_BYTES)


def trim_cache(directory, maximum_bytes):
    if not directory.is_dir():
        return 0
    files = []
    total = 0
    for path in directory.glob("*.jpg"):
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((stat.st_mtime_ns, stat.st_size, path))
        total += stat.st_size
    removed = 0
    for _mtime, size, path in sorted(files):
        if total <= maximum_bytes:
            break
        try:
            path.unlink()
        except OSError:
            continue
        total -= size
        removed += 1
    return removed


def cleanup_orphan_video_thumbnails():
    expected = set()
    for section, config in MEDIA_SECTIONS.items():
        for path, relative in iter_media_files(config["root"], config["extensions"]):
            if media_kind(path) != "video":
                continue
            try:
                expected.add(video_thumb_path_for(section, path, relative).resolve())
            except OSError:
                continue

    if not VIDEO_CACHE_ROOT.exists():
        return 0

    removed = 0
    for cache_file in VIDEO_CACHE_ROOT.glob("*.jpg"):
        try:
            resolved = cache_file.resolve()
        except OSError:
            continue
        if resolved in expected:
            continue
        try:
            cache_file.unlink()
            removed += 1
        except OSError:
            pass

    return removed


def cleanup_orphan_media_derivatives():
    expected = set()
    for section, config in MEDIA_SECTIONS.items():
        for path, relative in iter_media_files(config["root"], config["extensions"]):
            for variant in DERIVATIVE_SIZES:
                try:
                    expected.add(
                        derivative_path_for(section, path, relative, variant).resolve()
                    )
                except OSError:
                    continue

    if not DERIVATIVE_ROOT.exists():
        return 0

    removed = 0
    for cache_file in DERIVATIVE_ROOT.glob("*.jpg"):
        try:
            resolved = cache_file.resolve()
        except OSError:
            continue
        if resolved in expected:
            continue
        try:
            cache_file.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def cleanup_orphan_editor_previews():
    expected = set()
    for path, relative in iter_photo_files(PHOTO_EXTENSIONS):
        try:
            expected.add(editor_preview_path(path, relative).resolve())
        except OSError:
            continue
    if not EDITOR_PREVIEW_ROOT.exists():
        return 0
    removed = 0
    for cache_file in EDITOR_PREVIEW_ROOT.glob("*.jpg"):
        try:
            if cache_file.resolve() in expected:
                continue
            cache_file.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def update_index_state(**updates):
    with INDEX_LOCK:
        INDEX_STATE.update(updates)


def rebuild_review_index():
    with INDEX_REBUILD_LOCK:
        return rebuild_review_index_locked()


def rebuild_review_index_locked():
    started = time.time()
    update_index_state(running=True, message="Indicizzazione media in corso.")

    sections = {}
    total_items = 0

    try:
        for section, config in MEDIA_SECTIONS.items():
            items = scan_media_filesystem(section, "all")
            kind_counts = {}
            for item in items:
                kind = item.get("kind", "file")
                kind_counts[kind] = kind_counts.get(kind, 0) + 1

            sections[section] = {
                "label": config["label"],
                "root": str(config["root"]),
                "exists": config["root"].exists(),
                "empty_message": config["empty"],
                "count": len(items),
                "kind_counts": kind_counts,
                "items": items,
            }
            total_items += len(items)

        cleanup_orphan_video_thumbnails()
        cleanup_orphan_media_derivatives()
        cleanup_orphan_editor_previews()

        index = {
            "version": INDEX_VERSION,
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_ts": time.time(),
            "duration_ms": int((time.time() - started) * 1000),
            "sections": sections,
        }
        save_review_index(index)
        update_index_state(
            running=False,
            last_scan=index["updated"],
            duration_ms=index["duration_ms"],
            items=total_items,
            message=f"Indice aggiornato: {total_items} file.",
        )
        return index
    except Exception as exc:
        update_index_state(
            running=False,
            errors=INDEX_STATE.get("errors", 0) + 1,
            message=f"Errore indice: {exc}",
        )
        raise


def get_review_index(force=False):
    if not force:
        index = load_review_index()
        if index:
            return index

    return rebuild_review_index()


def index_worker_loop():
    time.sleep(3)

    while True:
        try:
            rebuild_review_index()
        except Exception:
            pass

        time.sleep(INDEX_SCAN_INTERVAL_SECONDS)


def scan_media(section, kind_filter="all", use_index=True):
    if not use_index:
        return scan_media_filesystem(section, kind_filter)

    index = get_review_index()
    section_data = index.get("sections", {}).get(section)
    if not section_data:
        return scan_media_filesystem(section, kind_filter)

    items = section_data.get("items", [])
    return filter_kind(items, kind_filter)


def update_index_rating(section, file_id, rating):
    with INDEX_REBUILD_LOCK:
        index = load_review_index()
        if not index:
            return

        changed = False
        items = index.get("sections", {}).get(section, {}).get("items", [])
        for item in items:
            if item.get("id") == file_id:
                item["rating"] = rating
                changed = True
                break

        if changed:
            index["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            index["updated_ts"] = time.time()
            save_review_index(index)


def scan_photos():
    return scan_media("photo")


def load_trash():
    with TRASH_LOCK:
        try:
            payload = json.loads(TRASH_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        items = payload.get("items")
        deleted = payload.get("deleted_paths")
        trash = {
            "version": 1,
            "items": items if isinstance(items, dict) else {},
            "deleted_paths": [
                path for path in deleted if isinstance(path, str)
            ] if isinstance(deleted, list) else [],
        }
        changed, journals = recover_trash_journals(trash)
        if changed:
            save_trash(trash)
        for journal in journals:
            journal.unlink(missing_ok=True)
            try:
                journal.parent.rmdir()
            except OSError:
                pass
        return trash


def save_trash(trash):
    atomic_write_json(TRASH_FILE, trash, indent=2, sort_keys=True)


def storage_relative(section, relative):
    """Path as NIWA Import records it under the SSD root, e.g. photo/imports/..."""
    root = section_config(section)["root"]
    return (root.relative_to(STORAGE_ROOT) / relative).as_posix()


def safe_relative(value):
    relative = Path(str(value))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        return None
    return relative


def plain_name(value):
    name = str(value or "")
    return name if name not in ("", ".", "..") and Path(name).name == name else None


def recover_trash_journals(trash):
    if not TRASH_ROOT.is_dir():
        return False, []

    changed = False
    completed = []
    deleted = set(trash["deleted_paths"])
    for folder in TRASH_ROOT.iterdir():
        if not folder.is_dir() or not TRASH_ID_PATTERN.fullmatch(folder.name):
            continue
        journal = folder / TRASH_JOURNAL_NAME
        if not journal.is_file():
            continue
        try:
            item = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        config = MEDIA_SECTIONS.get(item.get("section")) if isinstance(item, dict) else None
        relative = safe_relative(item.get("relative", "")) if config else None
        name = plain_name(item.get("name")) if config else None
        if item.get("id") != folder.name or not relative or not name:
            continue

        stored = folder / name
        original = config["root"] / relative
        deleted_path = storage_relative(item["section"], relative)
        if stored.is_file():
            if trash["items"].get(folder.name) != item:
                trash["items"][folder.name] = item
                changed = True
            if deleted_path not in deleted:
                deleted.add(deleted_path)
                changed = True
            completed.append(journal)
            continue

        if not original.is_file():
            continue
        sidecar_name = plain_name(item.get("sidecar"))
        parked_sidecar = folder / (sidecar_name or "")
        target_sidecar = xmp_path_for(original)
        if sidecar_name and parked_sidecar.is_file() and not target_sidecar.exists():
            target_sidecar.parent.mkdir(parents=True, exist_ok=True)
            os.replace(parked_sidecar, target_sidecar)
        if trash["items"].pop(folder.name, None) is not None:
            changed = True
        if deleted_path in deleted:
            deleted.discard(deleted_path)
            changed = True
        completed.append(journal)

    normalized_deleted = sorted(deleted)
    if normalized_deleted != trash["deleted_paths"]:
        trash["deleted_paths"] = normalized_deleted
        changed = True
    return changed, completed


def remove_empty_folders(folder, root):
    """Remove folders left empty, walking up to the section root, which stays."""
    root = root.resolve()
    folder = folder.resolve()
    while folder != root and root in folder.parents:
        try:
            folder.rmdir()  # fails, and stops the walk, unless really empty
        except OSError:
            return
        folder = folder.parent


def free_restore_path(target):
    """The original path, or name-1.ext, name-2.ext... if something took it."""
    candidate = target
    counter = 1
    while candidate.exists():
        candidate = target.with_name(f"{target.stem}-{counter}{target.suffix}")
        counter += 1
    return candidate


def refresh_index_quietly():
    try:
        rebuild_review_index()
    except Exception:
        pass  # the index worker rebuilds again on its own schedule


def trash_media(section, file_ids):
    config = section_config(section)
    root = config["root"]
    moved = 0
    missing = 0
    deleted_at = time.strftime("%Y-%m-%d %H:%M:%S")
    with TRASH_LOCK:
        trash = load_trash()
        deleted = set(trash["deleted_paths"])
        for file_id in dict.fromkeys(file_ids):
            try:
                path, relative = resolve_media(root, file_id)
            except NotFound:
                missing += 1
                continue
            if path.suffix.lower() not in config["extensions"]:
                continue
            size = path.stat().st_size
            trash_id = uuid.uuid4().hex
            folder = TRASH_ROOT / trash_id
            folder.mkdir(parents=True)
            sidecar = xmp_path_for(path)
            sidecar_name = sidecar.name if sidecar.is_file() else None
            item = {
                "id": trash_id,
                "section": section,
                "relative": relative.as_posix(),
                "name": path.name,
                "sidecar": sidecar_name,
                "size": size,
                "deleted_at": deleted_at,
            }
            journal = folder / TRASH_JOURNAL_NAME
            atomic_write_json(journal, item, indent=2, sort_keys=True)
            if sidecar_name:
                os.replace(sidecar, folder / sidecar.name)
            os.replace(path, folder / path.name)
            trash["items"][trash_id] = item
            deleted.add(storage_relative(section, relative))
            trash["deleted_paths"] = sorted(deleted)
            save_trash(trash)
            journal.unlink(missing_ok=True)
            remove_empty_folders(path.parent, root)
            moved += 1
    if moved:
        refresh_index_quietly()
    return {"moved": moved, "missing": missing}


def restore_trash(trash_ids=None):
    restored = 0
    errors = []
    with TRASH_LOCK:
        trash = load_trash()
        deleted = set(trash["deleted_paths"])
        if trash_ids is None:
            wanted = list(trash["items"])
        else:
            wanted = [
                trash_id for trash_id in dict.fromkeys(trash_ids)
                if trash_id in trash["items"]
            ]
        for trash_id in wanted:
            item = trash["items"][trash_id]
            config = MEDIA_SECTIONS.get(item.get("section"))
            relative = safe_relative(item.get("relative", ""))
            name = plain_name(item.get("name"))
            stored = TRASH_ROOT / trash_id / (name or "")
            if (
                not config
                or not relative
                or not name
                or not TRASH_ID_PATTERN.fullmatch(trash_id)
                or not stored.is_file()
            ):
                errors.append(f"{name or trash_id}: non ripristinabile")
                continue
            target = free_restore_path(config["root"] / relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stored, target)
            sidecar_name = plain_name(item.get("sidecar"))
            sidecar = TRASH_ROOT / trash_id / (sidecar_name or "")
            if sidecar_name and sidecar.is_file() and not xmp_path_for(target).exists():
                os.replace(sidecar, xmp_path_for(target))
            shutil.rmtree(TRASH_ROOT / trash_id, ignore_errors=True)
            del trash["items"][trash_id]
            deleted.discard(storage_relative(item["section"], relative))
            restored += 1
        trash["deleted_paths"] = sorted(deleted)
        save_trash(trash)
    if restored:
        refresh_index_quietly()
    return {"restored": restored, "errors": errors}


def empty_trash():
    with TRASH_LOCK:
        trash = load_trash()
        before = dict(trash["items"])
        # Everything under .niwa_trash goes, leftovers of an interrupted batch too.
        shutil.rmtree(TRASH_ROOT, ignore_errors=True)
        # Whatever could not be removed stays listed. deleted_paths are kept on
        # purpose: emptied media must never be imported again.
        trash["items"] = {
            trash_id: item for trash_id, item in before.items()
            if (TRASH_ROOT / trash_id).exists()
        }
        save_trash(trash)
    removed = [item for trash_id, item in before.items() if trash_id not in trash["items"]]
    freed = sum(int(item.get("size") or 0) for item in removed)
    return {"removed": len(removed), "freed": freed, "freed_label": human_size(freed)}


def trashed_photo_raws():
    """Trashed photo RAWs as (path, relative), so their cached previews survive."""
    pairs = []
    for trash_id, item in load_trash()["items"].items():
        name = plain_name(item.get("name"))
        relative = safe_relative(item.get("relative", ""))
        if (
            item.get("section") != "photo"
            or not name
            or not relative
            or Path(name).suffix.lower() not in RAW_EXTENSIONS
        ):
            continue
        path = TRASH_ROOT / trash_id / name
        if path.is_file():
            pairs.append((path, relative))
    return pairs


def trash_public_item(item):
    name = item.get("name", "")
    relative = Path(item.get("relative") or name)
    size = int(item.get("size") or 0)
    try:
        # A rename keeps the capture time, so this is the gallery's sort key.
        mtime_ns = (TRASH_ROOT / str(item.get("id")) / name).stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    return {
        "relative_path": relative.as_posix(),
        "mtime_ns": mtime_ns,
        "mtime_label": time.strftime(
            "%Y-%m-%d %H:%M",
            time.localtime(mtime_ns / 1e9),
        ) if mtime_ns else "",
        "id": item.get("id"),
        "section": item.get("section"),
        "name": name,
        "folder": (Path(item.get("section") or "") / relative.parent).as_posix(),
        "kind": media_kind(Path(name)),
        "extension": Path(name).suffix.upper().lstrip("."),
        "size": size,
        "size_label": human_size(size),
        "deleted_at": item.get("deleted_at"),
        "preview_url": f"/api/trash/preview/{item.get('id')}",
    }


class ZipSink:
    """Write-only target that hands zip bytes over to a streaming response."""

    def __init__(self):
        self.parts = []

    def write(self, data):
        self.parts.append(bytes(data))
        return len(data)

    def flush(self):
        pass

    def take(self):
        data = b"".join(self.parts)
        self.parts = []
        return data


def zip_stream(entries):
    """Stream a stored (uncompressed) zip: RAW and JPG do not shrink anyway, and
    neither the Raspberry nor the tablet ever holds the whole archive in memory."""
    sink = ZipSink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, arcname in entries:
            info = zipfile.ZipInfo.from_file(path, arcname)
            info.compress_type = zipfile.ZIP_STORED
            with open(path, "rb") as source, archive.open(info, "w") as target:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    target.write(block)
                    data = sink.take()
                    if data:
                        yield data
    data = sink.take()  # the central directory is written on close
    if data:
        yield data


def cache_path_for(path, relative):
    stat = path.stat()
    key = (
        f"v{RAW_PREVIEW_VERSION}|{relative}|{stat.st_mtime_ns}|{stat.st_size}"
    ).encode("utf-8")
    digest = hashlib.sha1(key).hexdigest()
    return CACHE_ROOT / f"{digest}.jpg"


def jpg_export_path_for(path, relative):
    stat = path.stat()
    key = f"jpg-v1|{relative}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8")
    return JPG_EXPORT_ROOT / f"{hashlib.sha1(key).hexdigest()}.jpg"


def render_raw_jpg(path, relative):
    """Develop full-size sRGB JPEG once; never use the compressed RAW preview."""
    import rawpy
    from PIL import Image, ImageCms

    output = jpg_export_path_for(path, relative)
    with JPG_EXPORT_LOCK:
        if output.is_file() and output.stat().st_size > 0:
            return output
        JPG_EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
        temporary = JPG_EXPORT_ROOT / f"{uuid.uuid4().hex}.tmp"
        try:
            with rawpy.imread(str(path)) as raw:
                pixels = raw.postprocess(
                    use_camera_wb=True,
                    no_auto_bright=True,
                    output_color=rawpy.ColorSpace.sRGB,
                    output_bps=8,
                )
            profile = ImageCms.ImageCmsProfile(
                ImageCms.createProfile("sRGB")
            ).tobytes()
            Image.fromarray(pixels).save(
                temporary,
                format="JPEG",
                quality=100,
                subsampling=0,
                icc_profile=profile,
            )
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    return output


def print_ratio(preset, orientation):
    config = PRINT_PRESETS.get(preset)
    if (config is None or preset == "original"
            or orientation not in {"landscape", "portrait"}):
        raise ValueError("Formato o orientamento non valido.")
    pair = config.get("mm", config.get("ratio"))
    long_side, short_side = max(pair), min(pair)
    if preset == "1:1":
        return 1.0
    return (long_side / short_side if orientation == "landscape"
            else short_side / long_side)


def print_output_size(preset, orientation, source_size, frame_size=None):
    config = PRINT_PRESETS[preset]
    if preset == "original":
        width, height = source_size
        shrink = min(1.0, 6000 / max(width, height))
        return max(1, round(width * shrink)), max(1, round(height * shrink))
    if "pixels" in config:
        width, height = config["pixels"]
        return (width, height) if orientation == "landscape" else (height, width)
    if frame_size:
        return frame_size
    width, height = source_size
    ratio = print_ratio(preset, orientation)
    if width / height > ratio:
        width = round(height * ratio)
    else:
        height = round(width / ratio)
    shrink = min(1.0, 6000 / max(width, height))
    return max(1, round(width * shrink)), max(1, round(height * shrink))


def print_frame_metadata(frame_id):
    if not re.fullmatch(r"[0-9a-f]{32}", frame_id):
        abort(404)
    metadata_path = PRINT_FRAME_ROOT / f"{frame_id}.json"
    image_path = PRINT_FRAME_ROOT / f"{frame_id}.png"
    if not metadata_path.is_file() or not image_path.is_file():
        abort(404)
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        abort(404)
    if data.get("id") != frame_id:
        abort(404)
    return data, image_path


def print_frames():
    if not PRINT_FRAME_ROOT.is_dir():
        return []
    frames = []
    for metadata_path in PRINT_FRAME_ROOT.glob("*.json"):
        frame_id = metadata_path.stem
        if not re.fullmatch(r"[0-9a-f]{32}", frame_id):
            continue
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("id") == frame_id and (PRINT_FRAME_ROOT / f"{frame_id}.png").is_file():
            data["url"] = f"/api/print/frames/{frame_id}/image"
            data["thumbnail_url"] = f"/api/print/frames/{frame_id}/thumbnail"
            frames.append(data)
    return sorted(frames, key=lambda frame: (frame.get("collection", "").lower(), frame.get("name", "").lower()))


def editor_source(path, relative):
    from PIL import Image, ImageCms, ImageOps

    if path.suffix.lower() in RAW_EXTENSIONS:
        import rawpy
        with rawpy.imread(str(path)) as raw:
            pixels = raw.postprocess(
                use_camera_wb=True,
                no_auto_bright=True,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=8,
            )
        return Image.fromarray(pixels)
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original)
        profile = original.info.get("icc_profile")
        if profile:
            try:
                image = ImageCms.profileToProfile(
                    image, io.BytesIO(profile), ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
            except Exception:
                image = image.convert("RGB")
        else:
            image = image.convert("RGB")
        return image.copy()


def light_lut(exposure, shadows, highlights):
    result = []
    for level in range(256):
        value = ((level / 255) ** 2.2 * (2 ** exposure)) ** (1 / 2.2)
        value = min(1.0, value)
        value += shadows * 0.30 * (1 - value) ** 2
        value += highlights * 0.30 * value ** 2
        result.append(round(max(0.0, min(1.0, value)) * 255))
    return result * 3


def color_lut(contrast, temperature, tint):
    """Per-channel 8-bit adjustments used only on the exported copy."""
    channels = []
    gains = (
        1 + temperature * 0.15 + tint * 0.08,
        1 - tint * 0.16,
        1 - temperature * 0.15 + tint * 0.08,
    )
    for gain in gains:
        channels.extend(
            round(max(0, min(255, ((level - 127.5) * (1 + contrast) + 127.5) * gain)))
            for level in range(256)
        )
    return channels


def apply_color_controls(photo, contrast, temperature, tint, vibrance, saturation):
    from PIL import Image, ImageChops, ImageEnhance

    if contrast or temperature or tint:
        photo = photo.point(color_lut(contrast, temperature, tint))
    if saturation:
        photo = ImageEnhance.Color(photo).enhance(1 + saturation)
    if vibrance:
        red, green, blue = photo.split()
        brightest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        darkest = ImageChops.darker(ImageChops.darker(red, green), blue)
        low_color_mask = ImageChops.invert(ImageChops.subtract(brightest, darkest))
        boosted = ImageEnhance.Color(photo).enhance(1 + vibrance)
        photo = Image.composite(boosted, photo, low_color_mask)
    return photo


def reduce_luminance_noise(photo, amount):
    from PIL import Image, ImageFilter

    if not amount:
        return photo
    luminance, blue_difference, red_difference = photo.convert("YCbCr").split()
    blurred = luminance.filter(ImageFilter.GaussianBlur(radius=0.5 + 1.5 * amount))
    softened = Image.blend(luminance, blurred, amount)
    return Image.merge("YCbCr", (softened, blue_difference, red_difference)).convert("RGB")


def editor_preview_path(path, relative):
    stat = path.stat()
    key = f"editor-v1|{relative}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8")
    return EDITOR_PREVIEW_ROOT / f"{hashlib.sha1(key).hexdigest()}.jpg"


def render_editor_preview(path, relative):
    from PIL import Image

    output = editor_preview_path(path, relative)
    with EDITOR_PREVIEW_LOCK:
        if output.is_file() and output.stat().st_size:
            return output
        EDITOR_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in RAW_EXTENSIONS:
            source_path = render_raw_jpg(path, relative)
            with Image.open(source_path) as source:
                image = source.copy()
        else:
            image = editor_source(path, relative)
        image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
        temporary = EDITOR_PREVIEW_ROOT / f"{uuid.uuid4().hex}.tmp"
        try:
            image.save(temporary, format="JPEG", quality=93, subsampling=0)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    return output


def print_number(payload, key, minimum, maximum, default):
    try:
        number = float(payload.get(key, default))
    except (TypeError, ValueError):
        raise ValueError(f"Valore {key} non valido.") from None
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"Valore {key} fuori intervallo.")
    return number


def print_transform(image, size, zoom, offset_x, offset_y, rotation):
    from PIL import Image, ImageChops

    width, height = size
    source_width, source_height = image.size
    angle = math.radians(rotation)
    cosine, sine = math.cos(angle), math.sin(angle)
    # Keep the photo scale fixed while rotating; zoom changes only on request.
    scale = max(width / source_width, height / source_height) * zoom
    center_x = width * (0.5 + offset_x)
    center_y = height * (0.5 + offset_y)
    coefficients = (
        cosine / scale,
        sine / scale,
        source_width / 2 - (cosine * center_x + sine * center_y) / scale,
        -sine / scale,
        cosine / scale,
        source_height / 2 + (sine * center_x - cosine * center_y) / scale,
    )
    transformed = image.transform(
        size, Image.Transform.AFFINE, coefficients,
        resample=Image.Resampling.BICUBIC, fillcolor=(255, 255, 255),
    )
    coverage = Image.new("L", image.size, 255).transform(
        size, Image.Transform.AFFINE, coefficients,
        resample=Image.Resampling.NEAREST, fillcolor=0,
    )
    return transformed, coverage


# Borderless, the SELPHY enlarges whatever it gets to this whole page, so a file
# of exactly the card size printed past the perforations. Where the card really
# falls, in mm from the page edges: measured on the user's CP1500 with the
# Canon app on 2026-10-05 (docker/review-panel/selphy_calibration.py).
# ponytail: one printer measured; print the test sheet again for another unit, or for L and C.
SELPHY_PAGES = {
    "P": {
        "page": (1872, 1248),
        "landscape": {"left": 3.5, "right": 5.0, "top": 2.5, "bottom": 2.2},
        # Not measured yet: the landscape margins averaged, until a portrait test sheet.
        "portrait": {"left": 2.35, "right": 2.35, "top": 4.25, "bottom": 4.25},
    },
}


def selphy_page(card, preset, orientation):
    """The card on the printer's whole page, where the SELPHY really prints it.
    Around it, torn off or off the paper, the card's edges simply continue."""
    import numpy as np
    from PIL import Image

    layout = SELPHY_PAGES.get(preset)
    if not layout:
        return card
    page_w, page_h = layout["page"] if orientation == "landscape" else layout["page"][::-1]
    margin = {side: mm * 300 / 25.4 for side, mm in layout[orientation].items()}
    area_w = page_w - margin["left"] - margin["right"]
    area_h = page_h - margin["top"] - margin["bottom"]
    scale = max(area_w / card.width, area_h / card.height)
    width, height = round(card.width * scale), round(card.height * scale)
    pixels = np.asarray(card.convert("RGB").resize((width, height), Image.Resampling.LANCZOS))
    left = round(margin["left"] + (area_w - width) / 2)
    top = round(margin["top"] + (area_h - height) / 2)
    right, bottom = page_w - left - width, page_h - top - height
    pixels = pixels[max(-top, 0):height - max(-bottom, 0), max(-left, 0):width - max(-right, 0)]
    pad = ((max(top, 0), max(bottom, 0)), (max(left, 0), max(right, 0)), (0, 0))
    return Image.fromarray(np.pad(pixels, pad, mode="edge"))


def render_print_export(path, relative, payload):
    from PIL import Image, ImageChops, ImageCms

    preset = str(payload.get("preset", "P"))
    orientation = str(payload.get("orientation", "landscape"))
    file_type = str(payload.get("file_type", "jpg")).lower()
    if (preset not in PRINT_PRESETS
            or orientation not in {"landscape", "portrait"}):
        raise ValueError("Formato di esportazione non valido.")
    if file_type not in {"jpg", "png"}:
        raise ValueError("Scegli JPG o PNG.")
    frame_id = payload.get("frame_id")
    frame = None
    frame_info = None
    if frame_id:
        frame_info, frame_path = print_frame_metadata(str(frame_id))
        if frame_info["preset"] != preset or frame_info["orientation"] != orientation:
            raise ValueError("La cornice non corrisponde al formato scelto.")
        with Image.open(frame_path) as frame_image:
            frame = frame_image.convert("RGBA")
    exposure = print_number(payload, "exposure", -2, 2, 0)
    shadows = print_number(payload, "shadows", -1, 1, 0)
    highlights = print_number(payload, "highlights", -1, 1, 0)
    contrast = print_number(payload, "contrast", -100, 100, 0) / 100
    temperature = print_number(payload, "temperature", -100, 100, 0) / 100
    tint = print_number(payload, "tint", -100, 100, 0) / 100
    vibrance = print_number(payload, "vibrance", -100, 100, 0) / 100
    saturation = print_number(payload, "saturation", -100, 100, 0) / 100
    luminance_noise = print_number(payload, "luminance_noise", 0, 100, 0) / 100
    zoom = print_number(payload, "zoom", 1, 6, 1)
    offset_x = print_number(payload, "offset_x", -10, 10, 0)
    offset_y = print_number(payload, "offset_y", -10, 10, 0)
    rotation = print_number(payload, "rotation", -180, 180, 0)

    image = editor_source(path, relative)
    image = image.point(light_lut(exposure, shadows, highlights))
    size = print_output_size(preset, orientation, image.size, frame.size if frame else None)
    if max(size) > 6000 or size[0] * size[1] > 36_000_000:
        raise ValueError("Dimensioni di esportazione troppo grandi.")
    photo, coverage = print_transform(image, size, zoom, offset_x, offset_y, rotation)
    if frame:
        if frame.size != size:
            frame = frame.resize(size, Image.Resampling.LANCZOS)
        transparent = ImageChops.invert(frame.getchannel("A"))
    else:
        transparent = Image.new("L", size, 255)
    missing = ImageChops.multiply(ImageChops.invert(coverage), transparent)
    if missing.point(lambda value: 255 if value > 32 else 0).getbbox():
        raise ValueError("La foto non copre tutta l'area visibile: ingrandiscila o riduci lo spostamento.")
    photo = apply_color_controls(photo, contrast, temperature, tint, vibrance, saturation)
    photo = reduce_luminance_noise(photo, luminance_noise)
    if frame:
        photo.paste(frame, (0, 0), frame)
    photo = selphy_page(photo, preset, orientation)

    collection = (frame_info or {}).get("collection", "Generiche")
    folder_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", collection).strip("-")[:48] or "Generiche"
    destination = PRINT_EXPORT_ROOT / folder_name
    destination.mkdir(parents=True, exist_ok=True)
    source_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", path.stem).strip("-")[:48] or "Foto"
    filename = f"{source_name}_{preset.replace(':', '-')}_{uuid.uuid4().hex[:10]}.{file_type}"
    output = destination / filename
    temporary = destination / f".{uuid.uuid4().hex}.tmp"
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    print_dpi = {"dpi": (300, 300)} if preset in {"P", "L", "C"} else {}
    try:
        if file_type == "jpg":
            exif = Image.Exif()
            exif[274] = 1
            exif[270] = "NIWA Print Export"
            photo.save(temporary, format="JPEG", quality=100, subsampling=0,
                       icc_profile=profile, exif=exif.tobytes(), **print_dpi)
        else:
            photo.save(temporary, format="PNG", icc_profile=profile, optimize=True,
                       **print_dpi)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    export_id = base64.urlsafe_b64encode(str(output.relative_to(PRINT_EXPORT_ROOT)).replace("\\", "/").encode()).decode().rstrip("=")
    return {
        "name": filename,
        "size": output.stat().st_size,
        "width": photo.width,
        "height": photo.height,
        "download_url": f"/api/print/exports/{export_id}",
    }


def video_thumb_path_for(section, path, relative):
    stat = path.stat()
    key = f"{section}|{relative}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8")
    digest = hashlib.sha1(key).hexdigest()
    return VIDEO_CACHE_ROOT / f"{digest}.jpg"


def derivative_path_for(section, path, relative, variant):
    if variant not in DERIVATIVE_SIZES:
        raise ValueError("Unknown media derivative")
    stat = path.stat()
    key = (
        f"media-v{DERIVATIVE_VERSION}|{variant}|{section}|{relative}|"
        f"{stat.st_mtime_ns}|{stat.st_size}"
    ).encode("utf-8")
    return DERIVATIVE_ROOT / f"{hashlib.sha1(key).hexdigest()}.jpg"


def render_media_derivative(section, path, relative, variant):
    output = derivative_path_for(section, path, relative, variant)
    if output.is_file() and output.stat().st_size > 0:
        return output

    kind = media_kind(path)
    if kind == "raw":
        raw_relative = relative if section == "photo" else Path(section) / relative
        source_path = extract_raw_preview(path, raw_relative)
    elif kind == "video":
        source_path = extract_video_thumbnail(section, path, relative)
    else:
        source_path = path
    if not source_path:
        return None
    return write_bounded_jpeg(source_path, output, variant)


def write_bounded_jpeg(source_path, output, variant):
    from PIL import Image, ImageOps

    output.parent.mkdir(parents=True, exist_ok=True)
    maximum = DERIVATIVE_SIZES[variant]
    temporary = output.parent / f".{uuid.uuid4().hex}.tmp"
    try:
        with Image.open(source_path) as source:
            source.draft("RGB", (maximum, maximum))
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail(
                (maximum, maximum), Image.Resampling.LANCZOS, reducing_gap=3.0
            )
            save_options = {
                "format": "JPEG",
                "quality": 84 if variant == "thumb" else 90,
                "optimize": True,
                "progressive": True,
            }
            profile = source.info.get("icc_profile")
            if profile:
                save_options["icc_profile"] = profile
            image.save(temporary, **save_options)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def embedded_jpeg_span(path):
    """Offset and length of the best JPEG inside a RAW. Its IFDs come first,
    so a partial upload already says where the JPEG is."""
    command = ["exiftool", "-j", "-n"]
    for tag in EMBEDDED_JPEG_TAGS:
        command += [f"-{tag}Start", f"-{tag}Length"]
    try:
        result = subprocess.run(
            command + [str(path)], capture_output=True, timeout=15, check=False
        )
        tags = json.loads(result.stdout or b"[{}]")[0]
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError, KeyError):
        return None
    for tag in EMBEDDED_JPEG_TAGS:
        start, length = tags.get(f"{tag}Start"), tags.get(f"{tag}Length")
        if isinstance(start, int) and isinstance(length, int) and length > 0:
            return start, length
    return None


def incoming_bridge_raws():
    """RAWs the bridge is still sending. NIWA Import owns these files: read only."""
    try:
        sessions = json.loads(BRIDGE_SESSIONS_FILE.read_text(encoding="utf-8"))["sessions"]
        sessions = list(sessions.values())
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return []
    staging = BRIDGE_STAGING_ROOT.resolve()
    found = []
    for session in sessions:
        if not isinstance(session, dict) or session.get("status") != "active":
            continue
        objects = session.get("objects")
        for item in (objects.values() if isinstance(objects, dict) else []):
            if not isinstance(item, dict) or item.get("status") != "uploading":
                continue
            name = plain_name(item.get("filename"))
            session_id = plain_name(session.get("id"))
            staged_name = plain_name(item.get("staged_name"))
            if not name or not session_id or not staged_name:
                continue
            if Path(name).suffix.lower() not in RAW_EXTENSIONS:
                continue
            path = BRIDGE_STAGING_ROOT / session_id / staged_name
            try:
                if not path.resolve().is_relative_to(staging) or not path.is_file():
                    continue
                stat = path.stat()
                size = int(item.get("size") or 0)
            except (OSError, TypeError, ValueError):
                continue
            if size <= 0:
                continue
            found.append({
                "key": hashlib.sha1(f"{session_id}|{staged_name}".encode("utf-8")).hexdigest(),
                "name": name,
                "path": path,
                "size": size,
                "received": min(stat.st_size, size),
                "mtime": stat.st_mtime,
                "captured_at": str(item.get("captured_at") or ""),
            })
    found.sort(key=lambda entry: entry["captured_at"], reverse=True)
    return found


INCOMING_SPANS = {}


def incoming_preview(entry):
    """Grid and viewer images from the JPEG a RAW embeds, once its bytes arrived."""
    thumb = INCOMING_ROOT / f"{entry['key']}-thumb.jpg"
    if thumb.is_file():
        return True
    if entry["received"] < INCOMING_HEADER_BYTES:
        return False
    with INCOMING_LOCK:
        if thumb.is_file():
            return True
        span = INCOMING_SPANS.get(entry["key"]) or embedded_jpeg_span(entry["path"])
        if not span:
            return False
        INCOMING_SPANS[entry["key"]] = span
        start, length = span
        if entry["received"] < start + length:
            return False
        INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
        source = INCOMING_ROOT / f".{uuid.uuid4().hex}.jpg"
        try:
            with open(entry["path"], "rb") as handle:
                handle.seek(start)
                data = handle.read(length)
            if len(data) != length or not data.startswith(b"\xff\xd8"):
                return False
            source.write_bytes(data)
            copy_orientation(entry["path"], source)
            write_bounded_jpeg(source, INCOMING_ROOT / f"{entry['key']}-viewer.jpg", "viewer")
            # Written last: its presence means both images are ready.
            write_bounded_jpeg(source, thumb, "thumb")
        except Exception:
            app.logger.exception("Cannot preview incoming %s", entry["name"])
            return False
        finally:
            source.unlink(missing_ok=True)
    return True


def prune_incoming(keys):
    for key in list(INCOMING_SPANS):
        if key not in keys:
            INCOMING_SPANS.pop(key, None)
    if not INCOMING_ROOT.is_dir():
        return
    for cached in INCOMING_ROOT.glob("*.jpg"):
        if cached.name.split("-", 1)[0] not in keys:
            cached.unlink(missing_ok=True)


def send_immutable_image(path):
    response = send_file(
        path, mimetype="image/jpeg", conditional=True, max_age=31536000
    )
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def photo_signature(path):
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def state_key(relative):
    return str(relative).replace("\\", "/")


def load_preview_state():
    if not PREVIEW_STATE_FILE.exists():
        return {"files": {}}

    try:
        with open(PREVIEW_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"files": {}}

    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return {"files": {}}

    return data


def save_preview_state(state):
    atomic_write_json(PREVIEW_STATE_FILE, state, indent=2)


def preview_is_cached(path, relative):
    try:
        cache_path = cache_path_for(path, relative)
    except OSError:
        return False

    return cache_path.exists() and cache_path.stat().st_size > 0


def video_thumb_is_cached(section, path, relative):
    try:
        cache_path = video_thumb_path_for(section, path, relative)
    except OSError:
        return False

    return cache_path.exists() and cache_path.stat().st_size > 0


def photo_derivatives_ready(path, relative):
    try:
        return all(
            derivative_path_for("photo", path, relative, variant).is_file()
            for variant in DERIVATIVE_SIZES
        )
    except OSError:
        return False


def raw_is_stable(path):
    try:
        stat = path.stat()
    except OSError:
        return False

    age = time.time() - stat.st_mtime
    return age >= PREVIEW_STABLE_SECONDS


def count_cached_raw_previews():
    total = 0
    cached = 0

    for path, relative in iter_photo_files(RAW_EXTENSIONS):
        total += 1
        if preview_is_cached(path, relative):
            cached += 1

    return total, cached


def count_cached_video_thumbnails():
    total = 0
    cached = 0

    for section, config in MEDIA_SECTIONS.items():
        for path, relative in iter_media_files(config["root"], config["extensions"]):
            if media_kind(path) != "video":
                continue

            total += 1
            if video_thumb_is_cached(section, path, relative):
                cached += 1

    return total, cached


def update_worker_state(**updates):
    with WORKER_LOCK:
        WORKER_STATE.update(updates)


def preview_worker_loop():
    update_worker_state(running=True, message="Worker anteprime attivo.")

    while True:
        worked = False
        try:
            worked = run_preview_scan()
        except Exception as exc:
            update_worker_state(
                errors=WORKER_STATE.get("errors", 0) + 1,
                message=f"Errore worker: {exc}",
                current=None,
            )

        if not worked:
            time.sleep(PREVIEW_SCAN_INTERVAL_SECONDS)


def run_preview_scan():
    now = time.time()
    state = load_preview_state()
    files_state = state.setdefault("files", {})
    # Camera JPGs (RAW+JPG or JPG-only shooting) get grid and viewer images too.
    photo_files = list(iter_photo_files(PHOTO_EXTENSIONS))
    photo_files.sort(
        key=lambda pair: photo_signature(pair[0]).get("mtime_ns", 0),
        reverse=True,
    )
    raw_files = [pair for pair in photo_files if pair[0].suffix.lower() in RAW_EXTENSIONS]
    # Trashed RAWs keep their cached previews, so the trash view can show them.
    kept_files = raw_files + trashed_photo_raws()
    existing_keys = {state_key(relative) for _path, relative in kept_files + photo_files}
    cleanup_orphan_raw_previews(kept_files)

    for key, entry in list(files_state.items()):
        if key in existing_keys:
            continue

        preview = entry.get("preview")
        if preview:
            preview_path = Path(preview)
            try:
                if preview_path.exists() and preview_path.is_file():
                    preview_path.unlink()
            except OSError:
                pass

        del files_state[key]

    total, cached = count_cached_raw_previews()
    queued = 0

    update_worker_state(
        last_scan=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
        queued=0,
        cached=cached,
        current=None,
        message="Scansione RAW in corso.",
    )

    started = time.monotonic()
    worked = False
    for path, relative in photo_files:
        key = state_key(relative)
        is_raw = path.suffix.lower() in RAW_EXTENSIONS
        preview_cached = preview_is_cached(path, relative) if is_raw else True

        if preview_cached and photo_derivatives_ready(path, relative):
            files_state[key] = {
                **photo_signature(path),
                "status": "cached",
                "updated": now,
            }
            continue

        entry = files_state.get(key, {})
        last_error = float(entry.get("last_error", 0) or 0)

        if last_error and now - last_error < PREVIEW_RETRY_SECONDS:
            continue

        if not raw_is_stable(path):
            queued += 1
            files_state[key] = {
                **photo_signature(path),
                "status": "waiting_stable",
                "updated": now,
            }
            continue

        if worked and time.monotonic() - started >= PREVIEW_BATCH_SECONDS:
            break

        update_worker_state(
            current=key,
            queued=queued,
            cached=cached,
            message=f"Genero anteprima: {path.name}",
        )

        worked = True
        preview_path = extract_raw_preview(path, relative) if is_raw else path
        error = "No embedded JPEG preview found"
        if preview_path:
            # Grid and viewer images too, so the tablet never waits for them.
            try:
                for variant in DERIVATIVE_SIZES:
                    render_media_derivative("photo", path, relative, variant)
            except Exception as exc:
                preview_path = None
                error = f"Derived image failed: {exc}"

        if preview_path:
            cached += 0 if preview_cached else 1
            files_state[key] = {
                **photo_signature(path),
                "status": "cached",
                # Never a JPG original: stale entries have their "preview" deleted.
                **({"preview": str(preview_path)} if is_raw else {}),
                "updated": time.time(),
            }
            update_worker_state(
                processed=WORKER_STATE.get("processed", 0) + 1,
                cached=cached,
                current=None,
                message=f"Anteprima pronta: {path.name}",
            )
        else:
            files_state[key] = {
                **photo_signature(path),
                "status": "error",
                "last_error": time.time(),
                "error": error,
                "updated": time.time(),
            }
            update_worker_state(
                errors=WORKER_STATE.get("errors", 0) + 1,
                current=None,
                message=f"Anteprima non disponibile: {path.name}",
            )

    update_worker_state(
        queued=queued,
        cached=cached,
        current=None,
        message=f"Anteprime cache: {cached}/{total}",
    )
    save_preview_state(state)
    return worked


def placeholder_svg(title, message):
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="600" viewBox="0 0 900 600">
<rect width="900" height="600" fill="#111827"/>
<rect x="28" y="28" width="844" height="544" rx="18" fill="#1f2937" stroke="#374151"/>
<text x="450" y="280" text-anchor="middle" fill="#e5e7eb" font-family="Arial" font-size="32">{safe_title}</text>
<text x="450" y="330" text-anchor="middle" fill="#9ca3af" font-family="Arial" font-size="20">{safe_message}</text>
</svg>"""
    return Response(svg, mimetype="image/svg+xml")


def copy_orientation(raw_path, preview_path):
    """Embedded RAW previews come out unrotated: the rotation is stored in the
    RAW's own EXIF. Copy the tag over and browsers turn vertical shots upright,
    without re-encoding a single pixel."""
    try:
        subprocess.run(
            [
                "exiftool", "-q", "-overwrite_original",
                "-TagsFromFile", str(raw_path), "-Orientation", str(preview_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass  # an unrotated preview still beats no preview


def extract_raw_preview(path, relative):
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cache_path = cache_path_for(path, relative)

    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    tags = ["JpgFromRaw", "PreviewImage", "OtherImage", "ThumbnailImage"]
    temp_path = CACHE_ROOT / f".{uuid.uuid4().hex}.tmp.jpg"

    for tag in tags:
        try:
            result = subprocess.run(
                ["exiftool", "-b", f"-{tag}", str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if result.stdout:
            temp_path.write_bytes(result.stdout)
            if temp_path.stat().st_size > 0:
                copy_orientation(path, temp_path)
                temp_path.replace(cache_path)
                return cache_path

    if temp_path.exists():
        temp_path.unlink()

    return None


def extract_video_thumbnail(section, path, relative):
    VIDEO_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cache_path = video_thumb_path_for(section, path, relative)

    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    temp_path = VIDEO_CACHE_ROOT / f".{uuid.uuid4().hex}.tmp.jpg"
    attempts = [
        ["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(path), "-frames:v", "1", "-vf", "scale=900:-2", "-q:v", "5", str(temp_path)],
        ["ffmpeg", "-y", "-ss", "00:00:00.2", "-i", str(path), "-frames:v", "1", "-vf", "scale=900:-2", "-q:v", "5", str(temp_path)],
    ]

    for command in attempts:
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if result.returncode == 0 and temp_path.exists() and temp_path.stat().st_size > 0:
            temp_path.replace(cache_path)
            return cache_path

        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    return None


def request_pagination(total):
    has_pagination_request = any(key in request.args for key in ("page", "limit", "offset"))
    if not has_pagination_request:
        return {
            "enabled": False,
            "page": 1,
            "limit": total,
            "offset": 0,
            "total": total,
            "has_more": False,
            "next_page": None,
        }

    try:
        limit = int(request.args.get("limit", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        limit = DEFAULT_PAGE_SIZE
    limit = max(1, min(MAX_PAGE_SIZE, limit))

    if "offset" in request.args:
        try:
            offset = int(request.args.get("offset", 0))
        except (TypeError, ValueError):
            offset = 0
        offset = max(0, offset)
        page = (offset // limit) + 1
    else:
        try:
            page = int(request.args.get("page", 1))
        except (TypeError, ValueError):
            page = 1
        page = max(1, page)
        offset = (page - 1) * limit

    has_more = offset + limit < total
    return {
        "enabled": True,
        "page": page,
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": has_more,
        "next_page": page + 1 if has_more else None,
    }


def apply_pagination(items):
    pagination = request_pagination(len(items))
    if not pagination["enabled"]:
        return items, pagination

    start = pagination["offset"]
    end = start + pagination["limit"]
    return items[start:end], pagination


@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIWA Review</title>
<link rel="stylesheet" href="/static/print-editor.css?v=6">
<style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#172033;--panel2:#101827;--line:#334155;--text:#f8fafc;--muted:#94a3b8;--soft:#cbd5e1;--blue:#38bdf8}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:radial-gradient(circle at 24% 0%,rgba(56,189,248,.10),transparent 32%),linear-gradient(180deg,#0b1220,#0f172a 42%,#0b1220);color:var(--text);padding:20px}
h1{margin:0 0 6px 0;font-size:32px;letter-spacing:0}.subtitle{color:var(--muted);margin-bottom:18px;line-height:1.45}
.topbar{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:18px}
.button{display:inline-flex;align-items:center;justify-content:center;background:#263244;color:white;text-decoration:none;padding:10px 12px;border-radius:10px;border:1px solid rgba(148,163,184,.22);min-height:40px;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.button:hover{background:#334155}.status{color:var(--muted);font-size:14px;margin:12px 0}
.toolbar{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:stretch;margin:12px 0}
.worker{background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));border:1px solid rgba(148,163,184,.18);border-radius:12px;padding:12px;color:#d1d5db;font-size:14px;line-height:1.4}
.worker strong{color:#e5e7eb}
.toolbar-actions{display:flex;align-items:stretch;gap:8px}
.small-button{background:#101827;color:#e5e7eb;border:1px solid rgba(148,163,184,.20);border-radius:10px;padding:10px 12px;min-height:42px}
.small-button:hover{background:#334155}.small-button:disabled{opacity:.55}
.tabs,.filters{display:flex;gap:8px;margin:16px 0;flex-wrap:wrap}
.filter-row{display:none}.filter-row.visible{display:flex}
.tab,.filter-button{background:#101827;color:#e5e7eb;border:1px solid rgba(148,163,184,.20);border-radius:10px;padding:10px 12px}
.tab.active,.filter-button.active{background:#0369a1;border-color:#38bdf8;color:white}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.card{background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));border:1px solid rgba(148,163,184,.18);border-radius:12px;overflow:hidden;box-shadow:0 18px 34px rgba(0,0,0,.22);position:relative}
.thumb{width:100%;aspect-ratio:3/2;object-fit:cover;background:#101827;display:block}
.video-thumb{filter:saturate(.9)}.play-badge{position:absolute;top:10px;right:10px;background:rgba(17,24,39,.74);border-radius:999px;padding:6px 9px;color:#e5e7eb;font-size:13px}
.info{padding:10px}.name{font-weight:bold;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{color:var(--muted);font-size:12px;margin-top:4px}.badge{display:inline-block;background:#263244;border:1px solid rgba(148,163,184,.18);color:#e5e7eb;border-radius:999px;padding:3px 7px;font-size:11px;margin-top:8px}
.empty{background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));border:1px solid rgba(148,163,184,.18);border-radius:12px;padding:18px;color:var(--muted)}
.load-more-wrap{display:flex;justify-content:center;margin:16px 0}.load-more-wrap.hidden{display:none}.load-more{min-width:180px}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.9);display:none;align-items:center;justify-content:center;padding:12px;z-index:10}
.modal.open{display:flex}.modal-inner{position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center}
.modal img,.modal video{max-width:100%;max-height:100%;object-fit:contain}
.modal video{background:#000}
.overlay-button{position:absolute;background:rgba(17,24,39,.72);color:white;text-decoration:none;border:none;border-radius:999px;padding:10px 12px;backdrop-filter:blur(8px)}
.overlay-button:hover{background:rgba(55,65,81,.9)}
.download-button{top:14px;right:14px}
.jpg-download-button{top:62px;right:14px}
.editor-open-button{top:14px;right:14px;cursor:pointer;background:#a77564;font-weight:700}
.modal-inner.printable .download-button{top:62px}.modal-inner.printable .jpg-download-button{top:110px}
.nav-button{top:50%;transform:translateY(-50%);width:42px;height:42px;font-size:26px;line-height:20px;display:flex;align-items:center;justify-content:center}
.nav-prev{left:14px}.nav-next{right:14px}
.photo-counter{position:absolute;left:14px;top:14px;background:rgba(17,24,39,.72);color:#e5e7eb;border-radius:999px;padding:8px 11px;font-size:13px;backdrop-filter:blur(8px)}
.rating{position:absolute;left:14px;bottom:14px;display:flex;gap:4px;background:rgba(17,24,39,.72);border-radius:999px;padding:8px 10px;backdrop-filter:blur(8px)}
.rating.hidden{display:none}
.star{background:transparent;border:none;color:#6b7280;font-size:24px;line-height:1;padding:0 2px}
.star.active{color:#facc15}
:root{--bg:#0f0d0d;--panel:#211918;--panel2:#151112;--line:rgba(203,144,124,.28);--text:#fff7f0;--muted:#c8afa4;--soft:#eadbd4;--blue:#d59a84;--accent:#d59a84;--accent-strong:#f0b8a2}
body{background:radial-gradient(circle at 18% -5%,rgba(213,154,132,.22),transparent 34%),radial-gradient(circle at 84% 8%,rgba(246,226,209,.08),transparent 28%),linear-gradient(180deg,#0e0c0c,#171211 46%,#0e0c0c)}
.brand-heading{display:flex;align-items:center;gap:12px;min-width:0}.brand-logo{width:52px;height:52px;border-radius:50%;border:1px solid rgba(213,154,132,.42);background:#f2dfcf;box-shadow:0 16px 34px rgba(0,0,0,.28);flex:0 0 auto}.brand-copy{min-width:0}
h1{color:#fff4ec}.subtitle{color:var(--muted)}
.button,.tab,.filter-button,.small-button{background:rgba(64,45,42,.92);border-color:var(--line)}
.button:hover,.tab:hover,.filter-button:hover,.small-button:hover{background:rgba(87,61,56,.96);border-color:rgba(213,154,132,.42)}
.tab.active,.filter-button.active{background:linear-gradient(180deg,#d59a84,#9f6f63);border-color:rgba(240,184,162,.45);color:#fffaf5}
.card,.worker,.empty{background:linear-gradient(180deg,rgba(42,31,29,.94),rgba(18,14,14,.96));border-color:var(--line)}
.thumb{background:#151112}.badge{background:rgba(64,45,42,.92);border-color:var(--line)}
.overlay-button,.photo-counter,.rating{background:rgba(28,20,19,.76)}
.card.selected{outline:3px solid var(--accent-strong);outline-offset:-3px}
.card.selected::after{content:'';position:absolute;top:8px;left:8px;width:24px;height:24px;border-radius:50%;background:var(--accent-strong);box-shadow:0 0 0 3px rgba(15,13,13,.85)}
.selection-bar{position:sticky;bottom:10px;z-index:5;display:none;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-top:14px;padding:12px;border-radius:12px;border:1px solid var(--line);background:rgba(28,20,19,.95);box-shadow:0 18px 34px rgba(0,0,0,.4);backdrop-filter:blur(8px)}
.selection-bar.visible{display:flex}.selection-info{color:var(--soft);font-size:14px}
.selection-actions{display:flex;gap:8px;flex-wrap:wrap}.small-button.hidden{display:none}
.small-button.danger,.overlay-button.danger{background:rgba(127,29,29,.88);border-color:rgba(248,113,113,.45)}
.small-button.danger:hover,.overlay-button.danger:hover{background:rgba(153,27,27,.96)}
.delete-button{bottom:14px;right:14px}
/* Compact lighttable: same actions, less chrome around the photographs. */
body{padding:14px}h1{font-size:26px;margin-bottom:3px}.subtitle{font-size:13px;margin:0}.topbar{align-items:center;margin-bottom:8px}.brand-logo{width:44px;height:44px}
.tabs,.filters{margin:9px 0;gap:7px}.status{font-size:13px;margin:7px 0 9px}.toolbar{display:flex;align-items:flex-start;gap:8px;margin:8px 0 12px;flex-wrap:wrap}.toolbar-actions{order:0}.diagnostics{order:1;flex:1;min-width:240px}.diagnostics summary{cursor:pointer;color:var(--muted);font-size:13px;padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:rgba(42,31,29,.82)}.diagnostics[open] summary{margin-bottom:8px}
.grid{grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:8px}.card{aspect-ratio:3/2;border-radius:11px;box-shadow:0 10px 24px rgba(0,0,0,.2)}.thumb{height:100%;aspect-ratio:auto}.info{position:absolute;inset:auto 0 0;padding:28px 9px 8px;background:linear-gradient(transparent,rgba(10,8,8,.94))}.name{font-size:13px;text-shadow:0 1px 3px #000}.meta{color:#eadbd4;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.badges{position:absolute;top:8px;left:8px;max-width:calc(100% - 16px);display:flex;gap:4px;flex-wrap:wrap;pointer-events:none}.badge{margin:0;background:rgba(28,20,19,.78);backdrop-filter:blur(6px)}.badge.same-name{background:rgba(120,72,24,.9);border-color:rgba(250,204,21,.45);color:#fde68a}.card-stars{color:#facc15;font-size:12px;letter-spacing:1px;line-height:1;margin-bottom:3px;text-shadow:0 1px 3px #000}
.trash-card{aspect-ratio:auto}.trash-card .thumb{height:auto;aspect-ratio:3/2}.trash-card .info{position:relative;padding:9px;background:none}
.modal{background:rgba(5,4,4,.96)}.viewer-meta{position:absolute;left:14px;top:14px;max-width:70%;background:rgba(28,20,19,.76);border-radius:12px;padding:8px 11px;backdrop-filter:blur(8px)}.viewer-name{font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.viewer-meta .photo-counter{position:static;padding:0;background:none;border-radius:0;color:var(--muted);font-size:12px;margin-top:2px}.close-button{right:14px;top:14px;width:42px;height:42px;padding:0;font-size:24px}.viewer-actions{position:absolute;right:14px;bottom:14px;display:flex;gap:7px;align-items:center;flex-wrap:wrap;justify-content:flex-end;max-width:72%}.viewer-actions .overlay-button{position:static;font-size:14px}.card.selected .badges{left:40px}.selection-actions .danger{margin-left:14px}
.incoming{margin:0 0 12px}.incoming.hidden{display:none}.incoming-title{color:var(--muted);font-size:13px;margin-bottom:6px}.incoming-list{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px}.incoming-card{flex:0 0 160px;position:relative;aspect-ratio:3/2;border-radius:11px;overflow:hidden;border:1px dashed var(--accent);background:#151112;padding:0;color:inherit;font:inherit;text-align:left;cursor:pointer}.incoming-card:disabled{cursor:default}.incoming-card img{width:100%;height:100%;object-fit:cover;display:block}.incoming-wait{display:flex;align-items:center;justify-content:center;height:100%;padding:8px 8px 40px;color:var(--muted);font-size:12px;text-align:center}.incoming-bar{position:absolute;left:0;right:0;bottom:0;height:4px;background:rgba(0,0,0,.45)}.incoming-bar span{display:block;height:100%;background:var(--accent-strong)}
.modal.incoming-view .viewer-actions,.modal.incoming-view .nav-button,.modal.incoming-view .rating{display:none}
@media(max-width:800px){body{padding:10px}.brand-logo{width:40px;height:40px}h1{font-size:22px}.topbar .button{min-height:36px;padding:8px 10px}.toolbar{display:grid;grid-template-columns:1fr}.toolbar-actions{display:grid;grid-template-columns:1fr 1fr}.diagnostics{min-width:0}.modal{padding:5px}.nav-button{width:36px;height:36px;font-size:22px;opacity:.72}.viewer-meta{top:8px;left:8px;max-width:68%}.close-button{top:8px;right:8px}.viewer-actions{left:8px;right:8px;bottom:8px;max-width:none;justify-content:center}.viewer-actions .overlay-button{padding:8px 10px;font-size:12px}.rating{left:8px;bottom:58px}.grid{grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:7px}}
</style>
</head>
<body>
<div class="topbar">
<div class="brand-heading">
<img class="brand-logo" src="/static/niwa-logo.png" alt="">
<div class="brand-copy">
<h1>NIWA Review</h1>
<div class="subtitle">Gallery locale per foto, video Nikon e media GoPro dal NAS.</div>
</div>
</div>
<a class="button" id="dashboardLink" href="/">Dashboard</a>
</div>

<div class="tabs">
<button class="tab active" data-section="photo" onclick="setSection('photo')">Foto</button>
<button class="tab" data-section="video" onclick="setSection('video')">Video</button>
<button class="tab" data-section="gopro" onclick="setSection('gopro')">GoPro</button>
<button class="tab" data-section="companion" onclick="setSection('companion')">Companion</button>
<button class="tab" id="trashTab" data-section="trash" onclick="setSection('trash')">Cestino</button>
</div>

<div class="filters filter-row" id="goproFilters">
<button class="filter-button active" data-filter="all" onclick="setGoProFilter('all')">Tutti</button>
<button class="filter-button" data-filter="photo" onclick="setGoProFilter('photo')">Foto</button>
<button class="filter-button" data-filter="video" onclick="setGoProFilter('video')">Video</button>
</div>

<div class="status" id="status">Caricamento...</div>
<div class="toolbar">
<details class="diagnostics">
<summary>Stato indice e anteprime</summary>
<div class="worker" id="indexStatus">Indice: controllo stato...</div>
<div class="worker" id="workerStatus" style="margin-top:8px">Anteprime: controllo stato...</div>
</details>
<div class="toolbar-actions">
<button class="small-button" id="selectButton" onclick="toggleSelectionMode()">Seleziona</button>
<button class="small-button" id="refreshIndexButton" onclick="refreshIndex()">Aggiorna indice</button>
</div>
</div>
<section class="incoming hidden" id="incoming" aria-label="Foto in arrivo dal bridge">
<div class="incoming-title">In arrivo dal bridge</div>
<div class="incoming-list" id="incomingList"></div>
</section>
<div class="grid" id="gallery"></div>
<div class="load-more-wrap hidden" id="loadMoreWrap">
<button class="small-button load-more" id="loadMoreButton" onclick="loadMoreMedia()">Carica altri</button>
</div>
<div class="selection-bar" id="selectionBar">
<div class="selection-info" id="selectionInfo"></div>
<div class="selection-actions">
<button class="small-button" onclick="selectAll()">Seleziona tutto</button>
<button class="small-button" data-needs-selection onclick="clearSelection()">Deseleziona</button>
<button class="small-button" data-mode="media" data-needs-selection onclick="downloadSelection()">Scarica</button>
<button class="small-button" data-mode="trash" data-needs-selection onclick="restoreSelection()">Ripristina selezionati</button>
<button class="small-button danger" data-mode="media" data-needs-selection onclick="trashSelection()">Elimina</button>
<button class="small-button" data-mode="trash" onclick="restoreAll()">Ripristina tutto</button>
<button class="small-button danger" data-mode="trash" onclick="emptyTrash()">Svuota cestino</button>
</div>
</div>

<div class="modal" id="modal" onclick="closeModal(event)" ontouchstart="startSwipe(event)" ontouchend="endSwipe(event)">
<div class="modal-inner">
<div class="viewer-meta"><div class="viewer-name" id="viewerName"></div><div class="photo-counter" id="photoCounter"></div></div>
<button class="overlay-button close-button" onclick="event.stopPropagation();closeModal()" aria-label="Chiudi">&times;</button>
<button class="overlay-button nav-button nav-prev" onclick="showPreviousPhoto(event)">&lsaquo;</button>
<img id="modalImage" alt="" onclick="event.stopPropagation()">
<video id="modalVideo" controls playsinline onclick="event.stopPropagation()"></video>
<button class="overlay-button nav-button nav-next" onclick="showNextPhoto(event)">&rsaquo;</button>
<div class="viewer-actions" onclick="event.stopPropagation()">
<button class="overlay-button editor-open-button" id="editorOpenButton" onclick="openPrintEditor(event)" style="display:none">Prepara stampa</button>
<a class="overlay-button download-button" id="downloadLink" href="#">Scarica originale</a>
<a class="overlay-button jpg-download-button" id="downloadJpgLink" href="#" style="display:none">Scarica JPG HQ</a>
<button class="overlay-button danger delete-button" onclick="trashCurrentPhoto(event)">Elimina</button>
</div>
<div class="rating" id="ratingStars" onclick="event.stopPropagation()"></div>
</div>
</div>

<div class="print-editor" id="printEditor" role="dialog" aria-modal="true" aria-label="Editor stampa" hidden>
<div class="print-editor-shell">
<div class="print-editor-head">
<div><h2>Prepara stampa</h2><div id="printEditorName" class="print-muted"></div></div>
<button type="button" class="small-button" id="printEditorClose">Torna alla foto</button>
</div>
<div class="print-editor-body">
<div class="print-preview-panel">
<canvas id="printCanvas" aria-label="Anteprima della foto e della cornice"></canvas>
<div class="print-muted" id="printEditorStatus">Caricamento anteprima...</div>
</div>
<div class="print-controls">
<div id="printStepFrames">
<h3>Cornice <span id="printActiveFrame" class="print-active-frame">Caricamento...</span></h3>
<div class="print-frame-picker">
<label id="printCollectionFilterLabel">Mostra cornici<select id="printCollectionFilter"><option value="">Tutte le collezioni</option></select></label>
<div id="printFrameGallery" class="print-frame-carousel" aria-label="Cornici disponibili"></div>
<button type="button" class="small-button" id="printManageFrames">Gestisci cornici</button>
</div>
<h3>Inquadra la foto</h3>
<div class="print-select-row"><label>Ingrandimento <output id="printZoomValue">1,00×</output><input id="printZoom" type="range" min="1" max="6" step="0.01" value="1"></label><label>Rotazione <output id="printRotationValue">0°</output><input id="printRotation" type="range" min="-180" max="180" step="1" value="0"></label></div>
<p class="print-muted">Trascina la foto; usa due dita per ingrandire o ruotare. La cornice resta fissa e il movimento si ferma prima di scoprire spazi vuoti. Per muoverla di più, ingrandisci la foto.</p>
<div class="print-actions print-position-actions"><button type="button" class="small-button" id="printRotate90">Ruota 90°</button><button type="button" class="small-button" id="printResetPosition">Ripristina posizione</button></div>
<details id="printStepLights" class="print-section"><summary>Regola la foto (facoltativo)</summary>
<p class="print-muted">Modifiche non distruttive. La foto originale resta invariata.</p>
<h4>Luce</h4>
<label>Esposizione <output id="printExposureValue">0</output><input id="printExposure" type="range" min="-2" max="2" step="0.05" value="0"></label>
<label>Ombre <output id="printShadowsValue">0</output><input id="printShadows" type="range" min="-1" max="1" step="0.05" value="0"></label>
<label>Alte luci <output id="printHighlightsValue">0</output><input id="printHighlights" type="range" min="-1" max="1" step="0.05" value="0"></label>
<label>Contrasto <output id="printContrastValue">0</output><input id="printContrast" type="range" min="-100" max="100" step="1" value="0"></label>
<h4>Colore</h4>
<label>Temperatura <output id="printTemperatureValue">0</output><input id="printTemperature" type="range" min="-100" max="100" step="1" value="0"></label>
<label>Tinta <output id="printTintValue">0</output><input id="printTint" type="range" min="-100" max="100" step="1" value="0"></label>
<label>Vividezza <output id="printVibranceValue">0</output><input id="printVibrance" type="range" min="-100" max="100" step="1" value="0"></label>
<label>Saturazione <output id="printSaturationValue">0</output><input id="printSaturation" type="range" min="-100" max="100" step="1" value="0"></label>
<h4>Dettaglio</h4>
<label>Rumore luminanza <output id="printLuminanceNoiseValue">0</output><input id="printLuminanceNoise" type="range" min="0" max="100" step="1" value="0"></label>
<div class="print-actions"><button type="button" class="small-button" id="printResetLights">Ripristina regolazioni</button></div>
</details>
<details id="printExportOptions" class="print-section"><summary>Formato e opzioni di esportazione</summary>
<div class="print-select-row">
<label>Formato<select id="printPreset"></select></label>
<label>Orientamento<select id="printOrientation"><option value="landscape">Orizzontale</option><option value="portrait">Verticale</option></select></label>
<label>File<select id="printFileType"><option value="jpg">JPG · stampa</option><option value="png">PNG · digitale</option></select></label>
</div>
<p class="print-muted">Con una cornice, il formato segue la cornice. Per la SELPHY scegli JPG e la carta corrispondente (P/L/C). La cartolina P esce gia' con il margine che la SELPHY stampa oltre le linee tratteggiate: stampala senza bordi, senza ritagli.</p>
</details>
<div id="printExportResult" class="print-export-result" hidden><span id="printExportResultText"></span><a id="printRedownload" class="small-button" href="#">Scarica di nuovo</a></div>
<div class="print-export-bar"><span id="printExportSummary" class="print-muted">Preparazione...</span><button type="button" class="small-button print-primary" id="printExport" disabled>Esporta JPG</button></div>
</div>
<div id="printStepManage" hidden>
<h3>Gestisci cornici</h3>
<p class="print-muted">Carica PNG con una zona trasparente per la foto o elimina quelle che non servono. Le esportazioni già salvate restano disponibili.</p>
<form id="printFrameUpload" class="print-upload">
<label>Nome<input name="name" maxlength="80" placeholder="Nome cornice"></label>
<label>Collezione<input name="collection" maxlength="80" placeholder="Generiche o nome dell'evento" value="Generiche"></label>
<div class="print-select-row"><label>Formato<select name="preset" id="printUploadPreset"></select></label><label>Orientamento<select name="orientation" id="printUploadOrientation"><option value="landscape">Orizzontale</option><option value="portrait">Verticale</option></select></label></div>
<label>PNG con zona trasparente<input name="file" type="file" accept="image/png,.png" required></label>
<button type="submit" class="small-button">Carica cornice</button>
</form>
<div id="printFrameManageList" class="print-frame-gallery"></div>
<div class="print-actions"><button type="button" class="small-button print-primary" id="printManageDone">Torna alla stampa</button></div>
</div>
</div>
</div>
</div>
</div>

<script>
function serviceUrl(port, path=''){
    return `${window.location.protocol}//${window.location.hostname}:${port}${path}`;
}

document.getElementById('dashboardLink').href = serviceUrl(3000);

let PHOTOS = [];
let CURRENT_INDEX = -1;
let CURRENT_SECTION = 'photo';
let GOPRO_FILTER = 'all';
let LOAD_SEQUENCE = 0;
let SWIPE_START_X = 0;
let SWIPE_START_Y = 0;
const PAGE_SIZE = 80;
let CURRENT_PAGE = 1;
let HAS_MORE = false;
let TOTAL_ITEMS = 0;
const NL = String.fromCharCode(10);
let SELECTING = false;
const SELECTED = new Map();
let TRASH_ITEMS = [];
let LIVE_REFRESH_BUSY = false;
let LAST_MEDIA_STATUS = '';
let LOADING_MORE = false;
let INCOMING = [];
let PREFETCHED = [];
// New shots are merged only near the top, so they never move the grid under a finger.
const LIVE_REFRESH_TOP = 300;

const SECTION_LABELS = {
    photo: 'foto',
    video: 'video',
    gopro: 'media GoPro',
    companion: 'scatti Companion'
};

function setSection(section){
    CURRENT_SECTION = section;
    document.querySelectorAll('.tab').forEach((button)=>{
        button.classList.toggle('active', button.dataset.section === section);
    });
    document.getElementById('goproFilters').classList.toggle('visible', section === 'gopro');
    document.getElementById('workerStatus').style.display = section === 'photo' ? 'block' : 'none';
    document.getElementById('incoming').classList.toggle('hidden', section !== 'photo' || !INCOMING.length);
    SELECTING = false;
    SELECTED.clear();
    renderSelection();
    if(section === 'trash'){
        loadTrash();
        return;
    }
    loadMedia(true);
}

function setGoProFilter(filter){
    GOPRO_FILTER = filter;
    document.querySelectorAll('.filter-button').forEach((button)=>{
        button.classList.toggle('active', button.dataset.filter === filter);
    });
    loadMedia(true);
}

function appendText(parent, className, value){
    const element = document.createElement('div');
    element.className = className;
    element.textContent = value == null ? '' : String(value);
    parent.appendChild(element);
    return element;
}

// Import keeps both files when two shots share a name; the hash is noise on a card.
const SAME_NAME_SUFFIX = /_conflict_[0-9a-f]{8}(?:_[0-9]+)?(?=[.][^.]+$)/i;
const KIND_LABELS = {raw:'RAW', video:'VIDEO'};

function fillMediaCard(card, item, trashed=false){
    const image = document.createElement('img');
    image.className = 'thumb' + (item.kind === 'video' ? ' video-thumb' : '');
    image.loading = 'lazy';
    image.decoding = 'async';
    image.src = item.thumbnail_url || item.preview_url;
    image.alt = '';
    card.appendChild(image);
    if(item.kind === 'video'){
        appendText(card, 'play-badge', 'Play');
    }

    const name = item.name || '';
    const sameName = SAME_NAME_SUFFIX.test(name);
    card.title = name;
    const info = document.createElement('div');
    info.className = 'info';
    appendText(info, 'name', sameName ? name.replace(SAME_NAME_SUFFIX, '') : name);
    appendText(info, 'meta', `${item.size_label} - ${item.mtime_label}`);
    if(trashed){
        appendText(info, 'meta', `Eliminato ${item.deleted_at || ''}`);
        appendText(info, 'meta', item.folder);
    }
    const badges = document.createElement('div');
    badges.className = 'badges';
    appendText(badges, 'badge', KIND_LABELS[item.kind] || item.extension || '');
    if(sameName){
        appendText(badges, 'badge same-name', 'stesso nome').title =
            'Un altro file ha lo stesso nome ma contenuto diverso: sono conservati entrambi.';
    }
    card.appendChild(info);
    card.appendChild(badges);
    renderCardStars(card, item.rating || 0);
}

function renderCardStars(card, rating){
    let stars = card.querySelector('.card-stars');
    if(!rating){
        if(stars) stars.remove();
        return;
    }
    if(!stars){
        stars = document.createElement('div');
        stars.className = 'card-stars';
        card.querySelector('.info').prepend(stars);
    }
    stars.textContent = String.fromCharCode(9733).repeat(rating);
    stars.setAttribute('aria-label', `${rating} stelle`);
}

function setLabeledStatus(elementId, label, message){
    const element = document.getElementById(elementId);
    const strong = document.createElement('strong');
    strong.textContent = label;
    element.replaceChildren(strong, document.createTextNode(` ${message}`));
}

function itemCard(item){
    const card = document.createElement('div');
    card.className = 'card' + (SELECTED.has(item.id) ? ' selected' : '');
    card.dataset.id = item.id;
    card.onclick = ()=> SELECTING ? toggleSelected(item, card) : openPhoto(item.id);

    fillMediaCard(card, item);
    return card;
}

function renderLoadMore(){
    const wrap = document.getElementById('loadMoreWrap');
    const button = document.getElementById('loadMoreButton');
    wrap.classList.toggle('hidden', !HAS_MORE);
    button.disabled = !HAS_MORE;
    button.textContent = HAS_MORE ? `Carica altri (${PHOTOS.length}/${TOTAL_ITEMS})` : 'Tutto caricato';
}

async function loadMedia(reset=true){
    const status = document.getElementById('status');
    const gallery = document.getElementById('gallery');
    const requestSection = CURRENT_SECTION;
    const requestFilter = GOPRO_FILTER;
    const requestId = ++LOAD_SEQUENCE;
    const label = SECTION_LABELS[requestSection] || 'media';

    if(reset){
        CURRENT_PAGE = 1;
        HAS_MORE = false;
        TOTAL_ITEMS = 0;
        PHOTOS = [];
        gallery.innerHTML = '';
    }

    status.textContent = reset ? `Caricamento indice ${label}...` : `Caricamento altri ${label}...`;
    renderLoadMore();

    try{
        let url = `/api/media/${requestSection}?page=${CURRENT_PAGE}&limit=${PAGE_SIZE}`;
        if(requestSection === 'gopro'){
            url += `&kind=${encodeURIComponent(requestFilter)}`;
        }

        const res = await fetch(url);
        const data = await res.json();

        if(requestId !== LOAD_SEQUENCE || requestSection !== CURRENT_SECTION){
            return;
        }

        // Shots that arrived meanwhile shift the pages: never show a card twice.
        const known = reset ? null : new Set(PHOTOS.map((photo)=>photo.id));
        const incoming = (data.items || []).filter((item)=>!known || !known.has(item.id));
        PHOTOS = reset ? incoming : PHOTOS.concat(incoming);
        TOTAL_ITEMS = data.pagination ? data.pagination.total : PHOTOS.length;
        HAS_MORE = Boolean(data.pagination && data.pagination.has_more);

        LAST_MEDIA_STATUS = `${PHOTOS.length}/${TOTAL_ITEMS} file caricati da ${data.storage_path || data.root}`;
        status.textContent = LAST_MEDIA_STATUS;

        if(!PHOTOS.length){
            gallery.replaceChildren();
            appendText(gallery, 'empty', data.empty_message || 'Nessun file trovato.');
            renderLoadMore();
            return;
        }

        incoming.forEach((item)=>gallery.appendChild(itemCard(item)));
        renderLoadMore();
        return true;
    }catch(e){
        if(requestId !== LOAD_SEQUENCE || requestSection !== CURRENT_SECTION){
            return;
        }
        status.textContent = 'Errore caricamento media: ' + e.message;
        renderLoadMore();
        return false;
    }
}

async function loadMoreMedia(){
    if(!HAS_MORE || LOADING_MORE){
        return;
    }
    LOADING_MORE = true;
    const page = ++CURRENT_PAGE;
    let loaded = false;
    try{
        loaded = await loadMedia(false);
    }finally{
        LOADING_MORE = false;
    }
    if(!loaded){
        // A failed page is retried by the button or the next scroll, not skipped.
        if(CURRENT_PAGE === page) CURRENT_PAGE = page - 1;
        return;
    }
    maybeLoadMore();
}

function maybeLoadMore(){
    const wrap = document.getElementById('loadMoreWrap');
    if(HAS_MORE && !LOADING_MORE && wrap.getBoundingClientRect().top < window.innerHeight + 800){
        loadMoreMedia();
    }
}

async function refreshLivePhotos(){
    if(LIVE_REFRESH_BUSY || CURRENT_SECTION !== 'photo' || window.scrollY > LIVE_REFRESH_TOP ||
       SELECTING || document.visibilityState !== 'visible' ||
       document.getElementById('modal').classList.contains('open')){
        return;
    }
    LIVE_REFRESH_BUSY = true;
    const requestId = LOAD_SEQUENCE;
    try{
        const res = await fetch(`/api/media/photo?page=1&limit=${PAGE_SIZE}`, {cache:'no-store'});
        if(!res.ok){ throw new Error(`HTTP ${res.status}`); }
        const data = await res.json();
        if(requestId !== LOAD_SEQUENCE || CURRENT_SECTION !== 'photo' ||
           window.scrollY > LIVE_REFRESH_TOP || SELECTING ||
           document.visibilityState !== 'visible' ||
           document.getElementById('modal').classList.contains('open')){
            return;
        }
        const incoming = data.items || [];
        const total = data.pagination ? data.pagination.total : incoming.length;
        const head = PHOTOS.slice(0, incoming.length);
        if(total !== TOTAL_ITEMS || incoming.length !== head.length ||
           incoming.some((item, index)=>item.id !== head[index].id)){
            await loadMedia(true);
        }else if(LAST_MEDIA_STATUS){
            document.getElementById('status').textContent = LAST_MEDIA_STATUS;
        }
    }catch(e){
        document.getElementById('status').textContent =
            'Aggiornamento automatico non disponibile: ' + e.message;
    }finally{
        LIVE_REFRESH_BUSY = false;
    }
}

async function loadIndexStatus(){
    try{
        const res = await fetch('/api/index/status');
        const data = await res.json();
        const index = data.index || {};
        const worker = data.worker || {};
        const message = worker.running ? 'Indicizzazione in corso...' : (worker.message || 'Indice pronto.');
        setLabeledStatus(
            'indexStatus', 'Indice media:',
            `${index.total_items || 0} file. ${message}`
        );
    }catch(e){
        document.getElementById('indexStatus').textContent = 'Indice: stato non disponibile.';
    }
}

async function refreshIndex(){
    const button = document.getElementById('refreshIndexButton');
    button.disabled = true;
    button.textContent = 'Aggiorno...';
    try{
        const res = await fetch('/api/index/rebuild', {method:'POST'});
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }
        await loadIndexStatus();
        await (inTrash() ? loadTrash() : loadMedia(true));
    }catch(e){
        document.getElementById('indexStatus').textContent = 'Errore indice: ' + e.message;
    }finally{
        button.disabled = false;
        button.textContent = 'Aggiorna indice';
    }
}

async function loadPreviewStatus(){
    try{
        const res = await fetch('/api/previews/status');
        const data = await res.json();
        const worker = data.worker || {};
        const total = data.raw_total || 0;
        const cached = data.raw_cached || 0;
        const videoTotal = data.video_total || 0;
        const videoCached = data.video_cached || 0;
        const current = worker.current ? ` - ${worker.current}` : '';

        setLabeledStatus(
            'workerStatus', 'Anteprime:',
            `RAW ${cached}/${total}, video ${videoCached}/${videoTotal}. ${worker.message || ''}${current}`
        );
    }catch(e){
        document.getElementById('workerStatus').textContent = 'Anteprime: stato non disponibile.';
    }
}

function openPhoto(id){
    const index = PHOTOS.findIndex((photo)=>photo.id === id);
    if(index < 0){
        return;
    }

    CURRENT_INDEX = index;
    renderCurrentPhoto();
    document.getElementById('modal').classList.add('open');
}

function renderCurrentPhoto(){
    const item = PHOTOS[CURRENT_INDEX];
    if(!item){
        return;
    }
    document.getElementById('modal').classList.remove('incoming-view');

    const image = document.getElementById('modalImage');
    const video = document.getElementById('modalVideo');

    if(item.kind === 'video'){
        image.style.display = 'none';
        image.removeAttribute('src');
        video.style.display = 'block';
        video.src = item.media_url;
        video.load();
    }else{
        video.pause();
        video.removeAttribute('src');
        video.style.display = 'none';
        image.style.display = 'block';
        image.src = item.preview_url;
    }

    document.getElementById('downloadLink').href = item.download_url;
    document.getElementById('downloadLink').textContent = item.kind === 'raw' ? 'Scarica RAW' : 'Scarica originale';
    const jpgLink = document.getElementById('downloadJpgLink');
    jpgLink.style.display = item.download_jpg_url ? 'block' : 'none';
    if(item.download_jpg_url) jpgLink.href = item.download_jpg_url;
    const printable = CURRENT_SECTION === 'photo' && item.kind !== 'video';
    document.querySelector('.modal-inner').classList.toggle('printable', printable);
    document.getElementById('editorOpenButton').style.display = printable ? 'block' : 'none';
    document.getElementById('viewerName').textContent = item.name;
    document.getElementById('photoCounter').textContent = `${CURRENT_INDEX + 1} / ${PHOTOS.length}`;

    const rating = document.getElementById('ratingStars');
    if(item){
        rating.classList.remove('hidden');
        renderRating(item.rating || 0);
    }else{
        rating.classList.add('hidden');
        rating.innerHTML = '';
    }
    prefetchNeighbours();
}

function prefetchNeighbours(){
    // Swiping then shows a photo already in the browser cache, even on weak Wi-Fi.
    PREFETCHED = [-1, 1]
        .map((step)=>PHOTOS[(CURRENT_INDEX + step + PHOTOS.length) % PHOTOS.length])
        .filter((item)=>item && item.kind !== 'video')
        .map((item)=>{
            const image = new Image();
            image.src = item.preview_url;
            return image;
        });
}

function openPrintEditor(event){
    event.stopPropagation();
    const item = PHOTOS[CURRENT_INDEX];
    if(!item || CURRENT_SECTION !== 'photo' || item.kind === 'video') return;
    document.getElementById('modal').classList.remove('open');
    window.NiwaPrintEditor.open(item);
}

function renderRating(rating){
    const container = document.getElementById('ratingStars');
    container.innerHTML = '';

    for(let value = 1; value <= 5; value++){
        const button = document.createElement('button');
        button.className = 'star' + (value <= rating ? ' active' : '');
        button.textContent = String.fromCharCode(9733);
        button.onclick = (event)=>setRating(value, event);
        container.appendChild(button);
    }
}

async function setRating(rating, event){
    if(event){
        event.stopPropagation();
    }

    const item = PHOTOS[CURRENT_INDEX];
    if(!item){
        return;
    }

    const nextRating = item.rating === rating ? 0 : rating;

    try{
        const res = await fetch(`/api/rating/${item.section}/${item.id}`, {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({rating:nextRating})
        });
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }
        item.rating = data.rating;
        renderRating(item.rating);
        const card = document.querySelector(`#gallery .card[data-id="${item.id}"]`);
        if(card) renderCardStars(card, item.rating);
    }catch(e){
        alert('Errore salvataggio rating: ' + e.message);
    }
}

function showPreviousPhoto(event){
    if(event){
        event.stopPropagation();
    }

    if(!PHOTOS.length){
        return;
    }

    CURRENT_INDEX = (CURRENT_INDEX - 1 + PHOTOS.length) % PHOTOS.length;
    renderCurrentPhoto();
}

function showNextPhoto(event){
    if(event){
        event.stopPropagation();
    }

    if(!PHOTOS.length){
        return;
    }

    CURRENT_INDEX = (CURRENT_INDEX + 1) % PHOTOS.length;
    renderCurrentPhoto();
}

function closeModal(event){
    if(event && event.target.id !== 'modal' && !event.target.classList.contains('modal-inner')){
        return;
    }
    document.getElementById('modalVideo').pause();
    document.getElementById('modal').classList.remove('open', 'incoming-view');
}

function incomingCard(item){
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'incoming-card';
    card.disabled = !item.preview_url;
    card.title = item.name;
    if(item.thumbnail_url){
        const image = document.createElement('img');
        image.src = item.thumbnail_url;
        image.alt = '';
        card.appendChild(image);
    }else{
        appendText(card, 'incoming-wait', 'Anteprima in arrivo...');
    }
    const info = document.createElement('div');
    info.className = 'info';
    appendText(info, 'name', item.name);
    appendText(info, 'meta', item.stalled
        ? `In pausa - ${item.progress}%`
        : `${item.progress}% di ${item.size_label}`);
    card.appendChild(info);
    const bar = document.createElement('div');
    bar.className = 'incoming-bar';
    const fill = document.createElement('span');
    fill.style.width = `${item.progress}%`;
    bar.appendChild(fill);
    card.appendChild(bar);
    card.onclick = ()=>openIncoming(item);
    return card;
}

async function loadIncoming(){
    if(CURRENT_SECTION !== 'photo' || document.visibilityState !== 'visible'){
        return;
    }
    try{
        const res = await fetch('/api/incoming', {cache:'no-store'});
        if(!res.ok){ return; }
        INCOMING = (await res.json()).items || [];
    }catch(e){
        return;
    }
    if(CURRENT_SECTION !== 'photo'){
        return;
    }
    document.getElementById('incoming').classList.toggle('hidden', !INCOMING.length);
    document.getElementById('incomingList').replaceChildren(...INCOMING.map(incomingCard));
}

function openIncoming(item){
    // View only: the full RAW is still on its way, so no rating, download or delete yet.
    const video = document.getElementById('modalVideo');
    video.pause();
    video.style.display = 'none';
    const image = document.getElementById('modalImage');
    image.style.display = 'block';
    image.src = item.preview_url;
    document.getElementById('viewerName').textContent = item.name;
    document.getElementById('photoCounter').textContent = `In arrivo dal bridge: ${item.progress}%`;
    document.getElementById('modal').classList.add('open', 'incoming-view');
}

function startSwipe(event){
    const touch = event.changedTouches[0];
    SWIPE_START_X = touch.clientX;
    SWIPE_START_Y = touch.clientY;
}

function endSwipe(event){
    const touch = event.changedTouches[0];
    const deltaX = touch.clientX - SWIPE_START_X;
    const deltaY = touch.clientY - SWIPE_START_Y;

    if(Math.abs(deltaX) < 50 || Math.abs(deltaX) < Math.abs(deltaY)){
        return;
    }

    event.stopPropagation();

    if(deltaX < 0){
        showNextPhoto();
    }else{
        showPreviousPhoto();
    }
}

document.addEventListener('keydown', (event)=>{
    if(!document.getElementById('modal').classList.contains('open')){
        return;
    }

    if(event.key === 'ArrowLeft'){
        showPreviousPhoto();
    }else if(event.key === 'ArrowRight'){
        showNextPhoto();
    }else if(event.key === 'Escape'){
        closeModal();
    }
});

function humanSize(bytes){
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = bytes || 0;
    let index = 0;
    while(value >= 1024 && index < units.length - 1){
        value /= 1024;
        index += 1;
    }
    return index === 0 ? `${value} B` : `${value.toFixed(1)} ${units[index]}`;
}

function inTrash(){
    return CURRENT_SECTION === 'trash';
}

function selectionSize(){
    let total = 0;
    SELECTED.forEach((size)=>{ total += size; });
    return total;
}

function refreshCardSelection(){
    document.querySelectorAll('#gallery .card').forEach((card)=>{
        card.classList.toggle('selected', SELECTED.has(card.dataset.id));
    });
}

function renderSelection(){
    const trash = inTrash();
    document.getElementById('selectionBar').classList.toggle('visible', SELECTING || (trash && TRASH_ITEMS.length > 0));
    const selectButton = document.getElementById('selectButton');
    selectButton.classList.toggle('hidden', trash);
    selectButton.textContent = SELECTING ? 'Annulla selezione' : 'Seleziona';
    document.querySelectorAll('#selectionBar [data-mode]').forEach((button)=>{
        button.classList.toggle('hidden', button.dataset.mode !== (trash ? 'trash' : 'media'));
    });
    document.querySelectorAll('#selectionBar [data-needs-selection]').forEach((button)=>{
        button.disabled = !SELECTED.size;
    });
    document.getElementById('selectionInfo').textContent = SELECTED.size
        ? `${SELECTED.size} selezionati - ${humanSize(selectionSize())}`
        : (trash ? 'Tocca un file per selezionarlo.' : 'Tocca i file da selezionare.');
}

function setSelecting(on){
    SELECTING = on;
    SELECTED.clear();
    refreshCardSelection();
    renderSelection();
}

function toggleSelectionMode(){
    setSelecting(!SELECTING);
}

function toggleSelected(item, card){
    if(SELECTED.has(item.id)){
        SELECTED.delete(item.id);
    }else{
        SELECTED.set(item.id, item.size || 0);
    }
    card.classList.toggle('selected', SELECTED.has(item.id));
    renderSelection();
}

function clearSelection(){
    SELECTED.clear();
    refreshCardSelection();
    renderSelection();
}

async function selectAll(){
    if(inTrash()){
        TRASH_ITEMS.forEach((item)=>SELECTED.set(item.id, item.size || 0));
    }else{
        let url = `/api/media/${CURRENT_SECTION}/selection`;
        if(CURRENT_SECTION === 'gopro'){
            url += `?kind=${encodeURIComponent(GOPRO_FILTER)}`;
        }
        try{
            const res = await fetch(url);
            const data = await res.json();
            (data.items || []).forEach((item)=>SELECTED.set(item.id, item.size || 0));
        }catch(e){
            alert('Errore selezione: ' + e.message);
            return;
        }
    }
    refreshCardSelection();
    renderSelection();
}

function downloadSelection(){
    if(!SELECTED.size){
        return;
    }
    // A real form POST lets the browser stream the zip straight to disk.
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = `/api/media/${CURRENT_SECTION}/download`;
    form.style.display = 'none';
    SELECTED.forEach((_size, id)=>{
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'ids';
        input.value = id;
        form.appendChild(input);
    });
    document.body.appendChild(form);
    form.submit();
    form.remove();
}

async function postJson(url, body){
    const res = await fetch(url, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body)
    });
    const data = await res.json().catch(()=>({}));
    if(!res.ok || data.error){
        throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
}

async function trashSelection(){
    if(!SELECTED.size){
        return;
    }
    const count = SELECTED.size;
    const head = count >= TOTAL_ITEMS
        ? `Spostare TUTTI i ${count} file nel cestino?`
        : `Spostare ${count} file selezionati nel cestino?`;
    if(!confirm(head + NL + NL + `${humanSize(selectionSize())}. Potrai ripristinarli dal Cestino.`)){
        return;
    }
    try{
        const data = await postJson(`/api/media/${CURRENT_SECTION}/trash`, {ids:[...SELECTED.keys()]});
        setSelecting(false);
        await loadMedia(true);
        loadIndexStatus();
        updateTrashCount();
        if(data.missing){
            alert(`${data.moved} file spostati nel cestino. ${data.missing} non trovati: forse erano già stati eliminati.`);
        }
    }catch(e){
        alert('Errore eliminazione: ' + e.message);
    }
}

async function trashCurrentPhoto(event){
    if(event){
        event.stopPropagation();
    }
    const item = PHOTOS[CURRENT_INDEX];
    if(!item){
        return;
    }
    if(!confirm(`Spostare ${item.name} nel cestino?` + NL + NL + 'Potrai ripristinarlo dal Cestino.')){
        return;
    }
    try{
        await postJson(`/api/media/${item.section}/trash`, {ids:[item.id]});
    }catch(e){
        alert('Errore eliminazione: ' + e.message);
        return;
    }
    PHOTOS.splice(CURRENT_INDEX, 1);
    TOTAL_ITEMS = Math.max(0, TOTAL_ITEMS - 1);
    const card = document.querySelector(`#gallery .card[data-id="${item.id}"]`);
    if(card){
        card.remove();
    }
    updateTrashCount();
    loadIndexStatus();
    if(!PHOTOS.length){
        closeModal();
        loadMedia(true);
        return;
    }
    CURRENT_INDEX = CURRENT_INDEX % PHOTOS.length;
    renderCurrentPhoto();
}

function trashCard(item){
    const card = document.createElement('div');
    card.className = 'card trash-card' + (SELECTED.has(item.id) ? ' selected' : '');
    card.dataset.id = item.id;
    card.onclick = ()=>toggleSelected(item, card);
    fillMediaCard(card, item, true);
    return card;
}

function setTrashCount(count){
    document.getElementById('trashTab').textContent = count ? `Cestino (${count})` : 'Cestino';
}

async function updateTrashCount(){
    try{
        const res = await fetch('/api/trash');
        const data = await res.json();
        setTrashCount(data.count || 0);
    }catch(e){
        setTrashCount(0);
    }
}

async function loadTrash(){
    const status = document.getElementById('status');
    const gallery = document.getElementById('gallery');
    const requestId = ++LOAD_SEQUENCE;
    PHOTOS = [];
    HAS_MORE = false;
    gallery.innerHTML = '';
    renderLoadMore();
    status.textContent = 'Caricamento cestino...';
    try{
        const res = await fetch('/api/trash');
        const data = await res.json();
        if(requestId !== LOAD_SEQUENCE || !inTrash()){
            return;
        }
        TRASH_ITEMS = data.items || [];
        TOTAL_ITEMS = TRASH_ITEMS.length;
        setTrashCount(TRASH_ITEMS.length);
        status.textContent = TRASH_ITEMS.length
            ? `${TRASH_ITEMS.length} file nel cestino - ${data.total_size_label}. Lo spazio si libera solo con Svuota cestino.`
            : 'Il cestino è vuoto.';
        if(!TRASH_ITEMS.length){
            gallery.replaceChildren();
            appendText(gallery, 'empty', 'Nessun file nel cestino.');
        }
        TRASH_ITEMS.forEach((item)=>gallery.appendChild(trashCard(item)));
        renderSelection();
    }catch(e){
        if(requestId === LOAD_SEQUENCE){
            status.textContent = 'Errore caricamento cestino: ' + e.message;
        }
    }
}

async function restoreFromTrash(body){
    try{
        const data = await postJson('/api/trash/restore', body);
        SELECTED.clear();
        await loadTrash();
        loadIndexStatus();
        if(data.errors && data.errors.length){
            alert(`${data.restored} file ripristinati.` + NL + data.errors.join(NL));
        }
    }catch(e){
        alert('Errore ripristino: ' + e.message);
    }
}

function restoreSelection(){
    if(SELECTED.size){
        restoreFromTrash({ids:[...SELECTED.keys()]});
    }
}

function restoreAll(){
    if(TRASH_ITEMS.length){
        restoreFromTrash({all:true});
    }
}

async function emptyTrash(){
    if(!TRASH_ITEMS.length){
        return;
    }
    const total = TRASH_ITEMS.reduce((sum, item)=>sum + (item.size || 0), 0);
    const message = 'Svuotare il cestino?' + NL + NL
        + `${TRASH_ITEMS.length} file (${humanSize(total)}) verranno eliminati definitivamente. `
        + `L'operazione non si può annullare.`;
    if(!confirm(message)){
        return;
    }
    try{
        await postJson('/api/trash/empty', {confirm:true});
        SELECTED.clear();
        await loadTrash();
    }catch(e){
        alert('Errore svuotamento: ' + e.message);
    }
}

loadMedia(true);
renderSelection();
updateTrashCount();
new IntersectionObserver((entries)=>{
    if(entries.some((entry)=>entry.isIntersecting)) maybeLoadMore();
}, {rootMargin:'800px 0px'}).observe(document.getElementById('loadMoreWrap'));
loadIndexStatus();
loadPreviewStatus();
setInterval(loadIndexStatus, 15000);
setInterval(loadPreviewStatus, 10000);
setInterval(refreshLivePhotos, 5000);
loadIncoming();
setInterval(loadIncoming, 4000);
document.addEventListener('visibilitychange', ()=>{
    if(document.visibilityState === 'visible') refreshLivePhotos();
});
</script>
<script src="/static/print-editor.js?v=10"></script>
</body>
</html>
"""


@app.route("/api/photos")
def api_photos():
    return jsonify({
        "root": str(PHOTO_ROOT),
        "items": scan_photos(),
    })


@app.route("/api/media/<section>")
def api_media(section):
    config = section_config(section)
    kind_filter = request.args.get("kind", "all")
    if kind_filter not in {"all", "photo", "video"}:
        kind_filter = "all"

    items = scan_media(section, kind_filter)
    page_items, pagination = apply_pagination(items)
    return jsonify({
        "section": section,
        "label": config["label"],
        "root": str(config["root"]),
        "storage_path": str(config["root"]),
        "exists": config["root"].exists(),
        "empty_message": config["empty"],
        "items": page_items,
        "pagination": pagination,
        "index": index_summary(get_review_index()),
    })


@app.route("/api/preview/<file_id>")
def api_preview(file_id):
    path, relative = resolve_photo(file_id)
    suffix = path.suffix.lower()

    if suffix in JPEG_EXTENSIONS:
        return send_file(path)

    if suffix not in RAW_EXTENSIONS:
        abort(404)

    preview_path = extract_raw_preview(path, relative)
    if preview_path:
        return send_file(preview_path, mimetype="image/jpeg")

    return placeholder_svg(path.name, "Anteprima RAW non disponibile")


@app.route("/api/preview/<section>/<file_id>")
def api_preview_section(section, file_id):
    config = section_config(section)
    path, relative = resolve_media(config["root"], file_id)
    suffix = path.suffix.lower()

    if suffix in JPEG_EXTENSIONS:
        return send_file(path)

    if suffix not in RAW_EXTENSIONS or suffix not in config["extensions"]:
        abort(404)

    preview_path = extract_raw_preview(path, Path(section) / relative)
    if preview_path:
        return send_file(preview_path, mimetype="image/jpeg")

    return placeholder_svg(path.name, "Anteprima RAW non disponibile")


@app.route("/api/incoming")
def api_incoming():
    entries = incoming_bridge_raws()
    prune_incoming({entry["key"] for entry in entries})
    now = time.time()
    items = []
    for entry in entries:
        ready = incoming_preview(entry)
        key = entry["key"]
        items.append({
            "key": key,
            "name": entry["name"],
            "size_label": human_size(entry["size"]),
            "progress": int(entry["received"] * 100 / entry["size"]),
            "stalled": now - entry["mtime"] > INCOMING_STALL_SECONDS,
            "thumbnail_url": f"/api/incoming/{key}/thumb" if ready else None,
            "preview_url": f"/api/incoming/{key}/viewer" if ready else None,
        })
    return jsonify({"items": items})


@app.route("/api/incoming/<key>/<variant>")
def api_incoming_image(key, variant):
    if variant not in DERIVATIVE_SIZES or not re.fullmatch("[0-9a-f]{40}", key):
        abort(404)
    path = INCOMING_ROOT / f"{key}-{variant}.jpg"
    if not path.is_file():
        abort(404)
    return send_immutable_image(path)


@app.route("/api/media-image/<variant>/<section>/<file_id>")
def api_media_image(variant, section, file_id):
    if variant not in DERIVATIVE_SIZES:
        abort(404)
    config = section_config(section)
    path, relative = resolve_media(config["root"], file_id)
    if path.suffix.lower() not in config["extensions"]:
        abort(404)
    try:
        image_path = render_media_derivative(section, path, relative, variant)
    except Exception:
        app.logger.exception("Cannot render %s image for %s", variant, path)
        image_path = None
    if image_path:
        return send_immutable_image(image_path)
    return placeholder_svg(path.name, "Anteprima non disponibile")


@app.route("/api/media-file/<section>/<file_id>")
def api_media_file(section, file_id):
    config = section_config(section)
    path, _relative = resolve_media(config["root"], file_id)

    if path.suffix.lower() not in config["extensions"]:
        abort(404)

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return send_file(path, mimetype=mime, conditional=True)


@app.route("/api/video-thumb/<section>/<file_id>")
def api_video_thumb(section, file_id):
    config = section_config(section)
    path, relative = resolve_media(config["root"], file_id)

    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        abort(404)

    thumb_path = extract_video_thumbnail(section, path, relative)
    if thumb_path:
        return send_file(thumb_path, mimetype="image/jpeg")

    return placeholder_svg(path.name, "Anteprima video non disponibile")


@app.route("/api/download/<file_id>")
def api_download_legacy(file_id):
    path, _relative = resolve_photo(file_id)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return send_file(path, mimetype=mime, as_attachment=True, download_name=path.name)


@app.route("/api/download/<section>/<file_id>")
def api_download(section, file_id):
    config = section_config(section)
    path, _relative = resolve_media(config["root"], file_id)

    if path.suffix.lower() not in config["extensions"]:
        abort(404)

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return send_file(path, mimetype=mime, as_attachment=True, download_name=path.name)


@app.route("/api/download-jpg/<section>/<file_id>")
def api_download_jpg(section, file_id):
    if section != "photo":
        abort(404)
    config = section_config(section)
    path, relative = resolve_media(config["root"], file_id)
    if path.suffix.lower() not in RAW_EXTENSIONS or path.suffix.lower() not in config["extensions"]:
        abort(404)
    try:
        jpg = render_raw_jpg(path, relative)
    except Exception:
        app.logger.exception("Cannot render full-size JPG for %s", path)
        return jsonify({"error": "Conversione JPG non disponibile per questo RAW."}), 503
    return send_file(
        jpg,
        mimetype="image/jpeg",
        as_attachment=True,
        download_name=f"{path.stem}.jpg",
    )


@app.route("/api/print/presets")
def api_print_presets():
    return jsonify({"presets": PRINT_PRESETS})


@app.route("/api/print/frames", methods=["GET", "POST"])
def api_print_frames():
    if request.method == "GET":
        return jsonify({"frames": print_frames()})
    if request.content_length and request.content_length > 18 * 1024 * 1024:
        return jsonify({"error": "PNG troppo grande (massimo 16 MB)."}), 413
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"error": "Seleziona un file PNG."}), 400
    raw = upload.stream.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        return jsonify({"error": "PNG troppo grande (massimo 16 MB)."}), 413
    preset = request.form.get("preset", "")
    orientation = request.form.get("orientation", "")
    if (preset not in PRINT_PRESETS or preset == "original"
            or orientation not in {"landscape", "portrait"}):
        return jsonify({"error": "Formato o orientamento non valido."}), 400
    name = request.form.get("name", "").strip()[:80] or Path(upload.filename or "Cornice").stem[:80]
    collection = request.form.get("collection", "Generiche").strip()[:80] or "Generiche"
    if any(ord(char) < 32 for char in name + collection):
        return jsonify({"error": "Nome o collezione non validi."}), 400
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG":
                raise ValueError("Sono accettati solo file PNG.")
            width, height = image.size
            if min(width, height) < 300 or max(width, height) > 6000 or width * height > 36_000_000:
                raise ValueError("La cornice deve avere dimensioni tra 300 e 6000 px (massimo 36 MP).")
            image.load()
            alpha_min, alpha_max = image.convert("RGBA").getchannel("A").getextrema()
            if alpha_min == 255 or alpha_max == 0:
                raise ValueError("Il PNG deve contenere grafica visibile e una zona trasparente per la foto.")
            expected = print_ratio(preset, orientation)
            if abs(width / height / expected - 1) > 0.003:
                raise ValueError("Il rapporto del PNG non corrisponde al formato selezionato.")
            required = print_output_size(preset, orientation, (width, height))
            if preset in {"P", "L", "C"} and (width < required[0] or height < required[1]):
                raise ValueError("Risoluzione della cornice insufficiente per la stampa a 300 dpi.")
            thumbnail = image.convert("RGBA")
            thumbnail.thumbnail((280, 280), Image.Resampling.LANCZOS)
            thumbnail_bytes = io.BytesIO()
            thumbnail.save(thumbnail_bytes, format="PNG", optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        return jsonify({"error": str(error)}), 400

    frame_id = uuid.uuid4().hex
    metadata = {
        "id": frame_id, "name": name, "collection": collection,
        "preset": preset, "orientation": orientation,
        "width": width, "height": height,
    }
    with PRINT_FRAME_LOCK:
        PRINT_FRAME_ROOT.mkdir(parents=True, exist_ok=True)
        image_path = PRINT_FRAME_ROOT / f"{frame_id}.png"
        thumbnail_path = PRINT_FRAME_ROOT / f"{frame_id}.thumb.png"
        metadata_path = PRINT_FRAME_ROOT / f"{frame_id}.json"
        try:
            image_path.write_bytes(raw)
            thumbnail_path.write_bytes(thumbnail_bytes.getvalue())
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        except OSError:
            image_path.unlink(missing_ok=True)
            thumbnail_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            raise
    metadata["url"] = f"/api/print/frames/{frame_id}/image"
    metadata["thumbnail_url"] = f"/api/print/frames/{frame_id}/thumbnail"
    return jsonify(metadata), 201


@app.route("/api/print/frames/<frame_id>/image")
def api_print_frame_image(frame_id):
    _metadata, path = print_frame_metadata(frame_id)
    return send_file(path, mimetype="image/png")


@app.route("/api/print/frames/<frame_id>/thumbnail")
def api_print_frame_thumbnail(frame_id):
    _metadata, _path = print_frame_metadata(frame_id)
    thumbnail = PRINT_FRAME_ROOT / f"{frame_id}.thumb.png"
    if not thumbnail.is_file():
        abort(404)
    return send_file(thumbnail, mimetype="image/png")


@app.route("/api/print/frames/<frame_id>", methods=["DELETE"])
def api_print_frame_delete(frame_id):
    _metadata, path = print_frame_metadata(frame_id)
    with PRINT_FRAME_LOCK:
        path.unlink(missing_ok=True)
        (PRINT_FRAME_ROOT / f"{frame_id}.thumb.png").unlink(missing_ok=True)
        (PRINT_FRAME_ROOT / f"{frame_id}.json").unlink(missing_ok=True)
    return jsonify({"deleted": frame_id})


@app.route("/api/print/editor-preview/<file_id>")
def api_print_editor_preview(file_id):
    path, relative = resolve_photo(file_id)
    if path.suffix.lower() not in PHOTO_EXTENSIONS:
        abort(404)
    try:
        preview = render_editor_preview(path, relative)
    except Exception:
        app.logger.exception("Cannot render editor preview for %s", path)
        return jsonify({"error": "Anteprima editor non disponibile."}), 503
    return send_file(preview, mimetype="image/jpeg")


@app.route("/api/print/export", methods=["POST"])
def api_print_export():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Richiesta non valida."}), 400
    file_id = payload.get("id")
    if not isinstance(file_id, str):
        return jsonify({"error": "Foto non valida."}), 400
    path, relative = resolve_photo(file_id)
    if path.suffix.lower() not in PHOTO_EXTENSIONS:
        abort(404)
    try:
        result = render_print_export(path, relative, payload)
    except NotFound:
        raise
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception("Cannot export print image for %s", path)
        return jsonify({"error": "Esportazione non riuscita; controlla lo spazio SSD e riprova."}), 503
    return jsonify(result)


@app.route("/api/print/exports/<file_id>")
def api_print_export_download(file_id):
    path, _relative = resolve_media(PRINT_EXPORT_ROOT, file_id)
    if path.suffix.lower() not in {".jpg", ".png"}:
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)


@app.route("/api/rating/<file_id>", methods=["POST"])
def api_set_rating(file_id):
    return set_media_rating("photo", file_id)


@app.route("/api/rating/<section>/<file_id>", methods=["POST"])
def api_set_section_rating(section, file_id):
    return set_media_rating(section, file_id)


def set_media_rating(section, file_id):
    config = section_config(section)
    path, _relative = resolve_media(config["root"], file_id)
    payload = request.get_json(silent=True) or {}

    if path.suffix.lower() not in config["extensions"]:
        return jsonify({"error": "Rating non disponibile per questo file."}), 400

    try:
        rating = int(payload.get("rating", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Rating non valido."}), 400

    rating = max(0, min(5, rating))

    try:
        write_rating(path, rating)
    except OSError as exc:
        return jsonify({"error": str(exc)}), 500

    final_rating = read_rating(path)
    update_index_rating(section, file_id, final_rating)

    return jsonify({
        "ok": True,
        "rating": final_rating,
        "xmp": str(xmp_path_for(path)),
    })


def requested_ids(payload):
    ids = payload.get("ids") if isinstance(payload, dict) else None
    if not isinstance(ids, list) or not all(isinstance(value, str) for value in ids):
        abort(400, "ids deve essere una lista")
    return ids


@app.route("/api/media/<section>/selection")
def api_media_selection(section):
    section_config(section)
    kind_filter = request.args.get("kind", "all")
    if kind_filter not in {"all", "photo", "video"}:
        kind_filter = "all"
    items = scan_media(section, kind_filter)
    return jsonify({
        "items": [{"id": item["id"], "size": item.get("size", 0)} for item in items],
    })


@app.route("/api/media/<section>/trash", methods=["POST"])
def api_media_trash(section):
    ids = requested_ids(request.get_json(silent=True))
    return jsonify({"ok": True, **trash_media(section, ids)})


@app.route("/api/media/<section>/download", methods=["POST"])
def api_media_download(section):
    config = section_config(section)
    entries = []
    for file_id in dict.fromkeys(request.form.getlist("ids")):
        try:
            path, relative = resolve_media(config["root"], file_id)
        except NotFound:
            continue
        if path.suffix.lower() not in config["extensions"]:
            continue
        entries.append((path, relative.as_posix()))
        sidecar = xmp_path_for(path)
        if sidecar.is_file():
            entries.append((sidecar, (relative.parent / sidecar.name).as_posix()))

    if not entries:
        abort(404, "Nessun file da scaricare")

    name = f"niwa-{section}-{time.strftime('%Y%m%d-%H%M')}.zip"
    return Response(
        zip_stream(entries),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.route("/api/trash")
def api_trash():
    items = [trash_public_item(item) for item in load_trash()["items"].values()]
    items.sort(key=media_order, reverse=True)
    total = sum(item["size"] for item in items)
    return jsonify({
        "items": items,
        "count": len(items),
        "total_size": total,
        "total_size_label": human_size(total),
    })


@app.route("/api/trash/preview/<trash_id>")
def api_trash_preview(trash_id):
    item = load_trash()["items"].get(trash_id)
    name = plain_name(item.get("name")) if item else None
    relative = safe_relative(item.get("relative", "")) if item else None
    if not TRASH_ID_PATTERN.fullmatch(trash_id) or not name or not relative:
        abort(404)
    path = TRASH_ROOT / trash_id / name
    if not path.is_file():
        abort(404)

    suffix = path.suffix.lower()
    if suffix in JPEG_EXTENSIONS:
        return send_file(path)
    if suffix in RAW_EXTENSIONS:
        # Same cache key as the live file: a rename keeps size and mtime.
        if item.get("section") != "photo":
            relative = Path(item["section"]) / relative
        preview_path = extract_raw_preview(path, relative)
        if preview_path:
            return send_file(preview_path, mimetype="image/jpeg")
    return placeholder_svg(name, "Nel cestino")


@app.route("/api/trash/restore", methods=["POST"])
def api_trash_restore():
    payload = request.get_json(silent=True) or {}
    if payload.get("all") is True:
        return jsonify({"ok": True, **restore_trash()})
    return jsonify({"ok": True, **restore_trash(requested_ids(payload))})


@app.route("/api/trash/empty", methods=["POST"])
def api_trash_empty():
    payload = request.get_json(silent=True) or {}
    if payload.get("confirm") is not True:
        abort(400, "Conferma richiesta")
    return jsonify({"ok": True, **empty_trash()})


@app.route("/api/status")
def api_status():
    return jsonify({
        "photo_root": str(PHOTO_ROOT),
        "photo_root_exists": PHOTO_ROOT.exists(),
        "video_root": str(VIDEO_ROOT),
        "video_root_exists": VIDEO_ROOT.exists(),
        "gopro_root": str(GOPRO_ROOT),
        "gopro_root_exists": GOPRO_ROOT.exists(),
        "companion_root": str(COMPANION_ROOT),
        "companion_root_exists": COMPANION_ROOT.exists(),
        "cache_root": str(CACHE_ROOT),
        "exiftool": subprocess.run(
            ["sh", "-c", "command -v exiftool >/dev/null 2>&1"],
            check=False
        ).returncode == 0,
        "ffmpeg": subprocess.run(
            ["sh", "-c", "command -v ffmpeg >/dev/null 2>&1"],
            check=False
        ).returncode == 0,
        "index_file": str(REVIEW_INDEX_FILE),
        "index": index_summary(get_review_index()),
    })


@app.route("/api/index/status")
def api_index_status():
    index = get_review_index()

    with INDEX_LOCK:
        worker = dict(INDEX_STATE)

    return jsonify({
        "index_file": str(REVIEW_INDEX_FILE),
        "scan_interval_seconds": INDEX_SCAN_INTERVAL_SECONDS,
        "index": index_summary(index),
        "worker": worker,
    })


@app.route("/api/index/rebuild", methods=["POST"])
def api_index_rebuild():
    try:
        index = rebuild_review_index()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "ok": True,
        "index": index_summary(index),
    })


@app.route("/api/previews/status")
def api_preview_status():
    total, cached = count_cached_raw_previews()
    video_total, video_cached = count_cached_video_thumbnails()
    state = load_preview_state()
    errors = [
        {"path": path, **entry}
        for path, entry in state.get("files", {}).items()
        if entry.get("status") == "error"
    ]

    with WORKER_LOCK:
        worker = dict(WORKER_STATE)

    return jsonify({
        "raw_total": total,
        "raw_cached": cached,
        "video_total": video_total,
        "video_cached": video_cached,
        "cache_root": str(CACHE_ROOT),
        "video_cache_root": str(VIDEO_CACHE_ROOT),
        "state_file": str(PREVIEW_STATE_FILE),
        "scan_interval_seconds": PREVIEW_SCAN_INTERVAL_SECONDS,
        "stable_seconds": PREVIEW_STABLE_SECONDS,
        "error_count": len(errors),
        "errors": errors[:20],
        "worker": worker,
    })


if __name__ == "__main__":
    worker = threading.Thread(target=preview_worker_loop, daemon=True)
    worker.start()
    index_worker = threading.Thread(target=index_worker_loop, daemon=True)
    index_worker.start()
    app.run(host="0.0.0.0", port=5052)
