from flask import Flask, jsonify, request
from pathlib import Path
import copy
import json
import time
import requests

app = Flask(__name__)

DATA_DIR = Path("/data")
DEVICES_FILE = DATA_DIR / "lights_devices.json"
REQUEST_TIMEOUT = 3

DEFAULT_CONFIG = {
    "version": 1,
    "active": "demo_light",
    "devices": [
        {
            "id": "demo_light",
            "name": "Luce Demo",
            "type": "esp32_pan_tilt",
            "host": "",
            "enabled": True,
            "demo": True,
            "state": {
                "pan": 90,
                "tilt": 90,
                "online": True,
                "last_seen": None,
                "message": "Modalita demo: nessun modulo ESP32 collegato.",
            },
            "pan": {"min": 30, "max": 150, "center": 90, "invert": False},
            "tilt": {"min": 40, "max": 140, "center": 90, "invert": False},
            "presets": [
                {"name": "Centro", "pan": 90, "tilt": 90},
                {"name": "Key alta", "pan": 75, "tilt": 65},
                {"name": "Side soft", "pan": 120, "tilt": 90},
            ],
        }
    ],
}


def now_label():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def clamp(value, minimum, maximum):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def normalize_device(device):
    result = copy.deepcopy(device)
    result.setdefault("id", "light")
    result.setdefault("name", result["id"])
    result.setdefault("type", "esp32_pan_tilt")
    result.setdefault("host", "")
    result.setdefault("enabled", True)
    result.setdefault("demo", not bool(result.get("host")))
    result.setdefault("pan", {})
    result.setdefault("tilt", {})
    result["pan"].setdefault("min", 30)
    result["pan"].setdefault("max", 150)
    result["pan"].setdefault("center", 90)
    result["pan"].setdefault("invert", False)
    result["tilt"].setdefault("min", 40)
    result["tilt"].setdefault("max", 140)
    result["tilt"].setdefault("center", 90)
    result["tilt"].setdefault("invert", False)
    result.setdefault("presets", [])
    result.setdefault("state", {})
    result["state"].setdefault("pan", result["pan"]["center"])
    result["state"].setdefault("tilt", result["tilt"]["center"])
    result["state"].setdefault("online", bool(result.get("demo")))
    result["state"].setdefault("last_seen", None)
    result["state"].setdefault("message", "Pronto.")
    return result


def load_config():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DEVICES_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = copy.deepcopy(DEFAULT_CONFIG)
        data["warning"] = "lights_devices.json corrotto: uso fallback demo."

    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        data = copy.deepcopy(DEFAULT_CONFIG)

    data.setdefault("version", 1)
    data["devices"] = [normalize_device(device) for device in data.get("devices", [])]
    if not data["devices"]:
        data["devices"] = [normalize_device(DEFAULT_CONFIG["devices"][0])]
    data.setdefault("active", data["devices"][0]["id"])
    return data


def save_config(config):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = DEVICES_FILE.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    temp_path.replace(DEVICES_FILE)


def find_device(config, device_id):
    for device in config.get("devices", []):
        if device.get("id") == device_id:
            return device
    return None


def api_base(device):
    host = str(device.get("host", "")).strip()
    if not host:
        return ""
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"http://{host}".rstrip("/")


def device_public(device):
    public = copy.deepcopy(device)
    public["configured"] = bool(public.get("host"))
    public["api_base"] = api_base(public) if public.get("host") else ""
    return public


def send_to_device(device, endpoint, payload=None):
    if device.get("demo") or not device.get("host"):
        return {"ok": True, "demo": True, "response": {"message": "Comando simulato in modalita demo."}}

    url = f"{api_base(device)}{endpoint}"
    try:
        if payload is None:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
        else:
            response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"ok": False, "demo": False, "error": str(exc)}

    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    return {"ok": True, "demo": False, "response": data}


def apply_position(device, pan, tilt):
    pan_value = clamp(pan, device["pan"]["min"], device["pan"]["max"])
    tilt_value = clamp(tilt, device["tilt"]["min"], device["tilt"]["max"])
    device["state"]["pan"] = pan_value
    device["state"]["tilt"] = tilt_value

    result = send_to_device(device, "/move", {"pan": pan_value, "tilt": tilt_value})
    if result["ok"]:
        device["state"]["online"] = True
        device["state"]["last_seen"] = now_label()
        device["state"]["message"] = result["response"].get("message", "Posizione aggiornata.")
    else:
        device["state"]["online"] = False
        device["state"]["message"] = result["error"]
    return result


@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIWA Lighting</title>
<style>
:root{
  color-scheme:dark;
  --bg:#0b1220;--panel:#172033;--panel2:#101827;--line:#334155;
  --text:#f8fafc;--muted:#94a3b8;--soft:#cbd5e1;--blue:#38bdf8;
  --amber:#f59e0b;--green:#22c55e;--red:#ef4444;--violet:#a78bfa;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 24% 0%,rgba(56,189,248,.10),transparent 32%),linear-gradient(180deg,#0b1220,#0f172a 42%,#0b1220);color:var(--text);font-family:Arial,sans-serif;padding:20px}
h1,h2,h3,p{margin-top:0} h1{font-size:32px;margin-bottom:6px;letter-spacing:0} h2{font-size:18px;margin-bottom:12px;letter-spacing:0} h3{font-size:15px;margin-bottom:8px}
button,input{font:inherit}
.topbar{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:18px}
.subtitle{color:var(--muted);line-height:1.45;max-width:920px}
.button{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid rgba(148,163,184,.22);background:#263244;color:white;text-decoration:none;border-radius:10px;padding:10px 12px;min-height:40px;cursor:pointer;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.button:hover{background:#334155}.button.primary{background:#0369a1}.button.small{min-height:34px;padding:7px 10px;font-size:14px}.button.ghost{background:transparent;border-color:var(--line)}
.layout{display:grid;grid-template-columns:300px minmax(0,1fr) 340px;gap:14px;align-items:start}
.card{background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));border:1px solid rgba(148,163,184,.18);border-radius:12px;padding:16px;box-shadow:0 18px 34px rgba(0,0,0,.22)}
.preset-list{display:grid;gap:9px}.preset{width:100%;text-align:left;color:white;background:rgba(15,23,42,.92);border:1px solid rgba(148,163,184,.22);border-radius:10px;padding:12px;cursor:pointer;transition:border-color .15s ease,background .15s ease,transform .15s ease}
.preset:hover{background:#111c30;border-color:#475569}.preset.active{border-color:var(--blue);background:linear-gradient(90deg,rgba(14,116,144,.34),rgba(15,23,42,.94));box-shadow:0 0 0 1px rgba(56,189,248,.28)}.preset-title{font-weight:bold}.preset-meta{color:var(--muted);font-size:12px;margin-top:5px;line-height:1.35}
.stage{min-height:520px;display:grid;grid-template-rows:auto 1fr;gap:12px}.schema-head{display:flex;justify-content:space-between;gap:12px;align-items:start}
.schema-tags{display:flex;gap:6px;flex-wrap:wrap}.pill{display:inline-flex;border:1px solid rgba(148,163,184,.22);background:#0f172a;color:#dbeafe;border-radius:999px;padding:5px 8px;font-size:12px}.pill.warn{color:#fde68a;border-color:#854d0e}.pill.ok{color:#86efac;border-color:#166534}
.diagram-wrap{background:radial-gradient(circle at 50% 42%,rgba(30,41,59,.72),#0b1220 62%);border:1px solid rgba(148,163,184,.20);border-radius:12px;min-height:440px;overflow:hidden;position:relative}
svg{width:100%;height:100%;min-height:440px;display:block}.zone{fill:#111827}.subject-head{fill:#e2e8f0;stroke:#ffffff;stroke-width:1.8}.subject-body{fill:#94a3b8;stroke:#e2e8f0;stroke-width:1}.subject-nose{fill:#0f172a}.camera{fill:#38bdf8}.camera-lens{fill:#0f172a}.camera-front{fill:#bae6fd}.light-body{fill:#f8fafc;stroke:#0f172a;stroke-width:1.6}.light-number{fill:#0f172a;font-size:6px;font-weight:bold}.beam{fill:rgba(245,158,11,.16);stroke:rgba(245,158,11,.42);stroke-width:.7}.beam.cool{fill:rgba(56,189,248,.13);stroke:rgba(56,189,248,.36)}.beam.rim{fill:rgba(167,139,250,.16);stroke:rgba(167,139,250,.42)}
.legend{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.legend-item{display:flex;align-items:center;gap:7px;background:rgba(15,23,42,.92);border:1px solid rgba(148,163,184,.20);border-radius:999px;padding:6px 9px;color:#dbeafe;font-size:12px}.legend-num{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#f8fafc;color:#0f172a;font-weight:bold}
.details-band{grid-column:2/-1;display:grid;grid-template-columns:minmax(0,1.4fr) minmax(260px,.8fr);gap:14px}.light-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.light-card{background:rgba(15,23,42,.90);border:1px solid rgba(148,163,184,.20);border-radius:10px;padding:12px}.light-title{display:flex;justify-content:space-between;gap:8px;font-weight:bold;margin-bottom:10px}.light-heading{display:flex;align-items:center;gap:8px}.kv{display:grid;grid-template-columns:82px 1fr;gap:6px;font-size:13px;color:#dbeafe}.kv span:nth-child(odd){color:var(--muted)}
.notes{color:#cbd5e1;line-height:1.45;font-size:14px}.notes ul{margin:8px 0 0 18px;padding:0}.notes li{margin:6px 0}.preview-card{background:linear-gradient(180deg,rgba(17,24,39,.96),rgba(15,23,42,.96))}.photo-preview{width:100%;aspect-ratio:4/5;background:#050816;border:1px solid rgba(148,163,184,.20);border-radius:10px;overflow:hidden;box-shadow:0 18px 30px rgba(0,0,0,.28)}.photo-preview img{display:block;width:100%;height:100%;object-fit:cover}.preview-note{color:var(--muted);font-size:13px;line-height:1.4;margin-top:12px}
.hardware{margin-top:12px}.hardware summary{cursor:pointer;color:#cbd5e1}.status{color:var(--muted);font-size:13px;margin:8px 0}.device-list{display:grid;gap:8px;margin-top:8px}.device{background:#0f172a;border:1px solid var(--line);border-radius:10px;padding:10px;color:white;text-align:left}.device.active{border-color:#38bdf8}.field label{display:block;color:#cbd5e1;font-size:13px;margin:10px 0 5px}.field input{width:100%;background:#0f172a;border:1px solid var(--line);border-radius:10px;color:white;padding:10px}.axis{margin-top:12px}.axis-head{display:flex;justify-content:space-between;color:#dbeafe;margin-bottom:6px}input[type=range]{width:100%;accent-color:#38bdf8}.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
@media(max-width:1100px){.layout{grid-template-columns:260px minmax(0,1fr)}.preview-card{grid-column:1/-1}.details-band{grid-column:1/-1}.stage{min-height:auto}}
@media(max-width:760px){body{padding:12px}.topbar{display:block}.topbar .button{margin-top:10px}.layout{grid-template-columns:1fr}.details-band{grid-template-columns:1fr}.schema-head{display:block}h1{font-size:26px}.diagram-wrap,svg{min-height:390px}.kv{grid-template-columns:84px 1fr}}
</style>
</head>
<body>
<div class="topbar">
  <div>
    <h1>NIWA Lighting</h1>
    <div class="subtitle">Schemi luce pratici per posizionare soggetto, camera, stativi e modificatori. Il controllo ESP32 resta disponibile come modulo sperimentale.</div>
  </div>
  <a class="button" id="dashboardLink" href="/">Dashboard</a>
</div>

<div class="layout">
  <section class="card">
    <h2>Schemi</h2>
    <div class="preset-list" id="presetList"></div>
  </section>

  <section class="card stage">
    <div class="schema-head">
      <div>
        <h2 id="schemaTitle">Schema luce</h2>
        <div class="subtitle" id="schemaSummary"></div>
      </div>
      <div class="schema-tags" id="schemaTags"></div>
    </div>
    <div class="diagram-wrap" id="diagramWrap"></div>
  </section>

  <section class="card preview-card">
    <h2>Anteprima risultato</h2>
    <div id="photoPreview"></div>
  </section>

  <section class="details-band">
    <div class="card">
      <h2>Dettagli luci</h2>
      <div class="light-grid" id="lightDetails"></div>
    </div>
    <div class="card">
      <h2>Note operative</h2>
      <div class="notes" id="setupNotes"></div>
    </div>
  </section>
</div>

<details class="card hardware">
  <summary>Modulo ESP32 sperimentale</summary>
  <div class="status" id="status">Caricamento modulo...</div>
  <div class="device-list" id="deviceList"></div>
  <div class="row"><button class="button small" onclick="refreshStatus()">Aggiorna stato</button></div>
  <div class="field"><label>Host ESP32</label><input id="deviceHost" placeholder="10.42.0.xxx"></div>
  <div class="row">
    <button class="button small primary" onclick="saveDevice()">Salva host</button>
    <button class="button small" onclick="centerDevice()">Centro</button>
    <button class="button small" onclick="setDemoMode()">Demo</button>
  </div>
  <div class="axis">
    <div class="axis-head"><span>Pan</span><strong id="panValue">90</strong></div>
    <input id="panSlider" type="range" min="30" max="150" value="90" oninput="queueMove()" onchange="sendMove()">
  </div>
  <div class="axis">
    <div class="axis-head"><span>Tilt</span><strong id="tiltValue">90</strong></div>
    <input id="tiltSlider" type="range" min="40" max="140" value="90" oninput="queueMove()" onchange="sendMove()">
  </div>
</details>

<script>
function serviceUrl(port, path=''){
  return `${window.location.protocol}//${window.location.hostname}:${port}${path}`;
}
document.getElementById('dashboardLink').href = serviceUrl(3000);

const SCHEMAS = [
  {
    id:'rembrandt', title:'Rembrandt', mood:'Ritratto classico',
    summary:'Key light alta a circa 45 gradi. Cerca il piccolo triangolo di luce sulla guancia in ombra.',
    tags:['1 luce','ritratto','contrastato'],
    subject:{x:50,y:52}, camera:{x:50,y:86},
    lights:[
      {id:'key',name:'Key light',role:'Principale',x:32,y:68,target:{x:50,y:52},angle:'45 gradi frontale laterale',height:'Poco sopra gli occhi',distance:'1 - 1.5 m',modifier:'Softbox medio o ombrello',beam:'warm'}
    ],
    notes:['Ruota il soggetto leggermente verso la luce se il triangolo sparisce.','Avvicina il softbox per ombre piu morbide, allontanalo per piu contrasto.','Tieni la camera sul lato opposto alla luce per mantenere profondita.'],
    safety:['Usa zavorra se il softbox e grande.','Evita tilt estremi dello stativo senza contrappeso.']
  },
  {
    id:'butterfly', title:'Butterfly / Paramount', mood:'Beauty pulito',
    summary:'Luce centrale alta sopra la camera, inclinata verso il volto. Ombra piccola sotto il naso.',
    tags:['1 luce','beauty','simmetrico'],
    subject:{x:50,y:50}, camera:{x:50,y:86},
    lights:[
      {id:'key',name:'Key light',role:'Principale',x:50,y:68,target:{x:50,y:50},angle:'Frontale alto, sopra asse camera',height:'30-60 cm sopra gli occhi',distance:'1 - 1.2 m',modifier:'Beauty dish o softbox',beam:'warm'}
    ],
    notes:['Funziona bene con volto frontale alla camera.','Se le orbite diventano scure, abbassa leggermente la luce.','Puoi aggiungere pannello riflettente sotto il mento.'],
    safety:['Attenzione a stativo davanti al soggetto e vicino alla camera.','Blocca bene il modificatore se e montato alto.']
  },
  {
    id:'clamshell', title:'Clamshell', mood:'Beauty morbido',
    summary:'Key light alta frontale e fill sotto il volto. Look pulito, pelle morbida, ombre ridotte.',
    tags:['2 luci','beauty','morbido'],
    subject:{x:50,y:50}, camera:{x:50,y:88},
    lights:[
      {id:'key',name:'Key light',role:'Principale',x:50,y:66,target:{x:50,y:50},angle:'Frontale alto, sopra asse camera',height:'Sopra gli occhi',distance:'1 m',modifier:'Softbox/beauty dish',beam:'warm'},
      {id:'fill',name:'Fill / riflettore',role:'Riempimento',x:50,y:76,target:{x:50,y:54},angle:'Frontale basso verso volto',height:'Sotto il mento',distance:'0.5 - 1 m',modifier:'Pannello o luce debole',beam:'cool'}
    ],
    notes:['Mantieni il fill 1-2 stop sotto la key se vuoi volume.','Per beauty molto pulito avvicina fill e key.','Ottimo per ritratto, makeup e cosplay glam.'],
    safety:['Non mettere il fill dove intralcia soggetto o camera.','Occhio ai riflessi se il soggetto porta occhiali.']
  },
  {
    id:'split', title:'Split Light', mood:'Drammatico netto',
    summary:'Luce laterale a 90 gradi. Meta volto illuminata, meta in ombra.',
    tags:['1 luce','drammatico','low key'],
    subject:{x:50,y:52}, camera:{x:50,y:86},
    lights:[
      {id:'key',name:'Side key',role:'Principale',x:20,y:52,target:{x:50,y:52},angle:'90 gradi laterale',height:'Altezza occhi o poco sopra',distance:'1 - 1.5 m',modifier:'Softbox con griglia',beam:'warm'}
    ],
    notes:['Ruota il volto poco alla volta per decidere quanta luce entra sul lato in ombra.','Con griglia controlli meglio lo spill sullo sfondo.','Perfetto per look dark, armor, cosplay villain.'],
    safety:['Stativo laterale fuori passaggio.','Con softbox grande usa sempre peso alla base.']
  },
  {
    id:'rim', title:'Rim + Key Soft', mood:'Separazione soggetto',
    summary:'Key morbida frontale laterale e rim dietro al soggetto per separarlo dallo sfondo.',
    tags:['2 luci','ritratto','cinematic'],
    subject:{x:50,y:52}, camera:{x:50,y:86},
    lights:[
      {id:'key',name:'Key soft',role:'Principale',x:32,y:68,target:{x:50,y:52},angle:'45 gradi frontale',height:'Sopra occhi',distance:'1 - 1.5 m',modifier:'Softbox',beam:'warm'},
      {id:'rim',name:'Rim light',role:'Contorno',x:72,y:28,target:{x:55,y:47},angle:'Dietro laterale verso spalle/capelli',height:'Sopra testa',distance:'1.5 - 2 m',modifier:'Griglia o snoot',beam:'rim'}
    ],
    notes:['Il rim deve colpire bordo capelli/spalla, non entrare diretto in lente.','Usa bandiere o griglia se crea flare.','Ottimo con sfondi scuri.'],
    safety:['Rim dietro al soggetto: segnala cavi e stativi.','Evita luce puntata direttamente negli occhi da dietro.']
  },
  {
    id:'cosplay', title:'Cosplay Hero', mood:'Epico controllato',
    summary:'Key laterale alta, rim colorato e fill leggero per mantenere dettaglio su costume e props.',
    tags:['3 luci','cosplay','colori'],
    subject:{x:50,y:50}, camera:{x:50,y:87},
    lights:[
      {id:'key',name:'Key dramatic',role:'Principale',x:30,y:68,target:{x:50,y:50},angle:'45 gradi alto laterale frontale',height:'Sopra testa',distance:'1.5 m',modifier:'Softbox/griglia',beam:'warm'},
      {id:'rim',name:'Rim color',role:'Accento',x:72,y:30,target:{x:56,y:47},angle:'Dietro laterale',height:'Sopra spalle',distance:'1.5 - 2 m',modifier:'Gel colore + griglia',beam:'rim'},
      {id:'fill',name:'Fill basso',role:'Dettaglio',x:58,y:74,target:{x:50,y:55},angle:'Basso frontale leggermente opposto alla key',height:'Torace',distance:'1 - 2 m',modifier:'Pannello o luce debole',beam:'cool'}
    ],
    notes:['Scegli rim complementare al colore dominante del costume.','Mantieni fill debole per non perdere mood.','Controlla riflessi su armature, props lucidi e lenti.'],
    safety:['Costumi voluminosi richiedono passaggi liberi.','Stativi zavorrati se il soggetto si muove o posa con props.']
  },
  {
    id:'product', title:'Product Small Setup', mood:'Oggetto/tabletop',
    summary:'Luce grande laterale, fill controllato e sfondo separato. Pensato per piccoli oggetti.',
    tags:['2-3 luci','prodotto','tabletop'],
    subject:{x:50,y:48}, camera:{x:50,y:86},
    lights:[
      {id:'key',name:'Large soft key',role:'Principale',x:30,y:56,target:{x:50,y:48},angle:'Laterale morbida leggermente frontale',height:'Poco sopra oggetto',distance:'0.5 - 1 m',modifier:'Softbox grande vicino',beam:'warm'},
      {id:'fill',name:'Card fill',role:'Riempimento',x:70,y:54,target:{x:50,y:48},angle:'Rimbalzo lato opposto',height:'Altezza oggetto',distance:'Vicino',modifier:'Pannello bianco/argento',beam:'cool'},
      {id:'back',name:'Background',role:'Sfondo',x:50,y:24,target:{x:50,y:10},angle:'Verso fondale dietro il prodotto',height:'Bassa o media',distance:'Dietro il soggetto',modifier:'Snoot/griglia opzionale',beam:'rim'}
    ],
    notes:['Avvicina molto la key per riflessi grandi e morbidi.','Usa cartoncini neri per disegnare bordi su oggetti lucidi.','Blocca camera su treppiede se fai focus stacking.'],
    safety:['Attenzione a cavi sul tavolo.','Non appoggiare modificatori caldi vicino a carta o tessuti.']
  }
];

let selectedSchema = SCHEMAS[0];
let CONFIG = null;
let ACTIVE = null;
let MOVE_TIMER = null;

function selectSchema(id){
  selectedSchema = SCHEMAS.find((schema)=>schema.id === id) || SCHEMAS[0];
  renderSchemas();
}

function renderSchemas(){
  document.getElementById('presetList').innerHTML = SCHEMAS.map((schema)=>`
    <button class="preset ${schema.id === selectedSchema.id ? 'active' : ''}" onclick="selectSchema('${schema.id}')">
      <div class="preset-title">${escapeHtml(schema.title)}</div>
      <div class="preset-meta">${escapeHtml(schema.mood)} · ${schema.tags.join(' · ')}</div>
    </button>
  `).join('');

  document.getElementById('schemaTitle').textContent = selectedSchema.title;
  document.getElementById('schemaSummary').textContent = selectedSchema.summary;
  document.getElementById('schemaTags').innerHTML = selectedSchema.tags.map((tag)=>`<span class="pill">${escapeHtml(tag)}</span>`).join('');
  document.getElementById('diagramWrap').innerHTML = buildDiagram(selectedSchema) + buildLegend(selectedSchema);
  document.getElementById('lightDetails').innerHTML = selectedSchema.lights.map(lightCard).join('');
  document.getElementById('setupNotes').innerHTML = listHtml(selectedSchema.notes);
  document.getElementById('photoPreview').innerHTML = previewHtml(selectedSchema);
}

function buildDiagram(schema){
  const subject = schema.subject;
  const camera = schema.camera;
  const lights = schema.lights.map((light, index)=>lightSvg(light, subject, index)).join('');
  return `
  <svg viewBox="0 0 100 100" role="img" aria-label="Schema luci ${escapeHtml(schema.title)}">
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#cbd5e1"></path>
      </marker>
    </defs>
    <rect class="zone" x="0" y="0" width="100" height="100"></rect>
    ${lights}
    <g transform="translate(${subject.x} ${subject.y})">
      <path class="subject-body" d="M -7 8 Q 0 1 7 8 L 7 12 L -7 12 Z"></path>
      <circle class="subject-head" cx="0" cy="0" r="5.6"></circle>
      <path class="subject-nose" d="M -2 5 L 2 5 L 0 9 Z"></path>
    </g>
    <g transform="translate(${camera.x} ${camera.y})">
      <path class="camera-front" d="M -3 -8 L 3 -8 L 0 -13 Z"></path>
      <rect class="camera" x="-6" y="-4" width="12" height="8" rx="1.5"></rect>
      <circle class="camera-lens" cx="0" cy="0" r="2.2"></circle>
    </g>
  </svg>`;
}

function buildLegend(schema){
  return `<div class="legend">${schema.lights.map((light, index)=>`
    <div class="legend-item"><span class="legend-num">${index + 1}</span><span>${escapeHtml(light.name)} · ${escapeHtml(light.role)}</span></div>
  `).join('')}</div>`;
}

function lightSvg(light, subject, index){
  const beamClass = light.beam === 'cool' ? 'beam cool' : light.beam === 'rim' ? 'beam rim' : 'beam';
  const bx1 = light.x;
  const by1 = light.y;
  const target = light.target || subject;
  const bx2 = target.x;
  const by2 = target.y;
  const dx = bx2 - bx1;
  const dy = by2 - by1;
  const len = Math.max(1, Math.sqrt(dx * dx + dy * dy));
  const sx = -dy / len * 2.4;
  const sy = dx / len * 2.4;
  const tx = -dy / len * 8;
  const ty = dx / len * 8;
  const p1x = bx1 + sx;
  const p1y = by1 + sy;
  const p2x = bx1 - sx;
  const p2y = by1 - sy;
  const p3x = bx2 - tx;
  const p3y = by2 - ty;
  const p4x = bx2 + tx;
  const p4y = by2 + ty;
  return `
    <polygon class="${beamClass}" points="${p1x},${p1y} ${p2x},${p2y} ${p3x},${p3y} ${p4x},${p4y}"></polygon>
    <circle class="light-body" cx="${light.x}" cy="${light.y}" r="4"></circle>
    <text class="light-number" x="${light.x}" y="${light.y + 2}" text-anchor="middle">${index + 1}</text>
  `;
}

function lightCard(light){
  return `<div class="light-card">
    <div class="light-title"><span class="light-heading"><span class="legend-num">${selectedSchema.lights.indexOf(light) + 1}</span>${escapeHtml(light.name)}</span><span class="pill ok">${escapeHtml(light.role)}</span></div>
    <div class="kv">
      <span>Angolo</span><span>${escapeHtml(light.angle)}</span>
      <span>Altezza</span><span>${escapeHtml(light.height)}</span>
      <span>Distanza</span><span>${escapeHtml(light.distance)}</span>
      <span>Modifier</span><span>${escapeHtml(light.modifier)}</span>
    </div>
  </div>`;
}

function listHtml(items){
  return `<ul>${items.map((item)=>`<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
}

function previewHtml(schema){
  const previews = {
    rembrandt: {file:'rembrandt.png', note:'Contrasto laterale e triangolo di luce sulla guancia in ombra.'},
    butterfly: {file:'butterfly.png', note:'Volto simmetrico con ombra piccola sotto il naso.'},
    clamshell: {file:'clamshell.png', note:'Beauty morbido con ombre aperte e fill dal basso.'},
    split: {file:'split.png', note:'Meta volto illuminata e meta in ombra per un look netto.'},
    rim: {file:'rim.png', note:'Key morbida davanti e contorno luminoso su capelli/spalle.'},
    cosplay: {file:'cosplay.png', note:'Look hero con key calda, fill leggero e rim colorato.'},
    product: {file:'product.png', note:'Oggetto con soft key laterale, fill opposto e sfondo separato.'}
  };
  const preview = previews[schema.id] || previews.rembrandt;
  return `<div class="photo-preview">
    <img src="/static/previews/${preview.file}" alt="Anteprima ${escapeHtml(schema.title)}">
  </div><div class="preview-note">${escapeHtml(preview.note)}</div>`;
}

function setStatus(message, danger=false){
  const status = document.getElementById('status');
  status.textContent = message;
  status.style.color = danger ? '#fca5a5' : '#94a3b8';
}

async function api(path, options={}){
  const res = await fetch(path, options);
  const data = await res.json();
  if(!res.ok || data.error){ throw new Error(data.error || `HTTP ${res.status}`); }
  return data;
}

async function loadDevices(){
  try{
    CONFIG = await api('/api/devices');
    ACTIVE = CONFIG.devices.find((device)=>device.id === CONFIG.active) || CONFIG.devices[0];
    renderHardware();
    setStatus('Modulo hardware caricato.');
  }catch(e){
    setStatus('Errore hardware: ' + e.message, true);
  }
}

function renderHardware(){
  if(!ACTIVE){ return; }
  document.getElementById('deviceList').innerHTML = CONFIG.devices.map((device)=>`
    <button class="device ${ACTIVE.id === device.id ? 'active' : ''}" onclick="selectDevice('${device.id}')">
      <strong>${escapeHtml(device.name)}</strong><br>
      <span class="status">${device.demo ? 'Demo' : escapeHtml(device.host || 'Host mancante')} · ${device.state.online ? 'Online' : 'Offline'}</span>
    </button>
  `).join('');
  document.getElementById('deviceHost').value = ACTIVE.host || '';
  const panSlider = document.getElementById('panSlider');
  const tiltSlider = document.getElementById('tiltSlider');
  panSlider.min = ACTIVE.pan.min; panSlider.max = ACTIVE.pan.max; panSlider.value = ACTIVE.state.pan;
  tiltSlider.min = ACTIVE.tilt.min; tiltSlider.max = ACTIVE.tilt.max; tiltSlider.value = ACTIVE.state.tilt;
  renderAxisValues();
}

function selectDevice(id){
  ACTIVE = CONFIG.devices.find((device)=>device.id === id);
  renderHardware();
}

function renderAxisValues(){
  document.getElementById('panValue').textContent = document.getElementById('panSlider').value;
  document.getElementById('tiltValue').textContent = document.getElementById('tiltSlider').value;
}

function queueMove(){
  renderAxisValues();
  clearTimeout(MOVE_TIMER);
  MOVE_TIMER = setTimeout(sendMove, 350);
}

async function sendMove(){
  if(!ACTIVE){ return; }
  clearTimeout(MOVE_TIMER);
  const pan = Number(document.getElementById('panSlider').value);
  const tilt = Number(document.getElementById('tiltSlider').value);
  try{
    const data = await api(`/api/devices/${ACTIVE.id}/move`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({pan,tilt})
    });
    CONFIG = data.config;
    ACTIVE = CONFIG.devices.find((device)=>device.id === data.device.id);
    renderHardware();
    setStatus(data.message || 'Posizione inviata.');
  }catch(e){ setStatus('Errore movimento: ' + e.message, true); }
}

async function centerDevice(){
  if(!ACTIVE){ return; }
  try{
    const data = await api(`/api/devices/${ACTIVE.id}/center`, {method:'POST'});
    CONFIG = data.config;
    ACTIVE = CONFIG.devices.find((device)=>device.id === data.device.id);
    renderHardware();
    setStatus('Modulo centrato.');
  }catch(e){ setStatus('Errore centro: ' + e.message, true); }
}

async function saveDevice(){
  if(!ACTIVE){ return; }
  try{
    const data = await api(`/api/devices/${ACTIVE.id}`, {
      method:'PUT',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:ACTIVE.name,host:document.getElementById('deviceHost').value.trim()})
    });
    CONFIG = data.config;
    ACTIVE = CONFIG.devices.find((device)=>device.id === data.device.id);
    renderHardware();
    setStatus('Host salvato.');
  }catch(e){ setStatus('Errore salvataggio: ' + e.message, true); }
}

async function setDemoMode(){
  document.getElementById('deviceHost').value = '';
  await saveDevice();
}

async function refreshStatus(){
  if(!ACTIVE){ return; }
  try{
    const data = await api(`/api/devices/${ACTIVE.id}/status`);
    CONFIG = data.config;
    ACTIVE = CONFIG.devices.find((device)=>device.id === data.device.id);
    renderHardware();
    setStatus(ACTIVE.state.message || 'Stato aggiornato.');
  }catch(e){ setStatus('Errore stato: ' + e.message, true); }
}

function escapeHtml(value){
  return String(value).replace(/[&<>"']/g,(char)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
}

renderSchemas();
loadDevices();
</script>
</body>
</html>
"""


@app.route("/api/devices")
def api_devices():
    config = load_config()
    return jsonify({
        "version": config.get("version", 1),
        "active": config.get("active"),
        "devices": [device_public(device) for device in config.get("devices", [])],
        "warning": config.get("warning"),
    })


@app.route("/api/devices/<device_id>")
def api_device(device_id):
    config = load_config()
    device = find_device(config, device_id)
    if not device:
        return jsonify({"error": "Modulo luce non trovato."}), 404
    return jsonify({"device": device_public(device)})


@app.route("/api/devices/<device_id>", methods=["PUT"])
def api_update_device(device_id):
    config = load_config()
    device = find_device(config, device_id)
    if not device:
        return jsonify({"error": "Modulo luce non trovato."}), 404

    payload = request.get_json(silent=True) or {}
    device["name"] = str(payload.get("name") or device["name"]).strip()
    device["host"] = str(payload.get("host") or "").strip()
    device["demo"] = not bool(device["host"])

    pan = payload.get("pan") or {}
    tilt = payload.get("tilt") or {}
    device["pan"]["min"] = clamp(pan.get("min", device["pan"]["min"]), 0, 180)
    device["pan"]["max"] = clamp(pan.get("max", device["pan"]["max"]), 0, 180)
    device["tilt"]["min"] = clamp(tilt.get("min", device["tilt"]["min"]), 0, 180)
    device["tilt"]["max"] = clamp(tilt.get("max", device["tilt"]["max"]), 0, 180)

    if device["pan"]["min"] > device["pan"]["max"]:
        device["pan"]["min"], device["pan"]["max"] = device["pan"]["max"], device["pan"]["min"]
    if device["tilt"]["min"] > device["tilt"]["max"]:
        device["tilt"]["min"], device["tilt"]["max"] = device["tilt"]["max"], device["tilt"]["min"]

    device["state"]["pan"] = clamp(device["state"]["pan"], device["pan"]["min"], device["pan"]["max"])
    device["state"]["tilt"] = clamp(device["state"]["tilt"], device["tilt"]["min"], device["tilt"]["max"])
    device["state"]["online"] = bool(device["demo"])
    device["state"]["message"] = "Configurazione salvata."

    save_config(config)
    return jsonify({
        "ok": True,
        "device": device_public(device),
        "config": {
            "version": config.get("version", 1),
            "active": config.get("active"),
            "devices": [device_public(item) for item in config.get("devices", [])],
        },
    })


@app.route("/api/devices/<device_id>/move", methods=["POST"])
def api_move(device_id):
    config = load_config()
    device = find_device(config, device_id)
    if not device:
        return jsonify({"error": "Modulo luce non trovato."}), 404

    payload = request.get_json(silent=True) or {}
    result = apply_position(device, payload.get("pan"), payload.get("tilt"))
    save_config(config)
    return jsonify({
        "ok": result["ok"],
        "message": device["state"]["message"],
        "device": device_public(device),
        "config": {
            "version": config.get("version", 1),
            "active": config.get("active"),
            "devices": [device_public(item) for item in config.get("devices", [])],
        },
    }), 200 if result["ok"] else 502


@app.route("/api/devices/<device_id>/center", methods=["POST"])
def api_center(device_id):
    config = load_config()
    device = find_device(config, device_id)
    if not device:
        return jsonify({"error": "Modulo luce non trovato."}), 404

    result = apply_position(device, device["pan"]["center"], device["tilt"]["center"])
    save_config(config)
    return jsonify({
        "ok": result["ok"],
        "message": device["state"]["message"],
        "device": device_public(device),
        "config": {
            "version": config.get("version", 1),
            "active": config.get("active"),
            "devices": [device_public(item) for item in config.get("devices", [])],
        },
    }), 200 if result["ok"] else 502


@app.route("/api/devices/<device_id>/status")
def api_status(device_id):
    config = load_config()
    device = find_device(config, device_id)
    if not device:
        return jsonify({"error": "Modulo luce non trovato."}), 404

    result = send_to_device(device, "/status")
    if result["ok"]:
        response = result.get("response", {})
        device["state"]["online"] = True
        device["state"]["last_seen"] = now_label()
        device["state"]["message"] = response.get("message", "Modulo online.")
        if "pan" in response:
            device["state"]["pan"] = clamp(response["pan"], device["pan"]["min"], device["pan"]["max"])
        if "tilt" in response:
            device["state"]["tilt"] = clamp(response["tilt"], device["tilt"]["min"], device["tilt"]["max"])
    else:
        device["state"]["online"] = False
        device["state"]["message"] = result["error"]

    save_config(config)
    return jsonify({
        "ok": result["ok"],
        "device": device_public(device),
        "config": {
            "version": config.get("version", 1),
            "active": config.get("active"),
            "devices": [device_public(item) for item in config.get("devices", [])],
        },
    }), 200 if result["ok"] else 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055)
