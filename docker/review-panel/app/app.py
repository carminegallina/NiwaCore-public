from flask import Flask, Response, abort, jsonify, request, send_file
from pathlib import Path
import base64
import hashlib
import html
import json
import mimetypes
import os
import subprocess
import threading
import time
import xml.etree.ElementTree as ET

app = Flask(__name__)

PHOTO_ROOT = Path("/storage/photo")
VIDEO_ROOT = Path("/storage/video")
GOPRO_ROOT = Path("/storage/gopro")
CACHE_ROOT = Path("/storage/.niwa_cache/review_previews")
PREVIEW_STATE_FILE = CACHE_ROOT / "preview_state.json"

PREVIEW_SCAN_INTERVAL_SECONDS = 20
PREVIEW_STABLE_SECONDS = 60
PREVIEW_RETRY_SECONDS = 300

RAW_EXTENSIONS = {".nef", ".nrw", ".dng", ".arw", ".cr2", ".cr3", ".raf", ".rw2"}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
PHOTO_EXTENSIONS = RAW_EXTENSIONS | JPEG_EXTENSIONS
GOPRO_EXTENSIONS = JPEG_EXTENSIONS | VIDEO_EXTENSIONS

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
    return path.with_suffix(".xmp")


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


def scan_media(section, kind_filter="all"):
    config = section_config(section)
    root_path = config["root"]
    items = []

    for path, relative in iter_media_files(root_path, config["extensions"]):
        suffix = path.suffix.lower()
        kind = media_kind(path)

        if kind_filter == "photo" and kind == "video":
            continue
        if kind_filter == "video" and kind != "video":
            continue

        try:
            stat = path.stat()
        except OSError:
            continue

        file_id = encode_id(relative)
        preview_url = f"/api/media-file/{section}/{file_id}"
        if section == "photo" and suffix in RAW_EXTENSIONS:
            preview_url = f"/api/preview/{file_id}"

        item = {
            "id": file_id,
            "section": section,
            "name": path.name,
            "relative_path": str(relative).replace("\\", "/"),
            "extension": suffix.upper().lstrip("."),
            "kind": kind,
            "size": stat.st_size,
            "size_label": human_size(stat.st_size),
            "mtime": stat.st_mtime,
            "mtime_label": time.strftime(
                "%Y-%m-%d %H:%M",
                time.localtime(stat.st_mtime)
            ),
            "preview_url": preview_url,
            "media_url": f"/api/media-file/{section}/{file_id}",
            "download_url": f"/api/download/{section}/{file_id}",
            "rating": read_rating(path) if section == "photo" and kind != "video" else 0,
        }
        items.append(item)

    items.sort(key=lambda item: item["mtime"], reverse=True)
    return items


def scan_photos():
    return scan_media("photo")


def cache_path_for(path, relative):
    stat = path.stat()
    key = f"{relative}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8")
    digest = hashlib.sha1(key).hexdigest()
    return CACHE_ROOT / f"{digest}.jpg"


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
    existing_keys = {state_key(relative) for _path, relative in raw_files}

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
                temp_path.replace(cache_path)
                return cache_path

    if temp_path.exists():
        temp_path.unlink()

    return None


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
.worker{background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));border:1px solid rgba(148,163,184,.18);border-radius:12px;padding:12px;margin:12px 0;color:#d1d5db;font-size:14px}
.worker strong{color:#e5e7eb}
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
@media(max-width:800px){.topbar{display:block}.topbar .button{margin-top:10px}.modal{padding:6px}.nav-button{width:36px;height:36px;font-size:22px;opacity:.72}.download-button{top:10px;right:10px}.photo-counter{top:10px;left:10px}}
</style>
</head>
<body>
<div class="topbar">
<div>
<h1>NIWA Review</h1>
<div class="subtitle">Gallery locale per foto, video Nikon e media GoPro dal NAS.</div>
</div>
<a class="button" id="dashboardLink" href="/">Dashboard</a>
</div>

<div class="tabs">
<button class="tab active" data-section="photo" onclick="setSection('photo')">Foto</button>
<button class="tab" data-section="video" onclick="setSection('video')">Video</button>
<button class="tab" data-section="gopro" onclick="setSection('gopro')">GoPro</button>
</div>

<div class="filters filter-row" id="goproFilters">
<button class="filter-button active" data-filter="all" onclick="setGoProFilter('all')">Tutti</button>
<button class="filter-button" data-filter="photo" onclick="setGoProFilter('photo')">Foto</button>
<button class="filter-button" data-filter="video" onclick="setGoProFilter('video')">Video</button>
</div>

<div class="status" id="status">Caricamento...</div>
<div class="worker" id="workerStatus">Anteprime: controllo stato...</div>
<div class="grid" id="gallery"></div>

<div class="modal" id="modal" onclick="closeModal(event)" ontouchstart="startSwipe(event)" ontouchend="endSwipe(event)">
<div class="modal-inner">
<div class="photo-counter" id="photoCounter"></div>
<button class="overlay-button nav-button nav-prev" onclick="showPreviousPhoto(event)">&lsaquo;</button>
<img id="modalImage" alt="" onclick="event.stopPropagation()">
<video id="modalVideo" controls playsinline onclick="event.stopPropagation()"></video>
<button class="overlay-button nav-button nav-next" onclick="showNextPhoto(event)">&rsaquo;</button>
<a class="overlay-button download-button" id="downloadLink" href="#" onclick="event.stopPropagation()">Scarica originale</a>
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

const SECTION_LABELS = {
    photo: 'foto',
    video: 'video',
    gopro: 'media GoPro'
};

function setSection(section){
    CURRENT_SECTION = section;
    document.querySelectorAll('.tab').forEach((button)=>{
        button.classList.toggle('active', button.dataset.section === section);
    });
    document.getElementById('goproFilters').classList.toggle('visible', section === 'gopro');
    document.getElementById('workerStatus').style.display = section === 'photo' ? 'block' : 'none';
    loadMedia();
}

function setGoProFilter(filter){
    GOPRO_FILTER = filter;
    document.querySelectorAll('.filter-button').forEach((button)=>{
        button.classList.toggle('active', button.dataset.filter === filter);
    });
    loadMedia();
}

async function loadMedia(){
    const status = document.getElementById('status');
    const gallery = document.getElementById('gallery');
    const requestSection = CURRENT_SECTION;
    const requestFilter = GOPRO_FILTER;
    const requestId = ++LOAD_SEQUENCE;
    const label = SECTION_LABELS[requestSection] || 'media';
    status.textContent = `Scansione ${label}...`;
    gallery.innerHTML = '';

    try{
        let url = `/api/media/${requestSection}`;
        if(requestSection === 'gopro'){
            url += `?kind=${encodeURIComponent(requestFilter)}`;
        }

        const res = await fetch(url);
        const data = await res.json();

        if(requestId !== LOAD_SEQUENCE || requestSection !== CURRENT_SECTION){
            return;
        }

        PHOTOS = data.items || [];

        status.textContent = `${PHOTOS.length} file trovati in ${data.storage_path || data.root}`;

        if(!PHOTOS.length){
            gallery.innerHTML = `<div class="empty">${data.empty_message || 'Nessun file trovato.'}</div>`;
            return;
        }

        PHOTOS.forEach((item)=>{
            const card = document.createElement('div');
            card.className = 'card';
            card.onclick = ()=>openPhoto(item.id);

            const thumb = item.kind === 'video'
                ? `<video class="thumb video-thumb" muted preload="metadata" src="${item.media_url}"></video><div class="play-badge">Play</div>`
                : `<img class="thumb" loading="lazy" src="${item.preview_url}" alt="">`;

            card.innerHTML = `
                ${thumb}
                <div class="info">
                    <div class="name">${item.name}</div>
                    <div class="meta">${item.size_label} - ${item.mtime_label}</div>
                    <span class="badge">${item.extension}</span>
                </div>
            `;
            gallery.appendChild(card);
        });
    }catch(e){
        if(requestId !== LOAD_SEQUENCE || requestSection !== CURRENT_SECTION){
            return;
        }
        status.textContent = 'Errore caricamento media: ' + e.message;
    }
}

async function loadPreviewStatus(){
    try{
        const res = await fetch('/api/previews/status');
        const data = await res.json();
        const worker = data.worker || {};
        const total = data.raw_total || 0;
        const cached = data.raw_cached || 0;
        const current = worker.current ? ` - ${worker.current}` : '';

        document.getElementById('workerStatus').innerHTML =
            `<strong>Anteprime RAW:</strong> ${cached}/${total} in cache. ${worker.message || ''}${current}`;
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
    if(item.section === 'photo' && item.kind !== 'video'){
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
    if(!item || item.section !== 'photo'){
        return;
    }

    const nextRating = item.rating === rating ? 0 : rating;

    try{
        const res = await fetch(`/api/rating/${item.id}`, {
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

loadMedia();
loadPreviewStatus();
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
    return jsonify({
        "section": section,
        "label": config["label"],
        "root": str(config["root"]),
        "storage_path": str(config["root"]),
        "exists": config["root"].exists(),
        "empty_message": config["empty"],
        "items": items,
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


@app.route("/api/media-file/<section>/<file_id>")
def api_media_file(section, file_id):
    config = section_config(section)
    path, _relative = resolve_media(config["root"], file_id)

    if path.suffix.lower() not in config["extensions"]:
        abort(404)

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return send_file(path, mimetype=mime, conditional=True)


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
    path, _relative = resolve_photo(file_id)
    payload = request.get_json(silent=True) or {}

    if path.suffix.lower() not in PHOTO_EXTENSIONS:
        return jsonify({"error": "Rating disponibile solo per le foto."}), 400

    try:
        rating = int(payload.get("rating", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Rating non valido."}), 400

    rating = max(0, min(5, rating))

    try:
        write_rating(path, rating)
    except OSError as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "ok": True,
        "rating": read_rating(path),
        "xmp": str(xmp_path_for(path)),
    })


@app.route("/api/status")
def api_status():
    return jsonify({
        "photo_root": str(PHOTO_ROOT),
        "photo_root_exists": PHOTO_ROOT.exists(),
        "video_root": str(VIDEO_ROOT),
        "video_root_exists": VIDEO_ROOT.exists(),
        "gopro_root": str(GOPRO_ROOT),
        "gopro_root_exists": GOPRO_ROOT.exists(),
        "cache_root": str(CACHE_ROOT),
        "exiftool": subprocess.run(
            ["sh", "-c", "command -v exiftool >/dev/null 2>&1"],
            check=False
        ).returncode == 0,
    })


@app.route("/api/previews/status")
def api_preview_status():
    total, cached = count_cached_raw_previews()
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
        "cache_root": str(CACHE_ROOT),
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
    app.run(host="0.0.0.0", port=5052)
