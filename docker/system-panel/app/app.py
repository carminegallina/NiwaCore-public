# Copyright (c) 2026 Carmine Gallina - https://github.com/carminegallina
from flask import Flask, jsonify, request
from datetime import datetime, timezone, timedelta
from pathlib import Path
import http.client
import json
import os
import shutil
import socket
import subprocess
import time
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


app = Flask(__name__)

PORT = int(os.environ.get("NIWA_SYSTEM_PORT", "5056"))
STORAGE_ROOT = Path(os.environ.get("NIWA_STORAGE_ROOT", "/storage"))
LAN_IP = os.environ.get("NIWA_LAN_IP", "192.168.1.100")
HOTSPOT_IP = os.environ.get("NIWA_HOTSPOT_IP", "10.42.0.1")
TAILSCALE_IP = os.environ.get("NIWA_TAILSCALE_IP", "100.64.0.1")
TIMEZONE_NAME = os.environ.get("NIWA_TIMEZONE", "Europe/Rome")
# Shared with the host: this container only drops a request file here and the
# root-owned niwa-admin wrapper validates and applies it.
HOTSPOT_DIR = Path(os.environ.get("NIWA_HOTSPOT_DIR", "/hotspot"))
HOTSPOT_CHANNELS = ("1", "6", "11")

GB = 1024 ** 3

SERVICE_CHECKS = [
    {
        "id": "homepage",
        "name": "Homepage",
        "group": "Core",
        "kind": "http",
        "port": 3000,
        "path": "/",
        "critical": True,
        "href_port": 3000,
    },
    {
        "id": "filebrowser",
        "name": "FileBrowser",
        "group": "Core",
        "kind": "http",
        "port": 8080,
        "path": "/",
        "critical": True,
        "href_port": 8080,
    },
    {
        "id": "drone",
        "name": "NIWA Drone",
        "group": "Pannelli",
        "kind": "http",
        "port": 5051,
        "path": "/",
        "critical": True,
        "href_port": 5051,
    },
    {
        "id": "review",
        "name": "NIWA Review",
        "group": "Pannelli",
        "kind": "http",
        "port": 5052,
        "path": "/",
        "critical": True,
        "href_port": 5052,
    },
    {
        "id": "storage",
        "name": "NIWA Storage",
        "group": "Pannelli",
        "kind": "http",
        "port": 5053,
        "path": "/",
        "critical": True,
        "href_port": 5053,
    },
    {
        "id": "shooting",
        "name": "NIWA Shooting Tools",
        "group": "Pannelli",
        "kind": "http",
        "port": 5054,
        "path": "/",
        "critical": True,
        "href_port": 5054,
    },
    {
        "id": "lights",
        "name": "NIWA Lights",
        "group": "Pannelli",
        "kind": "http",
        "port": 5055,
        "path": "/",
        "critical": True,
        "href_port": 5055,
    },
    {
        "id": "system",
        "name": "NIWA System",
        "group": "Pannelli",
        "kind": "http",
        "port": 5056,
        "path": "/api/health",
        "critical": True,
        "href_port": 5056,
    },
    {
        "id": "import",
        "name": "NIWA Import",
        "group": "Pannelli",
        "kind": "http",
        "port": 5057,
        "path": "/api/health",
        "critical": True,
        "href_port": 5057,
    },
    {
        "id": "companion",
        "name": "NIWA Companion",
        "group": "Pannelli",
        "kind": "http",
        "port": 5058,
        "path": "/api/health",
        "critical": True,
        "href_port": 5058,
    },
    {
        "id": "glances",
        "name": "Glances",
        "group": "Monitor",
        "kind": "http",
        "port": 61208,
        "path": "/",
        "critical": False,
        "href_port": 61208,
    },
    {
        "id": "portainer",
        "name": "Portainer",
        "group": "Monitor",
        "kind": "tcp",
        "port": 9443,
        "critical": False,
        "href_port": 9443,
        "note": "HTTPS locale: il browser puo mostrare un avviso certificato.",
    },
    {
        "id": "samba",
        "name": "Samba",
        "group": "Condivisione",
        "kind": "tcp",
        "port": 445,
        "critical": True,
        "note": "Share Windows \\\\niwahub\\media.",
    },
    {
        "id": "ssh",
        "name": "SSH",
        "group": "Manutenzione",
        "kind": "tcp",
        "port": 22,
        "critical": False,
    },
]


def human_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def human_duration(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _seconds = divmod(seconds, 60)

    parts = []
    if days:
        parts.append(f"{days} g")
    if hours or days:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return " ".join(parts)


def now_label():
    if ZoneInfo:
        try:
            return datetime.now(ZoneInfo(TIMEZONE_NAME)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    return datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M:%S")


def status_weight(status):
    return {"ok": 0, "warning": 1, "error": 2}.get(status, 2)


def item(status, name, detail, item_id, group, critical=True, **extra):
    return {
        "id": item_id,
        "name": name,
        "group": group,
        "status": status,
        "detail": detail,
        "critical": critical,
        **extra,
    }


def tcp_check(port, timeout=1.6):
    started = time.time()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            elapsed_ms = int((time.time() - started) * 1000)
            return "ok", f"Porta {port} raggiungibile in {elapsed_ms} ms"
    except OSError as error:
        return "error", f"Porta {port} non raggiungibile: {error}"


def http_check(port, path="/", timeout=2.2):
    started = time.time()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        connection.request("GET", path, headers={"User-Agent": "NIWA-System/1.0"})
        response = connection.getresponse()
        response.read(128)
        elapsed_ms = int((time.time() - started) * 1000)
        if 200 <= response.status < 500:
            return "ok", f"HTTP {response.status} in {elapsed_ms} ms"
        return "error", f"HTTP {response.status} in {elapsed_ms} ms"
    except OSError as error:
        return "error", f"HTTP non raggiungibile: {error}"
    finally:
        try:
            connection.close()
        except Exception:
            pass


def check_service(service):
    if service["kind"] == "http":
        status, detail = http_check(service["port"], service.get("path", "/"))
    else:
        status, detail = tcp_check(service["port"])

    if status == "error" and not service.get("critical", True):
        status = "warning"

    href = None
    href_port = service.get("href_port")
    if href_port:
        protocol = "https" if href_port == 9443 else "http"
        href = f"{protocol}://__HOST__:{href_port}"

    return item(
        status=status,
        name=service["name"],
        detail=service.get("note") or detail,
        item_id=service["id"],
        group=service["group"],
        critical=service.get("critical", True),
        port=service["port"],
        kind=service["kind"],
        href=href,
        live_detail=detail,
    )


def command_output(command, timeout=2):
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def current_ips():
    output = command_output(["hostname", "-I"])
    if output:
        return [part for part in output.split() if part]

    try:
        return socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return []


def network_checks(ips):
    checks = []

    def add_ip_check(item_id, name, expected, critical, fallback_prefix=None):
        found_exact = expected in ips
        found_prefix = bool(fallback_prefix and any(ip.startswith(fallback_prefix) for ip in ips))
        if found_exact:
            checks.append(item("ok", name, f"{expected} presente", item_id, "Rete", critical))
        elif found_prefix:
            checks.append(item("warning", name, f"{expected} non trovato, ma e presente un IP compatibile", item_id, "Rete", critical))
        else:
            status = "error" if critical else "warning"
            checks.append(item(status, name, f"{expected} non trovato tra gli IP attivi", item_id, "Rete", critical))

    # Away from home there is no cable and often no internet: both are normal,
    # so LAN and Tailscale only describe the situation and never raise an alarm.
    lan = [ip for ip in ips if ip.startswith("192.168.")]
    if LAN_IP in lan:
        lan_detail = f"{LAN_IP} presente"
    elif lan:
        lan_detail = f"Collegata con {', '.join(lan)}"
    else:
        lan_detail = "Non collegata: normale fuori casa"
    checks.append(item("ok", "LAN cablata", lan_detail, "lan_ip", "Rete", False))

    add_ip_check("hotspot_ip", "Hotspot NIWA-AP", HOTSPOT_IP, True, "10.42.")

    tailscale = [ip for ip in ips if ip.startswith("100.")]
    if TAILSCALE_IP in tailscale:
        tailscale_detail = f"{TAILSCALE_IP} presente"
    elif tailscale:
        tailscale_detail = f"Attivo con {', '.join(tailscale)}"
    else:
        tailscale_detail = "Non attivo: serve internet"
    checks.append(item("ok", "Tailscale", tailscale_detail, "tailscale_ip", "Rete", False))

    return checks


def storage_check():
    if not STORAGE_ROOT.exists():
        return item(
            "error",
            "SSD media",
            f"{STORAGE_ROOT} non esiste nel container",
            "storage_mount",
            "Storage",
            True,
        )

    try:
        usage = shutil.disk_usage(STORAGE_ROOT)
    except OSError as error:
        return item("error", "SSD media", f"Errore lettura storage: {error}", "storage_mount", "Storage", True)

    total_gb = usage.total / GB
    free_percent = (usage.free / usage.total) * 100 if usage.total else 0
    used_percent = (usage.used / usage.total) * 100 if usage.total else 0

    if total_gb < 100:
        status = "error"
        detail = f"Volume troppo piccolo per essere il Kioxia SSD: {human_size(usage.total)}"
    elif free_percent < 5:
        status = "error"
        detail = f"Spazio quasi esaurito: {human_size(usage.free)} liberi"
    elif free_percent < 15:
        status = "warning"
        detail = f"Spazio basso: {human_size(usage.free)} liberi"
    else:
        status = "ok"
        detail = f"{human_size(usage.free)} liberi su {human_size(usage.total)}"

    return item(
        status,
        "SSD media",
        detail,
        "storage_mount",
        "Storage",
        True,
        total_label=human_size(usage.total),
        used_label=human_size(usage.used),
        free_label=human_size(usage.free),
        used_percent=round(used_percent, 1),
        free_percent=round(free_percent, 1),
        path=str(STORAGE_ROOT),
    )


def uptime_info():
    try:
        raw = Path("/proc/uptime").read_text(encoding="utf-8").split()[0]
        seconds = float(raw)
    except (OSError, ValueError, IndexError):
        seconds = 0
    return {
        "seconds": int(seconds),
        "label": human_duration(seconds) if seconds else "non disponibile",
    }


def build_status():
    services = [check_service(service) for service in SERVICE_CHECKS]
    ips = current_ips()
    checks = [storage_check(), *network_checks(ips)]
    all_items = services + checks

    critical_errors = [entry for entry in all_items if entry["critical"] and entry["status"] == "error"]
    any_errors = [entry for entry in all_items if entry["status"] == "error"]
    warnings = [entry for entry in all_items if entry["status"] == "warning"]

    if critical_errors:
        overall = "error"
        label = "Intervento richiesto"
        message = f"{len(critical_errors)} controlli critici non OK"
    elif any_errors or warnings:
        overall = "warning"
        label = "Da controllare"
        message = f"{len(warnings) + len(any_errors)} avvisi presenti"
    else:
        overall = "ok"
        label = "Tutto ok"
        message = "Servizi, storage e rete sono disponibili"

    ok_count = sum(1 for entry in all_items if entry["status"] == "ok")
    warning_count = sum(1 for entry in all_items if entry["status"] == "warning")
    error_count = sum(1 for entry in all_items if entry["status"] == "error")

    groups = {}
    for entry in all_items:
        groups.setdefault(entry["group"], []).append(entry)
    for entries in groups.values():
        entries.sort(key=lambda entry: (status_weight(entry["status"]), entry["name"]))

    return {
        "updated": now_label(),
        "overall": {
            "status": overall,
            "label": label,
            "message": message,
            "ok": ok_count,
            "warning": warning_count,
            "error": error_count,
            "total": len(all_items),
        },
        "uptime": uptime_info(),
        "ips": ips,
        "services": services,
        "checks": checks,
        "groups": groups,
    }


def read_hotspot_json(name):
    try:
        data = json.loads((HOTSPOT_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def channel_load(networks):
    # ponytail: rough airtime/interference score, each neighbour weighs its dB
    # above a -100 dBm floor, scaled down by channel distance (no overlap at 5+).
    # Good enough to rank 1/6/11; real spectrum analysis would need other hardware.
    load = {}
    for candidate in HOTSPOT_CHANNELS:
        score, count, strongest = 0.0, 0, None
        for network in networks:
            try:
                channel, signal = int(network["channel"]), float(network["signal"])
            except (KeyError, TypeError, ValueError):
                continue
            distance = abs(channel - int(candidate))
            if distance >= 5:
                continue
            count += 1
            score += max(0.0, signal + 100) * (1 - distance / 5)
            strongest = signal if strongest is None else max(strongest, signal)
        load[candidate] = {"networks": count, "strongest": strongest, "score": round(score, 1)}
    return load


def hotspot_scan(current_channel):
    scan = read_hotspot_json("scan.json")
    networks = scan.get("networks") if isinstance(scan.get("networks"), list) else []
    load = channel_load(networks) if scan.get("ok") is True else {}
    recommended = ""
    if load:
        best = min(entry["score"] for entry in load.values())
        # Prefer staying put on a tie: a switch drops the Wi-Fi for a few seconds.
        if current_channel in load and load[current_channel]["score"] == best:
            recommended = current_channel
        else:
            recommended = next(channel for channel, entry in load.items() if entry["score"] == best)
    return {
        "ok": scan.get("ok") is True,
        "message": str(scan.get("message", "")),
        "updated": str(scan.get("updated", "")),
        "total": len(networks),
        "channels": load,
        "recommended": recommended,
    }


def hotspot_state():
    status = read_hotspot_json("status.json")
    try:
        pending = (HOTSPOT_DIR / "request").read_text(encoding="utf-8").strip()[:4]
    except OSError:
        pending = ""
    channel = str(status.get("channel", ""))
    return {
        "available": HOTSPOT_DIR.is_dir(),
        "pending": pending,
        "channel": channel,
        "ok": status.get("ok") is True,
        "message": str(status.get("message", "")),
        "updated": str(status.get("updated", "")),
        "channels": HOTSPOT_CHANNELS,
        "scan": hotspot_scan(channel),
    }


def drop_hotspot_request(value):
    temp = HOTSPOT_DIR / ".request.tmp"
    temp.write_text(value, encoding="utf-8")
    temp.replace(HOTSPOT_DIR / "request")


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "service": "system-panel", "updated": now_label()})


@app.route("/api/summary")
def summary():
    status = build_status()
    return jsonify({
        "updated": status["updated"],
        "overall": status["overall"],
        "uptime": status["uptime"],
    })


@app.route("/api/status")
def api_status():
    return jsonify(build_status())


@app.route("/api/hotspot")
def api_hotspot():
    return jsonify(hotspot_state())


@app.route("/api/hotspot/channel", methods=["POST"])
def api_hotspot_channel():
    # JSON only: CORS allows GET alone, so other sites cannot trigger this.
    payload = request.get_json(silent=True) if request.is_json else None
    channel = str(payload.get("channel", "")) if isinstance(payload, dict) else ""
    if channel not in HOTSPOT_CHANNELS:
        return jsonify({"error": "Canale non valido: scegli 1, 6 o 11."}), 400
    if not HOTSPOT_DIR.is_dir():
        return jsonify({"error": "Cartella richieste hotspot non montata."}), 503
    drop_hotspot_request(channel)
    return jsonify(hotspot_state()), 202


@app.route("/api/hotspot/scan", methods=["POST"])
def api_hotspot_scan():
    if not request.is_json:
        return jsonify({"error": "Richiesta non valida."}), 400
    if not HOTSPOT_DIR.is_dir():
        return jsonify({"error": "Cartella richieste hotspot non montata."}), 503
    if (HOTSPOT_DIR / "request").exists():
        return jsonify({"error": "Il Raspberry sta gia' lavorando sull'hotspot, riprova tra poco."}), 409
    drop_hotspot_request("scan")
    return jsonify(hotspot_state()), 202


@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIWA System</title>
<style>
:root{color-scheme:dark;--bg:#0f0d0d;--panel:#211918;--panel2:#151112;--line:rgba(203,144,124,.28);--text:#fff7f0;--muted:#c8afa4;--soft:#eadbd4;--accent:#d59a84;--accent-strong:#f0b8a2;--ok:#22c55e;--warn:#facc15;--err:#ef4444}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:radial-gradient(circle at 18% -5%,rgba(213,154,132,.22),transparent 34%),radial-gradient(circle at 84% 8%,rgba(246,226,209,.08),transparent 28%),linear-gradient(180deg,#0e0c0c,#171211 46%,#0e0c0c);color:var(--text);padding:20px}
h1{margin:0 0 6px;font-size:32px;letter-spacing:0;color:#fff4ec}.subtitle{color:var(--muted);line-height:1.45}.topbar{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:18px}.brand-heading{display:flex;align-items:center;gap:12px;min-width:0}.brand-logo{width:52px;height:52px;border-radius:50%;border:1px solid rgba(213,154,132,.42);background:#f2dfcf;box-shadow:0 16px 34px rgba(0,0,0,.28);flex:0 0 auto}.brand-copy{min-width:0}.button{display:inline-flex;align-items:center;justify-content:center;background:rgba(64,45,42,.92);color:white;text-decoration:none;padding:10px 12px;border-radius:10px;border:1px solid var(--line);min-height:40px;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}.button:hover{background:rgba(87,61,56,.96);border-color:rgba(213,154,132,.42)}
.hero{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(260px,.75fr);gap:14px;align-items:stretch;margin-bottom:14px}.card{background:linear-gradient(180deg,rgba(42,31,29,.94),rgba(18,14,14,.96));border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:0 18px 34px rgba(0,0,0,.25)}.overall{display:grid;grid-template-columns:auto 1fr;gap:14px;align-items:center}.mark{width:76px;height:76px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:26px;border:1px solid rgba(255,255,255,.18);box-shadow:0 18px 34px rgba(0,0,0,.25)}.mark.ok{background:rgba(34,197,94,.16);color:#86efac;border-color:rgba(34,197,94,.42)}.mark.warning{background:rgba(250,204,21,.15);color:#fde68a;border-color:rgba(250,204,21,.45)}.mark.error{background:rgba(239,68,68,.16);color:#fecaca;border-color:rgba(239,68,68,.45)}.headline{font-size:30px;font-weight:bold;margin-bottom:4px}.muted{color:var(--muted);line-height:1.45}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.metric{background:rgba(21,17,18,.92);border:1px solid rgba(203,144,124,.20);border-radius:10px;padding:12px}.metric-value{font-size:24px;font-weight:bold}.metric-label{color:var(--muted);font-size:13px;margin-top:4px}
.section-head{display:flex;justify-content:space-between;gap:10px;align-items:center;margin:20px 0 10px}h2{margin:0;font-size:20px;color:#fff4ec}.updated{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.service-card{display:flex;flex-direction:column;gap:10px;min-height:150px}.service-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.service-name{font-weight:bold}.group{color:var(--muted);font-size:12px;margin-top:3px}.status-pill{border-radius:999px;padding:5px 9px;font-weight:bold;font-size:12px;border:1px solid rgba(255,255,255,.16);white-space:nowrap}.status-pill.ok{background:rgba(34,197,94,.14);color:#86efac;border-color:rgba(34,197,94,.36)}.status-pill.warning{background:rgba(250,204,21,.14);color:#fde68a;border-color:rgba(250,204,21,.38)}.status-pill.error{background:rgba(239,68,68,.14);color:#fecaca;border-color:rgba(239,68,68,.40)}.detail{color:#eadbd4;line-height:1.4;font-size:14px;flex:1}.service-link{color:#f0b8a2;text-decoration:none;font-size:13px}.service-link:hover{text-decoration:underline}.bar{height:12px;background:#151112;border:1px solid rgba(203,144,124,.18);border-radius:999px;overflow:hidden;margin-top:10px}.bar-fill{height:100%;background:linear-gradient(90deg,#d59a84,#f0b8a2);width:0}.ips{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.ip{background:rgba(64,45,42,.92);border:1px solid var(--line);border-radius:999px;padding:5px 8px;color:#ffe0d1;font-size:12px}.loading{color:var(--muted);padding:16px}.error-box{border-color:rgba(239,68,68,.42);color:#fecaca}
.hotspot-card{display:grid;gap:12px}.channel-buttons{display:flex;gap:8px;flex-wrap:wrap}.channel-button{cursor:pointer;font:inherit;min-width:110px}.channel-button.active{background:linear-gradient(180deg,#d59a84,#9f6f63);border-color:rgba(240,184,162,.45)}.channel-button:disabled{opacity:.55;cursor:default}.hotspot-current{font-weight:bold;font-size:18px}.scan-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}.scan-entry{background:rgba(21,17,18,.92);border:1px solid rgba(203,144,124,.20);border-radius:10px;padding:10px;font-size:14px;line-height:1.4}.scan-entry.best{border-color:rgba(34,197,94,.55)}.scan-entry strong{display:block}.scan-best{color:#86efac;font-size:12px;font-weight:bold}
@media(max-width:820px){body{padding:12px}.topbar{display:block}.brand-logo{width:44px;height:44px}.topbar .button{margin-top:10px}.hero{grid-template-columns:1fr}.overall{grid-template-columns:1fr}.mark{width:62px;height:62px}.headline{font-size:25px}.metrics{grid-template-columns:1fr}.section-head{display:block}.updated{margin-top:5px}.service-card{min-height:auto}}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand-heading">
    <img class="brand-logo" src="/static/niwa-logo.png" alt="">
    <div class="brand-copy">
      <h1>NIWA System</h1>
      <div class="subtitle">Stato rapido di servizi, rete e storage locale.</div>
    </div>
  </div>
  <a class="button" id="dashboardLink" href="/">Dashboard</a>
</div>

<section class="hero">
  <div class="card overall">
    <div class="mark" id="overallMark">...</div>
    <div>
      <div class="headline" id="overallLabel">Caricamento</div>
      <div class="muted" id="overallMessage">Controllo servizi in corso.</div>
    </div>
  </div>
  <div class="card">
    <div class="metrics">
      <div class="metric"><div class="metric-value" id="okCount">-</div><div class="metric-label">OK</div></div>
      <div class="metric"><div class="metric-value" id="warnCount">-</div><div class="metric-label">Avvisi</div></div>
      <div class="metric"><div class="metric-value" id="errCount">-</div><div class="metric-label">Errori</div></div>
    </div>
    <div class="muted" style="margin-top:12px">Uptime: <strong id="uptime">-</strong></div>
    <div class="ips" id="ipList"></div>
  </div>
</section>

<div class="section-head">
  <h2>Controlli principali</h2>
  <div class="updated" id="updated">-</div>
</div>
<div class="grid" id="checksGrid"><div class="card loading">Caricamento...</div></div>

<div class="section-head">
  <h2>Canale hotspot</h2>
  <div class="updated" id="hotspotUpdated">-</div>
</div>
<div class="card hotspot-card">
  <div class="hotspot-current" id="hotspotCurrent">Caricamento...</div>
  <div class="muted" id="hotspotMessage"></div>
  <div class="channel-buttons">
    <button class="button channel-button" data-channel="1" onclick="setHotspotChannel('1')">Canale 1</button>
    <button class="button channel-button" data-channel="6" onclick="setHotspotChannel('6')">Canale 6</button>
    <button class="button channel-button" data-channel="11" onclick="setHotspotChannel('11')">Canale 11</button>
  </div>
  <div><button class="button channel-button" id="scanButton" onclick="scanHotspot()">Cerca il canale piu libero</button></div>
  <div class="muted" id="scanMessage"></div>
  <div class="scan-list" id="scanList"></div>
  <div class="muted">La ricerca non spegne il Wi-Fi. Cambiare canale invece fa cadere NIWA-AP per qualche secondo: tablet ed ESP32 si ricollegano da soli.</div>
</div>

<div class="section-head">
  <h2>Servizi</h2>
  <div class="updated">Aggiornamento automatico ogni 15 secondi</div>
</div>
<div class="grid" id="servicesGrid"><div class="card loading">Caricamento...</div></div>

<script>
function serviceUrl(port, path=''){
  return `${window.location.protocol}//${window.location.hostname}:${port}${path}`;
}

document.getElementById('dashboardLink').href = serviceUrl(3000);

function statusText(status){
  if(status === 'ok') return 'OK';
  if(status === 'warning') return 'ATTENZIONE';
  return 'ERRORE';
}

function markText(status){
  if(status === 'ok') return 'OK';
  if(status === 'warning') return '!';
  return 'X';
}

function escapeHtml(value){
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;',
    '<':'&lt;',
    '>':'&gt;',
    '"':'&quot;',
    "'":'&#39;'
  }[char]));
}

function localizeHref(href){
  if(!href) return null;
  return href.replace('__HOST__', window.location.hostname);
}

function renderItem(entry){
  const href = localizeHref(entry.href);
  const storageBar = entry.id === 'storage_mount' && typeof entry.used_percent === 'number'
    ? `<div class="bar"><div class="bar-fill" style="width:${entry.used_percent}%"></div></div>`
    : '';
  const link = href ? `<a class="service-link" href="${escapeHtml(href)}">Apri</a>` : '';
  return `<div class="card service-card">
    <div class="service-head">
      <div>
        <div class="service-name">${escapeHtml(entry.name)}</div>
        <div class="group">${escapeHtml(entry.group)}</div>
      </div>
      <span class="status-pill ${entry.status}">${statusText(entry.status)}</span>
    </div>
    <div class="detail">${escapeHtml(entry.detail)}</div>
    ${storageBar}
    ${link}
  </div>`;
}

function sortItems(items){
  const weight = {error: 0, warning: 1, ok: 2};
  return [...items].sort((a, b) => (weight[a.status] - weight[b.status]) || a.name.localeCompare(b.name));
}

async function loadStatus(){
  const mark = document.getElementById('overallMark');
  const label = document.getElementById('overallLabel');
  const message = document.getElementById('overallMessage');
  const servicesGrid = document.getElementById('servicesGrid');
  const checksGrid = document.getElementById('checksGrid');

  try{
    const res = await fetch('/api/status', {cache:'no-store'});
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    mark.className = `mark ${data.overall.status}`;
    mark.textContent = markText(data.overall.status);
    label.textContent = data.overall.label;
    message.textContent = data.overall.message;
    document.getElementById('okCount').textContent = data.overall.ok;
    document.getElementById('warnCount').textContent = data.overall.warning;
    document.getElementById('errCount').textContent = data.overall.error;
    document.getElementById('uptime').textContent = data.uptime.label;
    document.getElementById('updated').textContent = `Aggiornato: ${data.updated}`;
    document.getElementById('ipList').innerHTML = data.ips.map(ip => `<span class="ip">${escapeHtml(ip)}</span>`).join('');
    checksGrid.innerHTML = sortItems(data.checks).map(renderItem).join('');
    servicesGrid.innerHTML = sortItems(data.services).map(renderItem).join('');
  }catch(error){
    mark.className = 'mark error';
    mark.textContent = 'X';
    label.textContent = 'System non disponibile';
    message.textContent = error.message;
    checksGrid.innerHTML = '<div class="card error-box">Impossibile aggiornare lo stato.</div>';
    servicesGrid.innerHTML = '';
  }
}

let HOTSPOT_BUSY = false;

function renderHotspot(data){
  const current = document.getElementById('hotspotCurrent');
  const message = document.getElementById('hotspotMessage');
  if(!data.available){
    current.textContent = 'Cambio canale non disponibile';
    message.textContent = 'La cartella condivisa con il Raspberry non e montata nel container.';
  }else if(data.pending && data.pending !== 'scan'){
    current.textContent = 'Cambio canale in corso...';
    message.textContent = 'Il Wi-Fi puo cadere per qualche secondo.';
  }else{
    current.textContent = data.channel ? `Canale attuale: ${data.channel}` : 'Canale non ancora letto';
    message.textContent = data.message || 'Nessun esito registrato: installa niwa-hotspot.path sul Raspberry.';
  }
  document.getElementById('hotspotUpdated').textContent = data.updated ? `Esito: ${data.updated}` : '-';
  document.querySelectorAll('.channel-button').forEach((button)=>{
    button.classList.toggle('active', !!button.dataset.channel && button.dataset.channel === data.channel);
    button.disabled = HOTSPOT_BUSY || !!data.pending || !data.available;
  });
  renderScan(data.scan, data.pending === 'scan');
}

function renderScan(scan, scanning){
  const message = document.getElementById('scanMessage');
  const list = document.getElementById('scanList');
  list.replaceChildren();
  if(scanning){
    message.textContent = 'Ricerca delle reti vicine in corso...';
    return;
  }
  if(!scan.updated){
    message.textContent = 'Nessuna ricerca fatta: premi il pulsante sul posto.';
    return;
  }
  if(!scan.ok){
    message.textContent = `${scan.message} (${scan.updated}). Usa un'app tipo WiFi Analyzer sul tablet.`;
    return;
  }
  message.textContent = `${scan.total} reti a 2,4 GHz trovate (${scan.updated}). Il consiglio pesa quante reti si sovrappongono e quanto sono forti.`;
  Object.entries(scan.channels).forEach(([channel, entry])=>{
    const box = document.createElement('div');
    box.className = 'scan-entry' + (channel === scan.recommended ? ' best' : '');
    const title = document.createElement('strong');
    title.textContent = `Canale ${channel}`;
    box.appendChild(title);
    if(channel === scan.recommended){
      const best = document.createElement('span');
      best.className = 'scan-best';
      best.textContent = 'CONSIGLIATO';
      box.appendChild(best);
    }
    const detail = document.createElement('div');
    detail.textContent = entry.networks
      ? `${entry.networks} ${entry.networks === 1 ? 'rete vicina' : 'reti vicine'}, la piu forte ${Math.round(entry.strongest)} dBm`
      : 'Nessuna rete vicina';
    box.appendChild(detail);
    list.appendChild(box);
  });
}

async function scanHotspot(){
  HOTSPOT_BUSY = true;
  let before = '';
  try{
    before = (await loadHotspot()).scan.updated;
    const res = await fetch('/api/hotspot/scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    const data = await res.json().catch(()=>({}));
    if(!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    renderHotspot(data);
    for(let attempt = 0; attempt < 20; attempt++){
      await new Promise((resolve)=>setTimeout(resolve, 2000));
      const next = await loadHotspot().catch(()=>null);
      if(next && !next.pending && next.scan.updated !== before) break;
    }
  }catch(error){
    alert('Ricerca non avviata: ' + error.message);
  }
  HOTSPOT_BUSY = false;
  loadHotspot().catch(()=>{});
}

async function loadHotspot(){
  const res = await fetch('/api/hotspot', {cache:'no-store'});
  if(!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  renderHotspot(data);
  return data;
}

async function setHotspotChannel(channel){
  if(!confirm(`Passare l'hotspot NIWA-AP al canale ${channel}?

Il Wi-Fi si spegne per qualche secondo; tablet ed ESP32 si ricollegano da soli e un trasferimento in corso riprende dopo.`)) return;
  HOTSPOT_BUSY = true;
  let before = '';
  try{
    before = (await loadHotspot()).updated;
    const res = await fetch('/api/hotspot/channel', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({channel})
    });
    const data = await res.json().catch(()=>({}));
    if(!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    renderHotspot(data);
  }catch(error){
    HOTSPOT_BUSY = false;
    alert('Cambio canale non richiesto: ' + error.message);
    loadHotspot().catch(()=>{});
    return;
  }
  // The tablet may lose Wi-Fi meanwhile: keep polling through failed requests.
  for(let attempt = 0; attempt < 45; attempt++){
    await new Promise((resolve)=>setTimeout(resolve, 2000));
    try{
      const data = await loadHotspot();
      if(!data.pending && data.updated !== before) break;
    }catch(error){}
  }
  HOTSPOT_BUSY = false;
  try{
    const data = await loadHotspot();
    if(data.pending || data.updated === before){
      document.getElementById('hotspotMessage').textContent = 'Nessuna risposta dal Raspberry: controlla che niwa-hotspot.path sia attivo.';
    }
  }catch(error){}
}

loadStatus();
loadHotspot().catch(()=>{});
setInterval(loadStatus, 15000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
