from flask import Flask, Response, abort, jsonify, request, send_file
from pathlib import Path
import base64
import hashlib
import html
import json
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
VIDEO_CACHE_ROOT = Path("/storage/.niwa_cache/review_video_thumbs")
PREVIEW_STATE_FILE = CACHE_ROOT / "preview_state.json"
DATA_ROOT = Path("/data")
REVIEW_INDEX_FILE = DATA_ROOT / "review_index.json"
STORAGE_ROOT = Path("/storage")
TRASH_ROOT = STORAGE_ROOT / ".niwa_trash"
# NIWA Import reads deleted_paths from here so deleted media never come back.
TRASH_FILE = DATA_ROOT / "review_trash.json"
TRASH_ID_PATTERN = re.compile("[0-9a-f]{32}")
TRASH_LOCK = threading.Lock()

INDEX_VERSION = 1
INDEX_SCAN_INTERVAL_SECONDS = 120
PREVIEW_SCAN_INTERVAL_SECONDS = 20
# Part of every RAW preview cache key: bump it to regenerate them all.
# 2: previews carry the RAW orientation, so vertical shots show upright.
RAW_PREVIEW_VERSION = 2
PREVIEW_STABLE_SECONDS = 60
PREVIEW_RETRY_SECONDS = 300
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
    preview_url = f"/api/media-file/{section}/{file_id}"
    if section == "photo" and suffix in RAW_EXTENSIONS:
        preview_url = f"/api/preview/{file_id}"
    elif section == "gopro" and suffix in RAW_EXTENSIONS:
        preview_url = f"/api/preview/gopro/{file_id}"
    elif kind == "video":
        preview_url = f"/api/video-thumb/{section}/{file_id}"

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
        "preview_url": preview_url,
        "media_url": f"/api/media-file/{section}/{file_id}",
        "download_url": f"/api/download/{section}/{file_id}",
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
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    temp_path = REVIEW_INDEX_FILE.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    temp_path.replace(REVIEW_INDEX_FILE)


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
    for path, relative in raw_files:
        try:
            expected.add(cache_path_for(path, relative).resolve())
        except OSError:
            continue

    if not CACHE_ROOT.exists():
        return 0

    removed = 0
    for cache_file in CACHE_ROOT.glob("*.jpg"):
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


def update_index_state(**updates):
    with INDEX_LOCK:
        INDEX_STATE.update(updates)


def rebuild_review_index():
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
    try:
        payload = json.loads(TRASH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    items = payload.get("items")
    deleted = payload.get("deleted_paths")
    return {
        "version": 1,
        "items": items if isinstance(items, dict) else {},
        "deleted_paths": [
            path for path in deleted if isinstance(path, str)
        ] if isinstance(deleted, list) else [],
    }


def save_trash(trash):
    TRASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = TRASH_FILE.with_name(TRASH_FILE.name + ".tmp")
    temporary.write_text(
        json.dumps(trash, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, TRASH_FILE)


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
    return name if name and Path(name).name == name else None


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
    # ponytail: the trash list is saved once per batch, to spare the SD card.
    # A crash mid-batch leaves moved files safe in .niwa_trash but unlisted.
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
            os.replace(path, folder / path.name)
            sidecar_name = None
            if sidecar.is_file():
                os.replace(sidecar, folder / sidecar.name)
                sidecar_name = sidecar.name
            trash["items"][trash_id] = {
                "id": trash_id,
                "section": section,
                "relative": relative.as_posix(),
                "name": path.name,
                "sidecar": sidecar_name,
                "size": size,
                "deleted_at": deleted_at,
            }
            deleted.add(storage_relative(section, relative))
            remove_empty_folders(path.parent, root)
            moved += 1
        trash["deleted_paths"] = sorted(deleted)
        save_trash(trash)
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


def video_thumb_path_for(section, path, relative):
    stat = path.stat()
    key = f"{section}|{relative}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8")
    digest = hashlib.sha1(key).hexdigest()
    return VIDEO_CACHE_ROOT / f"{digest}.jpg"


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
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    temp_path = PREVIEW_STATE_FILE.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    temp_path.replace(PREVIEW_STATE_FILE)


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
        try:
            run_preview_scan()
        except Exception as exc:
            update_worker_state(
                errors=WORKER_STATE.get("errors", 0) + 1,
                message=f"Errore worker: {exc}",
                current=None,
            )

        time.sleep(PREVIEW_SCAN_INTERVAL_SECONDS)


def run_preview_scan():
    now = time.time()
    state = load_preview_state()
    files_state = state.setdefault("files", {})
    raw_files = list(iter_photo_files(RAW_EXTENSIONS))
    # Trashed RAWs keep their cached previews, so the trash view can show them.
    kept_files = raw_files + trashed_photo_raws()
    existing_keys = {state_key(relative) for _path, relative in kept_files}
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

    for path, relative in raw_files:
        key = state_key(relative)

        if preview_is_cached(path, relative):
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

        update_worker_state(
            current=key,
            queued=queued,
            cached=cached,
            message=f"Genero anteprima: {path.name}",
        )

        preview_path = extract_raw_preview(path, relative)

        if preview_path:
            cached += 1
            files_state[key] = {
                **photo_signature(path),
                "status": "cached",
                "preview": str(preview_path),
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
                "error": "No embedded JPEG preview found",
                "updated": time.time(),
            }
            update_worker_state(
                errors=WORKER_STATE.get("errors", 0) + 1,
                current=None,
                message=f"Anteprima non disponibile: {path.name}",
            )

        save_preview_state(state)
        return

    update_worker_state(
        queued=queued,
        cached=cached,
        current=None,
        message=f"Anteprime cache: {cached}/{total}",
    )
    save_preview_state(state)


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
    temp_path = cache_path.with_suffix(".tmp")

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

    temp_path = cache_path.with_suffix(".tmp.jpg")
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
@media(max-width:800px){.topbar{display:block}.brand-logo{width:44px;height:44px}.topbar .button{margin-top:10px}.toolbar{grid-template-columns:1fr}.toolbar-actions{display:grid;grid-template-columns:1fr}.modal{padding:6px}.nav-button{width:36px;height:36px;font-size:22px;opacity:.72}.download-button{top:10px;right:10px}.photo-counter{top:10px;left:10px}}
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
<div>
<div class="worker" id="indexStatus">Indice: controllo stato...</div>
<div class="worker" id="workerStatus" style="margin-top:10px">Anteprime: controllo stato...</div>
</div>
<div class="toolbar-actions">
<button class="small-button" id="selectButton" onclick="toggleSelectionMode()">Seleziona</button>
<button class="small-button" id="refreshIndexButton" onclick="refreshIndex()">Aggiorna indice</button>
</div>
</div>
<div class="grid" id="gallery"></div>
<div class="load-more-wrap hidden" id="loadMoreWrap">
<button class="small-button load-more" id="loadMoreButton" onclick="loadMoreMedia()">Carica altri</button>
</div>
<div class="selection-bar" id="selectionBar">
<div class="selection-info" id="selectionInfo"></div>
<div class="selection-actions">
<button class="small-button" onclick="selectAll()">Seleziona tutto</button>
<button class="small-button" onclick="clearSelection()">Deseleziona</button>
<button class="small-button" data-mode="media" onclick="downloadSelection()">Scarica</button>
<button class="small-button danger" data-mode="media" onclick="trashSelection()">Elimina</button>
<button class="small-button" data-mode="trash" onclick="restoreSelection()">Ripristina selezionati</button>
<button class="small-button" data-mode="trash" onclick="restoreAll()">Ripristina tutto</button>
<button class="small-button danger" data-mode="trash" onclick="emptyTrash()">Svuota cestino</button>
</div>
</div>

<div class="modal" id="modal" onclick="closeModal(event)" ontouchstart="startSwipe(event)" ontouchend="endSwipe(event)">
<div class="modal-inner">
<div class="photo-counter" id="photoCounter"></div>
<button class="overlay-button nav-button nav-prev" onclick="showPreviousPhoto(event)">&lsaquo;</button>
<img id="modalImage" alt="" onclick="event.stopPropagation()">
<video id="modalVideo" controls playsinline onclick="event.stopPropagation()"></video>
<button class="overlay-button nav-button nav-next" onclick="showNextPhoto(event)">&rsaquo;</button>
<a class="overlay-button download-button" id="downloadLink" href="#" onclick="event.stopPropagation()">Scarica originale</a>
<button class="overlay-button danger delete-button" onclick="trashCurrentPhoto(event)">Elimina</button>
<div class="rating" id="ratingStars" onclick="event.stopPropagation()"></div>
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

function itemCard(item){
    const card = document.createElement('div');
    card.className = 'card' + (SELECTED.has(item.id) ? ' selected' : '');
    card.dataset.id = item.id;
    card.onclick = ()=> SELECTING ? toggleSelected(item, card) : openPhoto(item.id);

    const thumb = item.kind === 'video'
        ? `<img class="thumb video-thumb" loading="lazy" src="${item.preview_url}" alt=""><div class="play-badge">Play</div>`
        : `<img class="thumb" loading="lazy" src="${item.preview_url}" alt="">`;

    card.innerHTML = `
        ${thumb}
        <div class="info">
            <div class="name">${item.name}</div>
            <div class="meta">${item.size_label} - ${item.mtime_label}</div>
            <span class="badge">${item.extension}</span>
        </div>
    `;
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

        const incoming = data.items || [];
        PHOTOS = reset ? incoming : PHOTOS.concat(incoming);
        TOTAL_ITEMS = data.pagination ? data.pagination.total : PHOTOS.length;
        HAS_MORE = Boolean(data.pagination && data.pagination.has_more);

        status.textContent = `${PHOTOS.length}/${TOTAL_ITEMS} file caricati da ${data.storage_path || data.root}`;

        if(!PHOTOS.length){
            gallery.innerHTML = `<div class="empty">${data.empty_message || 'Nessun file trovato.'}</div>`;
            renderLoadMore();
            return;
        }

        incoming.forEach((item)=>gallery.appendChild(itemCard(item)));
        renderLoadMore();
    }catch(e){
        if(requestId !== LOAD_SEQUENCE || requestSection !== CURRENT_SECTION){
            return;
        }
        status.textContent = 'Errore caricamento media: ' + e.message;
        renderLoadMore();
    }
}

async function loadMoreMedia(){
    if(!HAS_MORE){
        return;
    }
    CURRENT_PAGE += 1;
    await loadMedia(false);
}

async function loadIndexStatus(){
    try{
        const res = await fetch('/api/index/status');
        const data = await res.json();
        const index = data.index || {};
        const worker = data.worker || {};
        const message = worker.running ? 'Indicizzazione in corso...' : (worker.message || 'Indice pronto.');
        document.getElementById('indexStatus').innerHTML =
            `<strong>Indice media:</strong> ${index.total_items || 0} file. ${message}`;
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

        document.getElementById('workerStatus').innerHTML =
            `<strong>Anteprime:</strong> RAW ${cached}/${total}, video ${videoCached}/${videoTotal}. ${worker.message || ''}${current}`;
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
    document.getElementById('photoCounter').textContent = `${CURRENT_INDEX + 1} / ${PHOTOS.length}`;

    const rating = document.getElementById('ratingStars');
    if(item){
        rating.classList.remove('hidden');
        renderRating(item.rating || 0);
    }else{
        rating.classList.add('hidden');
        rating.innerHTML = '';
    }
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
    document.getElementById('modal').classList.remove('open');
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
    document.getElementById('selectionBar').classList.toggle('visible', SELECTING || trash);
    const selectButton = document.getElementById('selectButton');
    selectButton.classList.toggle('hidden', trash);
    selectButton.textContent = SELECTING ? 'Annulla selezione' : 'Seleziona';
    document.querySelectorAll('#selectionBar [data-mode]').forEach((button)=>{
        button.classList.toggle('hidden', button.dataset.mode !== (trash ? 'trash' : 'media'));
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
    card.className = 'card' + (SELECTED.has(item.id) ? ' selected' : '');
    card.dataset.id = item.id;
    card.onclick = ()=>toggleSelected(item, card);
    card.innerHTML = `
        <img class="thumb" loading="lazy" src="${item.preview_url}" alt="">
        <div class="info">
            <div class="name">${item.name}</div>
            <div class="meta">${item.size_label} - ${item.mtime_label}</div>
            <div class="meta">Eliminato ${item.deleted_at}</div>
            <div class="meta">${item.folder}</div>
            <span class="badge">${item.extension}</span>
        </div>
    `;
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
            gallery.innerHTML = '<div class="empty">Nessun file nel cestino.</div>';
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
loadIndexStatus();
loadPreviewStatus();
setInterval(loadIndexStatus, 15000);
setInterval(loadPreviewStatus, 10000);
</script>
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
