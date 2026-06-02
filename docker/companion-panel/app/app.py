from flask import Flask, Response, jsonify, request
from pathlib import Path
import copy
import json
import os
import threading
import time


app = Flask(__name__)

PORT = int(os.environ.get("NIWA_COMPANION_PORT", "5058"))
DATA_ROOT = Path(os.environ.get("NIWA_COMPANION_DATA_ROOT", "/data"))
STATE_FILE = DATA_ROOT / "companion_state.json"
EVENTS_FILE = DATA_ROOT / "companion_events.json"
STATE_LOCK = threading.Lock()
EVENT_LIMIT = 240
ONLINE_SECONDS = 35

EXPRESSIONS = [
    {"id": "idle", "label": "Idle", "group": "Base", "detail": "Occhi rilassati, battito e piccoli sguardi."},
    {"id": "happy", "label": "Happy", "group": "Base", "detail": "Occhi sorridenti con rimbalzo morbido."},
    {"id": "curious", "label": "Curious", "group": "Base", "detail": "Un occhio piu grande e sguardo laterale."},
    {"id": "excited", "label": "Excited", "group": "Base", "detail": "Occhi luminosi e movimento rapido."},
    {"id": "sleepy", "label": "Sleepy", "group": "Base", "detail": "Palpebre pesanti e ritmo lento."},
    {"id": "sleeping", "label": "Sleeping", "group": "Base", "detail": "Riposo con respiro e piccole Z."},
    {"id": "alert", "label": "Alert", "group": "Base", "detail": "Occhi larghi e concentrati."},
    {"id": "surprised", "label": "Surprised", "group": "Base", "detail": "Apertura improvvisa e tremolio."},
    {"id": "sad", "label": "Sad", "group": "Base", "detail": "Sguardo abbassato e movimento lento."},
    {"id": "annoyed", "label": "Annoyed", "group": "Base", "detail": "Occhi stretti e inclinati."},
    {"id": "love", "label": "Love", "group": "Base", "detail": "Cuori con pulsazione morbida."},
    {"id": "thinking", "label": "Thinking", "group": "Base", "detail": "Sguardo alto e puntini animati."},
    {"id": "photo_mode", "label": "Photo Mode", "group": "Speciali", "detail": "Mirino animato richiamato solo dal pannello."},
    {"id": "tracking", "label": "Tracking", "group": "Speciali", "detail": "Pupille in movimento, senza tracking reale."},
    {"id": "scanning", "label": "Scanning", "group": "Speciali", "detail": "Linea di scansione grafica, senza riconoscimento."},
    {"id": "offline", "label": "Offline", "group": "Speciali", "detail": "Occhi tratteggiati di avviso."},
    {"id": "blink", "label": "Blink", "group": "Azioni", "detail": "Battito di palpebre manuale."},
    {"id": "wink", "label": "Wink", "group": "Azioni", "detail": "Occhiolino manuale."},
    {"id": "wake_up", "label": "Wake Up", "group": "Azioni", "detail": "Apertura graduale degli occhi."},
    {"id": "fall_asleep", "label": "Fall Asleep", "group": "Azioni", "detail": "Passaggio graduale al riposo."},
    {"id": "photo_capture", "label": "Photo Capture", "group": "Azioni", "detail": "Flash grafico manuale, senza scattare foto."},
]
EXPRESSION_IDS = {entry["id"] for entry in EXPRESSIONS}
ACTION_RULES = {
    "blink": {"duration_ms": 1200},
    "wink": {"duration_ms": 1500},
    "wake_up": {"duration_ms": 2200, "resume": "idle"},
    "fall_asleep": {"duration_ms": 2600, "resume": "sleeping"},
    "photo_capture": {"duration_ms": 1300},
}


def now_ts():
    return time.time()


def now_label():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def default_state():
    return {
        "version": 1,
        "expression": "idle",
        "revision": 1,
        "updated": now_label(),
        "updated_ts": now_ts(),
        "source": "system",
        "active_device": "companion_01",
        "devices": {
            "companion_01": {
                "id": "companion_01",
                "name": "NIWA Companion 01",
                "paired": True,
                "last_seen": None,
                "ip": None,
                "rssi": None,
                "battery_percent": None,
                "firmware": None,
                "oled": None,
                "message": "In attesa del primo heartbeat ESP32-CAM.",
            }
        },
    }


def atomic_json_write(path, data):
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    temp_path.replace(path)


def load_state():
    if not STATE_FILE.exists():
        state = default_state()
        atomic_json_write(STATE_FILE, state)
        return state

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except Exception:
        state = default_state()
        atomic_json_write(STATE_FILE, state)
        return state

    state.setdefault("version", 1)
    state.setdefault("expression", "idle")
    state.setdefault("revision", 1)
    state.setdefault("updated", now_label())
    state.setdefault("updated_ts", now_ts())
    state.setdefault("source", "system")
    state.setdefault("active_device", "companion_01")
    state.setdefault("devices", {})
    if "companion_01" not in state["devices"]:
        state["devices"]["companion_01"] = default_state()["devices"]["companion_01"]
    settle_expired_action(state)
    return state


def save_state(state):
    atomic_json_write(STATE_FILE, state)


def settle_expired_action(state):
    expires_ts = state.get("action_expires_ts")
    if not expires_ts or now_ts() < float(expires_ts):
        return False

    state["expression"] = state.get("resume_expression") or "idle"
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated"] = now_label()
    state["updated_ts"] = now_ts()
    state["source"] = "action-timeout"
    state.pop("action_expires_ts", None)
    state.pop("resume_expression", None)
    save_state(state)
    return True


def schedule_action_settlement(duration_ms):
    def settle_later():
        time.sleep(duration_ms / 1000)
        with STATE_LOCK:
            load_state()

    threading.Thread(target=settle_later, daemon=True).start()


def append_event(event_type, message, **extra):
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as handle:
            events = json.load(handle)
    except Exception:
        events = []

    events.append({
        "type": event_type,
        "message": message,
        "timestamp": now_label(),
        "timestamp_ts": now_ts(),
        **extra,
    })
    events = events[-EVENT_LIMIT:]
    atomic_json_write(EVENTS_FILE, events)
    return events[-1]


def public_device(device):
    result = copy.deepcopy(device)
    last_seen = result.get("last_seen")
    result["online"] = bool(last_seen and now_ts() - float(last_seen) <= ONLINE_SECONDS)
    result["last_seen_label"] = result.get("last_seen_label")
    return result


def public_state(state=None):
    if state is None:
        state = load_state()
    result = copy.deepcopy(state)
    result["devices"] = {
        device_id: public_device(device)
        for device_id, device in state.get("devices", {}).items()
    }
    return result


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "service": "companion-panel", "version": "0.1.0"})


@app.route("/api/status")
def api_status():
    with STATE_LOCK:
        state = public_state()
    return jsonify({"ok": True, "state": state, "expressions": EXPRESSIONS})


@app.route("/api/expressions")
def api_expressions():
    return jsonify({"items": EXPRESSIONS})


@app.route("/api/expression", methods=["GET", "POST"])
def api_expression():
    if request.method == "GET":
        with STATE_LOCK:
            state = load_state()
        return jsonify({
            "expression": state["expression"],
            "revision": state["revision"],
            "updated": state["updated"],
            "source": state["source"],
        })

    payload = request.get_json(silent=True) or {}
    expression = str(payload.get("expression", "")).strip()
    if expression not in EXPRESSION_IDS:
        return jsonify({"error": "Espressione non valida."}), 400

    with STATE_LOCK:
        state = load_state()
        previous_expression = state.get("expression", "idle")
        previous_resume = state.get("resume_expression")
        state["expression"] = expression
        state["revision"] = int(state.get("revision", 0)) + 1
        state["updated"] = now_label()
        state["updated_ts"] = now_ts()
        state["source"] = str(payload.get("source", "dashboard"))[:60]
        action_rule = ACTION_RULES.get(expression)
        if action_rule:
            state["resume_expression"] = (
                action_rule.get("resume")
                or previous_resume
                or previous_expression
                or "idle"
            )
            state["action_expires_ts"] = now_ts() + action_rule["duration_ms"] / 1000
        else:
            state.pop("resume_expression", None)
            state.pop("action_expires_ts", None)
        save_state(state)
        event = append_event("expression", f"Espressione impostata: {expression}", expression=expression)

    if action_rule:
        schedule_action_settlement(action_rule["duration_ms"])

    return jsonify({"ok": True, "state": public_state(state), "event": event})


@app.route("/api/devices/register", methods=["POST"])
def api_register_device():
    payload = request.get_json(silent=True) or {}
    device_id = str(payload.get("id", "")).strip()
    if not device_id or not all(character.isalnum() or character in "_-" for character in device_id):
        return jsonify({"error": "ID dispositivo non valido."}), 400

    with STATE_LOCK:
        state = load_state()
        device = state["devices"].setdefault(device_id, {
            "id": device_id,
            "name": str(payload.get("name") or device_id)[:80],
            "paired": False,
            "last_seen": None,
            "message": "Registrato, pairing futuro non ancora attivo.",
        })
        device["name"] = str(payload.get("name") or device.get("name") or device_id)[:80]
        save_state(state)
        append_event("device", f"Dispositivo registrato: {device_id}", device_id=device_id)

    return jsonify({"ok": True, "device": public_device(device)})


@app.route("/api/devices/<device_id>/heartbeat", methods=["POST"])
def api_device_heartbeat(device_id):
    payload = request.get_json(silent=True) or {}
    with STATE_LOCK:
        state = load_state()
        device = state["devices"].setdefault(device_id, {
            "id": device_id,
            "name": str(payload.get("name") or device_id)[:80],
            "paired": False,
        })
        was_online = public_device(device).get("online", False)
        device.update({
            "name": str(payload.get("name") or device.get("name") or device_id)[:80],
            "last_seen": now_ts(),
            "last_seen_label": now_label(),
            "ip": payload.get("ip"),
            "rssi": payload.get("rssi"),
            "battery_percent": payload.get("battery_percent"),
            "firmware": payload.get("firmware"),
            "oled": payload.get("oled"),
            "message": str(payload.get("message") or "Heartbeat ricevuto.")[:160],
        })
        save_state(state)
        if not was_online:
            append_event("device", f"{device_id} online", device_id=device_id)

    return jsonify({"ok": True, "expression": state["expression"], "revision": state["revision"]})


@app.route("/api/devices/<device_id>/expression")
def api_device_expression(device_id):
    with STATE_LOCK:
        state = load_state()
    return jsonify({
        "ok": True,
        "device_id": device_id,
        "expression": state["expression"],
        "revision": state["revision"],
        "poll_after_ms": 900,
    })


@app.route("/api/events")
def api_events():
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as handle:
            events = json.load(handle)
    except Exception:
        events = []
    return jsonify({"items": list(reversed(events[-80:]))})


@app.route("/api/stream")
def api_stream():
    def generate():
        previous_revision = None
        while True:
            with STATE_LOCK:
                state = public_state()
            revision = state.get("revision")
            if revision != previous_revision:
                yield f"event: state\ndata: {json.dumps(state)}\n\n"
                previous_revision = revision
            else:
                yield ": keep-alive\n\n"
            time.sleep(0.35)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIWA Companion</title>
<style>
:root{color-scheme:dark;--bg:#0f0d0d;--panel:#211918;--panel2:#151112;--line:rgba(203,144,124,.28);--text:#fff7f0;--muted:#c8afa4;--soft:#eadbd4;--accent:#d59a84;--accent-strong:#f0b8a2;--ok:#22c55e;--warn:#facc15}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 18% -5%,rgba(213,154,132,.22),transparent 34%),radial-gradient(circle at 84% 8%,rgba(246,226,209,.08),transparent 28%),linear-gradient(180deg,#0e0c0c,#171211 46%,#0e0c0c);color:var(--text);font-family:Arial,sans-serif;padding:20px}
h1,h2,h3,p{margin-top:0}h1{font-size:32px;margin-bottom:6px;letter-spacing:0;color:#fff4ec}h2{font-size:18px;margin-bottom:12px}h3{font-size:15px;margin-bottom:8px}
.topbar{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:18px}.brand-heading{display:flex;align-items:center;gap:12px}.brand-logo{width:52px;height:52px;border-radius:50%;border:1px solid rgba(213,154,132,.42);background:#f2dfcf;box-shadow:0 16px 34px rgba(0,0,0,.28)}.subtitle,.muted{color:var(--muted);line-height:1.45}.button{display:inline-flex;align-items:center;justify-content:center;background:rgba(64,45,42,.92);color:#fff;text-decoration:none;border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-height:40px;cursor:pointer}.button:hover{background:rgba(87,61,56,.96);border-color:rgba(213,154,132,.46)}
.layout{display:grid;grid-template-columns:minmax(320px,.95fr) minmax(420px,1.4fr);gap:14px;align-items:start}.card{background:linear-gradient(180deg,rgba(42,31,29,.94),rgba(18,14,14,.96));border:1px solid var(--line);border-radius:8px;padding:16px;box-shadow:0 18px 34px rgba(0,0,0,.25)}.stack{display:grid;gap:14px}.face-stage{display:grid;place-items:center;background:#050404;border:1px solid rgba(213,154,132,.24);border-radius:8px;overflow:hidden;aspect-ratio:2/1}.face-stage canvas{width:100%;height:100%;display:block}.face-meta{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-top:12px}.expression-label{font-size:22px;font-weight:bold;color:#fff4ec}.pill{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;padding:5px 8px;font-size:12px;color:#ffe0d1;background:rgba(64,45,42,.72)}.pill.online{color:#86efac;border-color:rgba(34,197,94,.36);background:rgba(34,197,94,.12)}.pill.offline{color:#fde68a;border-color:rgba(250,204,21,.36);background:rgba(250,204,21,.10)}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.metric{background:rgba(21,17,18,.92);border:1px solid rgba(203,144,124,.20);border-radius:8px;padding:10px}.metric-value{font-weight:bold;font-size:16px;color:#fff4ec}.metric-label{font-size:11px;color:var(--muted);margin-top:4px}.camera-placeholder{aspect-ratio:16/9;display:grid;place-items:center;background:#080707;border:1px dashed rgba(213,154,132,.30);border-radius:8px;color:var(--muted);text-align:center;padding:14px}
.group{margin-top:16px}.group:first-child{margin-top:0}.group-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;color:#f0b8a2;font-weight:bold}.expression-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:8px}.expression{min-height:64px;text-align:left;background:rgba(21,17,18,.92);color:#ffe0d1;border:1px solid rgba(203,144,124,.20);border-radius:8px;padding:9px;cursor:pointer}.expression:hover{background:#2b1e1b;border-color:rgba(213,154,132,.46)}.expression.active{background:linear-gradient(180deg,rgba(213,154,132,.34),rgba(64,45,42,.92));border-color:var(--accent-strong);box-shadow:0 0 0 1px rgba(240,184,162,.18)}.expression strong{display:block;font-size:14px}.expression span{display:block;color:var(--muted);font-size:11px;line-height:1.3;margin-top:4px}.events{display:grid;gap:8px;max-height:260px;overflow:auto}.event{border-left:2px solid var(--accent);padding:7px 9px;background:rgba(21,17,18,.72);font-size:13px}.event small{display:block;color:var(--muted);margin-top:3px}
@media(max-width:920px){.layout{grid-template-columns:1fr}}@media(max-width:620px){body{padding:12px}.topbar{display:block}.brand-logo{width:44px;height:44px}.topbar .button{margin-top:10px}.metrics{grid-template-columns:1fr}.expression-grid{grid-template-columns:repeat(2,minmax(0,1fr))}h1{font-size:27px}}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand-heading">
    <img class="brand-logo" src="/static/niwa-logo.png" alt="">
    <div>
      <h1>NIWA Companion</h1>
      <div class="subtitle">Volto espressivo locale e controllo manuale del primo pet robot NIWA.</div>
    </div>
  </div>
  <a class="button" id="dashboardLink" href="/">Dashboard</a>
</div>
<div class="layout">
  <div class="stack">
    <section class="card">
      <h2>Anteprima volto</h2>
      <div class="face-stage"><canvas id="faceCanvas" width="512" height="256"></canvas></div>
      <div class="face-meta">
        <div><div class="expression-label" id="currentExpression">Idle</div><div class="muted" id="currentDetail">Pronto.</div></div>
        <span class="pill offline" id="devicePill">ESP32 offline</span>
      </div>
    </section>
    <section class="card">
      <h2>Companion 01</h2>
      <div class="metrics">
        <div class="metric"><div class="metric-value" id="wifiState">Offline</div><div class="metric-label">Wi-Fi</div></div>
        <div class="metric"><div class="metric-value" id="batteryState">-</div><div class="metric-label">Batteria futura</div></div>
        <div class="metric"><div class="metric-value" id="firmwareState">-</div><div class="metric-label">Firmware</div></div>
      </div>
    </section>
    <section class="card">
      <h2>Camera</h2>
      <div class="camera-placeholder">Anteprima camera non attiva<br><span class="muted">Il modulo volto resta indipendente dalla camera.</span></div>
    </section>
    <section class="card">
      <h2>Eventi</h2>
      <div class="events" id="events"><div class="muted">Nessun evento.</div></div>
    </section>
  </div>
  <section class="card">
    <h2>Espressioni</h2>
    <div class="muted">Photo Mode, Tracking e Scanning sono animazioni manuali. Non usano ancora la camera.</div>
    <div id="expressionGroups"></div>
  </section>
</div>
<script>
const canvas=document.getElementById('faceCanvas');const ctx=canvas.getContext('2d');let expressions=[];let current='idle';let next='idle';let openness=1;let transitionPhase='idle';let lastTime=performance.now();
document.getElementById('dashboardLink').href=`${location.protocol}//${location.hostname}:3000`;
function labelFor(id){return(expressions.find(x=>x.id===id)||{label:id,detail:''})}
function line(x1,y1,x2,y2,w=8){ctx.lineWidth=w;ctx.lineCap='round';ctx.strokeStyle='#fff7f0';ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke()}
function rect(x,y,w,h,fill=false){ctx.strokeStyle='#fff7f0';ctx.fillStyle='#fff7f0';ctx.lineWidth=7;fill?ctx.fillRect(x,y,w,h):ctx.strokeRect(x,y,w,h)}
function circle(x,y,r,fill=false,color='#fff7f0'){ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=7;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);fill?ctx.fill():ctx.stroke()}
function arc(x,y,r,a,b,w=8){ctx.strokeStyle='#fff7f0';ctx.lineWidth=w;ctx.lineCap='round';ctx.beginPath();ctx.arc(x,y,r,a,b);ctx.stroke()}
function heart(x,y,s){ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.moveTo(x,y+s);ctx.bezierCurveTo(x-s*1.4,y,x-s*.8,y-s,x,y-s*.25);ctx.bezierCurveTo(x+s*.8,y-s,x+s*1.4,y,x,y+s);ctx.fill()}
function eye(x,y,w,h,pupil=true){ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.roundRect(x-w/2,y-h/2,w,h,Math.min(18,h/2));ctx.fill();if(pupil){circle(x,y,Math.max(5,Math.min(w,h)*.22),true,'#080707')}}
function drawFace(id,t,open=1){ctx.clearRect(0,0,512,256);ctx.fillStyle='#050404';ctx.fillRect(0,0,512,256);const bob=Math.sin(t*2.6)*4;const lx=166,rx=346,y=126+bob;const blink=(Math.sin(t*.72)>0.985)?0.08:open;const h=72*Math.max(.06,blink);
 if(id==='happy'){arc(lx,y+12,45,Math.PI,Math.PI*2);arc(rx,y+12,45,Math.PI,Math.PI*2)}
 else if(id==='curious'){eye(lx,y,88,88*blink);eye(rx,y+8,55,55*blink)}
 else if(id==='excited'){eye(lx,y,92,h);eye(rx,y,92,h);line(72,52,92,72,5);line(92,52,72,72,5);line(420,52,440,72,5);line(440,52,420,72,5)}
 else if(id==='sleepy'){rect(lx-45,y-5,90,18,true);rect(rx-45,y-5,90,18,true)}
 else if(id==='sleeping'||id==='fall_asleep'){line(lx-42,y,lx+42,y+8);line(rx-42,y+8,rx+42,y);ctx.font='bold 42px Arial';ctx.fillStyle='#fff7f0';ctx.fillText('Z',390,70);ctx.font='bold 26px Arial';ctx.fillText('Z',430,38)}
 else if(id==='alert'){rect(lx-42,y-44,84,88);rect(rx-42,y-44,84,88);circle(lx,y,11,true);circle(rx,y,11,true)}
 else if(id==='surprised'){circle(lx,y,52);circle(rx,y,52);circle(lx,y,13,true);circle(rx,y,13,true)}
 else if(id==='sad'){line(lx-46,y-30,lx+44,y-2);line(rx-44,y-2,rx+46,y-30);circle(lx,y+18,12,true);circle(rx,y+18,12,true)}
 else if(id==='annoyed'){line(lx-48,y-26,lx+46,y+3);line(rx-46,y+3,rx+48,y-26);rect(lx-42,y+10,84,17,true);rect(rx-42,y+10,84,17,true)}
 else if(id==='love'){const pulse=1+Math.sin(t*4)*.12;heart(lx,y,45*pulse);heart(rx,y,45*pulse)}
 else if(id==='thinking'){eye(lx,y,88,h);eye(rx,y,88,h);circle(lx+18,y-18,9,true);circle(rx+18,y-18,9,true);circle(410,65,7,true);circle(438,48,10,true);circle(470,32,13,true)}
 else if(id==='photo_mode'||id==='photo_capture'){rect(lx-50,y-50,100,100);rect(rx-50,y-50,100,100);line(lx-22,y,lx+22,y,4);line(lx,y-22,lx,y+22,4);line(rx-22,y,rx+22,y,4);line(rx,y-22,rx,y+22,4);if(id==='photo_capture'&&Math.sin(t*8)>0){ctx.fillStyle='rgba(255,247,240,.65)';ctx.fillRect(0,0,512,256)}}
 else if(id==='tracking'){const dx=Math.sin(t*2.2)*24,dy=Math.cos(t*1.7)*14;eye(lx,y,92,h,false);eye(rx,y,92,h,false);circle(lx+dx,y+dy,14,true,'#080707');circle(rx+dx,y+dy,14,true,'#080707')}
 else if(id==='scanning'){eye(lx,y,92,h,false);eye(rx,y,92,h,false);ctx.fillStyle='rgba(240,184,162,.74)';ctx.fillRect(0,(t*95)%256,512,5)}
 else if(id==='offline'){line(lx-36,y-30,lx+36,y+30);line(lx+36,y-30,lx-36,y+30);line(rx-36,y-30,rx+36,y+30);line(rx+36,y-30,rx-36,y+30)}
 else if(id==='wink'){eye(lx,y,92,h);line(rx-43,y,rx+43,y)}
 else if(id==='blink'){line(lx-43,y,lx+43,y);line(rx-43,y,rx+43,y)}
 else if(id==='wake_up'){eye(lx,y,92,72*Math.min(1,(Math.sin(t*1.4)+1)/2));eye(rx,y,92,72*Math.min(1,(Math.sin(t*1.4)+1)/2))}
 else{eye(lx,y,92,h);eye(rx,y,92,h)}
}
function animate(now){const dt=Math.min(.08,(now-lastTime)/1000);lastTime=now;if(transitionPhase==='closing'){openness=Math.max(0,openness-dt*6);if(openness===0){current=next;transitionPhase='opening'}}else if(transitionPhase==='opening'){openness=Math.min(1,openness+dt*6);if(openness===1)transitionPhase='idle'}drawFace(current,now/1000,openness);requestAnimationFrame(animate)}
function setPreview(id){if(id!==next){next=id;transitionPhase='closing'}const item=labelFor(id);document.getElementById('currentExpression').textContent=item.label;document.getElementById('currentDetail').textContent=item.detail;document.querySelectorAll('.expression').forEach(b=>b.classList.toggle('active',b.dataset.id===id))}
async function sendExpression(id){const r=await fetch('/api/expression',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expression:id,source:'dashboard'})});if(!r.ok)throw new Error('Cambio espressione non riuscito');setPreview(id);loadEvents()}
function renderButtons(){const groups={};expressions.forEach(e=>(groups[e.group]??=[]).push(e));document.getElementById('expressionGroups').innerHTML=Object.entries(groups).map(([group,items])=>`<div class="group"><div class="group-title">${group}<span class="pill">${items.length}</span></div><div class="expression-grid">${items.map(e=>`<button class="expression" data-id="${e.id}" onclick="sendExpression('${e.id}')"><strong>${e.label}</strong><span>${e.detail}</span></button>`).join('')}</div></div>`).join('')}
async function loadStatus(){const data=await(await fetch('/api/status',{cache:'no-store'})).json();expressions=data.expressions;renderButtons();setPreview(data.state.expression);const d=data.state.devices.companion_01||{};const p=document.getElementById('devicePill');p.className=`pill ${d.online?'online':'offline'}`;p.textContent=d.online?'ESP32 online':'ESP32 offline';document.getElementById('wifiState').textContent=d.online?(d.rssi?`${d.rssi} dBm`:'Online'):'Offline';document.getElementById('batteryState').textContent=d.battery_percent??'-';document.getElementById('firmwareState').textContent=d.firmware??'-'}
async function loadEvents(){const data=await(await fetch('/api/events',{cache:'no-store'})).json();document.getElementById('events').innerHTML=data.items.length?data.items.slice(0,14).map(e=>`<div class="event">${e.message}<small>${e.timestamp}</small></div>`).join(''):'<div class="muted">Nessun evento.</div>'}
new EventSource('/api/stream').addEventListener('state',event=>{const state=JSON.parse(event.data);setPreview(state.expression);loadStatus()});loadStatus();loadEvents();setInterval(loadStatus,4000);setInterval(loadEvents,10000);requestAnimationFrame(animate);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
