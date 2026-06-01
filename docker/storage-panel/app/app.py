from flask import jsonify
from flask import Flask
from pathlib import Path
import os
import shutil
import time

app = Flask(__name__)

STORAGE_ROOT = Path("/storage")

MEDIA_GROUPS = [
    {
        "id": "photo",
        "label": "Foto",
        "path": "photo",
        "extensions": [
            ".3fr", ".arw", ".cr2", ".cr3", ".dng", ".erf", ".fff", ".iiq",
            ".jpg", ".jpeg", ".kdc", ".mos", ".mrw", ".nef", ".nrw", ".orf",
            ".pef", ".raf", ".raw", ".rwl", ".rw2", ".srw", ".x3f", ".xmp",
        ],
    },
    {
        "id": "video",
        "label": "Video",
        "path": "video",
        "extensions": [".avi", ".braw", ".crm", ".m2ts", ".m4v", ".mov", ".mp4", ".mts", ".mxf"],
    },
    {
        "id": "gopro",
        "label": "GoPro",
        "path": "gopro",
        "extensions": [".gpr", ".jpg", ".jpeg", ".mp4", ".mov", ".m4v"],
    },
    {
        "id": "backstage",
        "label": "Backstage",
        "path": "backstage",
        "extensions": [".jpg", ".jpeg", ".png", ".mp4", ".mov"],
    },
    {
        "id": "exports",
        "label": "Exports",
        "path": "exports",
        "extensions": [".jpg", ".jpeg", ".png", ".mp4", ".mov", ".pdf"],
    },
    {
        "id": "backup",
        "label": "Backup",
        "path": "backup",
        "extensions": [],
    },
    {
        "id": "events",
        "label": "Events",
        "path": "events",
        "extensions": [],
    },
]


def human_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def empty_stats():
    return {
        "bytes": 0,
        "size_label": "0 B",
        "files": 0,
        "matched_files": 0,
        "extensions": {},
        "exists": False,
        "errors": 0,
    }


def scan_folder(path, extensions):
    stats = empty_stats()
    stats["exists"] = path.exists()

    if not path.exists():
        return stats

    extension_filter = {extension.lower() for extension in extensions}

    for root, dirs, files in os.walk(path):
        dirs[:] = [
            directory for directory in dirs
            if not directory.startswith(".") and directory != ".niwa_cache"
        ]

        for filename in files:
            file_path = Path(root) / filename
            suffix = file_path.suffix.lower() or "(none)"

            try:
                size = file_path.stat().st_size
            except OSError:
                stats["errors"] += 1
                continue

            stats["files"] += 1
            stats["bytes"] += size
            stats["extensions"][suffix] = stats["extensions"].get(suffix, 0) + 1

            if not extension_filter or suffix in extension_filter:
                stats["matched_files"] += 1

    stats["size_label"] = human_size(stats["bytes"])
    return stats


def scan_storage():
    usage = shutil.disk_usage(STORAGE_ROOT)
    groups = []

    for group in MEDIA_GROUPS:
        path = STORAGE_ROOT / group["path"]
        stats = scan_folder(path, group["extensions"])
        groups.append({
            **group,
            **stats,
            "absolute_path": str(path),
            "percent_of_used": (
                round((stats["bytes"] / usage.used) * 100, 1)
                if usage.used else 0
            ),
        })

    groups.sort(key=lambda item: item["bytes"], reverse=True)

    return {
        "storage_root": str(STORAGE_ROOT),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "total_label": human_size(usage.total),
        "used_label": human_size(usage.used),
        "free_label": human_size(usage.free),
        "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0,
        "free_percent": round((usage.free / usage.total) * 100, 1) if usage.total else 0,
        "groups": groups,
    }


@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIWA Storage</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#172033;--panel2:#101827;--line:#334155;--text:#f8fafc;--muted:#94a3b8;--soft:#cbd5e1;--blue:#38bdf8;--green:#22c55e;--yellow:#facc15;--red:#ef4444}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:radial-gradient(circle at 24% 0%,rgba(56,189,248,.10),transparent 32%),linear-gradient(180deg,#0b1220,#0f172a 42%,#0b1220);color:var(--text);padding:20px}
h1{margin:0 0 6px 0;font-size:32px;letter-spacing:0}.subtitle{color:var(--muted);margin-bottom:18px;line-height:1.45}
.topbar{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:18px}
.button{display:inline-flex;align-items:center;justify-content:center;background:#263244;color:white;text-decoration:none;padding:10px 12px;border-radius:10px;border:1px solid rgba(148,163,184,.22);min-height:40px;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.button:hover{background:#334155}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.card{background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));border:1px solid rgba(148,163,184,.18);border-radius:12px;padding:16px;box-shadow:0 18px 34px rgba(0,0,0,.22)}
.value{font-size:28px;font-weight:bold;margin:8px 0}.label{color:var(--muted);font-size:14px;line-height:1.4}.small{color:var(--muted);font-size:12px}
.bar{height:12px;background:#101827;border:1px solid rgba(148,163,184,.14);border-radius:999px;overflow:hidden;margin-top:10px}
.bar-fill{height:100%;background:#38bdf8;width:0%}.group{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center}
.group-name{font-weight:bold}.pill{display:inline-block;background:rgba(15,23,42,.92);border:1px solid rgba(148,163,184,.20);border-radius:999px;padding:4px 8px;margin:6px 4px 0 0;color:#dbeafe;font-size:12px}
.missing{border-color:rgba(239,68,68,.58)}.status{color:var(--muted);margin:12px 0;font-size:14px}
:root{--bg:#0f0d0d;--panel:#211918;--panel2:#151112;--line:rgba(203,144,124,.28);--text:#fff7f0;--muted:#c8afa4;--soft:#eadbd4;--blue:#d59a84;--accent:#d59a84;--accent-strong:#f0b8a2}
body{background:radial-gradient(circle at 18% -5%,rgba(213,154,132,.22),transparent 34%),radial-gradient(circle at 84% 8%,rgba(246,226,209,.08),transparent 28%),linear-gradient(180deg,#0e0c0c,#171211 46%,#0e0c0c)}
.brand-heading{display:flex;align-items:center;gap:12px;min-width:0}.brand-logo{width:52px;height:52px;border-radius:50%;border:1px solid rgba(213,154,132,.42);background:#f2dfcf;box-shadow:0 16px 34px rgba(0,0,0,.28);flex:0 0 auto}.brand-copy{min-width:0}
h1{color:#fff4ec}.subtitle{color:var(--muted)}
.button{background:rgba(64,45,42,.92);border-color:var(--line)}.button:hover{background:rgba(87,61,56,.96);border-color:rgba(213,154,132,.42)}
.card{background:linear-gradient(180deg,rgba(42,31,29,.94),rgba(18,14,14,.96));border-color:var(--line);box-shadow:0 18px 34px rgba(0,0,0,.25)}
.bar{background:#151112;border-color:rgba(203,144,124,.18)}.bar-fill{background:linear-gradient(90deg,#d59a84,#f0b8a2)}
.pill{background:rgba(64,45,42,.92);border-color:var(--line);color:#ffe0d1}
@media(max-width:700px){.topbar{display:block}.brand-logo{width:44px;height:44px}.topbar .button{margin-top:10px}.group{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="topbar">
<div class="brand-heading">
<img class="brand-logo" src="/static/niwa-logo.png" alt="">
<div class="brand-copy">
<h1>NIWA Storage</h1>
<div class="subtitle">Spazio SSD e riepilogo cartelle media.</div>
</div>
</div>
<a class="button" id="dashboardLink" href="/">Dashboard</a>
</div>

<div class="status" id="status">Caricamento...</div>

<div class="grid" id="summary"></div>
<div class="grid" id="groups" style="margin-top:12px"></div>

<script>
function serviceUrl(port, path=''){
    return `${window.location.protocol}//${window.location.hostname}:${port}${path}`;
}

document.getElementById('dashboardLink').href = serviceUrl(3000);

async function loadStorage(){
    const status = document.getElementById('status');
    const summary = document.getElementById('summary');
    const groups = document.getElementById('groups');

    try{
        const res = await fetch('/api/storage');
        const data = await res.json();

        status.textContent = 'Aggiornamento: ' + data.updated;
        summary.innerHTML = `
            <div class="card">
                <div class="label">Spazio usato</div>
                <div class="value">${data.used_label}</div>
                <div class="label">${data.used_percent}% di ${data.total_label}</div>
                <div class="bar"><div class="bar-fill" style="width:${data.used_percent}%"></div></div>
            </div>
            <div class="card">
                <div class="label">Spazio libero</div>
                <div class="value">${data.free_label}</div>
                <div class="label">${data.free_percent}% disponibile</div>
            </div>
            <div class="card">
                <div class="label">Percorso storage</div>
                <div class="value" style="font-size:18px">${data.storage_root}</div>
                <div class="label">SSD montato nel container in sola lettura</div>
            </div>
        `;

        groups.innerHTML = '';

        data.groups.forEach((group)=>{
            const div = document.createElement('div');
            div.className = 'card' + (group.exists ? '' : ' missing');
            const topExtensions = Object.entries(group.extensions)
                .sort((a,b)=>b[1]-a[1])
                .slice(0,6)
                .map(([ext,count])=>`<span class="pill">${ext}: ${count}</span>`)
                .join('');

            div.innerHTML = `
                <div class="group">
                    <div>
                        <div class="group-name">${group.label}</div>
                        <div class="small">${group.absolute_path}</div>
                    </div>
                    <div class="value" style="font-size:22px">${group.size_label}</div>
                </div>
                <div class="label">${group.files} file totali, ${group.matched_files} media rilevanti</div>
                <div class="bar"><div class="bar-fill" style="width:${Math.min(group.percent_of_used,100)}%"></div></div>
                <div>${topExtensions || '<span class="pill">nessun file</span>'}</div>
            `;
            groups.appendChild(div);
        });
    }catch(e){
        status.textContent = 'Errore lettura storage: ' + e.message;
    }
}

loadStorage();
setInterval(loadStorage, 30000);
</script>
</body>
</html>
"""


@app.route("/api/storage")
def api_storage():
    return jsonify(scan_storage())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5053)
