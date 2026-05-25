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

app = Flask(__name__)

PHOTO_ROOT = Path("/storage/photo")
CACHE_ROOT = Path("/storage/.niwa_cache/review_previews")
PREVIEW_STATE_FILE = CACHE_ROOT / "preview_state.json"

PREVIEW_SCAN_INTERVAL_SECONDS = 20
PREVIEW_STABLE_SECONDS = 60
PREVIEW_RETRY_SECONDS = 300

RAW_EXTENSIONS = {".nef", ".nrw", ".dng", ".arw", ".cr2", ".cr3", ".raf", ".rw2"}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}
PHOTO_EXTENSIONS = RAW_EXTENSIONS | JPEG_EXTENSIONS

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


def resolve_photo(file_id):
    relative = decode_id(file_id)
    path = (PHOTO_ROOT / relative).resolve()
    root = PHOTO_ROOT.resolve()

    try:
        path.relative_to(root)
    except ValueError:
        abort(400, "Path outside photo root")

    if not path.exists() or not path.is_file():
        abort(404, "File not found")

    return path, relative


def human_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def is_raw(path):
    return path.suffix.lower() in RAW_EXTENSIONS


def iter_photo_files(extensions):
    if not PHOTO_ROOT.exists():
        return

    for root, dirs, files in os.walk(PHOTO_ROOT):
        dirs[:] = [
            directory for directory in dirs
            if not directory.startswith(".") and directory != ".niwa_cache"
        ]

        root_path = Path(root)
        for filename in files:
            path = root_path / filename
            if path.suffix.lower() not in extensions:
                continue

            try:
                relative = path.relative_to(PHOTO_ROOT)
            except ValueError:
                continue

            yield path, relative


def scan_photos():
    items = []

    for path, relative in iter_photo_files(PHOTO_EXTENSIONS):
        suffix = path.suffix.lower()

        try:
            stat = path.stat()
        except OSError:
            continue

        items.append({
            "id": encode_id(relative),
            "name": path.name,
            "relative_path": str(relative).replace("\\", "/"),
            "extension": suffix.upper().lstrip("."),
            "kind": "raw" if suffix in RAW_EXTENSIONS else "jpg",
            "size": stat.st_size,
            "size_label": human_size(stat.st_size),
            "mtime": stat.st_mtime,
            "mtime_label": time.strftime(
                "%Y-%m-%d %H:%M",
                time.localtime(stat.st_mtime)
            ),
            "preview_url": f"/api/preview/{encode_id(relative)}",
            "download_url": f"/api/download/{encode_id(relative)}",
        })

    items.sort(key=lambda item: item["mtime"], reverse=True)
    return items


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
body{margin:0;font-family:Arial,sans-serif;background:#111827;color:white;padding:20px}
h1{margin:0 0 8px 0}.subtitle{color:#9ca3af;margin-bottom:18px}
.topbar{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}
.button{display:inline-block;background:#374151;color:white;text-decoration:none;padding:10px 12px;border-radius:10px;border:none}
.button:hover{background:#4b5563}.status{color:#9ca3af;font-size:14px;margin:12px 0}
.worker{background:#1f2937;border-radius:12px;padding:12px;margin:12px 0;color:#d1d5db;font-size:14px}
.worker strong{color:#e5e7eb}
.tabs{display:flex;gap:8px;margin:16px 0;flex-wrap:wrap}
.tab{background:#1f2937;color:#e5e7eb;border:none;border-radius:10px;padding:10px 12px}
.tab.active{background:#2563eb;color:white}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.card{background:#1f2937;border-radius:12px;overflow:hidden;box-shadow:0 8px 20px rgba(0,0,0,.25)}
.thumb{width:100%;aspect-ratio:3/2;object-fit:cover;background:#111827;display:block}
.info{padding:10px}.name{font-weight:bold;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{color:#9ca3af;font-size:12px;margin-top:4px}.badge{display:inline-block;background:#374151;color:#e5e7eb;border-radius:999px;padding:3px 7px;font-size:11px;margin-top:8px}
.empty{background:#1f2937;border-radius:12px;padding:18px;color:#9ca3af}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.9);display:none;align-items:center;justify-content:center;padding:12px;z-index:10}
.modal.open{display:flex}.modal-inner{position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center}
.modal img{max-width:100%;max-height:100%;object-fit:contain}
.overlay-button{position:absolute;background:rgba(17,24,39,.72);color:white;text-decoration:none;border:none;border-radius:999px;padding:10px 12px;backdrop-filter:blur(8px)}
.overlay-button:hover{background:rgba(55,65,81,.9)}
.download-button{top:14px;right:14px}
.nav-button{top:50%;transform:translateY(-50%);width:42px;height:42px;font-size:26px;line-height:20px;display:flex;align-items:center;justify-content:center}
.nav-prev{left:14px}.nav-next{right:14px}
.photo-counter{position:absolute;left:14px;top:14px;background:rgba(17,24,39,.72);color:#e5e7eb;border-radius:999px;padding:8px 11px;font-size:13px;backdrop-filter:blur(8px)}
@media(max-width:800px){.topbar{display:block}.topbar .button{margin-top:10px}.modal{padding:6px}.nav-button{width:36px;height:36px;font-size:22px;opacity:.72}.download-button{top:10px;right:10px}.photo-counter{top:10px;left:10px}}
</style>
</head>
<body>
<div class="topbar">
<div>
<h1>NIWA Review</h1>
<div class="subtitle">Anteprime RAW/JPG dalla cartella photo del NAS.</div>
</div>
<a class="button" href="http://10.42.0.1:3000">Dashboard</a>
</div>

<div class="tabs">
<button class="tab active" data-section="photo" onclick="setSection('photo')">Foto</button>
<button class="tab" data-section="video" onclick="setSection('video')" disabled>Video</button>
<button class="tab" data-section="drone" onclick="setSection('drone')" disabled>Drone</button>
<button class="tab" data-section="gopro" onclick="setSection('gopro')" disabled>GoPro</button>
<button class="tab" data-section="insta360" onclick="setSection('insta360')" disabled>Insta360</button>
</div>

<div class="status" id="status">Caricamento...</div>
<div class="worker" id="workerStatus">Anteprime: controllo stato...</div>
<div class="grid" id="gallery"></div>

<div class="modal" id="modal" onclick="closeModal(event)" ontouchstart="startSwipe(event)" ontouchend="endSwipe(event)">
<div class="modal-inner">
<div class="photo-counter" id="photoCounter"></div>
<button class="overlay-button nav-button nav-prev" onclick="showPreviousPhoto(event)">‹</button>
<img id="modalImage" alt="" onclick="event.stopPropagation()">
<button class="overlay-button nav-button nav-next" onclick="showNextPhoto(event)">›</button>
<a class="overlay-button download-button" id="downloadLink" href="#" onclick="event.stopPropagation()">Scarica RAW</a>
</div>
</div>

<script>
let PHOTOS = [];
let CURRENT_INDEX = -1;
let SWIPE_START_X = 0;
let SWIPE_START_Y = 0;

function setSection(section){
    if(section !== 'photo'){
        return;
    }
}

async function loadPhotos(){
    const status = document.getElementById('status');
    const gallery = document.getElementById('gallery');
    status.textContent = 'Scansione foto...';
    gallery.innerHTML = '';

    try{
        const res = await fetch('/api/photos');
        const data = await res.json();
        PHOTOS = data.items || [];

        status.textContent = `${PHOTOS.length} file foto trovati in /mnt/niwa-storage/photo`;

        if(!PHOTOS.length){
            gallery.innerHTML = '<div class="empty">Nessun RAW o JPG trovato nella cartella photo.</div>';
            return;
        }

        PHOTOS.forEach((item)=>{
            const card = document.createElement('div');
            card.className = 'card';
            card.onclick = ()=>openPhoto(item.id);
            card.innerHTML = `
                <img class="thumb" loading="lazy" src="${item.preview_url}" alt="">
                <div class="info">
                    <div class="name">${item.name}</div>
                    <div class="meta">${item.size_label} - ${item.mtime_label}</div>
                    <span class="badge">${item.extension}</span>
                </div>
            `;
            gallery.appendChild(card);
        });
    }catch(e){
        status.textContent = 'Errore caricamento foto: ' + e.message;
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

    document.getElementById('modalImage').src = item.preview_url;
    document.getElementById('downloadLink').href = item.download_url;
    document.getElementById('photoCounter').textContent = `${CURRENT_INDEX + 1} / ${PHOTOS.length}`;
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

loadPhotos();
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


@app.route("/api/download/<file_id>")
def api_download(file_id):
    path, _relative = resolve_photo(file_id)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return send_file(path, mimetype=mime, as_attachment=True, download_name=path.name)


@app.route("/api/status")
def api_status():
    return jsonify({
        "photo_root": str(PHOTO_ROOT),
        "photo_root_exists": PHOTO_ROOT.exists(),
        "cache_root": str(CACHE_ROOT),
        "exiftool": subprocess.run(
            ["sh", "-c", "command -v exiftool >/dev/null 2>&1"],
            check=False
        ).returncode == 0,
    })


@app.route("/api/previews/status")
def api_preview_status():
    total, cached = count_cached_raw_previews()

    with WORKER_LOCK:
        worker = dict(WORKER_STATE)

    return jsonify({
        "raw_total": total,
        "raw_cached": cached,
        "cache_root": str(CACHE_ROOT),
        "state_file": str(PREVIEW_STATE_FILE),
        "scan_interval_seconds": PREVIEW_SCAN_INTERVAL_SECONDS,
        "stable_seconds": PREVIEW_STABLE_SECONDS,
        "worker": worker,
    })


if __name__ == "__main__":
    worker = threading.Thread(target=preview_worker_loop, daemon=True)
    worker.start()
    app.run(host="0.0.0.0", port=5052)
