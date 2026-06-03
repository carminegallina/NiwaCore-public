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
    {"id": "idle", "label": "Idle", "group": "Emozioni", "detail": "Occhi morbidi, battito naturale e piccoli sguardi."},
    {"id": "serene", "label": "Serene", "group": "Emozioni", "detail": "Occhi morbidi a cupola e sguardo calmo."},
    {"id": "happy", "label": "Happy", "group": "Emozioni", "detail": "Occhi sorridenti e bocca tenera."},
    {"id": "joyful", "label": "Joyful", "group": "Emozioni", "detail": "Occhi stretti e bocca triangolare aperta."},
    {"id": "laughing", "label": "Laughing", "group": "Emozioni", "detail": "Occhi stretti e grande sorriso segmentato."},
    {"id": "cheerful", "label": "Cheerful", "group": "Emozioni", "detail": "Occhi ad arco e sorriso aperto."},
    {"id": "curious", "label": "Curious", "group": "Emozioni", "detail": "Occhi base attenti, sopracciglio curioso e bocca piccola."},
    {"id": "excited", "label": "Excited", "group": "Emozioni", "detail": "Occhi base grandi, bocca aperta e scintille animate."},
    {"id": "wonder", "label": "Wonder", "group": "Emozioni", "detail": "Occhi bitmap dalla reference, copiati senza specchio."},
    {"id": "surprised", "label": "Surprised", "group": "Emozioni", "detail": "Occhi tondi più grandi e piccola bocca aperta."},
    {"id": "shocked", "label": "Shocked", "group": "Emozioni", "detail": "Occhietti piccoli e bocca trapezoidale."},
    {"id": "confused", "label": "Confused", "group": "Emozioni", "detail": "Occhi base asimmetrici, sopracciglia contrarie e bocca perplessa."},
    {"id": "smug", "label": "Smug", "group": "Emozioni", "detail": "Occhi a mezzaluna pieni e bocca furbetta."},
    {"id": "sad", "label": "Sad", "group": "Emozioni", "detail": "Occhi morbidi abbassati dalla reference."},
    {"id": "crying", "label": "Crying", "group": "Emozioni", "detail": "Occhi tristi schiacciati con lacrima dalla reference."},
    {"id": "sobbing", "label": "Sobbing", "group": "Emozioni", "detail": "Occhi chiusi, bocca separata e lacrime animate dalla reference."},
    {"id": "annoyed", "label": "Annoyed", "group": "Emozioni", "detail": "Occhi stretti, sopracciglia tese e bocca rigida."},
    {"id": "angry", "label": "Angry", "group": "Emozioni", "detail": "Occhi inclinati ciano, senza bocca, ispirati alla reference."},
    {"id": "love", "label": "Love", "group": "Emozioni", "detail": "Cuori rosa e bocca morbida dalla reference."},
    {"id": "thinking", "label": "Thinking", "group": "Emozioni", "detail": "Occhi base concentrati, bocca hmm e bolle di pensiero."},
    {"id": "sleepy", "label": "Sleepy", "group": "Riposo", "detail": "Occhi pesanti, morbidi e bocca stanca senza Z."},
    {"id": "sleeping", "label": "Sleeping", "group": "Riposo", "detail": "Occhi chiusi, respiro e piccole Z."},
    {"id": "alert", "label": "Alert", "group": "Riposo", "detail": "Occhi aperti e segnale di attenzione in alto a destra."},
    {"id": "photo_mode", "label": "Photo Mode", "group": "Speciali", "detail": "Faccina normale con fotocamera stilizzata davanti."},
    {"id": "eating", "label": "Eating", "group": "Speciali", "detail": "Faccina idle con hamburger davanti."},
    {"id": "drinking", "label": "Drinking", "group": "Speciali", "detail": "Faccina idle con bicchiere e cannuccia."},
    {"id": "tracking", "label": "Tracking", "group": "Speciali", "detail": "Solo occhi concentrati in movimento, senza tracking reale."},
    {"id": "scanning", "label": "Scanning", "group": "Speciali", "detail": "Occhi concentrati con linea di scansione morbida."},
    {"id": "offline", "label": "Offline", "group": "Speciali", "detail": "Occhi tratteggiati di avviso."},
    {"id": "blink", "label": "Blink", "group": "Azioni", "detail": "Battito di palpebre manuale."},
    {"id": "wink", "label": "Wink", "group": "Azioni", "detail": "Occhiolino manuale."},
    {"id": "wake_up", "label": "Wake Up", "group": "Azioni", "detail": "Risveglio da fessura centrale curva verso occhi base completi."},
    {"id": "fall_asleep", "label": "Fall Asleep", "group": "Azioni", "detail": "Passaggio graduale al riposo."},
    {"id": "photo_capture", "label": "Photo Capture", "group": "Azioni", "detail": "Faccina con fotocamera e flash grafico manuale."},
]
EXPRESSION_IDS = {entry["id"] for entry in EXPRESSIONS}
ACTION_RULES = {
    "blink": {"duration_ms": 1200},
    "wink": {"duration_ms": 1500},
    "wake_up": {"duration_ms": 3200, "resume": "idle"},
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
    return jsonify({"ok": True, "service": "companion-panel", "version": "0.4.59-preview"})


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
const canvas=document.getElementById('faceCanvas');const ctx=canvas.getContext('2d');let expressions=[];let current='idle';let next='idle';let openness=1;let transitionPhase='idle';let lastTime=performance.now();let expressionStartedAt=performance.now()/1000;
document.getElementById('dashboardLink').href=`${location.protocol}//${location.hostname}:3000`;
function labelFor(id){return(expressions.find(x=>x.id===id)||{label:id,detail:''})}
function line(x1,y1,x2,y2,w=8){ctx.lineWidth=w;ctx.lineCap='round';ctx.strokeStyle='#fff7f0';ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke()}
function rect(x,y,w,h,fill=false){ctx.strokeStyle='#fff7f0';ctx.fillStyle='#fff7f0';ctx.lineWidth=7;fill?ctx.fillRect(x,y,w,h):ctx.strokeRect(x,y,w,h)}
function roundedRect(x,y,w,h,r=12,fill=false){const rr=Math.min(r,w/2,h/2);ctx.strokeStyle='#fff7f0';ctx.fillStyle='#fff7f0';ctx.lineWidth=7;ctx.beginPath();ctx.moveTo(x+rr,y);ctx.lineTo(x+w-rr,y);ctx.quadraticCurveTo(x+w,y,x+w,y+rr);ctx.lineTo(x+w,y+h-rr);ctx.quadraticCurveTo(x+w,y+h,x+w-rr,y+h);ctx.lineTo(x+rr,y+h);ctx.quadraticCurveTo(x,y+h,x,y+h-rr);ctx.lineTo(x,y+rr);ctx.quadraticCurveTo(x,y,x+rr,y);fill?ctx.fill():ctx.stroke()}
function circle(x,y,r,fill=false,color='#fff7f0'){ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=7;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);fill?ctx.fill():ctx.stroke()}
function oval(x,y,rx,ry,fill=true,color='#fff7f0'){ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=7;ctx.beginPath();ctx.ellipse(x,y,rx,Math.max(2,ry),0,0,Math.PI*2);fill?ctx.fill():ctx.stroke()}
const BASE_EYE_OUTLINE=[[-11,-50],[1,-51],[13,-50],[25,-47],[35,-42],[43,-35],[49,-27],[53,-17],[56,-6],[57,6],[56,18],[52,29],[46,38],[37,45],[26,50],[14,53],[1,54],[-12,53],[-24,50],[-34,45],[-43,38],[-49,29],[-53,19],[-55,8],[-55,-4],[-53,-15],[-49,-26],[-43,-35],[-34,-42],[-23,-47]];
function smoothClosedShape(points){ctx.beginPath();ctx.moveTo(points[0][0],points[0][1]);for(let i=0;i<points.length;i++){const p0=points[(i-1+points.length)%points.length],p1=points[i],p2=points[(i+1)%points.length],p3=points[(i+2)%points.length];ctx.bezierCurveTo(p1[0]+(p2[0]-p0[0])/6,p1[1]+(p2[1]-p0[1])/6,p2[0]-(p3[0]-p1[0])/6,p2[1]-(p3[1]-p1[1])/6,p2[0],p2[1])}ctx.closePath()}
const baseEyeSource=new Image();let baseEyeVectorOutline=null;
function traceBaseEyeOutline(image){const scratch=document.createElement('canvas');scratch.width=image.width;scratch.height=image.height;const source=scratch.getContext('2d');source.drawImage(image,0,0);const pixels=source.getImageData(0,0,scratch.width,scratch.height).data,cx=85,cy=82,samples=96,maxRadius=100,radii=[];for(let index=0;index<samples;index++){const angle=Math.PI*2*index/samples,cos=Math.cos(angle),sin=Math.sin(angle);let edge=0;for(let radius=0;radius<=maxRadius;radius+=.5){const px=Math.round(cx+cos*radius),py=Math.round(cy+sin*radius);if(px<0||px>=scratch.width||py<0||py>=scratch.height)break;if(pixels[(py*scratch.width+px)*4+3]>=96)edge=radius}radii.push(edge)}let smooth=radii;for(let pass=0;pass<3;pass++){smooth=smooth.map((_,index)=>(smooth[(index-3+samples)%samples]+2*smooth[(index-2+samples)%samples]+3*smooth[(index-1+samples)%samples]+4*smooth[index]+3*smooth[(index+1)%samples]+2*smooth[(index+2)%samples]+smooth[(index+3)%samples])/16)}return smooth.map((radius,index)=>{const angle=Math.PI*2*index/samples;return[Math.cos(angle)*radius,Math.sin(angle)*radius]})}
baseEyeSource.onload=()=>{baseEyeVectorOutline=traceBaseEyeOutline(baseEyeSource)};baseEyeSource.src='/static/companion-base-eye.png';
function baseEye(x,y,mirror=false,open=1,size=1){ctx.save();ctx.translate(x,y);ctx.scale((mirror?-1:1)*112/139*size,Math.max(.08,open)*123/153*size);ctx.fillStyle='#fff7f0';smoothClosedShape(baseEyeVectorOutline||BASE_EYE_OUTLINE);ctx.fill();ctx.restore()}
function baseEyeReveal(x,y,mirror=false,phase=1,size=1){const reveal=clamp01(phase),top=-4-reveal*51,bottom=4+reveal*51;ctx.save();ctx.translate(x,y);ctx.scale((mirror?-1:1)*112/139*size,123/153*size);ctx.save();ctx.beginPath();ctx.moveTo(-56,3);ctx.bezierCurveTo(-38,top,-16,top-4,0,top-2);ctx.bezierCurveTo(17,top,39,top,57,3);ctx.bezierCurveTo(41,bottom,17,bottom+4,0,bottom+2);ctx.bezierCurveTo(-17,bottom,-40,bottom,-56,3);ctx.closePath();ctx.clip();ctx.fillStyle='#fff7f0';smoothClosedShape(baseEyeVectorOutline||BASE_EYE_OUTLINE);ctx.fill();ctx.restore();if(reveal<.18){ctx.globalAlpha=1-reveal/.18;ctx.strokeStyle='#fff7f0';ctx.lineWidth=8;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-50,3);ctx.bezierCurveTo(-24,-7,24,-7,50,3);ctx.stroke()}ctx.restore()}
function curve(x1,y1,cx,cy,x2,y2,w=8){ctx.lineWidth=w;ctx.lineCap='round';ctx.strokeStyle='#fff7f0';ctx.beginPath();ctx.moveTo(x1,y1);ctx.quadraticCurveTo(cx,cy,x2,y2);ctx.stroke()}
function heart(x,y,s,color='#fff7f0'){ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x,y+s);ctx.bezierCurveTo(x-s*1.4,y,x-s*.8,y-s,x,y-s*.25);ctx.bezierCurveTo(x+s*.8,y-s,x+s*1.4,y,x,y+s);ctx.fill()}
function eye(x,y,rx,ry,dx=0,dy=0,pupil=false){oval(x,y,rx,ry);if(pupil&&ry>8)circle(x+dx,y+dy,Math.max(5,Math.min(rx,ry)*.3),true,'#080707')}
const SERENE_EYE_FALLBACK=[[-3,-10],[4,-9],[9,-7],[13,-4],[15,0],[16,4],[16,6],[15,8],[13,9],[12,11],[11,11],[8,10],[-12,10],[-15,8],[-16,5],[-16,0],[-14,-4],[-10,-7],[-6,-9]];
const sereneEyeSource=new Image();let sereneEyeVectorOutline=null;
function traceSereneEyeOutline(image){const scratch=document.createElement('canvas');scratch.width=image.width;scratch.height=image.height;const source=scratch.getContext('2d');source.drawImage(image,0,0);const pixels=source.getImageData(0,0,scratch.width,scratch.height).data,cx=21,cy=22.5,samples=72,maxRadius=24,radii=[];for(let index=0;index<samples;index++){const angle=Math.PI*2*index/samples,cos=Math.cos(angle),sin=Math.sin(angle);let edge=0;for(let radius=0;radius<=maxRadius;radius+=.25){const px=Math.round(cx+cos*radius),py=Math.round(cy+sin*radius);if(px<0||px>=48||py<0||py>=scratch.height)break;if(pixels[(py*scratch.width+px)*4+3]>=96)edge=radius}radii.push(edge)}let smooth=radii;for(let pass=0;pass<3;pass++){smooth=smooth.map((_,index)=>(smooth[(index-2+samples)%samples]+2*smooth[(index-1+samples)%samples]+3*smooth[index]+2*smooth[(index+1)%samples]+smooth[(index+2)%samples])/9)}return smooth.map((radius,index)=>{const angle=Math.PI*2*index/samples;return[Math.cos(angle)*radius,Math.sin(angle)*radius]})}
sereneEyeSource.onload=()=>{sereneEyeVectorOutline=traceSereneEyeOutline(sereneEyeSource)};sereneEyeSource.src='/static/companion-serene-eyes.png';
function sereneEye(x,y,mirror=false,scale=3){ctx.save();ctx.translate(x,y);ctx.scale(mirror?-scale:scale,scale);ctx.fillStyle='#fff7f0';smoothClosedShape(sereneEyeVectorOutline||SERENE_EYE_FALLBACK);ctx.fill();ctx.restore()}
const joyfulReferenceSource=new Image(),joyfulEyeMask=document.createElement('canvas'),joyfulMouthMask=document.createElement('canvas');
const JOYFUL_EYE_CROP={x:67,y:72,w:149,h:114},JOYFUL_MOUTH_CROP={x:207,y:203,w:195,h:136};let joyfulMasksReady=false;
joyfulEyeMask.width=JOYFUL_EYE_CROP.w;joyfulEyeMask.height=JOYFUL_EYE_CROP.h;joyfulMouthMask.width=JOYFUL_MOUTH_CROP.w;joyfulMouthMask.height=JOYFUL_MOUTH_CROP.h;
function buildLuminanceMask(source,target,crop,threshold=26,gain=3.2,color=[255,247,240]){const mask=target.getContext('2d');mask.clearRect(0,0,target.width,target.height);mask.drawImage(source,crop.x,crop.y,crop.w,crop.h,0,0,crop.w,crop.h);const frame=mask.getImageData(0,0,crop.w,crop.h);for(let offset=0;offset<frame.data.length;offset+=4){const luminance=Math.max(frame.data[offset],frame.data[offset+1],frame.data[offset+2]),alpha=Math.max(0,Math.min(255,(luminance-threshold)*gain));frame.data[offset]=color[0];frame.data[offset+1]=color[1];frame.data[offset+2]=color[2];frame.data[offset+3]=alpha}mask.putImageData(frame,0,0)}
joyfulReferenceSource.onload=()=>{buildLuminanceMask(joyfulReferenceSource,joyfulEyeMask,JOYFUL_EYE_CROP);buildLuminanceMask(joyfulReferenceSource,joyfulMouthMask,JOYFUL_MOUTH_CROP);joyfulMasksReady=true};joyfulReferenceSource.src='/static/companion-joyful-reference.png';
function joyfulEye(x,y,mirror=false,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(mirror?-scale:scale,scale);if(joyfulMasksReady){ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(joyfulEyeMask,-47,-25,94,50)}else{squeezedEye(0,0,1,72,30,10)}ctx.restore()}
function joyfulMouth(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);if(joyfulMasksReady){ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(joyfulMouthMask,-39,-28,78,56)}else{triangleMouth(0,0,58,48)}ctx.restore()}
function curiousBrow(x,y,mirror=false,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(mirror?-scale:scale,scale);ctx.strokeStyle='#fff7f0';ctx.lineWidth=14;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-35,6);ctx.quadraticCurveTo(-4,-17,34,5);ctx.stroke();ctx.restore()}
function tinyCuriousMouth(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.rotate(-.48);oval(0,0,16*scale,10*scale,true);ctx.restore()}
function excitedMouth(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.ellipse(0,0,38,25,0,0,Math.PI*2);ctx.fill();ctx.restore()}
function puzzledMouth(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.strokeStyle='#fff7f0';ctx.lineWidth=9;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-38,4);ctx.bezierCurveTo(-17,-8,9,15,38,-1);ctx.stroke();ctx.restore()}
function squeezedEye(x,y,direction=1,w=72,h=30,stroke=10){const tip=x+direction*w/2,tail=x-direction*w/2;ctx.lineWidth=stroke;ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle='#fff7f0';ctx.beginPath();ctx.moveTo(tail,y-h/2);ctx.quadraticCurveTo(x-direction*w*.02,y-h*.12,tip,y);ctx.quadraticCurveTo(x-direction*w*.02,y+h*.12,tail,y+h/2);ctx.stroke()}
function arcEye(x,y,w=90,h=30,stroke=10){curve(x-w/2,y+h*.28,x,y-h,x+w/2,y+h*.28,stroke)}
function triangleMouth(x,y,w=56,h=48){ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.moveTo(x-w/2+7,y-h/2);ctx.quadraticCurveTo(x-w/2,y-h/2,x-w/2+2,y-h/2+8);ctx.lineTo(x-7,y+h/2-3);ctx.quadraticCurveTo(x,y+h/2+3,x+7,y+h/2-3);ctx.lineTo(x+w/2-2,y-h/2+8);ctx.quadraticCurveTo(x+w/2,y-h/2,x+w/2-7,y-h/2);ctx.closePath();ctx.fill()}
function trapezoidMouth(x,y,w=58,h=60){ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.moveTo(x-w*.26,y-h/2);ctx.quadraticCurveTo(x,y-h/2-3,x+w*.26,y-h/2);ctx.lineTo(x+w/2,y+h/2-7);ctx.quadraticCurveTo(x+w*.48,y+h/2,x+w*.36,y+h/2);ctx.lineTo(x-w*.36,y+h/2);ctx.quadraticCurveTo(x-w*.48,y+h/2,x-w/2,y+h/2-7);ctx.closePath();ctx.fill()}
function pillMouth(x,y,w=74,h=32){ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.ellipse(x,y,w/2,h/2,0,0,Math.PI*2);ctx.fill()}
function segmentedGrin(x,y,w=158,h=58,segments=5){const left=x-w/2,right=x+w/2,top=y-h*.42,bottom=y+h*.58;ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.moveTo(left+9,top);ctx.bezierCurveTo(x-w*.3,top+4,x-w*.2,top+7,x,top+7);ctx.bezierCurveTo(x+w*.2,top+7,x+w*.3,top+4,right-9,top);ctx.quadraticCurveTo(right+2,top+3,right-3,top+12);ctx.bezierCurveTo(x+w*.34,bottom+4,x-w*.34,bottom+4,left+3,top+12);ctx.quadraticCurveTo(left-2,top+3,left+9,top);ctx.closePath();ctx.fill();ctx.strokeStyle='#050404';ctx.lineWidth=5;ctx.lineCap='round';for(let i=1;i<segments;i++){const sx=x-w/2+w*i/segments;ctx.beginPath();ctx.moveTo(sx,top+10);ctx.lineTo(sx,bottom-4);ctx.stroke()}}
function mirrorHalf(cx,drawHalf){ctx.save();ctx.translate(cx,0);drawHalf();ctx.scale(-1,1);drawHalf();ctx.restore()}
function smugEyeHalf(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.moveTo(-86,18);ctx.bezierCurveTo(-91,4,-82,-10,-65,-20);ctx.bezierCurveTo(-24,-43,44,-35,90,25);ctx.quadraticCurveTo(96,35,88,39);ctx.bezierCurveTo(48,13,-3,-3,-58,19);ctx.bezierCurveTo(-74,26,-83,25,-86,18);ctx.closePath();ctx.fill();ctx.restore()}
function smugMouth(cx,y,scale=1){ctx.save();ctx.translate(cx,y);ctx.scale(scale,scale);ctx.strokeStyle='#fff7f0';ctx.lineWidth=9;ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();ctx.moveTo(-45,-2);ctx.quadraticCurveTo(-24,24,0,3);ctx.quadraticCurveTo(24,24,45,-2);ctx.stroke();ctx.restore()}
function smugFace(cx,eyeY,mouthY,scale=.82){mirrorHalf(cx,()=>smugEyeHalf(-112,eyeY,scale));smugMouth(cx,mouthY,scale)}
const loveReferenceSource=new Image(),loveReferenceMask=document.createElement('canvas');
const LOVE_FACE_CROP={x:35,y:110,w:430,h:270};let loveReferenceReady=false;
loveReferenceMask.width=LOVE_FACE_CROP.w;loveReferenceMask.height=LOVE_FACE_CROP.h;
loveReferenceSource.onload=()=>{buildLuminanceMask(loveReferenceSource,loveReferenceMask,LOVE_FACE_CROP,45,4.8,[255,44,122]);loveReferenceReady=true};loveReferenceSource.src='/static/companion-love-reference.png';
const sadReferenceSource=new Image(),sadReferenceMask=document.createElement('canvas'),cryingReferenceSource=new Image(),cryingReferenceMask=document.createElement('canvas');
const SAD_FACE_CROP={x:200,y:300,w:1050,h:440},CRYING_FACE_CROP={x:160,y:305,w:1280,h:500};let sadReferenceReady=false,cryingReferenceReady=false;
sadReferenceMask.width=SAD_FACE_CROP.w;sadReferenceMask.height=SAD_FACE_CROP.h;cryingReferenceMask.width=CRYING_FACE_CROP.w;cryingReferenceMask.height=CRYING_FACE_CROP.h;
sadReferenceSource.onload=()=>{buildLuminanceMask(sadReferenceSource,sadReferenceMask,SAD_FACE_CROP,45,4.6);sadReferenceReady=true};sadReferenceSource.src='/static/companion-sad-reference.png';
cryingReferenceSource.onload=()=>{buildLuminanceMask(cryingReferenceSource,cryingReferenceMask,CRYING_FACE_CROP,45,4.6);cryingReferenceReady=true};cryingReferenceSource.src='/static/companion-crying-reference.png';
const sobbingTearSource=new Image();let sobbingTearReady=false;sobbingTearSource.onload=()=>{sobbingTearReady=true};sobbingTearSource.src='/static/companion-sobbing-tear-reference.png';
function drawReferenceMask(mask,ready,cx,cy,w,h,fallback){ctx.save();if(ready){ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(mask,cx-w/2,cy-h/2,w,h)}else{fallback()}ctx.restore()}
function loveFace(cx,cy,t,scale=1){const pulse=scale*(1+Math.sin(t*4)*.035);drawReferenceMask(loveReferenceMask,loveReferenceReady,cx,cy,340*pulse,213*pulse,()=>{heart(cx-116,cy-35,42*pulse,'#ff2c7a');heart(cx+116,cy-35,42*pulse,'#ff2c7a');oval(cx,cy+58,42*pulse,25*pulse,true,'#ff2c7a')})}
function sadFace(cx,cy,scale=1){drawReferenceMask(sadReferenceMask,sadReferenceReady,cx,cy,360*scale,151*scale,()=>{closedEye(cx-112,cy,96,12);closedEye(cx+112,cy,96,12)})}
function cryingFace(cx,cy,scale=1){drawReferenceMask(cryingReferenceMask,cryingReferenceReady,cx,cy,390*scale,152*scale,()=>{closedEye(cx-112,cy,106,8);closedEye(cx+112,cy,106,8);tear(cx+142,cy+54,15)})}
function sobbingEyeHalf(x,y,t,scale=1){const shake=Math.sin(t*11.5)*1;ctx.save();ctx.translate(x,y+shake);ctx.scale(scale,scale);ctx.strokeStyle='#06b8ff';ctx.lineWidth=18;ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();ctx.moveTo(-78,-54);ctx.quadraticCurveTo(-24,-32,76,0);ctx.quadraticCurveTo(-24,32,-78,54);ctx.stroke();ctx.restore()}
function sobbingTearHalf(x,y,t,scale=1){const drawW=72,drawH=316,clipX=-108,clipY=-4,clipW=88,clipH=160,travel=drawH-clipH,flow=(t*74)%travel,yy=-travel+flow;ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.beginPath();ctx.rect(clipX,clipY,clipW,clipH);ctx.clip();if(sobbingTearReady){ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(sobbingTearSource,-100,yy,drawW,drawH)}else{ctx.strokeStyle='#06b8ff';ctx.lineWidth=52;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-72,0);ctx.bezierCurveTo(-104,36,-45,74,-72,112);ctx.bezierCurveTo(-100,140,-50,150,-72,156);ctx.stroke()}ctx.restore()}
function sobbingMouth(cx,y,t,scale=1){const wave=Math.sin(t*5.2)*3;ctx.save();ctx.translate(cx,y);ctx.scale(scale,scale);ctx.fillStyle='#06b8ff';ctx.beginPath();ctx.moveTo(-128,11);ctx.bezierCurveTo(-128,-18,-101,-42,-64,-39);ctx.bezierCurveTo(-48,-38,-37,-34,-26,-31);ctx.bezierCurveTo(10,-21,43,-21,78,-33);ctx.bezierCurveTo(109,-43,130,-18,130,10);ctx.bezierCurveTo(130,38,108,58,80,63);ctx.bezierCurveTo(48,68,26,51,0,51+wave*.35);ctx.bezierCurveTo(-26,51,-48,68,-80,63);ctx.bezierCurveTo(-108,58,-128,39,-130,16);ctx.quadraticCurveTo(-130,13,-128,11);ctx.closePath();ctx.fill();ctx.restore()}
function sobbingFace(cx,eyeY,mouthY,t,scale=.76){const bob=Math.sin(t*2.6)*1.2;mirrorHalf(cx,()=>sobbingTearHalf(-112,eyeY+35+bob,t,scale));sobbingMouth(cx,mouthY+8+bob*.15,t,scale);mirrorHalf(cx,()=>sobbingEyeHalf(-112,eyeY+bob,t,scale))}
function annoyedEyeHalf(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.moveTo(-79,13);ctx.bezierCurveTo(-58,-8,-17,-18,51,-5);ctx.quadraticCurveTo(76,0,84,13);ctx.bezierCurveTo(38,24,-31,25,-76,18);ctx.quadraticCurveTo(-86,16,-79,13);ctx.closePath();ctx.fill();ctx.restore()}
function annoyedBrowHalf(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.strokeStyle='#fff7f0';ctx.lineWidth=14;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-78,-12);ctx.quadraticCurveTo(-18,-4,70,18);ctx.stroke();ctx.restore()}
function annoyedMouth(cx,y,scale=1){ctx.save();ctx.translate(cx,y);ctx.scale(scale,scale);ctx.strokeStyle='#fff7f0';ctx.lineWidth=10;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-45,2);ctx.quadraticCurveTo(0,7,45,2);ctx.stroke();ctx.restore()}
function annoyedStressMark(x,y,t,scale=1){const pulse=scale*(1+Math.sin(t*5.5)*.08);ctx.save();ctx.translate(x,y);ctx.scale(pulse,pulse);ctx.strokeStyle='#fff7f0';ctx.lineWidth=6;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-14,0);ctx.lineTo(0,-13);ctx.moveTo(-1,8);ctx.lineTo(14,-8);ctx.moveTo(8,17);ctx.lineTo(21,5);ctx.stroke();ctx.restore()}
function annoyedFace(cx,eyeY,mouthY,t,scale=.78){mirrorHalf(cx,()=>annoyedEyeHalf(-112,eyeY,scale));mirrorHalf(cx,()=>annoyedBrowHalf(-112,eyeY-49,scale));annoyedMouth(cx,mouthY,scale);annoyedStressMark(cx+184,eyeY-72,t,scale*.8)}
function angryEyeHalf(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.fillStyle='#00eaff';ctx.beginPath();ctx.moveTo(-62,-38);ctx.bezierCurveTo(-31,-29,15,-16,66,-8);ctx.bezierCurveTo(66,9,59,28,43,41);ctx.bezierCurveTo(20,60,-18,58,-43,38);ctx.bezierCurveTo(-61,24,-72,-3,-70,-24);ctx.bezierCurveTo(-69,-34,-67,-40,-62,-38);ctx.closePath();ctx.fill();ctx.restore()}
function angryFace(cx,eyeY,t,scale=.82){const bob=Math.sin(t*2.15)*1.3,pulse=1+Math.sin(t*4.8)*.015;mirrorHalf(cx,()=>angryEyeHalf(-112,eyeY+bob,scale*pulse))}
function thinkingMouth(cx,y,scale=1){ctx.save();ctx.translate(cx,y);ctx.scale(scale,scale);ctx.strokeStyle='#fff7f0';ctx.lineWidth=8;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-33,5);ctx.bezierCurveTo(-13,-6,12,13,34,-2);ctx.stroke();ctx.restore()}
function thinkingDots(x,y,t,scale=1){const base=[[-2,42,6],[24,19,9],[55,-10,13]];base.forEach((dot,index)=>{const pulse=scale*(1+Math.sin(t*3.8+index*1.1)*.09);circle(x+dot[0]*scale,y+dot[1]*scale,dot[2]*pulse,true)})}
function thinkingFace(cx,eyeY,mouthY,t,scale=.82){const drift=Math.sin(t*1.4)*2;baseEye(cx-108+drift,eyeY,false,1,.74*scale);baseEye(cx+108+drift,eyeY,true,1,.74*scale);thinkingMouth(cx,mouthY,scale);thinkingDots(cx+138,eyeY-86,t,scale)}
function sleepyEyeHalf(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.moveTo(-88,2);ctx.bezierCurveTo(-67,-13,-25,-16,28,-12);ctx.bezierCurveTo(61,-10,84,-5,91,2);ctx.quadraticCurveTo(99,11,86,16);ctx.bezierCurveTo(43,23,-25,22,-76,13);ctx.quadraticCurveTo(-98,10,-88,2);ctx.closePath();ctx.fill();ctx.restore()}
function sleepyEyeBagHalf(x,y,scale=1){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.strokeStyle='rgba(255,247,240,.38)';ctx.lineWidth=4;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-43,32);ctx.quadraticCurveTo(0,37,43,32);ctx.stroke();ctx.restore()}
function sleepyMouth(cx,y,scale=1){ctx.save();ctx.translate(cx,y);ctx.scale(scale,scale);ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.ellipse(0,4,18,10,0,0,Math.PI*2);ctx.fill();ctx.restore()}
function sleepyFace(cx,eyeY,mouthY,t,scale=.82){const slow=Math.sin(t*.72)*1.2;mirrorHalf(cx,()=>sleepyEyeHalf(-112,eyeY+slow,scale));mirrorHalf(cx,()=>sleepyEyeBagHalf(-112,eyeY+slow,scale));sleepyMouth(cx,mouthY+4+slow*.25,scale)}
function alertCornerMark(x,y,t,scale=1){const pulse=scale*(1+Math.sin(t*5.2)*.08);ctx.save();ctx.translate(x,y);ctx.scale(pulse,pulse);ctx.strokeStyle='rgba(255,247,240,.86)';ctx.lineWidth=6;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-8,-18);ctx.lineTo(-2,-41);ctx.moveTo(14,-8);ctx.lineTo(36,-27);ctx.moveTo(23,17);ctx.lineTo(49,9);ctx.stroke();ctx.restore()}
function alertMouth(cx,y,t,scale=1){const pulse=1+Math.sin(t*5.6)*.03;ctx.save();ctx.translate(cx,y);ctx.scale(scale*pulse,scale);ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.ellipse(0,2,15,20,0,0,Math.PI*2);ctx.fill();ctx.restore()}
function alertFace(cx,eyeY,mouthY,t,open=1,scale=.88){const pop=1+Math.sin(t*4.6)*.025;const lift=Math.sin(t*3.4)*1.2;baseEye(cx-108,eyeY+lift,false,open,.94*scale*pop);baseEye(cx+108,eyeY+lift,true,open,.94*scale*pop);alertCornerMark(cx+166,eyeY-57+lift,t,scale*.82);alertMouth(cx,mouthY+lift*.25,t,scale)}
function cameraBody(cx,y,t,scale=1,capture=false){const pulse=capture?1+Math.sin(t*10)*.035:1;ctx.save();ctx.translate(cx,y);ctx.scale(scale*pulse,scale*pulse);roundedRect(-88,-44,176,90,16,false);roundedRect(44,-59,31,16,7,true);circle(0,2,37,false);circle(0,2,16,true,'#050404');circle(0,2,8,true);line(-71,-21,-47,-21,5);line(49,34,70,34,5);ctx.restore()}
function photoModeFace(cx,eyeY,mouthY,t,open=1,capture=false){const bob=Math.sin(t*2.2)*1.6;baseEye(cx-105,eyeY+bob,false,open,.76);baseEye(cx+105,eyeY+bob,true,open,.76);cameraBody(cx,mouthY+8+bob*.25,t,.9,capture);if(capture&&Math.sin(t*14)>-.15){ctx.save();ctx.fillStyle='rgba(255,247,240,.16)';ctx.fillRect(0,0,512,256);ctx.restore()}}
function objectIdleEyes(cx,eyeY,t,open=1){const bob=Math.sin(t*2.15)*1.5;baseEye(cx-105,eyeY+bob,false,open,.76);baseEye(cx+105,eyeY+bob,true,open,.76);return bob}
function burgerObject(cx,y,t,scale=1){const bite=Math.sin(t*3.2)*1.5;ctx.save();ctx.translate(cx,y+bite);ctx.scale(scale,scale);ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.moveTo(-74,-12);ctx.bezierCurveTo(-66,-43,-34,-55,0,-55);ctx.bezierCurveTo(34,-55,66,-43,74,-12);ctx.quadraticCurveTo(45,-2,0,-2);ctx.quadraticCurveTo(-45,-2,-74,-12);ctx.fill();ctx.fillStyle='#050404';circle(-27,-32,3,true,'#050404');circle(0,-38,3,true,'#050404');circle(29,-30,3,true,'#050404');ctx.fillStyle='#fff7f0';roundedRect(-78,2,156,14,7,true);ctx.strokeStyle='#fff7f0';ctx.lineWidth=7;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-71,25);ctx.bezierCurveTo(-47,11,-24,36,0,22);ctx.bezierCurveTo(25,8,47,36,72,21);ctx.stroke();roundedRect(-68,35,136,24,12,true);ctx.restore()}
function cupObject(cx,y,t,scale=1){const bob=Math.sin(t*2.5)*1.2;ctx.save();ctx.translate(cx,y+bob);ctx.scale(scale,scale);ctx.strokeStyle='#fff7f0';ctx.fillStyle='#fff7f0';ctx.lineWidth=7;ctx.lineCap='round';line(18,-51,46,-88,7);line(46,-88,63,-88,7);roundedRect(-58,-55,116,18,9,false);ctx.beginPath();ctx.moveTo(-48,-37);ctx.lineTo(48,-37);ctx.lineTo(34,52);ctx.quadraticCurveTo(0,61,-34,52);ctx.closePath();ctx.stroke();line(-27,-11,27,-11,5);line(-20,19,20,19,5);ctx.strokeStyle='rgba(255,247,240,.75)';line(19,-21,9,40,5);ctx.restore()}
function eatingFace(cx,eyeY,mouthY,t,open=1){const bob=objectIdleEyes(cx,eyeY,t,open);burgerObject(cx,mouthY-8+bob*.2,t,.78)}
function drinkingFace(cx,eyeY,mouthY,t,open=1){const bob=objectIdleEyes(cx,eyeY,t,open);cupObject(cx,mouthY+10+bob*.2,t,.78)}
const wonderEyeSource=new Image();let wonderEyeReady=false;wonderEyeSource.onload=()=>{wonderEyeReady=true};wonderEyeSource.src='/static/companion-wonder-eye-reference.png';
function wonderEye(x,y,scale=1){const w=174*scale,h=185*scale;ctx.save();ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';if(wonderEyeReady){ctx.drawImage(wonderEyeSource,x-w/2,y-h/2,w,h)}else{baseEye(x,y,false,1,.95*scale)}ctx.restore()}
function wonderFace(cx,eyeY,t,scale=1){ctx.save();ctx.fillStyle='#000';ctx.fillRect(0,0,512,256);ctx.restore();wonderEye(cx-116,eyeY,scale);wonderEye(cx+116,eyeY,scale)}
function trackingEye(x,y,mirror,open,dx,dy,scale=.8){baseEye(x,y,mirror,open,scale);circle(x+dx,y+dy,8,true,'#050404')}
function trackingFace(cx,eyeY,mouthY,t,open=1){const lookX=Math.sin(t*1.45)*10,lookY=Math.cos(t*1.15)*5,bob=Math.sin(t*2.1)*1.4;trackingEye(cx-104,eyeY+bob,false,open,lookX,lookY,.82);trackingEye(cx+104,eyeY+bob,true,open,lookX,lookY,.82)}
function scanningBeam(cx,y,t,scale=1){const sweep=eyeScanY(t),pulse=.74+Math.sin(t*5.2)*.1;ctx.save();ctx.translate(cx,sweep);ctx.scale(scale,scale);ctx.strokeStyle=`rgba(255,247,240,${pulse})`;ctx.lineWidth=6;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-182,0);ctx.lineTo(182,0);ctx.stroke();ctx.strokeStyle='rgba(255,247,240,.2)';ctx.lineWidth=14;ctx.beginPath();ctx.moveTo(-150,0);ctx.lineTo(150,0);ctx.stroke();ctx.restore()}
function eyeScanY(t){return 70+((t*58)%110)}
function scanningFace(cx,eyeY,mouthY,t,open=1){const bob=Math.sin(t*1.9)*1.2;baseEye(cx-104,eyeY+bob,false,open,.78);baseEye(cx+104,eyeY+bob,true,open,.78);scanningBeam(cx,eyeY,t,.9);line(cx-28,mouthY+21,cx+28,mouthY+21,6)}
function clamp01(value){return Math.max(0,Math.min(1,value))}
function easeOut(value){const v=clamp01(value);return 1-Math.pow(1-v,3)}
function wakeYawn(cx,y,phase,scale=1){const alpha=clamp01(1-phase*1.55);if(alpha<=0)return;ctx.save();ctx.globalAlpha=.3+.5*alpha;ctx.translate(cx,y);ctx.scale(scale,scale);ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.ellipse(0,0,13+7*alpha,15+6*alpha,0,0,Math.PI*2);ctx.fill();ctx.restore()}
function wakeSpark(cx,y,phase){if(phase<.68)return;const pulse=1+Math.sin(phase*19)*.14;ctx.save();ctx.globalAlpha=clamp01((phase-.68)*2.5);sparkle(cx,y,11*pulse);circle(cx+24,y-15,3.5*pulse,true);ctx.restore()}
function wakeUpFace(cx,eyeY,mouthY,t,open=1){const phase=easeOut((t-expressionStartedAt)/2.72),bob=Math.sin(t*2.1)*(1.1+phase*1.2),lid=Math.max(.03,phase*open),size=.88+phase*.07;baseEyeReveal(cx-104,eyeY+bob,false,lid,size);baseEyeReveal(cx+104,eyeY+bob,true,lid,size);wakeYawn(cx,mouthY+6+bob*.25,phase,.78);if(phase>.58)wmouth(cx,mouthY+7+bob*.2,38+16*phase,7+5*phase);wakeSpark(cx+156,eyeY-55+bob,phase)}
function closedEye(x,y,w=82,depth=10,stroke=8){curve(x-w/2,y,x,y+depth,x+w/2,y,stroke)}
function brow(x,y,tilt=0,w=72){line(x-w/2,y-tilt,x+w/2,y+tilt,7)}
function smile(x,y,w=70,h=18,stroke=8){curve(x-w/2,y,x,y+h,x+w/2,y,stroke)}
function frown(x,y,w=64,h=16,stroke=8){curve(x-w/2,y,x,y-h,x+w/2,y,stroke)}
function wmouth(x,y,w=62,h=17){curve(x-w/2,y,x-w/4,y+h,x,y,7);curve(x,y,x+w/4,y+h,x+w/2,y,7)}
function sparkle(x,y,s=12){line(x-s,y,x+s,y,5);line(x,y-s,x,y+s,5)}
function excitedSparkle(x,y,t,phase=0){const pulse=1+Math.sin(t*7+phase)*.22;sparkle(x,y,14*pulse);circle(x+27,y-19,4*pulse,true);circle(x-23,y+21,3.5*pulse,true)}
function question(x,y){ctx.fillStyle='#fff7f0';ctx.font='bold 44px Arial';ctx.fillText('?',x,y)}
function exclamation(x,y){ctx.fillStyle='#fff7f0';ctx.font='bold 44px Arial';ctx.fillText('!',x,y)}
function tear(x,y,s=12){ctx.fillStyle='#fff7f0';ctx.beginPath();ctx.moveTo(x,y-s);ctx.quadraticCurveTo(x-s,y+s,x,y+s);ctx.quadraticCurveTo(x+s,y+s,x,y-s);ctx.fill()}
function stress(x,y){line(x,y,x+18,y-16,5);line(x+11,y+8,x+31,y-7,5);line(x+24,y+16,x+40,y+6,5)}
function drawReferenceBlink(){closedEye(144,118);closedEye(368,118)}
function drawReferenceFace(id,t,open){const naturalBlink=Math.sin(t*.72)>.985?.08:1;
 if(id==='idle'){const breathe=Math.sin(t*2.4)*3,ey=Math.max(.08,open*naturalBlink);baseEye(144,118+breathe,false,ey);baseEye(368,118+breathe,true,ey);return true}
 if(open<.34||naturalBlink<.5){drawReferenceBlink();return true}const bob=Math.sin(t*2.4)*3,jump=id==='laughing'?Math.sin(t*7)*4:0,mouthY=190+bob+jump;
 if(id==='serene'){sereneEye(144,112+bob);sereneEye(368,112+bob,true)}
 else if(id==='happy'){sereneEye(144,100+bob);sereneEye(368,100+bob,true);wmouth(256,186+bob,66,17)}
 else if(id==='wink'){sereneEye(144,104+bob);joyfulEye(368,106+bob,true);wmouth(256,188+bob,62,16)}
 else if(id==='joyful'){joyfulEye(144,104+bob);joyfulEye(368,104+bob,true);joyfulMouth(256,194+bob)}
 else if(id==='laughing'){joyfulEye(144,89+bob+jump,false,1.08);joyfulEye(368,89+bob+jump,true,1.08);segmentedGrin(256,mouthY,164,60,5)}
 else if(id==='cheerful'){arcEye(144,105+bob,92,31,10);arcEye(368,105+bob,92,31,10);joyfulMouth(256,194+bob)}
 else if(id==='curious'){baseEye(147,112+bob,false,1,.86);baseEye(365,107+bob,true,1,.9);curiousBrow(371,43+bob);tinyCuriousMouth(256,193+bob,1.18)}
 else if(id==='excited'){const pop=Math.sin(t*7.5)*4,pulse=1+Math.sin(t*6)*.035;baseEye(144,101+bob+pop,false,1,1.02*pulse);baseEye(368,101+bob-pop*.55,true,1,1.02*pulse);excitedMouth(256,194+bob,1+Math.sin(t*7)*.06);excitedSparkle(76,58,t,0);excitedSparkle(436,58,t,1.8)}
 else if(id==='confused'){baseEye(144,112+bob,false,1,.82);baseEye(368,112+bob,true,1,.82);brow(144,40+bob,8,68);brow(368,40+bob,-8,68);puzzledMouth(256,194+bob,1.02)}
 else if(id==='wonder'){wonderFace(256,125+bob,t,.92)}
 else if(id==='love'){loveFace(256,133+bob,t,1)}
 else if(id==='smug'){smugFace(256,98+bob,182+bob,.82)}
 else if(id==='sad'){sadFace(256,130+bob,1)}
 else if(id==='crying'){cryingFace(256,132+bob,1)}
 else if(id==='sobbing'){sobbingFace(256,80+bob,170+bob,t,.76)}
 else if(id==='annoyed'){annoyedFace(256,108+bob,192+bob,t,.78)}
 else if(id==='angry'){angryFace(256,116+bob,t,.86)}
 else if(id==='thinking'){thinkingFace(256,109+bob,192+bob,t,.86)}
 else if(id==='sleepy'){sleepyFace(256,117+bob,198+bob,t,.86)}
 else if(id==='alert'){alertFace(256,103+bob,196+bob,t,open,.9)}
 else if(id==='shocked'){circle(144,112+bob,14,false);circle(368,112+bob,14,false);trapezoidMouth(256,190+bob,60,62)}
 else if(id==='surprised'){baseEye(144,105+bob,false,1,1.12);baseEye(368,105+bob,true,1,1.12);circle(256,207+bob,15,true)}
 else return false;return true}
function drawFace(id,t,open=1){ctx.clearRect(0,0,512,256);ctx.fillStyle='#050404';ctx.fillRect(0,0,512,256);const bob=Math.sin(t*2.4)*4;const lx=166,rx=346,y=112+bob,mouthY=194+bob;const blink=(Math.sin(t*.72)>0.985)?0.08:open;const eyeRy=34*Math.max(.06,blink);const lookX=Math.sin(t*.7)*8,lookY=Math.cos(t*.53)*3;
 if(drawReferenceFace(id,t,open))return;
 if(id==='serene'){sereneEye(lx,y);sereneEye(rx,y,true)}
 else if(id==='happy'){sereneEye(lx,y);sereneEye(rx,y,true);wmouth(256,mouthY,62,16)}
 else if(id==='joyful'){joyfulEye(lx,y);joyfulEye(rx,y,true);joyfulMouth(256,mouthY+4)}
 else if(id==='laughing'){const jump=Math.sin(t*7)*5;joyfulEye(lx,y+jump,false,1.08);joyfulEye(rx,y+jump,true,1.08);segmentedGrin(256,mouthY,154,52,7)}
 else if(id==='cheerful'){arcEye(lx,y,92,31,10);arcEye(rx,y,92,31,10);joyfulMouth(256,mouthY+4)}
 else if(id==='curious'){baseEye(lx-19,y,false,1,.86);baseEye(rx+19,y-5,true,1,.9);curiousBrow(rx+25,y-69);tinyCuriousMouth(256,mouthY-1,1.18)}
 else if(id==='excited'){const pop=Math.sin(t*7.5)*4,pulse=1+Math.sin(t*6)*.035;baseEye(lx-22,y-11+pop,false,1,1.02*pulse);baseEye(rx+22,y-11-pop*.55,true,1,1.02*pulse);excitedMouth(256,mouthY,1+Math.sin(t*7)*.06);excitedSparkle(78,56,t,0);excitedSparkle(434,56,t,1.8)}
 else if(id==='surprised'){eye(lx,y,50,54*blink);eye(rx,y,50,54*blink);circle(256,mouthY,14,true);exclamation(420,76)}
 else if(id==='shocked'){circle(lx,y,13,false);circle(rx,y,13,false);trapezoidMouth(256,mouthY,58,60)}
 else if(id==='confused'){baseEye(lx-22,y,false,1,.82);baseEye(rx+22,y,true,1,.82);brow(lx-22,y-72,8,68);brow(rx+22,y-72,-8,68);puzzledMouth(256,mouthY,1.02)}
 else if(id==='wonder'){wonderFace(256,y+8,t,.92)}
 else if(id==='smug'){smugFace(256,y-14,mouthY-12,.82)}
 else if(id==='sad'){sadFace(256,y+18,1)}
 else if(id==='crying'){cryingFace(256,y+20,1)}
 else if(id==='sobbing'){sobbingFace(256,y-32,mouthY-24,t,.76)}
 else if(id==='annoyed'){annoyedFace(256,y-4,mouthY,t,.78)}
 else if(id==='angry'){angryFace(256,y+4,t,.86)}
 else if(id==='love'){loveFace(256,mouthY-61,t,1)}
 else if(id==='thinking'){thinkingFace(256,y-3,mouthY,t,.86)}
 else if(id==='sleepy'){sleepyFace(256,y+5,mouthY+4,t,.86)}
 else if(id==='sleeping'||id==='fall_asleep'){curve(lx-42,y,lx,y+12,lx+42,y,7);curve(rx-42,y,rx,y+12,rx+42,y,7);ctx.font='bold 42px Arial';ctx.fillStyle='#fff7f0';ctx.fillText('Z',390,75);ctx.font='bold 26px Arial';ctx.fillText('Z',438,43)}
 else if(id==='alert'){alertFace(256,y-9,mouthY+2,t,blink,.9)}
 else if(id==='photo_mode'||id==='photo_capture'){photoModeFace(256,y-16,mouthY-2,t,blink,id==='photo_capture')}
 else if(id==='eating'){eatingFace(256,y-16,mouthY,t,blink)}
 else if(id==='drinking'){drinkingFace(256,y-16,mouthY,t,blink)}
 else if(id==='tracking'){trackingFace(256,y-12,mouthY-7,t,blink)}
 else if(id==='scanning'){scanningFace(256,y-12,mouthY-9,t,blink)}
 else if(id==='offline'){line(lx-36,y-30,lx+36,y+30);line(lx+36,y-30,lx-36,y+30);line(rx-36,y-30,rx+36,y+30);line(rx+36,y-30,rx-36,y+30);line(226,mouthY+8,286,mouthY+8,7)}
 else if(id==='wink'){sereneEye(lx,y);joyfulEye(rx,y,true);wmouth(256,mouthY,50,12)}
 else if(id==='blink'){curve(lx-42,y,lx,y+8,lx+42,y,7);curve(rx-42,y,rx,y+8,rx+42,y,7)}
 else if(id==='wake_up'){wakeUpFace(256,y-8,mouthY-5,t,blink)}
 else{eye(lx+lookX,y+lookY,48,eyeRy);eye(rx+lookX,y+lookY,48,eyeRy);smile(256,mouthY,42,8,6)}
}
function animate(now){const dt=Math.min(.08,(now-lastTime)/1000);lastTime=now;if(transitionPhase==='closing'){openness=Math.max(0,openness-dt*6);if(openness===0){current=next;transitionPhase='opening'}}else if(transitionPhase==='opening'){openness=Math.min(1,openness+dt*6);if(openness===1)transitionPhase='idle'}drawFace(current,now/1000,openness);requestAnimationFrame(animate)}
function setPreview(id){if(id!==next){next=id;transitionPhase='closing';expressionStartedAt=performance.now()/1000}const item=labelFor(id);document.getElementById('currentExpression').textContent=item.label;document.getElementById('currentDetail').textContent=item.detail;document.querySelectorAll('.expression').forEach(b=>b.classList.toggle('active',b.dataset.id===id))}
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
