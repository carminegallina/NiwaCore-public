from flask import Flask, jsonify, request
import requests
import json
import os
import copy

app = Flask(__name__)

LAT = 40.771
LON = 14.789

DATA_FILE = "/data/drone_batteries.json"
DRONES_LIBRARY_FILE = "/data/drones_library.json"
MY_DRONES_FILE = "/data/my_drones.json"

DEFAULT_DRONE_LIBRARY = {
    "dji_neo": {
        "id": "dji_neo",
        "brand": "DJI",
        "model": "Neo",
        "name": "DJI Neo",
        "max_wind_kmh": 28.8,
        "max_wind_ms": 8.0,
        "source": "official",
        "notes": "Official wind resistance 8 m/s."
    },
    "dji_avata_2": {
        "id": "dji_avata_2",
        "brand": "DJI",
        "model": "Avata 2",
        "name": "DJI Avata 2",
        "max_wind_kmh": 38.5,
        "max_wind_ms": 10.7,
        "source": "official",
        "notes": "Official wind resistance 10.7 m/s."
    },
    "dji_avata": {
        "id": "dji_avata",
        "brand": "DJI",
        "model": "Avata",
        "name": "DJI Avata",
        "max_wind_kmh": 38.5,
        "max_wind_ms": 10.7,
        "source": "official",
        "notes": "Official wind resistance 10.7 m/s."
    },
    "dji_mini_3_pro": {
        "id": "dji_mini_3_pro",
        "brand": "DJI",
        "model": "Mini 3 Pro",
        "name": "DJI Mini 3 Pro",
        "max_wind_kmh": 38.5,
        "max_wind_ms": 10.7,
        "source": "official",
        "notes": "Official wind resistance 10.7 m/s."
    },
    "dji_mini_4_pro": {
        "id": "dji_mini_4_pro",
        "brand": "DJI",
        "model": "Mini 4 Pro",
        "name": "DJI Mini 4 Pro",
        "max_wind_kmh": 38.5,
        "max_wind_ms": 10.7,
        "source": "official",
        "notes": "Official wind resistance 10.7 m/s."
    },
    "dji_air_3": {
        "id": "dji_air_3",
        "brand": "DJI",
        "model": "Air 3",
        "name": "DJI Air 3",
        "max_wind_kmh": 43.2,
        "max_wind_ms": 12.0,
        "source": "official",
        "notes": "Official wind resistance 12 m/s."
    },
    "dji_air_3s": {
        "id": "dji_air_3s",
        "brand": "DJI",
        "model": "Air 3S",
        "name": "DJI Air 3S",
        "max_wind_kmh": 43.2,
        "max_wind_ms": 12.0,
        "source": "official",
        "notes": "Official wind resistance 12 m/s."
    },
    "dji_mavic_3_pro": {
        "id": "dji_mavic_3_pro",
        "brand": "DJI",
        "model": "Mavic 3 Pro",
        "name": "DJI Mavic 3 Pro",
        "max_wind_kmh": 43.2,
        "max_wind_ms": 12.0,
        "source": "official",
        "notes": "Official wind resistance 12 m/s."
    },
}

DEFAULT_MY_DRONES = {
    "active": "dji_neo",
    "items": ["dji_neo", "dji_avata_2"],
    "custom": {},
}

DEFAULT_BATTERIES = {
    "dji_neo": {"battery_count": 2, "batteries": [100, 100]},
    "dji_avata_2": {"battery_count": 3, "batteries": [100, 100, 100]},
}


def clone_default(data):
    return copy.deepcopy(data)


def save_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_json_file(path, default_data, create_if_missing=False):
    if not os.path.exists(path):
        data = clone_default(default_data)
        if create_if_missing:
            save_json_file(path, data)
        return data

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    return clone_default(default_data)


def load_drone_library():
    library = load_json_file(
        DRONES_LIBRARY_FILE,
        DEFAULT_DRONE_LIBRARY,
        create_if_missing=True
    )

    changed = False
    for drone_id, profile in DEFAULT_DRONE_LIBRARY.items():
        if drone_id not in library:
            library[drone_id] = clone_default(profile)
            changed = True
        elif isinstance(library[drone_id], dict):
            for key, value in profile.items():
                if key not in library[drone_id]:
                    library[drone_id][key] = value
                    changed = True

    if changed:
        save_json_file(DRONES_LIBRARY_FILE, library)

    return library


def load_my_drones(library=None):
    if library is None:
        library = load_drone_library()

    my_drones = load_json_file(
        MY_DRONES_FILE,
        DEFAULT_MY_DRONES,
        create_if_missing=True
    )

    custom = my_drones.get("custom")
    if not isinstance(custom, dict):
        custom = {}

    clean_custom = {}
    for drone_id, profile in custom.items():
        clean_profile = clean_drone_profile(profile, drone_id, source="user")
        if clean_profile:
            clean_custom[drone_id] = clean_profile

    valid_profiles = {}
    valid_profiles.update(library)
    valid_profiles.update(clean_custom)

    items = my_drones.get("items")
    if not isinstance(items, list):
        items = DEFAULT_MY_DRONES["items"]

    valid_items = []
    for drone_id in items:
        if drone_id in valid_profiles and drone_id not in valid_items:
            valid_items.append(drone_id)

    if not valid_items:
        valid_items = [
            drone_id for drone_id in DEFAULT_MY_DRONES["items"]
            if drone_id in library
        ]

    if not valid_items and library:
        valid_items = [next(iter(library))]

    active = my_drones.get("active")
    if active not in valid_items:
        active = valid_items[0] if valid_items else "dji_neo"

    clean_my_drones = {
        "active": active,
        "items": valid_items,
        "custom": clean_custom,
    }

    if clean_my_drones != my_drones:
        save_json_file(MY_DRONES_FILE, clean_my_drones)

    return clean_my_drones


def clean_drone_profile(profile, drone_id, source="user"):
    if not isinstance(profile, dict):
        return None

    brand = str(profile.get("brand", "")).strip()
    model = str(profile.get("model", "")).strip()
    name = str(profile.get("name", "")).strip()

    if not name:
        name = " ".join(part for part in [brand, model] if part).strip()

    try:
        max_wind_kmh = float(profile.get("max_wind_kmh", 0))
    except (TypeError, ValueError):
        max_wind_kmh = 0

    try:
        max_wind_ms = float(profile.get("max_wind_ms", 0))
    except (TypeError, ValueError):
        max_wind_ms = 0

    if max_wind_kmh <= 0 and max_wind_ms > 0:
        max_wind_kmh = round(max_wind_ms * 3.6, 1)

    if max_wind_ms <= 0 and max_wind_kmh > 0:
        max_wind_ms = round(max_wind_kmh / 3.6, 1)

    if not brand or not model or not name or max_wind_kmh <= 0:
        return None

    return {
        "id": drone_id,
        "brand": brand,
        "model": model,
        "name": name,
        "max_wind_kmh": round(max_wind_kmh, 1),
        "max_wind_ms": round(max_wind_ms, 1),
        "source": str(profile.get("source", source)).strip() or source,
        "notes": str(profile.get("notes", "")).strip(),
    }


def make_custom_drone_id(brand, model, existing_ids):
    base = f"custom_{brand}_{model}".lower()
    cleaned = []

    for char in base:
        if char.isascii() and char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append("_")

    drone_id = "_".join("".join(cleaned).split("_"))
    if not drone_id or drone_id == "custom":
        drone_id = "custom_drone"

    candidate = drone_id
    counter = 2
    while candidate in existing_ids:
        candidate = f"{drone_id}_{counter}"
        counter += 1

    return candidate


def get_drone_profiles(library=None, my_drones=None):
    if library is None:
        library = load_drone_library()
    if my_drones is None:
        my_drones = load_my_drones(library)

    profiles = {}
    profiles.update(library)
    profiles.update(my_drones.get("custom", {}))
    return profiles


def load_battery_data():
    if not os.path.exists(DATA_FILE):
        save_battery_data(DEFAULT_BATTERIES)
        return DEFAULT_BATTERIES

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_BATTERIES


def save_battery_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIWA Drone Panel</title>

<style>
body{margin:0;font-family:Arial,sans-serif;background:#111827;color:white;padding:20px}
.topbar{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;margin-bottom:24px}
.topbar a{color:white;text-decoration:none;background:#374151;padding:10px 12px;border-radius:10px}
.topbar a:hover{background:#4b5563}
h1{margin:0 0 8px 0}.subtitle{color:#9ca3af}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
.card{background:#1f2937;border-radius:16px;padding:18px;box-shadow:0 8px 20px rgba(0,0,0,.25)}
.card h2{margin-top:0;font-size:20px}.value{font-size:28px;font-weight:bold;margin:8px 0}.label{color:#9ca3af;font-size:14px}
.button{display:block;background:#374151;color:white;text-decoration:none;padding:12px;border-radius:10px;margin:8px 0}
.warning{background:#7f1d1d;padding:12px;border-radius:10px;margin-top:20px;color:#fecaca}
.small{color:#9ca3af;font-size:13px;margin-top:14px}
input,select{width:100%;padding:10px;border-radius:8px;border:none;margin-top:10px;box-sizing:border-box}
button{width:100%;padding:10px;border-radius:8px;border:none;margin-top:8px;background:#374151;color:white}
.safe{background:#064e3b}.caution{background:#78350f}.danger{background:#7f1d1d}
.checkitem{display:flex;gap:10px;align-items:center;margin:10px 0;color:#e5e7eb}
.checkitem input{width:auto;margin:0}
.drone-row{display:flex;gap:8px;align-items:center;margin-top:8px}
.drone-row button{width:auto;min-width:90px;margin-top:10px}
.drone-list{display:flex;flex-direction:column;gap:8px;margin-top:12px}
.drone-pill{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;background:#111827;border-radius:10px;padding:10px}
.drone-pill.active{border:1px solid #3b82f6}
.drone-pill button{width:auto;margin:0;padding:8px 10px}
.drone-meta{color:#9ca3af;font-size:12px;margin-top:3px}
.custom-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}

.battery-section{
    margin-top:16px;
    background:#1f2937;
    border-radius:16px;
    padding:18px;
    box-shadow:0 8px 20px rgba(0,0,0,.25);
}

.battery-header{
    display:grid;
    grid-template-columns:1fr minmax(160px,220px);
    gap:12px;
    align-items:end;
}

.battery-list{
    display:flex;
    flex-direction:row;
    gap:14px;
    overflow-x:auto;
    padding-top:14px;
    padding-bottom:4px;
}

.battery{
    min-width:240px;
    padding:14px;
    border-radius:14px;
    background:#111827;
    flex:0 0 auto;
}

.battery.green{border:2px solid #22c55e}
.battery.yellow{border:2px solid #eab308}
.battery.red{border:2px solid #ef4444}

.slider-row{
    display:flex;
    align-items:center;
    gap:10px;
    margin-top:10px;
}

.slider-box{
    flex:1;
    overflow:visible;
    padding:0 9px;
}

.battery-slider{
    --battery-level:0%;
    width:calc(100% + 18px);
    margin-left:-9px;
    margin-right:-9px;
    padding:0;
    appearance:none;
    -webkit-appearance:none;
    background:transparent;
}

.battery-slider::-webkit-slider-runnable-track{
    height:8px;
    background:linear-gradient(to right,#3b82f6 0%,#3b82f6 var(--battery-level),#374151 var(--battery-level),#374151 100%);
    border-radius:999px;
}

.battery-slider::-webkit-slider-thumb{
    -webkit-appearance:none;
    appearance:none;
    width:18px;
    height:18px;
    border-radius:50%;
    background:#e5e7eb;
    border:2px solid #111827;
    margin-top:-5px;
}

.battery-slider::-moz-range-track{
    height:8px;
    background:#374151;
    border-radius:999px;
}

.battery-slider::-moz-range-progress{
    height:8px;
    background:#3b82f6;
    border-radius:999px;
}

.battery-slider::-moz-range-thumb{
    width:18px;
    height:18px;
    border-radius:50%;
    background:#e5e7eb;
    border:2px solid #111827;
}

.percent{min-width:52px;text-align:right;font-weight:bold}

@media(max-width:700px){
    .battery-header{grid-template-columns:1fr}
    .drone-row{display:block}
    .drone-row button{width:100%}
    .custom-grid{grid-template-columns:1fr}
    .topbar{display:block}
    .topbar a{display:inline-block;margin-top:10px}
}
</style>
</head>

<body>

<div class="topbar">
<div>
<h1>🚁 NIWA Drone Panel</h1>
<div class="subtitle">Meteo operativo, batterie, checklist e sicurezza drone.</div>
</div>
<a id="dashboardLink" href="/">Dashboard</a>
</div>

<div class="grid">

<div class="card" id="safetyCard">
<h2>🛡 Drone Safety</h2>

<select id="droneSelect" onchange="saveDrone()">
<option value="dji_neo">DJI Neo</option>
<option value="dji_avata_2">DJI Avata 2</option>
</select>

<div class="value" id="safetyStatus">--</div>
<div class="label" id="safetyReason">Analisi condizioni...</div>
<div class="label" id="droneLimit">Limite vento drone: --</div>
</div>

<div class="card">
<h2>Gestione Droni</h2>
<div class="label">Gestisci libreria, droni posseduti e custom in una pagina dedicata.</div>
<a class="button" href="/drones">Apri gestione droni</a>
</div>

<div class="card">
<h2>📍 Posizione meteo</h2>
<div class="value" id="place">--</div>
<div class="label" id="coords">Coordinate: --</div>
<div class="label" id="source">Fonte: --</div>
<input id="placeInput" placeholder="Es. Napoli">
<button onclick="savePlace()">Imposta luogo</button>
<button onclick="clearPlace()">Usa fallback</button>
</div>

<div class="card"><h2>🌡 Temperatura</h2><div class="value" id="temp">--</div><div class="label">Temperatura attuale</div></div>
<div class="card"><h2>💧 Umidità</h2><div class="value" id="humidity">--</div><div class="label">Umidità relativa</div></div>
<div class="card"><h2>🌬 Vento 10 m</h2><div class="value" id="wind10">--</div><div class="label">Vicino al suolo</div></div>
<div class="card"><h2>🚁 Vento 80 m</h2><div class="value" id="wind80">--</div><div class="label">Quota indicativa drone</div></div>
<div class="card"><h2>🚁 Vento 120 m</h2><div class="value" id="wind120">--</div><div class="label">Quota limite tipica UAS</div></div>
<div class="card"><h2>💨 Raffiche</h2><div class="value" id="gusts">--</div><div class="label">Raffiche a 10 m</div></div>
<div class="card"><h2>☔ Pioggia</h2><div class="value" id="rain">--</div><div class="label">Precipitazione oraria</div></div>
<div class="card"><h2>🧭 Direzione</h2><div class="value" id="direction">--</div><div class="label">Direzione vento</div></div>

<div class="card">
<h2>✅ Checklist Pre-volo</h2>
<label class="checkitem"><input type="checkbox" data-check="battery_drone"> Batterie drone cariche</label>
<label class="checkitem"><input type="checkbox" data-check="battery_rc"> Radiocomando carico</label>
<label class="checkitem"><input type="checkbox" data-check="memory"> SD / memoria libera</label>
<label class="checkitem"><input type="checkbox" data-check="dflight"> Area verificata su d-flight</label>
<label class="checkitem"><input type="checkbox" data-check="wind"> Vento e raffiche controllati</label>
<label class="checkitem"><input type="checkbox" data-check="rth"> RTH e home point verificati</label>
<label class="checkitem"><input type="checkbox" data-check="propellers"> Eliche controllate</label>
<label class="checkitem"><input type="checkbox" data-check="people"> Area decollo/atterraggio sicura</label>
<button onclick="resetChecklist()">Reset checklist</button>
</div>

<div class="card">
<h2>🗺 Mappe & Regole</h2>
<a class="button" href="https://www.d-flight.it/web-app/" target="_blank">Apri d-flight</a>
<a class="button" href="https://www.windy.com/" target="_blank">Apri Windy</a>
<a class="button" href="https://www.uavforecast.com/" target="_blank">Apri UAV Forecast</a>
</div>

</div>

<div class="battery-section">
<div class="battery-header">
<div>
<h2>🔋 Batterie Drone</h2>
<div class="label">Gestione manuale delle batterie del drone selezionato. I valori vengono salvati sul Raspberry.</div>
</div>

<div>
<div class="label">Numero batterie</div>
<input id="batteryCount" type="number" min="1" max="12" value="3">
<button onclick="saveBatteryCount()">Salva</button>
</div>
</div>

<div id="batteryList" class="battery-list"></div>
</div>

<div class="small" id="updated">Aggiornamento: --</div>

<div class="warning">
⚠️ Dati meteo previsionali. Verifica sempre condizioni reali, app DJI, d-flight ufficiale e normativa applicabile.
</div>

<script>
function serviceUrl(port, path=''){
    return `${window.location.protocol}//${window.location.hostname}:${port}${path}`;
}

document.getElementById('dashboardLink').href = serviceUrl(3000);

let DRONES = {
    dji_neo: { id: 'dji_neo', name: 'DJI Neo', maxWind: 28.8 },
    dji_avata_2: { id: 'dji_avata_2', name: 'DJI Avata 2', maxWind: 38.5 }
};

let MY_DRONES = {
    active: 'dji_neo',
    items: ['dji_neo', 'dji_avata_2']
};

function currentDrone(){
    const saved = localStorage.getItem('niwa_drone') || MY_DRONES.active || 'dji_neo';

    if(DRONES[saved]){
        return saved;
    }

    const firstAvailable = MY_DRONES.items.find((droneId)=>DRONES[droneId]);
    const fallback = firstAvailable || 'dji_neo';
    localStorage.setItem('niwa_drone', fallback);
    return fallback;
}

function normalizeDroneProfile(id, profile){
    return {
        id,
        name: profile.name || `${profile.brand || ''} ${profile.model || ''}`.trim() || id,
        brand: profile.brand || '',
        model: profile.model || '',
        maxWind: Number(profile.max_wind_kmh || profile.maxWind || 0),
        maxWindMs: Number(profile.max_wind_ms || 0),
        source: profile.source || '',
        notes: profile.notes || ''
    };
}

function populateDroneSelect(){
    const select = document.getElementById('droneSelect');
    const selected = currentDrone();
    select.innerHTML = '';

    const itemIds = MY_DRONES.items.filter((droneId)=>DRONES[droneId]);
    const options = itemIds.length ? itemIds : Object.keys(DRONES);

    options.forEach((droneId)=>{
        const option = document.createElement('option');
        option.value = droneId;
        option.textContent = DRONES[droneId].name;
        select.appendChild(option);
    });

    select.value = DRONES[selected] ? selected : options[0];
}

function setDroneManagerStatus(message){
    const status = document.getElementById('droneManagerStatus');
    if(status){
        status.textContent = message || '';
    }
}

function renderDroneManager(){
    const librarySelect = document.getElementById('libraryDroneSelect');
    const myDroneList = document.getElementById('myDroneList');

    if(!librarySelect || !myDroneList){
        return;
    }

    const myDroneIds = MY_DRONES.items.filter((droneId)=>DRONES[droneId]);
    const libraryIds = Object.keys(DRONES).sort((a,b)=>DRONES[a].name.localeCompare(DRONES[b].name));
    const addableIds = libraryIds.filter((droneId)=>!myDroneIds.includes(droneId));

    librarySelect.innerHTML = '';

    if(addableIds.length){
        addableIds.forEach((droneId)=>{
            const option = document.createElement('option');
            option.value = droneId;
            option.textContent = `${DRONES[droneId].brand || 'Drone'} - ${DRONES[droneId].name}`;
            librarySelect.appendChild(option);
        });
        librarySelect.disabled = false;
    }else{
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Tutti i droni della libreria sono gia presenti';
        librarySelect.appendChild(option);
        librarySelect.disabled = true;
    }

    myDroneList.innerHTML = '';

    myDroneIds.forEach((droneId)=>{
        const drone = DRONES[droneId];
        const div = document.createElement('div');
        div.className = 'drone-pill' + (droneId === currentDrone() ? ' active' : '');
        div.innerHTML = `
            <div>
                <strong>${drone.name}</strong>
                <div class="drone-meta">${drone.brand || 'Drone'} ${drone.model || ''} - vento max ${drone.maxWind.toFixed(1)} km/h</div>
            </div>
            <button onclick="removeMyDrone('${droneId}')">Rimuovi</button>
        `;
        myDroneList.appendChild(div);
    });
}

async function loadDrones(){
    try{
        const res = await fetch('/api/drones');
        const data = await res.json();

        if(data.error){ throw new Error(data.error); }

        const loadedDrones = {};
        Object.entries(data.profiles || data.library || {}).forEach(([id, profile])=>{
            loadedDrones[id] = normalizeDroneProfile(id, profile);
        });

        if(Object.keys(loadedDrones).length){
            DRONES = loadedDrones;
        }

        if(data.my_drones && Array.isArray(data.my_drones.items)){
            MY_DRONES = data.my_drones;
        }
    }catch(e){
        document.getElementById('droneLimit').textContent = 'Profili drone offline: uso fallback locale.';
    }

    populateDroneSelect();
    renderDroneManager();
}

function loadDrone(){
    populateDroneSelect();
    renderDroneManager();
}

function saveDrone(){
    const selected = document.getElementById('droneSelect').value;
    MY_DRONES.active = selected;
    localStorage.setItem('niwa_drone', selected);
    setActiveDrone(selected);
    loadWeather();
    loadBatteries();
    renderDroneManager();
}

async function refreshDrones(){
    await loadDrones();
    loadWeather();
    loadBatteries();
}

async function setActiveDrone(droneId){
    try{
        await fetch('/api/my-drones/active', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({drone:droneId})
        });
    }catch(e){}
}

async function addSelectedDrone(){
    const select = document.getElementById('libraryDroneSelect');
    const drone = select.value;

    if(!drone){
        return;
    }

    try{
        const res = await fetch('/api/my-drones/add', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({drone})
        });
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }
        setDroneManagerStatus('Drone aggiunto.');
        await refreshDrones();
    }catch(e){
        setDroneManagerStatus('Errore aggiunta drone: ' + e.message);
    }
}

async function removeMyDrone(drone){
    try{
        const res = await fetch('/api/my-drones/remove', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({drone})
        });
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }
        localStorage.setItem('niwa_drone', data.my_drones.active);
        setDroneManagerStatus('Drone rimosso.');
        await refreshDrones();
    }catch(e){
        setDroneManagerStatus('Errore rimozione drone: ' + e.message);
    }
}

async function addCustomDrone(){
    const payload = {
        brand: document.getElementById('customBrand').value.trim(),
        model: document.getElementById('customModel').value.trim(),
        name: document.getElementById('customName').value.trim(),
        max_wind_kmh: Number(document.getElementById('customWindKmh').value),
        notes: document.getElementById('customNotes').value.trim()
    };

    try{
        const res = await fetch('/api/custom-drones', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(payload)
        });
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }

        ['customBrand','customModel','customName','customWindKmh','customNotes'].forEach((id)=>{
            document.getElementById(id).value = '';
        });

        localStorage.setItem('niwa_drone', data.my_drones.active);
        setDroneManagerStatus('Drone custom aggiunto.');
        await refreshDrones();
    }catch(e){
        setDroneManagerStatus('Errore custom: ' + e.message);
    }
}

function batteryColor(value){
    if(value >= 80) return 'green';
    if(value >= 30) return 'yellow';
    return 'red';
}

function updateBatterySliderFill(slider){
    slider.style.setProperty('--battery-level', slider.value + '%');
}

async function loadBatteries(){
    const drone = currentDrone();
    const res = await fetch(`/api/batteries?drone=${drone}`);
    const d = await res.json();

    document.getElementById('batteryCount').value = d.battery_count;

    const list = document.getElementById('batteryList');
    list.innerHTML = '';

    d.batteries.forEach((value, index)=>{
        const color = batteryColor(value);

        const div = document.createElement('div');
        div.className = `battery ${color}`;

        div.innerHTML = `
            <strong>Batteria ${index + 1}</strong>
            <div class="slider-row">
                <div class="slider-box">
                    <input class="battery-slider" type="range" min="0" max="100" value="${value}" id="battery_${index}" style="--battery-level:${value}%" oninput="updateBatteryLabel(${index})">
                </div>
                <span class="percent" id="battery_label_${index}">${value}%</span>
            </div>
            <button onclick="saveBattery(${index})">OK</button>
        `;

        list.appendChild(div);
    });
}

function updateBatteryLabel(index){
    const slider = document.getElementById(`battery_${index}`);
    const label = document.getElementById(`battery_label_${index}`);
    updateBatterySliderFill(slider);
    label.textContent = slider.value + '%';
}

async function saveBattery(index){
    const drone = currentDrone();
    const value = Number(document.getElementById(`battery_${index}`).value);

    await fetch('/api/batteries/update', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({drone, index, value})
    });

    loadBatteries();
}

async function saveBatteryCount(){
    const drone = currentDrone();
    const count = Number(document.getElementById('batteryCount').value);

    await fetch('/api/batteries/count', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({drone, count})
    });

    loadBatteries();
}

function savePlace(){
    const value = document.getElementById('placeInput').value.trim();
    if(value){
        localStorage.setItem('niwa_place', value);
        loadWeather();
    }
}

function clearPlace(){
    localStorage.removeItem('niwa_place');
    loadWeather();
}

function loadChecklist(){
    document.querySelectorAll('[data-check]').forEach(cb=>{
        const key = 'niwa_check_' + cb.dataset.check;
        cb.checked = localStorage.getItem(key) === 'true';
        cb.addEventListener('change', ()=>{
            localStorage.setItem(key, cb.checked);
        });
    });
}

function resetChecklist(){
    document.querySelectorAll('[data-check]').forEach(cb=>{
        cb.checked = false;
        localStorage.removeItem('niwa_check_' + cb.dataset.check);
    });
}

function updateSafety(d){
    const drone = DRONES[currentDrone()] || DRONES.dji_neo;
    const maxWind = Number(drone.maxWind || 0);
    const okLimit = maxWind * 0.65;
    const cautionLimit = maxWind * 0.90;

    const gusts = Number(d.gusts || 0);
    const rain = Number(d.rain || 0);
    const wind80 = Number(d.wind80 || 0);
    const wind120 = Number(d.wind120 || 0);
    const worstWind = Math.max(gusts, wind80, wind120);

    const card = document.getElementById('safetyCard');
    const status = document.getElementById('safetyStatus');
    const reason = document.getElementById('safetyReason');
    const limit = document.getElementById('droneLimit');

    card.classList.remove('safe','caution','danger');

    let level = 'safe';
    let text = '🟢 OK';
    let msg = `Condizioni entro margine prudenziale per ${drone.name}.`;

    if(rain > 0){
        level = 'danger';
        text = '🔴 SCONSIGLIATO';
        msg = 'Pioggia prevista/rilevata. Evita il volo salvo condizioni realmente sicure e consentite.';
    } else if(worstWind >= cautionLimit){
        level = 'danger';
        text = '🔴 SCONSIGLIATO';
        msg = `Vento/raffiche vicini o oltre il margine operativo prudente per ${drone.name}.`;
    } else if(worstWind >= okLimit){
        level = 'caution';
        text = '🟡 ATTENZIONE';
        msg = `Vento moderato rispetto al limite di ${drone.name}. Valuta area, quota, esperienza e batteria.`;
    }

    card.classList.add(level);
    status.textContent = text;
    reason.textContent = msg;
    limit.textContent = `Drone: ${drone.name} — resistenza vento max: ${maxWind.toFixed(1)} km/h`;
}

async function loadWeather(){
    try{
        let url = '/api/weather';
        const savedPlace = localStorage.getItem('niwa_place');

        if(savedPlace){
            url = `/api/weather?place=${encodeURIComponent(savedPlace)}&source=manual`;
        }

        const res = await fetch(url);
        const d = await res.json();

        if(d.error){ throw new Error(d.error); }

        document.getElementById('place').textContent = d.place;
        document.getElementById('coords').textContent = `Coordinate: ${d.lat}, ${d.lon}`;
        document.getElementById('source').textContent = `Fonte: ${d.source}`;

        document.getElementById('temp').textContent = d.temperature + ' °C';
        document.getElementById('humidity').textContent = d.humidity + ' %';
        document.getElementById('wind10').textContent = d.wind10 + ' km/h';
        document.getElementById('wind80').textContent = d.wind80 + ' km/h';
        document.getElementById('wind120').textContent = d.wind120 + ' km/h';
        document.getElementById('gusts').textContent = d.gusts + ' km/h';
        document.getElementById('rain').textContent = d.rain + ' mm';
        document.getElementById('direction').textContent = d.direction + '°';
        document.getElementById('updated').textContent = 'Aggiornamento: ' + d.updated;

        updateSafety(d);

    }catch(e){
        document.getElementById('updated').textContent = 'Errore meteo: ' + e.message;
    }
}

async function init(){
    await loadDrones();
    loadDrone();
    loadChecklist();
    loadBatteries();
    loadWeather();
}

init();
setInterval(loadWeather, 10 * 60 * 1000);
</script>

</body>
</html>
"""


@app.route("/drones")
def drones_page():
    return """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIWA - Gestione Droni</title>
<style>
body{margin:0;font-family:Arial,sans-serif;background:#111827;color:white;padding:20px}
h1{margin-bottom:8px}.subtitle{color:#9ca3af;margin-bottom:20px}
.topbar{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:16px}
.topbar a{color:white;text-decoration:none;background:#374151;padding:10px 12px;border-radius:10px}
.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,360px);gap:16px}
.card{background:#1f2937;border-radius:16px;padding:18px;box-shadow:0 8px 20px rgba(0,0,0,.25)}
.card h2{margin-top:0;font-size:20px}.label{color:#9ca3af;font-size:14px}.small{color:#9ca3af;font-size:13px;margin-top:10px}
input,select{width:100%;padding:10px;border-radius:8px;border:none;margin-top:10px;box-sizing:border-box}
button{padding:10px 12px;border-radius:8px;border:none;background:#374151;color:white}
button:hover,.topbar a:hover{background:#4b5563}.primary{background:#2563eb}.danger-btn{background:#7f1d1d}
.toolbar{display:grid;grid-template-columns:minmax(180px,280px) 1fr;gap:12px;align-items:end;margin-bottom:14px}
.drone-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.drone-card{background:#111827;border-radius:12px;padding:14px;border:1px solid transparent}
.drone-card.mine{border-color:#3b82f6}.drone-card.owned{border-color:#22c55e}.drone-card h3{margin:0 0 6px 0;font-size:17px}
.meta{color:#9ca3af;font-size:13px;line-height:1.4}.actions{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.owned-label{color:#86efac;font-size:13px;font-weight:bold;margin-top:12px}
.custom-grid{display:grid;grid-template-columns:1fr;gap:8px}.status{min-height:18px}
@media(max-width:850px){.layout{grid-template-columns:1fr}.toolbar{grid-template-columns:1fr}.topbar{display:block}.topbar a{display:inline-block;margin-top:10px}}
</style>
</head>
<body>
<div class="topbar">
<div>
<h1>Gestione Droni</h1>
<div class="subtitle">Libreria locale, droni posseduti e profili custom.</div>
</div>
<a href="/">Torna al Drone Panel</a>
</div>

<div class="layout">
<div class="card">
<h2>Libreria droni</h2>
<div class="toolbar">
<div>
<div class="label">Marca</div>
<select id="brandFilter" onchange="renderDroneLibrary()"></select>
</div>
<div class="label">La lista operativa del Drone Panel mostra solo i droni aggiunti a "I miei droni".</div>
</div>
<div id="droneLibrary" class="drone-grid"></div>
</div>

<div>
<div class="card">
<h2>I miei droni</h2>
<div id="myDroneSummary" class="drone-grid"></div>
<div class="small status" id="managerStatus"></div>
</div>

<div class="card" style="margin-top:16px">
<h2>Drone custom</h2>
<div class="label">Crea un profilo manuale per droni assemblati o non presenti in libreria.</div>
<div class="custom-grid">
<input id="customName" placeholder="Nome drone">
<input id="customWindKmh" type="number" min="1" step="0.1" placeholder="Vento max km/h">
<input id="customNotes" placeholder="Note opzionali">
<button class="primary" onclick="addCustomDrone()">Aggiungi custom</button>
</div>
</div>
</div>
</div>

<script>
let DRONES = {};
let MY_DRONES = {active:'dji_neo',items:[],custom:{}};

function normalizeDroneProfile(id, profile){
    return {
        id,
        name: profile.name || `${profile.brand || ''} ${profile.model || ''}`.trim() || id,
        brand: profile.brand || 'Custom',
        model: profile.model || '',
        maxWind: Number(profile.max_wind_kmh || profile.maxWind || 0),
        maxWindMs: Number(profile.max_wind_ms || 0),
        source: profile.source || '',
        notes: profile.notes || ''
    };
}

function setStatus(message){
    document.getElementById('managerStatus').textContent = message || '';
}

async function loadDrones(){
    const res = await fetch('/api/drones');
    const data = await res.json();
    const loaded = {};

    Object.entries(data.profiles || data.library || {}).forEach(([id, profile])=>{
        loaded[id] = normalizeDroneProfile(id, profile);
    });

    DRONES = loaded;
    MY_DRONES = data.my_drones || MY_DRONES;
    populateBrandFilter();
    renderDroneLibrary();
    renderMyDrones();
}

function populateBrandFilter(){
    const select = document.getElementById('brandFilter');
    const current = select.value;
    const brands = [...new Set(Object.values(DRONES).map((drone)=>drone.brand || 'Custom'))].sort();
    if(!brands.includes('Custom')){
        brands.push('Custom');
        brands.sort();
    }

    select.innerHTML = '';
    brands.forEach((brand)=>{
        const option = document.createElement('option');
        option.value = brand;
        option.textContent = brand;
        select.appendChild(option);
    });

    if(brands.includes(current)){
        select.value = current;
    }else if(brands.includes('DJI')){
        select.value = 'DJI';
    }else if(brands.length){
        select.value = brands[0];
    }
}

function renderDroneLibrary(){
    const container = document.getElementById('droneLibrary');
    const brand = document.getElementById('brandFilter').value;
    const myIds = MY_DRONES.items || [];
    const drones = Object.values(DRONES)
        .filter((drone)=>!brand || drone.brand === brand)
        .sort((a,b)=>a.name.localeCompare(b.name));

    container.innerHTML = '';

    if(!drones.length){
        container.innerHTML = brand === 'Custom'
            ? '<div class="label">Nessun drone custom salvato.</div>'
            : '<div class="label">Nessun drone per questa marca.</div>';
        return;
    }

    drones.forEach((drone)=>{
        const isMine = myIds.includes(drone.id);
        const card = document.createElement('div');
        card.className = 'drone-card' + (isMine ? ' owned' : '');

        card.innerHTML = `
            <h3>${drone.name}</h3>
            <div class="meta">${drone.brand} ${drone.model}</div>
            <div class="meta">Vento max: ${drone.maxWind.toFixed(1)} km/h (${drone.maxWindMs.toFixed(1)} m/s)</div>
            <div class="meta">${drone.notes || ''}</div>
        `;

        if(isMine){
            const label = document.createElement('div');
            label.className = 'owned-label';
            label.textContent = 'In flotta';
            card.appendChild(label);
        }else{
            const action = document.createElement('button');
            action.textContent = 'Aggiungi';
            action.className = 'primary';
            action.onclick = ()=>addMyDrone(drone.id);

            const actions = document.createElement('div');
            actions.className = 'actions';
            actions.appendChild(action);
            card.appendChild(actions);
        }

        container.appendChild(card);
    });
}

function renderMyDrones(){
    const container = document.getElementById('myDroneSummary');
    const myIds = (MY_DRONES.items || []).filter((id)=>DRONES[id]);
    container.innerHTML = '';

    if(!myIds.length){
        container.innerHTML = '<div class="label">Nessun drone selezionato.</div>';
        return;
    }

    myIds.forEach((id)=>{
        const drone = DRONES[id];
        const div = document.createElement('div');
        div.className = 'drone-card mine';
        div.innerHTML = `
            <h3>${drone.name}</h3>
            <div class="meta">${drone.brand} - vento max ${drone.maxWind.toFixed(1)} km/h</div>
        `;
        const actions = document.createElement('div');
        actions.className = 'actions';

        const removeButton = document.createElement('button');
        removeButton.className = 'danger-btn';
        removeButton.textContent = drone.brand === 'Custom' ? 'Elimina' : 'Rimuovi';
        removeButton.onclick = ()=>removeMyDrone(drone.id);

        actions.appendChild(removeButton);
        div.appendChild(actions);
        container.appendChild(div);
    });
}

async function addMyDrone(drone){
    try{
        const res = await fetch('/api/my-drones/add', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({drone})
        });
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }
        setStatus('Drone aggiunto.');
        await loadDrones();
    }catch(e){
        setStatus('Errore: ' + e.message);
    }
}

async function removeMyDrone(drone){
    try{
        const res = await fetch('/api/my-drones/remove', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({drone})
        });
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }
        setStatus('Drone rimosso.');
        await loadDrones();
    }catch(e){
        setStatus('Errore: ' + e.message);
    }
}

async function addCustomDrone(){
    const payload = {
        name: document.getElementById('customName').value.trim(),
        max_wind_kmh: Number(document.getElementById('customWindKmh').value),
        notes: document.getElementById('customNotes').value.trim()
    };

    try{
        const res = await fetch('/api/custom-drones', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(payload)
        });
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }

        ['customName','customWindKmh','customNotes'].forEach((id)=>{
            document.getElementById(id).value = '';
        });

        setStatus('Drone custom aggiunto.');
        await loadDrones();
    }catch(e){
        setStatus('Errore custom: ' + e.message);
    }
}

loadDrones().catch((e)=>setStatus('Errore caricamento droni: ' + e.message));
</script>
</body>
</html>
"""


def reverse_geocode(lat, lon):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "format": "json",
            "lat": lat,
            "lon": lon,
            "zoom": 10,
            "addressdetails": 1
        }
        headers = {"User-Agent": "NIWA-AP/1.0"}
        response = requests.get(url, params=params, headers=headers, timeout=8)
        response.raise_for_status()
        data = response.json()
        address = data.get("address", {})

        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
        )
        region = address.get("state") or address.get("region")
        parts = [p for p in [city, region] if p]

        return ", ".join(parts)

    except Exception:
        return "Località non disponibile"


@app.route("/api/weather")
def weather():
    place_query = request.args.get("place")
    source = request.args.get("source", "fallback")

    if place_query:
        try:
            geo_url = "https://nominatim.openstreetmap.org/search"
            geo_params = {"q": place_query, "format": "json", "limit": 1}
            headers = {"User-Agent": "NIWA-AP/1.0"}
            geo_res = requests.get(geo_url, params=geo_params, headers=headers, timeout=8)
            geo_res.raise_for_status()
            geo_data = geo_res.json()

            if geo_data:
                lat = geo_data[0]["lat"]
                lon = geo_data[0]["lon"]
            else:
                lat = str(LAT)
                lon = str(LON)
                source = "fallback"

        except Exception:
            lat = str(LAT)
            lon = str(LON)
            source = "fallback"
    else:
        lat = str(LAT)
        lon = str(LON)

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,precipitation,"
        f"wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        f"&hourly=wind_speed_80m,wind_speed_120m"
        f"&wind_speed_unit=kmh&timezone=auto"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        current = data["current"]
        current_hour = current["time"][:13]

        idx = next(
            (i for i, t in enumerate(data["hourly"]["time"]) if t[:13] == current_hour),
            None
        )

        place = reverse_geocode(lat, lon)

        return jsonify({
            "lat": lat,
            "lon": lon,
            "source": source,
            "place": place,
            "temperature": current["temperature_2m"],
            "humidity": current["relative_humidity_2m"],
            "wind10": current["wind_speed_10m"],
            "wind80": data["hourly"]["wind_speed_80m"][idx] if idx is not None else None,
            "wind120": data["hourly"]["wind_speed_120m"][idx] if idx is not None else None,
            "gusts": current["wind_gusts_10m"],
            "rain": current["precipitation"],
            "direction": current["wind_direction_10m"],
            "updated": current["time"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/drones")
def get_drones():
    library = load_drone_library()
    my_drones = load_my_drones(library)
    profiles = get_drone_profiles(library, my_drones)

    available = []
    for drone_id in my_drones["items"]:
        profile = profiles.get(drone_id)
        if profile:
            drone = {"id": drone_id}
            drone.update(profile)
            available.append(drone)

    return jsonify({
        "library": library,
        "profiles": profiles,
        "my_drones": my_drones,
        "available": available,
    })


@app.route("/api/my-drones/add", methods=["POST"])
def add_my_drone():
    payload = request.get_json(silent=True) or {}
    drone_id = payload.get("drone")

    library = load_drone_library()
    my_drones = load_my_drones(library)
    profiles = get_drone_profiles(library, my_drones)

    if drone_id not in profiles:
        return jsonify({"error": "Drone non presente nella libreria."}), 400

    if drone_id not in my_drones["items"]:
        my_drones["items"].append(drone_id)

    if my_drones.get("active") not in my_drones["items"]:
        my_drones["active"] = drone_id

    save_json_file(MY_DRONES_FILE, my_drones)

    return jsonify({"ok": True, "my_drones": my_drones})


@app.route("/api/my-drones/remove", methods=["POST"])
def remove_my_drone():
    payload = request.get_json(silent=True) or {}
    drone_id = payload.get("drone")

    library = load_drone_library()
    my_drones = load_my_drones(library)

    if drone_id not in my_drones["items"]:
        if drone_id in my_drones.get("custom", {}):
            del my_drones["custom"][drone_id]
            save_json_file(MY_DRONES_FILE, my_drones)
        return jsonify({"ok": True, "my_drones": my_drones})

    if len(my_drones["items"]) <= 1:
        return jsonify({"error": "Deve restare almeno un drone operativo."}), 400

    my_drones["items"] = [
        current_id for current_id in my_drones["items"]
        if current_id != drone_id
    ]

    if my_drones["active"] == drone_id:
        my_drones["active"] = my_drones["items"][0]

    if drone_id in my_drones.get("custom", {}):
        del my_drones["custom"][drone_id]

    save_json_file(MY_DRONES_FILE, my_drones)

    return jsonify({"ok": True, "my_drones": my_drones})


@app.route("/api/my-drones/active", methods=["POST"])
def set_active_drone():
    payload = request.get_json(silent=True) or {}
    drone_id = payload.get("drone")

    library = load_drone_library()
    my_drones = load_my_drones(library)

    if drone_id not in my_drones["items"]:
        return jsonify({"error": "Drone non presente nei miei droni."}), 400

    my_drones["active"] = drone_id
    save_json_file(MY_DRONES_FILE, my_drones)

    return jsonify({"ok": True, "my_drones": my_drones})


@app.route("/api/custom-drones", methods=["POST"])
def add_custom_drone():
    payload = request.get_json(silent=True) or {}

    library = load_drone_library()
    my_drones = load_my_drones(library)
    profiles = get_drone_profiles(library, my_drones)

    payload["brand"] = "Custom"
    payload["model"] = "Custom"

    brand = "Custom"
    model = str(payload.get("name", "")).strip() or "custom"
    drone_id = make_custom_drone_id(brand, model, profiles.keys())
    profile = clean_drone_profile(payload, drone_id, source="user")

    if not profile:
        return jsonify({
            "error": "Inserisci nome e vento max valido."
        }), 400

    my_drones.setdefault("custom", {})[drone_id] = profile

    if drone_id not in my_drones["items"]:
        my_drones["items"].append(drone_id)

    my_drones["active"] = drone_id
    save_json_file(MY_DRONES_FILE, my_drones)

    return jsonify({
        "ok": True,
        "drone": {"id": drone_id, **profile},
        "my_drones": my_drones,
    })


@app.route("/api/batteries")
def get_batteries():
    drone = request.args.get("drone", "dji_neo")
    data = load_battery_data()

    if drone not in data:
        data[drone] = {"battery_count": 1, "batteries": [100]}
        save_battery_data(data)

    return jsonify(data[drone])


@app.route("/api/batteries/update", methods=["POST"])
def update_battery():
    payload = request.json
    drone = payload.get("drone", "dji_neo")
    index = int(payload.get("index", 0))
    value = int(payload.get("value", 0))

    value = max(0, min(100, value))

    data = load_battery_data()

    if drone not in data:
        data[drone] = {"battery_count": 1, "batteries": [100]}

    batteries = data[drone]["batteries"]

    if 0 <= index < len(batteries):
        batteries[index] = value

    save_battery_data(data)

    return jsonify({"ok": True})


@app.route("/api/batteries/count", methods=["POST"])
def update_battery_count():
    payload = request.json
    drone = payload.get("drone", "dji_neo")
    count = int(payload.get("count", 1))

    count = max(1, min(12, count))

    data = load_battery_data()

    old = data.get(drone, {"batteries": []}).get("batteries", [])
    new_batteries = old[:count]

    while len(new_batteries) < count:
        new_batteries.append(100)

    data[drone] = {
        "battery_count": count,
        "batteries": new_batteries
    }

    save_battery_data(data)

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5051)
