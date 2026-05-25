from flask import Flask, jsonify, request
import requests
import json
import os

app = Flask(__name__)

LAT = 40.771
LON = 14.789

DATA_FILE = "/data/drone_batteries.json"

DEFAULT_BATTERIES = {
    "dji_neo": {"battery_count": 2, "batteries": [100, 100]},
    "dji_avata_2": {"battery_count": 3, "batteries": [100, 100, 100]},
}


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
h1{margin-bottom:8px}.subtitle{color:#9ca3af;margin-bottom:24px}
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
    background:#374151;
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
}
</style>
</head>

<body>

<h1>🚁 NIWA Drone Panel</h1>
<div class="subtitle">Meteo operativo, batterie, checklist e sicurezza drone.</div>

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
const DRONES = {
    dji_neo: { name: 'DJI Neo', maxWind: 28.8 },
    dji_avata_2: { name: 'DJI Avata 2', maxWind: 38.5 }
};

function currentDrone(){
    return localStorage.getItem('niwa_drone') || 'dji_neo';
}

function loadDrone(){
    document.getElementById('droneSelect').value = currentDrone();
}

function saveDrone(){
    localStorage.setItem('niwa_drone', document.getElementById('droneSelect').value);
    loadWeather();
    loadBatteries();
}

function batteryColor(value){
    if(value >= 80) return 'green';
    if(value >= 30) return 'yellow';
    return 'red';
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
                    <input class="battery-slider" type="range" min="0" max="100" value="${value}" id="battery_${index}" oninput="updateBatteryLabel(${index})">
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
    const drone = DRONES[currentDrone()];
    const maxWind = drone.maxWind;
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

loadDrone();
loadChecklist();
loadBatteries();
loadWeather();
setInterval(loadWeather, 10 * 60 * 1000);
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
