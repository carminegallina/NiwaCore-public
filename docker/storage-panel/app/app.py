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
        "extensions": [".nef", ".nrw", ".dng", ".jpg", ".jpeg", ".xmp"],
    },
    {
        "id": "video",
        "label": "Video",
        "path": "video",
        "extensions": [".mp4", ".mov", ".m4v"],
    },
    {
        "id": "gopro",
        "label": "GoPro",
        "path": "gopro",
        "extensions": [".jpg", ".jpeg", ".mp4", ".mov", ".m4v"],
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
body{margin:0;font-family:Arial,sans-serif;background:#111827;color:white;padding:20px}
h1{margin:0 0 8px 0}.subtitle{color:#9ca3af;margin-bottom:18px}
.topbar{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}
.button{display:inline-block;background:#374151;color:white;text-decoration:none;padding:10px 12px;border-radius:10px;border:none}
.button:hover{background:#4b5563}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.card{background:#1f2937;border-radius:12px;padding:16px;box-shadow:0 8px 20px rgba(0,0,0,.25)}
.value{font-size:28px;font-weight:bold;margin:8px 0}.label{color:#9ca3af;font-size:14px}.small{color:#9ca3af;font-size:12px}
.bar{height:12px;background:#374151;border-radius:999px;overflow:hidden;margin-top:10px}
.bar-fill{height:100%;background:#3b82f6;width:0%}.group{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center}
.group-name{font-weight:bold}.pill{display:inline-block;background:#111827;border-radius:999px;padding:4px 8px;margin:6px 4px 0 0;color:#d1d5db;font-size:12px}
.missing{border:1px solid #7f1d1d}.status{color:#9ca3af;margin:12px 0;font-size:14px}
@media(max-width:700px){.topbar{display:block}.topbar .button{margin-top:10px}.group{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="topbar">
<div>
<h1>NIWA Storage</h1>
<div class="subtitle">Spazio SSD e riepilogo cartelle media.</div>
</div>
<a class="button" href="http://10.42.0.1:3000">Dashboard</a>
</div>

<div class="status" id="status">Caricamento...</div>

<div class="grid" id="summary"></div>
<div class="grid" id="groups" style="margin-top:12px"></div>

<script>
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
