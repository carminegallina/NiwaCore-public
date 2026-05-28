from datetime import datetime, time, timedelta, timezone
from flask import Flask, jsonify, request
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
import math
import os
import requests

app = Flask(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
METNO_FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_SEARCH_URL = "https://photon.komoot.io/api/"
REQUEST_TIMEOUT = 10
DATA_DIR = Path("/data")
LOCATIONS_CACHE_FILE = DATA_DIR / "shooting_locations_cache.json"
PLAN_CACHE_FILE = DATA_DIR / "shooting_plan_cache.json"
DEFAULT_TIMEZONE = "Europe/Rome"
NOMINATIM_USER_AGENT = os.environ.get("NIWA_NOMINATIM_USER_AGENT", "NIWA-AP/0.1")
PLACE_SEARCH_COUNTRY = os.environ.get("NIWA_PLACE_SEARCH_COUNTRY", "it").strip().lower()
SECONDARY_WEATHER_SOURCE = os.environ.get("NIWA_SECONDARY_WEATHER_SOURCE", "metno").strip().lower()
METNO_USER_AGENT = os.environ.get("NIWA_METNO_USER_AGENT", "NIWA-AP/0.1")
UNCERTAINTY_THRESHOLDS = {
    "temperature_c": 4,
    "wind_kmh": 10,
    "cloud_percent": 35,
}

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


def safe_zoneinfo(name):
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def read_json(path, fallback):
    try:
        if not path.exists():
            return fallback
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(fallback)) else fallback
    except Exception:
        return fallback


def write_json(path, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    temp_path.replace(path)


def cache_key(latitude, longitude):
    return f"{round(float(latitude), 4):.4f},{round(float(longitude), 4):.4f}"


def utc_now_label():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def cache_age_hours(raw_time):
    parsed = parse_iso(raw_time)
    if not parsed:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(0, delta.total_seconds() / 3600)


def decimal_hour_to_time(value):
    if value is None:
        return None
    total_minutes = int(round(value * 60)) % (24 * 60)
    return time(total_minutes // 60, total_minutes % 60)


def solar_event_utc(day, latitude, longitude, is_sunrise):
    # NOAA sunrise/sunset approximation. Accurate enough for planning windows.
    zenith = 90.833
    n = day.timetuple().tm_yday
    lng_hour = longitude / 15.0
    approx = n + ((6 if is_sunrise else 18) - lng_hour) / 24
    mean_anomaly = (0.9856 * approx) - 3.289
    true_long = mean_anomaly + (1.916 * math.sin(math.radians(mean_anomaly))) + (0.020 * math.sin(math.radians(2 * mean_anomaly))) + 282.634
    true_long = true_long % 360
    right_ascension = math.degrees(math.atan(0.91764 * math.tan(math.radians(true_long)))) % 360
    quadrant_l = math.floor(true_long / 90) * 90
    quadrant_ra = math.floor(right_ascension / 90) * 90
    right_ascension = (right_ascension + quadrant_l - quadrant_ra) / 15
    sin_dec = 0.39782 * math.sin(math.radians(true_long))
    cos_dec = math.cos(math.asin(sin_dec))
    cos_hour = (math.cos(math.radians(zenith)) - (sin_dec * math.sin(math.radians(latitude)))) / (cos_dec * math.cos(math.radians(latitude)))

    if cos_hour > 1 or cos_hour < -1:
        return None

    hour_angle = 360 - math.degrees(math.acos(cos_hour)) if is_sunrise else math.degrees(math.acos(cos_hour))
    hour_angle /= 15
    local_mean = hour_angle + right_ascension - (0.06571 * approx) - 6.622
    utc_hour = (local_mean - lng_hour) % 24
    event_time = decimal_hour_to_time(utc_hour)
    if not event_time:
        return None
    return datetime.combine(day, event_time, tzinfo=timezone.utc)


def solar_times(day, latitude, longitude, timezone_name):
    tz = safe_zoneinfo(timezone_name)
    sunrise_utc = solar_event_utc(day, latitude, longitude, True)
    sunset_utc = solar_event_utc(day, latitude, longitude, False)
    sunrise = sunrise_utc.astimezone(tz) if sunrise_utc else None
    sunset = sunset_utc.astimezone(tz) if sunset_utc else None
    return sunrise, sunset


def label_from_dt(value):
    return value.strftime("%H:%M") if value else "-"


def shifted_dt_label(value, minutes):
    return (value + timedelta(minutes=minutes)).strftime("%H:%M") if value else "-"


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


def build_solar_daily_items(latitude, longitude, timezone_name, weather_daily=None):
    items = []
    tz = safe_zoneinfo(timezone_name)
    start_date = datetime.now(tz).date()
    daily = weather_daily or {}
    weather_codes = daily.get("weather_code", [])
    rain_max = daily.get("precipitation_probability_max", [])
    sunshine = daily.get("sunshine_duration", [])

    for index in range(7):
        current_date = start_date + timedelta(days=index)
        sunrise, sunset = solar_times(current_date, latitude, longitude, timezone_name)
        daylight_hours = ((sunset - sunrise).total_seconds() / 3600) if sunrise and sunset else 0
        sunshine_hours = number(sunshine[index], 0) / 3600 if index < len(sunshine) else None
        code = weather_codes[index] if index < len(weather_codes) else None
        rain = rain_max[index] if index < len(rain_max) else None
        items.append({
            "date": current_date.isoformat(),
            "label": current_date.strftime("%d/%m"),
            "sunrise": label_from_dt(sunrise),
            "sunset": label_from_dt(sunset),
            "blue_morning": f"{shifted_dt_label(sunrise, -35)} - {shifted_dt_label(sunrise, -10)}",
            "golden_morning": f"{label_from_dt(sunrise)} - {shifted_dt_label(sunrise, 60)}",
            "golden_evening": f"{shifted_dt_label(sunset, -60)} - {label_from_dt(sunset)}",
            "blue_evening": f"{shifted_dt_label(sunset, 10)} - {shifted_dt_label(sunset, 35)}",
            "weather": weather_label(code),
            "rain_probability": rain,
            "daylight_hours": round(daylight_hours, 1),
            "sunshine_hours": round(sunshine_hours, 1) if sunshine_hours is not None else None,
            "light_source": "calcolo locale",
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


def normalize_hour_key(raw_time, timezone_name=None):
    parsed = parse_iso(raw_time)
    if not parsed:
        return raw_time[:13] if raw_time else None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=safe_zoneinfo(timezone_name))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def fetch_open_meteo(latitude, longitude):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
        "forecast_days": 7,
        "daily": ",".join([
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
    response = requests.get(FORECAST_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def clean_nominatim_place(item):
    address = item.get("address", {}) if isinstance(item.get("address"), dict) else {}
    name = (
        item.get("name")
        or address.get("amenity")
        or address.get("building")
        or address.get("tourism")
        or address.get("leisure")
        or address.get("road")
        or item.get("display_name", "").split(",")[0]
    )
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
    )
    country = address.get("country") or ""

    return {
        "name": name or "Luogo",
        "display_name": item.get("display_name") or name or "Luogo",
        "country": country,
        "admin1": address.get("state") or address.get("region") or "",
        "city": city or "",
        "latitude": float(item.get("lat")),
        "longitude": float(item.get("lon")),
        "timezone": DEFAULT_TIMEZONE,
        "source": "Nominatim",
    }


def clean_photon_place(feature):
    properties = feature.get("properties", {}) if isinstance(feature.get("properties"), dict) else {}
    geometry = feature.get("geometry", {}) if isinstance(feature.get("geometry"), dict) else {}
    coordinates = geometry.get("coordinates", [])
    if len(coordinates) < 2:
        raise ValueError("Coordinate Photon mancanti")

    name = properties.get("name") or properties.get("street") or properties.get("city") or "Luogo"
    city = properties.get("city") or properties.get("county") or ""
    state = properties.get("state") or ""
    country = properties.get("country") or ""
    parts = [name, city, state, country]

    return {
        "name": name,
        "display_name": ", ".join(part for part in parts if part),
        "country": country,
        "admin1": state,
        "city": city,
        "latitude": float(coordinates[1]),
        "longitude": float(coordinates[0]),
        "timezone": DEFAULT_TIMEZONE,
        "source": "Photon",
    }


def place_rank(place, query):
    query_terms = [term for term in query.casefold().replace("'", " ").split() if len(term) > 1]
    haystack = f"{place.get('name', '')} {place.get('display_name', '')}".casefold()
    score = 0
    if place.get("name", "").casefold().startswith(query.casefold()):
        score += 40
    score += sum(12 for term in query_terms if term in haystack)
    if place.get("city"):
        score += 4
    if place.get("country", "").casefold() in {"italia", "italy"}:
        score += 4
    return score


def dedupe_and_rank_places(places, query, limit=6):
    seen = set()
    unique = []
    for place in places:
        coord_key = (round(float(place["latitude"]), 4), round(float(place["longitude"]), 4))
        text_key = (place.get("name", "").casefold(), place.get("city", "").casefold())
        display_key = place.get("display_name", "").casefold()[:90]
        keys = {coord_key, text_key, display_key}
        if any(key in seen for key in keys):
            continue
        seen.update(keys)
        unique.append(place)
    unique.sort(key=lambda place: place_rank(place, query), reverse=True)
    return unique[:limit]


def search_photon_places(query, limit=8):
    params = {
        "q": query,
        "limit": limit,
        "lang": "it",
    }
    response = requests.get(
        PHOTON_SEARCH_URL,
        params=params,
        headers={"User-Agent": NOMINATIM_USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    places = []
    for feature in response.json().get("features", []):
        try:
            place = clean_photon_place(feature)
            if PLACE_SEARCH_COUNTRY == "it" and place.get("country", "").casefold() not in {"italia", "italy"}:
                continue
            places.append(place)
        except (TypeError, ValueError):
            continue
    return places


def search_nominatim_places(query, limit=6):
    response = requests.get(
        NOMINATIM_SEARCH_URL,
        params={
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "namedetails": 1,
            "limit": limit,
            "countrycodes": PLACE_SEARCH_COUNTRY,
            "accept-language": "it",
        },
        headers={"User-Agent": NOMINATIM_USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    places = []
    for item in response.json():
        try:
            places.append(clean_nominatim_place(item))
        except (TypeError, ValueError):
            continue
    return places


def search_places(query, limit=6):
    places = []
    photon_error = None
    try:
        places.extend(search_photon_places(query, limit=limit + 2))
    except requests.RequestException as exc:
        photon_error = exc

    try:
        places.extend(search_nominatim_places(query, limit=limit))
    except requests.RequestException:
        if not places and photon_error:
            raise photon_error

    return dedupe_and_rank_places(places, query, limit=limit)


def fetch_metno(latitude, longitude):
    if SECONDARY_WEATHER_SOURCE not in {"metno", "met.no", "met_norway"}:
        return None

    headers = {"User-Agent": METNO_USER_AGENT}
    params = {"lat": round(latitude, 4), "lon": round(longitude, 4)}
    response = requests.get(METNO_FORECAST_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def metno_to_hourly_items(data):
    items = []
    timeseries = data.get("properties", {}).get("timeseries", [])
    for entry in timeseries[:48]:
        instant = entry.get("data", {}).get("instant", {}).get("details", {})
        next_1h = entry.get("data", {}).get("next_1_hours", {}).get("details", {})
        wind_ms = instant.get("wind_speed")
        item = {
            "time": entry.get("time"),
            "temperature_2m": instant.get("air_temperature"),
            "relative_humidity_2m": instant.get("relative_humidity"),
            "cloud_cover": instant.get("cloud_area_fraction"),
            "wind_speed_10m": round(wind_ms * 3.6, 1) if isinstance(wind_ms, (int, float)) else None,
            "precipitation_amount": next_1h.get("precipitation_amount"),
        }
        items.append(item)
    return items


def compare_weather_sources(primary_hourly, secondary_hourly, timezone_name):
    secondary_by_hour = {
        normalize_hour_key(item.get("time")): item
        for item in secondary_hourly
        if normalize_hour_key(item.get("time"))
    }

    checks = []
    compared = 0
    discrepancy_hits = 0
    severe_hits = 0

    for primary in primary_hourly[:24]:
        hour_key = normalize_hour_key(primary.get("time"), timezone_name)
        secondary = secondary_by_hour.get(hour_key)
        if not secondary:
            continue

        compared_fields = 0

        hour_flags = []
        severe = False
        if primary.get("temperature_2m") is not None and secondary.get("temperature_2m") is not None:
            compared_fields += 1
            temp_diff = abs(number(primary.get("temperature_2m"), 0) - number(secondary.get("temperature_2m"), 0))
            if temp_diff >= UNCERTAINTY_THRESHOLDS["temperature_c"]:
                hour_flags.append(f"temperatura {round(temp_diff, 1)}C")
                severe = True

        if primary.get("wind_speed_10m") is not None and secondary.get("wind_speed_10m") is not None:
            compared_fields += 1
            wind_diff = abs(number(primary.get("wind_speed_10m"), 0) - number(secondary.get("wind_speed_10m"), 0))
            if wind_diff >= UNCERTAINTY_THRESHOLDS["wind_kmh"]:
                hour_flags.append(f"vento {round(wind_diff, 1)} km/h")
                severe = True

        if primary.get("cloud_cover") is not None and secondary.get("cloud_cover") is not None:
            compared_fields += 1
            cloud_diff = abs(number(primary.get("cloud_cover"), 0) - number(secondary.get("cloud_cover"), 0))
            if cloud_diff >= UNCERTAINTY_THRESHOLDS["cloud_percent"]:
                hour_flags.append(f"nuvole {round(cloud_diff)}%")

        if primary.get("precipitation_probability") is not None and secondary.get("precipitation_amount") is not None:
            compared_fields += 1
            primary_rain = number(primary.get("precipitation_probability"), 0)
            secondary_rain_amount = number(secondary.get("precipitation_amount"), 0)
            rain_conflict = (primary_rain >= 60 and secondary_rain_amount < 0.1) or (primary_rain <= 20 and secondary_rain_amount >= 0.5)
            if rain_conflict:
                hour_flags.append("pioggia discordante")
                severe = True

        if compared_fields == 0:
            continue

        compared += 1
        if hour_flags:
            discrepancy_hits += 1
            if severe:
                severe_hits += 1
            checks.append({
                "hour": primary.get("label") or primary.get("time"),
                "items": hour_flags,
                "severity": "alta" if severe else "media",
            })

    uncertainty = "bassa"
    if compared == 0:
        uncertainty = "non verificabile"
    elif severe_hits >= 1:
        uncertainty = "alta"
    elif discrepancy_hits >= 1:
        uncertainty = "media"

    return {
        "enabled": True,
        "primary": "Open-Meteo",
        "secondary": "MET Norway",
        "compared_hours": compared,
        "uncertainty": uncertainty,
        "high_uncertainty": uncertainty == "alta",
        "discrepancies": checks[:8],
        "thresholds": UNCERTAINTY_THRESHOLDS,
    }


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
:root{color-scheme:dark;--bg:#0b1220;--panel:#172033;--panel2:#101827;--muted:#94a3b8;--text:#f8fafc;--line:#334155;--blue:#38bdf8;--green:#22c55e;--yellow:#facc15;--red:#ef4444;--soft:#cbd5e1}
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:radial-gradient(circle at 24% 0%,rgba(56,189,248,.10),transparent 32%),linear-gradient(180deg,#0b1220,#0f172a 42%,#0b1220);color:var(--text);padding:20px}
h1{margin:0 0 6px 0;font-size:32px;letter-spacing:0}.subtitle{color:var(--muted);margin-bottom:18px;line-height:1.45}
.topbar{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:18px}.button{display:inline-flex;align-items:center;justify-content:center;background:#263244;color:white;text-decoration:none;padding:10px 12px;border-radius:10px;border:1px solid rgba(148,163,184,.22);cursor:pointer;min-height:40px;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}.button:hover{background:#334155}
.toolbar{display:grid;grid-template-columns:1.3fr auto auto;gap:10px;margin:12px 0 16px}.toolbar input{width:100%;background:#101827;border:1px solid rgba(148,163,184,.20);border-radius:10px;color:white;padding:12px;font-size:16px}
.search-wrap{position:relative}.suggestions{display:none;position:absolute;left:0;right:0;top:calc(100% + 6px);z-index:6;background:#101827;border:1px solid rgba(148,163,184,.24);border-radius:12px;overflow:hidden;box-shadow:0 18px 34px rgba(0,0,0,.35)}.suggestions.visible{display:block}.suggestion{padding:11px 12px;border-top:1px solid rgba(148,163,184,.14);cursor:pointer}.suggestion:first-child{border-top:0}.suggestion:hover{background:#162338}.suggestion strong{display:block;font-size:14px}.suggestion span{display:block;color:var(--muted);font-size:12px;margin-top:3px;line-height:1.35}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.wide{grid-column:1/-1}
.card{background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));border:1px solid rgba(148,163,184,.18);border-radius:12px;padding:16px;box-shadow:0 18px 34px rgba(0,0,0,.22)}.card h2,.card h3{margin:0 0 10px 0}.card h2{font-size:18px}.card h3{font-size:16px}.muted{color:var(--muted);font-size:14px;line-height:1.45}.status{color:var(--muted);font-size:14px;margin:8px 0 14px}
.pill{display:inline-flex;align-items:center;gap:6px;background:rgba(15,23,42,.92);border:1px solid rgba(148,163,184,.20);border-radius:999px;padding:5px 9px;margin:4px 4px 0 0;color:#dbeafe;font-size:12px}.score{font-size:34px;font-weight:bold}.score.good{color:var(--green)}.score.mid{color:var(--yellow)}.score.bad{color:var(--red)}
.phase{display:grid;grid-template-columns:1fr auto;gap:6px;border-top:1px solid var(--line);padding:9px 0}.phase:first-child{border-top:0}.phase strong{font-size:14px}.phase span{color:#d1d5db;font-size:14px}
.hours{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}.hour{background:rgba(15,23,42,.90);border:1px solid rgba(148,163,184,.18);border-radius:10px;padding:10px}.hour .time{font-weight:bold}.hour .small{color:var(--muted);font-size:12px;margin-top:4px;line-height:1.35}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.tab{background:#101827;color:#e5e7eb;border:1px solid rgba(148,163,184,.20);border-radius:999px;padding:8px 10px;cursor:pointer}.tab.active{background:#0369a1;border-color:#38bdf8;color:white}
.swatches{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:12px}.swatch{height:58px;border-radius:10px;border:1px solid rgba(255,255,255,.2)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.field label{display:block;color:#d1d5db;font-size:13px;margin-bottom:6px}.field input,.field select{width:100%;background:#101827;border:1px solid rgba(148,163,184,.20);border-radius:10px;color:white;padding:10px}
.result{font-size:24px;font-weight:bold;margin-top:10px}.list{margin:0;padding-left:18px;color:#d1d5db;line-height:1.5}.checklist{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px}.check{display:flex;gap:8px;align-items:flex-start;background:rgba(15,23,42,.90);border:1px solid rgba(148,163,184,.18);border-radius:10px;padding:10px;color:#d1d5db;font-size:14px}
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
<div class="search-wrap">
<input id="locationInput" placeholder="Citta o luogo, es. Mostra d'Oltremare">
<div id="placeSuggestions" class="suggestions"></div>
</div>
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
let SELECTED_PLACE = null;
let suggestTimer = null;
let latestSuggestQuery = '';

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
        if(SELECTED_PLACE && SELECTED_PLACE.display_name === query){
            loadPlan(SELECTED_PLACE.latitude, SELECTED_PLACE.longitude, SELECTED_PLACE.name, SELECTED_PLACE.country, SELECTED_PLACE.timezone || '');
            return;
        }

        const places = await fetchPlaceSuggestions(query);
        if(!places.length){ throw new Error('Localita non trovata.'); }
        selectPlace(places[0]);
    }catch(e){
        status('Errore geocoding: ' + e.message, true);
    }
}

async function fetchPlaceSuggestions(query){
    const res = await fetch(`/api/places?q=${encodeURIComponent(query)}&_=${Date.now()}`, {cache:'no-store'});
    const data = await res.json();
    if(data.error){ throw new Error(data.error); }
    return data.results || [];
}

function renderPlaceSuggestions(places){
    const box = document.getElementById('placeSuggestions');
    if(!places.length){
        box.classList.remove('visible');
        box.innerHTML = '';
        return;
    }

    box.innerHTML = places.map((place, index)=>`
        <div class="suggestion" onclick="selectPlaceFromSuggestions(${index})">
            <strong>${escapeHtml(place.name)}</strong>
            <span>${escapeHtml(place.display_name)}</span>
        </div>
    `).join('');
    box._places = places;
    box.classList.add('visible');
}

function selectPlaceFromSuggestions(index){
    const box = document.getElementById('placeSuggestions');
    const place = (box._places || [])[index];
    if(place){
        selectPlace(place);
    }
}

function selectPlace(place){
    SELECTED_PLACE = place;
    document.getElementById('locationInput').value = place.display_name;
    document.getElementById('placeSuggestions').classList.remove('visible');
    loadPlan(place.latitude, place.longitude, place.name, place.country, place.timezone || '');
}

function queuePlaceSuggestions(){
    const query = document.getElementById('locationInput').value.trim();
    SELECTED_PLACE = null;
    clearTimeout(suggestTimer);

    if(query.length < 3){
        renderPlaceSuggestions([]);
        return;
    }

    suggestTimer = setTimeout(async ()=>{
        latestSuggestQuery = query;
        try{
            const places = await fetchPlaceSuggestions(query);
            if(document.getElementById('locationInput').value.trim() === latestSuggestQuery){
                renderPlaceSuggestions(places);
            }
        }catch(e){
            if(document.getElementById('locationInput').value.trim() === latestSuggestQuery){
                renderPlaceSuggestions([]);
            }
        }
    }, 300);
}

function useDeviceLocation(){
    if(!navigator.geolocation){
        status('GPS non disponibile nel browser.', true);
        return;
    }
    status('Leggo posizione dispositivo...');
    navigator.geolocation.getCurrentPosition(
        (pos)=>loadPlan(pos.coords.latitude, pos.coords.longitude, 'Posizione attuale', '', ''),
        (err)=>status('GPS non disponibile: ' + err.message, true),
        {enableHighAccuracy:true, timeout:10000}
    );
}

async function loadPlan(lat, lon, name, country, timezone){
    status(`Carico piano luce/meteo per ${name}...`);
    try{
        const res = await fetch(`/api/plan?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&name=${encodeURIComponent(name)}&country=${encodeURIComponent(country || '')}&timezone=${encodeURIComponent(timezone || '')}`);
        const data = await res.json();
        if(data.error){ throw new Error(data.error); }
        CURRENT_PLAN = data;
        renderPlan(data);
        const suffix = data.warning ? ` ${data.warning}` : '';
        status(`Piano caricato: ${data.location.name}${data.location.country ? ', ' + data.location.country : ''}.${suffix}`, Boolean(data.warning && data.weather_status !== 'meteo live'));
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
        <span class="pill">${data.weather_status || 'meteo non disponibile'}</span>
        <span class="pill">${data.weather_confidence ? 'Incertezza: ' + data.weather_confidence : 'Incertezza: non verificata'}</span>
        <span class="pill">Luce: ${data.light_source || 'calcolo locale'}</span>
    ` : 'Nessun dato giornaliero.';

    const score = data.hourly.length ? Math.round(data.hourly.slice(0, 6).reduce((sum, h)=>sum + h.score, 0) / Math.min(6, data.hourly.length)) : 0;
    const scoreEl = document.getElementById('shootingScore');
    scoreEl.textContent = data.hourly.length ? `${score}/100` : '--';
    scoreEl.className = 'score ' + (score >= 75 ? 'good' : score >= 45 ? 'mid' : 'bad');
    document.getElementById('scoreNotes').textContent = data.hourly[0] ? data.hourly[0].notes.join(' ') : 'Nessun dato orario.';
    if(data.weather_comparison && data.weather_comparison.high_uncertainty){
        const first = data.weather_comparison.discrepancies && data.weather_comparison.discrepancies.length ? data.weather_comparison.discrepancies[0] : null;
        const detail = first ? ` Prima differenza: ${first.hour}, ${first.items.join(', ')}.` : '';
        document.getElementById('scoreNotes').textContent = `Incertezza meteo alta: verifica condizioni prima di uscire.${detail}`;
    }

    document.getElementById('dailyPhases').innerHTML = data.daily.slice(0, 5).map(renderDay).join('');
    document.getElementById('hourlyCards').innerHTML = data.hourly.length ? data.hourly.slice(0, 18).map(renderHour).join('') : '<div class="muted">Meteo orario non disponibile. Le finestre luce restano calcolate localmente.</div>';
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
document.getElementById('locationInput').addEventListener('input', queuePlaceSuggestions);
document.addEventListener('click', (event)=>{
    if(!event.target.closest('.search-wrap')){
        document.getElementById('placeSuggestions').classList.remove('visible');
    }
});
</script>
</body>
</html>
"""


@app.route("/api/geocode")
def api_geocode():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query mancante."}), 400

    cached_locations = read_json(LOCATIONS_CACHE_FILE, {})
    normalized_query = query.casefold()

    try:
        response = requests.get(
            GEOCODING_URL,
            params={"name": query, "count": 5, "language": "it", "format": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        cached = cached_locations.get(normalized_query)
        if cached:
            cached["source"] = "cache"
            cached["warning"] = f"Geocoding online non disponibile: uso localita salvata. Dettaglio: {exc}"
            return jsonify(cached)
        return jsonify({"error": f"Geocoding non disponibile e nessuna cache locale: {exc}"}), 502

    data = response.json()
    results = []
    for item in data.get("results", []):
        results.append({
            "name": item.get("name"),
            "country": item.get("country"),
            "admin1": item.get("admin1"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "timezone": item.get("timezone"),
        })

    payload = {"results": results, "source": "Open-Meteo"}
    if results:
        cached_locations[normalized_query] = {
            "results": results,
            "source": "cache",
            "updated": utc_now_label(),
        }
        write_json(LOCATIONS_CACHE_FILE, cached_locations)

    return jsonify(payload)


@app.route("/api/places")
def api_places():
    query = request.args.get("q", "").strip()
    if len(query) < 3:
        return jsonify({"results": [], "source": "cache"})

    cached_locations = read_json(LOCATIONS_CACHE_FILE, {})
    cache_id = f"places:{query.casefold()}"

    try:
        places = search_places(query)
        payload = {
            "results": places,
            "source": "Photon + Nominatim",
            "updated": utc_now_label(),
        }
        if places:
            cached_locations[cache_id] = {
                "results": places,
                "source": "cache",
                "updated": payload["updated"],
            }
            write_json(LOCATIONS_CACHE_FILE, cached_locations)
        return jsonify(payload)
    except requests.RequestException as exc:
        cached = cached_locations.get(cache_id)
        if cached:
            cached = dict(cached)
            cached["warning"] = f"Ricerca luoghi online non disponibile: uso cache locale. Dettaglio: {exc}"
            return jsonify(cached)
        return jsonify({"error": f"Ricerca luoghi non disponibile e nessuna cache locale: {exc}"}), 502


@app.route("/api/plan")
def api_plan():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    name = request.args.get("name", "Localita")
    country = request.args.get("country", "")
    requested_timezone = request.args.get("timezone")

    try:
        latitude = float(lat)
        longitude = float(lon)
    except (TypeError, ValueError):
        return jsonify({"error": "Coordinate non valide."}), 400

    key = cache_key(latitude, longitude)
    plan_cache = read_json(PLAN_CACHE_FILE, {})
    cached_entry = plan_cache.get(key, {})
    timezone_name = requested_timezone or cached_entry.get("timezone") or DEFAULT_TIMEZONE

    weather_data = None
    secondary_data = None
    weather_status = "meteo non disponibile"
    weather_confidence = "non verificata"
    weather_comparison = {
        "enabled": SECONDARY_WEATHER_SOURCE not in {"", "none", "off", "disabled"},
        "primary": "Open-Meteo",
        "secondary": "MET Norway" if SECONDARY_WEATHER_SOURCE not in {"", "none", "off", "disabled"} else None,
        "compared_hours": 0,
        "uncertainty": "non verificata",
        "high_uncertainty": False,
        "discrepancies": [],
        "thresholds": UNCERTAINTY_THRESHOLDS,
    }
    warning = None
    warnings = []

    try:
        weather_data = fetch_open_meteo(latitude, longitude)
        timezone_name = weather_data.get("timezone") or timezone_name
        weather_status = "meteo live"
    except requests.RequestException as exc:
        cached_plan = cached_entry.get("plan")
        if cached_plan:
            cached_plan = dict(cached_plan)
            cached_age = cache_age_hours(cached_entry.get("updated"))
            cached_plan["weather_status"] = "meteo cache"
            cached_plan["cache_age_hours"] = round(cached_age, 1) if cached_age is not None else None
            cached_plan["warning"] = "Meteo online non disponibile: uso ultimo dato salvato."
            cached_plan["daily"] = build_solar_daily_items(latitude, longitude, timezone_name, cached_entry.get("weather_daily", {}))
            cached_plan["light_source"] = "calcolo locale"
            cached_plan["weather_confidence"] = "cache"
            cached_plan["weather_comparison"] = cached_plan.get("weather_comparison") or weather_comparison
            return jsonify(cached_plan)
        weather_status = "solo luce locale"
        warning = f"Meteo online non disponibile: {exc}"
        warnings.append(warning)

    daily = build_solar_daily_items(latitude, longitude, timezone_name, weather_data.get("daily", {}) if weather_data else {})
    hourly = build_hourly_items(weather_data.get("hourly", {})) if weather_data else []

    if weather_data and weather_comparison["enabled"]:
        try:
            secondary_data = fetch_metno(latitude, longitude)
            secondary_hourly = metno_to_hourly_items(secondary_data) if secondary_data else []
            weather_comparison = compare_weather_sources(hourly, secondary_hourly, timezone_name)
            weather_confidence = weather_comparison["uncertainty"]
            if weather_comparison["high_uncertainty"]:
                weather_status = "meteo live - incertezza alta"
                warnings.append("Open-Meteo e MET Norway divergono: considera il meteo incerto.")
        except requests.RequestException as exc:
            weather_confidence = "non verificata"
            weather_comparison["error"] = str(exc)
            warnings.append("Seconda fonte meteo non disponibile: confronto non eseguito.")
    elif weather_data:
        weather_confidence = "non verificata"

    payload = {
        "location": {
            "name": name,
            "country": country,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_name,
        },
        "daily": daily,
        "hourly": hourly,
        "source": "Open-Meteo + calcolo solare locale" if weather_data else "calcolo solare locale",
        "weather_status": weather_status,
        "weather_confidence": weather_confidence,
        "weather_comparison": weather_comparison,
        "light_source": "calcolo locale",
        "updated": utc_now_label(),
        "warning": " ".join(warnings) if warnings else warning,
        "notes": [
            "Alba e tramonto sono calcolati localmente da coordinate, data e timezone.",
            "Blue hour e golden hour sono stime operative.",
            "Meteo e vento restano previsioni e vanno verificati sul posto.",
            "Se Open-Meteo e MET Norway divergono oltre le soglie, il pannello mostra incertezza alta.",
        ],
    }

    if weather_data:
        plan_cache[key] = {
            "updated": payload["updated"],
            "timezone": timezone_name,
            "weather_daily": weather_data.get("daily", {}),
            "secondary_weather": secondary_data,
            "plan": payload,
        }
        write_json(PLAN_CACHE_FILE, plan_cache)

    return jsonify(payload)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5054)
