from datetime import datetime, timedelta
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 10

WEATHER_CODES = {
    0: "Sereno",
    1: "Prevalentemente sereno",
    2: "Parzialmente nuvoloso",
    3: "Coperto",
    45: "Nebbia",
    48: "Nebbia con brina",
    51: "Pioviggine leggera",
    53: "Pioviggine",
    55: "Pioviggine intensa",
    61: "Pioggia leggera",
    63: "Pioggia",
    65: "Pioggia intensa",
    71: "Neve leggera",
    73: "Neve",
    75: "Neve intensa",
    80: "Rovesci leggeri",
    81: "Rovesci",
    82: "Rovesci intensi",
    95: "Temporale",
    96: "Temporale con grandine",
    99: "Temporale con grandine intensa",
}


def weather_label(code):
    return WEATHER_CODES.get(code, f"Codice meteo {code}")


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def time_label(value):
    parsed = parse_iso(value)
    if not parsed:
        return "-"
    return parsed.strftime("%H:%M")


def shifted_label(value, minutes):
    parsed = parse_iso(value)
    if not parsed:
        return "-"
    return (parsed + timedelta(minutes=minutes)).strftime("%H:%M")


def number(value, default=0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def score_hour(hour):
    cloud = number(hour.get("cloud_cover"))
    rain = number(hour.get("precipitation_probability"))
    wind = number(hour.get("wind_speed_10m"))
    visibility = number(hour.get("visibility"), 10000)

    score = 100
    score -= min(rain, 100) * 0.45
    score -= max(0, wind - 15) * 1.2
    score -= max(0, 25 - min(cloud, 50)) * 0.2
    score -= max(0, cloud - 75) * 0.25
    if visibility and visibility < 5000:
        score -= (5000 - visibility) / 120

    return max(0, min(100, round(score)))


def hour_notes(hour):
    notes = []
    cloud = number(hour.get("cloud_cover"))
    rain = number(hour.get("precipitation_probability"))
    wind = number(hour.get("wind_speed_10m"))
    visibility = number(hour.get("visibility"), 10000)

    if rain >= 60:
        notes.append("Pioggia probabile: proteggi attrezzatura e valuta mood cinematico.")
    elif rain >= 30:
        notes.append("Rischio pioggia: porta copertura e tieni un piano B.")

    if cloud <= 20:
        notes.append("Luce dura se sei lontano da alba/tramonto: cerca ombra o controluce.")
    elif 35 <= cloud <= 75:
        notes.append("Nuvole interessanti: buono per ritratti, paesaggio e cielo drammatico.")
    elif cloud > 85:
        notes.append("Cielo coperto: luce morbida, ottima per ritratti e dettagli.")

    if wind >= 25:
        notes.append("Vento forte: attenzione a capelli, vestiti, treppiede e audio.")
    elif wind >= 15:
        notes.append("Vento presente: puo dare movimento a tessuti e capelli.")

    if visibility and visibility < 5000:
        notes.append("Visibilita bassa: possibile atmosfera, ma meno dettaglio sullo sfondo.")

    if not notes:
        notes.append("Condizioni pulite: scegli la luce, non solo il meteo.")

    return notes


def build_daily_items(daily):
    items = []
    dates = daily.get("time", [])
    sunrises = daily.get("sunrise", [])
    sunsets = daily.get("sunset", [])
    weather_codes = daily.get("weather_code", [])
    rain_max = daily.get("precipitation_probability_max", [])
    daylight = daily.get("daylight_duration", [])
    sunshine = daily.get("sunshine_duration", [])

    for index, date in enumerate(dates):
        sunrise = sunrises[index] if index < len(sunrises) else None
        sunset = sunsets[index] if index < len(sunsets) else None
        code = weather_codes[index] if index < len(weather_codes) else None
        rain = rain_max[index] if index < len(rain_max) else None
        daylight_hours = number(daylight[index], 0) / 3600 if index < len(daylight) else 0
        sunshine_hours = number(sunshine[index], 0) / 3600 if index < len(sunshine) else 0

        items.append({
            "date": date,
            "label": datetime.fromisoformat(date).strftime("%d/%m") if date else "-",
            "sunrise": time_label(sunrise),
            "sunset": time_label(sunset),
            "blue_morning": f"{shifted_label(sunrise, -35)} - {shifted_label(sunrise, -10)}",
            "golden_morning": f"{shifted_label(sunrise, 0)} - {shifted_label(sunrise, 60)}",
            "golden_evening": f"{shifted_label(sunset, -60)} - {time_label(sunset)}",
            "blue_evening": f"{shifted_label(sunset, 10)} - {shifted_label(sunset, 35)}",
            "weather": weather_label(code),
            "rain_probability": rain,
            "daylight_hours": round(daylight_hours, 1),
            "sunshine_hours": round(sunshine_hours, 1),
        })

    return items


def build_hourly_items(hourly):
    times = hourly.get("time", [])
    items = []

    for index, raw_time in enumerate(times[:48]):
        item = {
            "time": raw_time,
            "label": raw_time[11:16] if len(raw_time) >= 16 else raw_time,
            "temperature_2m": pick(hourly, "temperature_2m", index),
            "relative_humidity_2m": pick(hourly, "relative_humidity_2m", index),
            "precipitation_probability": pick(hourly, "precipitation_probability", index),
            "cloud_cover": pick(hourly, "cloud_cover", index),
            "wind_speed_10m": pick(hourly, "wind_speed_10m", index),
            "visibility": pick(hourly, "visibility", index),
            "weather_code": pick(hourly, "weather_code", index),
        }
        item["weather"] = weather_label(item["weather_code"])
        item["score"] = score_hour(item)
        item["notes"] = hour_notes(item)
        items.append(item)

    return items


def pick(data, key, index):
    values = data.get(key, [])
    return values[index] if index < len(values) else None


@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIWA Shooting Tools</title>
<style>
:root{color-scheme:dark;--bg:#111827;--panel:#1f2937;--muted:#9ca3af;--text:#f9fafb;--line:#374151;--blue:#3b82f6;--green:#22c55e;--yellow:#facc15;--red:#ef4444}
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--text);padding:20px}
h1{margin:0 0 8px 0}.subtitle{color:var(--muted);margin-bottom:18px;line-height:1.45}
.topbar{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}.button{display:inline-block;background:#374151;color:white;text-decoration:none;padding:10px 12px;border-radius:10px;border:none;cursor:pointer}.button:hover{background:#4b5563}
.toolbar{display:grid;grid-template-columns:1.3fr auto auto;gap:10px;margin:12px 0 16px}.toolbar input{width:100%;background:#0f172a;border:1px solid var(--line);border-radius:10px;color:white;padding:12px;font-size:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.wide{grid-column:1/-1}
.card{background:var(--panel);border-radius:12px;padding:16px;box-shadow:0 8px 20px rgba(0,0,0,.25)}.card h2,.card h3{margin:0 0 10px 0}.card h2{font-size:20px}.card h3{font-size:17px}.muted{color:var(--muted);font-size:14px;line-height:1.45}.status{color:var(--muted);font-size:14px;margin:8px 0 14px}
.pill{display:inline-flex;align-items:center;gap:6px;background:#111827;border:1px solid var(--line);border-radius:999px;padding:5px 9px;margin:4px 4px 0 0;color:#d1d5db;font-size:12px}.score{font-size:34px;font-weight:bold}.score.good{color:var(--green)}.score.mid{color:var(--yellow)}.score.bad{color:var(--red)}
.phase{display:grid;grid-template-columns:1fr auto;gap:6px;border-top:1px solid var(--line);padding:9px 0}.phase:first-child{border-top:0}.phase strong{font-size:14px}.phase span{color:#d1d5db;font-size:14px}
.hours{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}.hour{background:#111827;border:1px solid var(--line);border-radius:10px;padding:10px}.hour .time{font-weight:bold}.hour .small{color:var(--muted);font-size:12px;margin-top:4px;line-height:1.35}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.tab{background:#111827;color:#e5e7eb;border:1px solid var(--line);border-radius:999px;padding:8px 10px;cursor:pointer}.tab.active{background:#2563eb;border-color:#2563eb;color:white}
.swatches{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:12px}.swatch{height:58px;border-radius:10px;border:1px solid rgba(255,255,255,.2)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.field label{display:block;color:#d1d5db;font-size:13px;margin-bottom:6px}.field input,.field select{width:100%;background:#111827;border:1px solid var(--line);border-radius:10px;color:white;padding:10px}
.result{font-size:24px;font-weight:bold;margin-top:10px}.list{margin:0;padding-left:18px;color:#d1d5db;line-height:1.5}.checklist{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px}.check{display:flex;gap:8px;align-items:flex-start;background:#111827;border:1px solid var(--line);border-radius:10px;padding:10px;color:#d1d5db;font-size:14px}
.check input{margin-top:2px}.offline{border:1px solid #7f1d1d;background:#2a1720}
@media(max-width:760px){body{padding:14px}.topbar{display:block}.topbar .button{margin-top:10px}.toolbar{grid-template-columns:1fr}.form-row{grid-template-columns:1fr}.swatches{grid-template-columns:repeat(3,1fr)}}
</style>
</head>
<body>
<div class="topbar">
<div>
<h1>NIWA Shooting Tools</h1>
<div class="subtitle">Luce, meteo creativo, colore, esposizione e micro-checklist per foto e video.</div>
</div>
<a class="button" id="dashboardLink" href="/">Dashboard</a>
</div>

<div class="toolbar">
<input id="locationInput" placeholder="Citta o luogo, es. Torino, Milano, Rimini">
<button class="button" onclick="searchLocation()">Cerca</button>
<button class="button" onclick="useDeviceLocation()">GPS</button>
</div>
<div class="status" id="status">Scegli una localita per pianificare lo shooting.</div>

<div class="grid">
<div class="card">
<h2>Oggi</h2>
<div id="todaySummary" class="muted">Nessun piano caricato.</div>
</div>

<div class="card">
<h2>Indice Shooting</h2>
<div id="shootingScore" class="score mid">--</div>
<div id="scoreNotes" class="muted">Valuta luce, nuvole, vento e pioggia.</div>
</div>

<div class="card wide">
<h2>Teoria Colore</h2>
<div class="muted">Scegli un colore dominante e prova armonie rapide per outfit, fondali, gel, props o grading.</div>
<div class="form-row" style="margin-top:12px">
<div class="field"><label>Colore base</label><input id="baseColor" type="color" value="#3b82f6" oninput="updatePalette()"></div>
<div class="field"><label>Armonia</label><select id="harmony" onchange="updatePalette()"><option value="complementary">Complementare</option><option value="analogous">Analoga</option><option value="triadic">Triadica</option><option value="split">Split complementary</option><option value="mono">Monocromatica</option></select></div>
</div>
<div class="swatches" id="swatches"></div>
<div class="muted" id="colorNotes" style="margin-top:10px"></div>
</div>

<div class="card wide">
<h2>Finestre Luce</h2>
<div id="dailyPhases" class="grid"></div>
</div>

<div class="card wide">
<h2>Prossime Ore</h2>
<div class="hours" id="hourlyCards"></div>
</div>
</div>

<script>
function serviceUrl(port, path=''){
    return `${window.location.protocol}//${window.location.hostname}:${port}${path}`;
}

document.getElementById('dashboardLink').href = serviceUrl(3000);

let CURRENT_PLAN = null;

function status(text, danger=false){
    const el = document.getElementById('status');
    el.textContent = text;
    el.className = danger ? 'status offline' : 'status';
}

async function searchLocation(){
    const query = document.getElementById('locationInput').value.trim();
    if(!query){
        status('Inserisci una localita.', true);
        return;
    }

    status('Cerco localita...');
    try{
        const res = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }
        if(!data.results || !data.results.length){ throw new Error('Localita non trovata.'); }
        const place = data.results[0];
        loadPlan(place.latitude, place.longitude, place.name, place.country);
    }catch(e){
        status('Errore geocoding: ' + e.message, true);
    }
}

function useDeviceLocation(){
    if(!navigator.geolocation){
        status('GPS non disponibile nel browser.', true);
        return;
    }
    status('Leggo posizione dispositivo...');
    navigator.geolocation.getCurrentPosition(
        (pos)=>loadPlan(pos.coords.latitude, pos.coords.longitude, 'Posizione attuale', ''),
        (err)=>status('GPS non disponibile: ' + err.message, true),
        {enableHighAccuracy:true, timeout:10000}
    );
}

async function loadPlan(lat, lon, name, country){
    status(`Carico piano luce/meteo per ${name}...`);
    try{
        const res = await fetch(`/api/plan?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&name=${encodeURIComponent(name)}&country=${encodeURIComponent(country || '')}`);
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }
        CURRENT_PLAN = data;
        renderPlan(data);
        status(`Piano caricato: ${data.location.name}${data.location.country ? ', ' + data.location.country : ''}.`);
    }catch(e){
        status('Meteo/luce non disponibili: ' + e.message, true);
    }
}

function renderPlan(data){
    const today = data.daily[0];
    document.getElementById('todaySummary').innerHTML = today ? `
        <div class="phase"><strong>Alba</strong><span>${today.sunrise}</span></div>
        <div class="phase"><strong>Tramonto</strong><span>${today.sunset}</span></div>
        <div class="phase"><strong>Meteo</strong><span>${today.weather}</span></div>
        <div class="phase"><strong>Pioggia max</strong><span>${today.rain_probability ?? '-'}%</span></div>
        <div class="phase"><strong>Luce diurna</strong><span>${today.daylight_hours}h</span></div>
    ` : 'Nessun dato giornaliero.';

    const score = data.hourly.length ? Math.round(data.hourly.slice(0, 6).reduce((sum, h)=>sum + h.score, 0) / Math.min(6, data.hourly.length)) : 0;
    const scoreEl = document.getElementById('shootingScore');
    scoreEl.textContent = data.hourly.length ? `${score}/100` : '--';
    scoreEl.className = 'score ' + (score >= 75 ? 'good' : score >= 45 ? 'mid' : 'bad');
    document.getElementById('scoreNotes').textContent = data.hourly[0] ? data.hourly[0].notes.join(' ') : 'Nessun dato orario.';

    document.getElementById('dailyPhases').innerHTML = data.daily.slice(0, 5).map(renderDay).join('');
    document.getElementById('hourlyCards').innerHTML = data.hourly.slice(0, 18).map(renderHour).join('');
}

function renderDay(day){
    return `<div class="card">
        <h3>${day.label}</h3>
        <div class="phase"><strong>Blue mattina</strong><span>${day.blue_morning}</span></div>
        <div class="phase"><strong>Golden mattina</strong><span>${day.golden_morning}</span></div>
        <div class="phase"><strong>Golden sera</strong><span>${day.golden_evening}</span></div>
        <div class="phase"><strong>Blue sera</strong><span>${day.blue_evening}</span></div>
        <span class="pill">${day.weather}</span><span class="pill">Pioggia ${day.rain_probability ?? '-'}%</span>
    </div>`;
}

function renderHour(hour){
    const cls = hour.score >= 75 ? 'good' : hour.score >= 45 ? 'mid' : 'bad';
    return `<div class="hour">
        <div class="time">${hour.label} <span class="score ${cls}" style="font-size:18px">${hour.score}</span></div>
        <div class="small">${hour.weather}</div>
        <div class="small">Nuvole ${hour.cloud_cover ?? '-'}% - Pioggia ${hour.precipitation_probability ?? '-'}%</div>
        <div class="small">Vento ${hour.wind_speed_10m ?? '-'} km/h - Umidita ${hour.relative_humidity_2m ?? '-'}%</div>
    </div>`;
}

function updatePalette(){
    const base = hexToHsl(document.getElementById('baseColor').value);
    const harmony = document.getElementById('harmony').value;
    let hues = [];
    if(harmony === 'complementary') hues = [base.h, base.h + 180, base.h + 15, base.h + 195, base.h];
    if(harmony === 'analogous') hues = [base.h - 35, base.h - 18, base.h, base.h + 18, base.h + 35];
    if(harmony === 'triadic') hues = [base.h, base.h + 120, base.h + 240, base.h + 20, base.h - 20];
    if(harmony === 'split') hues = [base.h, base.h + 150, base.h + 210, base.h + 25, base.h - 25];
    if(harmony === 'mono') hues = [base.h, base.h, base.h, base.h, base.h];

    const swatches = hues.map((hue, index)=>{
        const light = harmony === 'mono' ? [32, 43, 54, 65, 76][index] : [42, 52, 58, 66, 74][index];
        return hslToHex(((hue % 360) + 360) % 360, base.s, light);
    });

    document.getElementById('swatches').innerHTML = swatches.map((color)=>`<div class="swatch" title="${color}" style="background:${color}"></div>`).join('');
    document.getElementById('colorNotes').textContent = colorAdvice(harmony);
}

function colorAdvice(harmony){
    const notes = {
        complementary: 'Complementare: contrasto forte, utile per soggetto/fondo e look poster.',
        analogous: 'Analoga: palette morbida e coerente, ottima per ritratto e storytelling elegante.',
        triadic: 'Triadica: energia e varietà, funziona bene con styling controllato.',
        split: 'Split complementary: contrasto piu gestibile del complementare puro.',
        mono: 'Monocromatica: pulita, grafica, ottima per serie coerenti e mood minimal.'
    };
    return notes[harmony];
}

function hexToHsl(hex){
    const r = parseInt(hex.slice(1,3),16)/255;
    const g = parseInt(hex.slice(3,5),16)/255;
    const b = parseInt(hex.slice(5,7),16)/255;
    const max = Math.max(r,g,b), min = Math.min(r,g,b);
    let h = 0, s = 0, l = (max + min) / 2;
    if(max !== min){
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        if(max === r) h = (g - b) / d + (g < b ? 6 : 0);
        if(max === g) h = (b - r) / d + 2;
        if(max === b) h = (r - g) / d + 4;
        h *= 60;
    }
    return {h, s: Math.round(s * 100), l: Math.round(l * 100)};
}

function hslToHex(h, s, l){
    s /= 100; l /= 100;
    const c = (1 - Math.abs(2*l - 1)) * s;
    const x = c * (1 - Math.abs((h/60) % 2 - 1));
    const m = l - c/2;
    let r=0,g=0,b=0;
    if(h < 60){r=c;g=x}else if(h < 120){r=x;g=c}else if(h < 180){g=c;b=x}else if(h < 240){g=x;b=c}else if(h < 300){r=x;b=c}else{r=c;b=x}
    return '#' + [r,g,b].map(v=>Math.round((v+m)*255).toString(16).padStart(2,'0')).join('');
}

function escapeHtml(value){
    return String(value).replace(/[&<>"']/g, (char)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
}

updatePalette();
</script>
</body>
</html>
"""


@app.route("/api/geocode")
def api_geocode():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query mancante."}), 400

    try:
        response = requests.get(
            GEOCODING_URL,
            params={"name": query, "count": 5, "language": "it", "format": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": f"Geocoding non disponibile: {exc}"}), 502

    data = response.json()
    results = []
    for item in data.get("results", []):
        results.append({
            "name": item.get("name"),
            "country": item.get("country"),
            "admin1": item.get("admin1"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
        })

    return jsonify({"results": results})


@app.route("/api/plan")
def api_plan():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    name = request.args.get("name", "Localita")
    country = request.args.get("country", "")

    try:
        latitude = float(lat)
        longitude = float(lon)
    except (TypeError, ValueError):
        return jsonify({"error": "Coordinate non valide."}), 400

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
        "forecast_days": 7,
        "daily": ",".join([
            "sunrise",
            "sunset",
            "daylight_duration",
            "sunshine_duration",
            "weather_code",
            "precipitation_probability_max",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation_probability",
            "cloud_cover",
            "wind_speed_10m",
            "visibility",
            "weather_code",
        ]),
    }

    try:
        response = requests.get(FORECAST_URL, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": f"Previsioni non disponibili: {exc}"}), 502

    data = response.json()
    daily = build_daily_items(data.get("daily", {}))
    hourly = build_hourly_items(data.get("hourly", {}))

    return jsonify({
        "location": {
            "name": name,
            "country": country,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": data.get("timezone"),
        },
        "daily": daily,
        "hourly": hourly,
        "source": "Open-Meteo",
        "notes": [
            "Blue hour e golden hour sono stime operative basate su alba/tramonto.",
            "Verifica sempre condizioni reali sul posto.",
        ],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5054)
