from flask import Flask, jsonify, request
from datetime import datetime, timezone
import requests
import json
import os
import copy

app = Flask(__name__)

LAT = 40.771
LON = 14.789

DATA_FILE = "/data/drone_batteries.json"
DRONES_LIBRARY_FILE = "/data/drones_library.json"
BUNDLED_DRONES_LIBRARY_FILE = os.path.join(os.path.dirname(__file__), "drones_library.json")
MY_DRONES_FILE = "/data/my_drones.json"
WEATHER_CACHE_FILE = "/data/drone_weather_cache.json"
DRONE_LOCATIONS_CACHE_FILE = "/data/drone_locations_cache.json"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
METNO_FORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_SEARCH_URL = "https://photon.komoot.io/api/"
SECONDARY_WEATHER_SOURCE = os.environ.get("NIWA_SECONDARY_WEATHER_SOURCE", "metno").strip().lower()
METNO_USER_AGENT = os.environ.get("NIWA_METNO_USER_AGENT", "NIWA-AP/0.1")
NOMINATIM_USER_AGENT = os.environ.get("NIWA_NOMINATIM_USER_AGENT", "NIWA-AP/0.1")
PLACE_SEARCH_COUNTRY = os.environ.get("NIWA_PLACE_SEARCH_COUNTRY", "it").strip().lower()
REQUEST_TIMEOUT = 10

WEATHER_DISCREPANCY_THRESHOLDS = {
    "temperature_c": 4,
    "wind_kmh": 8,
    "gust_kmh": 10,
}

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


def get_default_drone_library():
    try:
        with open(BUNDLED_DRONES_LIBRARY_FILE, "r", encoding="utf-8") as file:
            bundled_library = json.load(file)

        if isinstance(bundled_library, dict) and bundled_library:
            return bundled_library
    except Exception:
        pass

    return DEFAULT_DRONE_LIBRARY


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
    default_library = get_default_drone_library()
    library = load_json_file(
        DRONES_LIBRARY_FILE,
        default_library,
        create_if_missing=True
    )

    changed = False
    for drone_id, profile in default_library.items():
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


def number(value, default=0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def weather_cache_key(lat, lon):
    return f"{round(float(lat), 4):.4f},{round(float(lon), 4):.4f}"


def utc_now_label():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def cache_age_hours(raw_time):
    parsed = parse_iso(raw_time)
    if not parsed:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(0, delta.total_seconds() / 3600)


def fetch_open_meteo_drone_weather(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        ]),
        "hourly": ",".join([
            "wind_speed_80m",
            "wind_speed_120m",
        ]),
        "wind_speed_unit": "kmh",
        "timezone": "auto",
    }
    response = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def build_open_meteo_payload(data, lat, lon, source, place):
    current = data["current"]
    current_hour = current["time"][:13]
    hourly = data.get("hourly", {})
    hourly_times = hourly.get("time", [])

    idx = next(
        (i for i, t in enumerate(hourly_times) if t[:13] == current_hour),
        None
    )

    wind80_values = hourly.get("wind_speed_80m", [])
    wind120_values = hourly.get("wind_speed_120m", [])

    return {
        "lat": lat,
        "lon": lon,
        "source": source,
        "place": place,
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "wind10": current.get("wind_speed_10m"),
        "wind80": wind80_values[idx] if idx is not None and idx < len(wind80_values) else None,
        "wind120": wind120_values[idx] if idx is not None and idx < len(wind120_values) else None,
        "gusts": current.get("wind_gusts_10m"),
        "rain": current.get("precipitation"),
        "direction": current.get("wind_direction_10m"),
        "updated": current.get("time"),
    }


def fetch_metno_drone_weather(lat, lon):
    if SECONDARY_WEATHER_SOURCE not in {"metno", "met.no", "met_norway"}:
        return None

    headers = {"User-Agent": METNO_USER_AGENT}
    params = {"lat": round(float(lat), 4), "lon": round(float(lon), 4)}
    response = requests.get(METNO_FORECAST_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    timeseries = data.get("properties", {}).get("timeseries", [])
    if not timeseries:
        return None

    current = timeseries[0]
    instant = current.get("data", {}).get("instant", {}).get("details", {})
    next_1h = current.get("data", {}).get("next_1_hours", {}).get("details", {})
    wind_ms = instant.get("wind_speed")
    gust_ms = instant.get("wind_speed_of_gust")

    return {
        "time": current.get("time"),
        "temperature": instant.get("air_temperature"),
        "humidity": instant.get("relative_humidity"),
        "wind10": round(wind_ms * 3.6, 1) if isinstance(wind_ms, (int, float)) else None,
        "gusts": round(gust_ms * 3.6, 1) if isinstance(gust_ms, (int, float)) else None,
        "rain": next_1h.get("precipitation_amount"),
        "direction": instant.get("wind_from_direction"),
        "cloud_cover": instant.get("cloud_area_fraction"),
    }


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

    return {
        "name": name or "Luogo",
        "display_name": item.get("display_name") or name or "Luogo",
        "country": address.get("country") or "",
        "admin1": address.get("state") or address.get("region") or "",
        "city": city or "",
        "latitude": float(item.get("lat")),
        "longitude": float(item.get("lon")),
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
    response = requests.get(
        PHOTON_SEARCH_URL,
        params={
            "q": query,
            "limit": limit,
            "lang": "it",
        },
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


def compare_drone_weather(primary, secondary):
    comparison = {
        "enabled": SECONDARY_WEATHER_SOURCE not in {"", "none", "off", "disabled"},
        "primary": "Open-Meteo",
        "secondary": "MET Norway" if SECONDARY_WEATHER_SOURCE not in {"", "none", "off", "disabled"} else None,
        "uncertainty": "non verificata",
        "high_uncertainty": False,
        "discrepancies": [],
        "thresholds": WEATHER_DISCREPANCY_THRESHOLDS,
    }

    if not comparison["enabled"] or not secondary:
        return comparison

    discrepancies = []
    comparable = 0

    if primary.get("temperature") is not None and secondary.get("temperature") is not None:
        comparable += 1
        temp_diff = abs(number(primary.get("temperature")) - number(secondary.get("temperature")))
        if temp_diff >= WEATHER_DISCREPANCY_THRESHOLDS["temperature_c"]:
            discrepancies.append(f"temperatura {round(temp_diff, 1)}C")

    if primary.get("wind10") is not None and secondary.get("wind10") is not None:
        comparable += 1
        wind_diff = abs(number(primary.get("wind10")) - number(secondary.get("wind10")))
        if wind_diff >= WEATHER_DISCREPANCY_THRESHOLDS["wind_kmh"]:
            discrepancies.append(f"vento 10m {round(wind_diff, 1)} km/h")

    if primary.get("gusts") is not None and secondary.get("gusts") is not None:
        comparable += 1
        gust_diff = abs(number(primary.get("gusts")) - number(secondary.get("gusts")))
        if gust_diff >= WEATHER_DISCREPANCY_THRESHOLDS["gust_kmh"]:
            discrepancies.append(f"raffiche {round(gust_diff, 1)} km/h")

    if primary.get("rain") is not None and secondary.get("rain") is not None:
        comparable += 1
        primary_rain = number(primary.get("rain"))
        secondary_rain = number(secondary.get("rain"))
        rain_conflict = (primary_rain > 0 and secondary_rain <= 0) or (primary_rain <= 0 and secondary_rain >= 0.5)
        if rain_conflict:
            discrepancies.append("pioggia discordante")

    comparison["comparable_fields"] = comparable
    comparison["discrepancies"] = discrepancies
    if comparable == 0:
        comparison["uncertainty"] = "non verificabile"
    elif len(discrepancies) >= 2 or any(item.startswith(("vento", "raffiche")) for item in discrepancies):
        comparison["uncertainty"] = "alta"
        comparison["high_uncertainty"] = True
    elif discrepancies:
        comparison["uncertainty"] = "media"
    else:
        comparison["uncertainty"] = "bassa"

    return comparison


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
:root{color-scheme:dark;--bg:#0b1220;--panel:#172033;--panel2:#101827;--line:#334155;--text:#f8fafc;--muted:#94a3b8;--soft:#cbd5e1;--blue:#38bdf8;--green:#22c55e;--yellow:#facc15;--red:#ef4444}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:radial-gradient(circle at 24% 0%,rgba(56,189,248,.10),transparent 32%),linear-gradient(180deg,#0b1220,#0f172a 42%,#0b1220);color:var(--text);padding:20px}
.topbar{display:flex;gap:14px;align-items:flex-start;justify-content:space-between;margin-bottom:18px}
.topbar a{display:inline-flex;align-items:center;justify-content:center;color:white;text-decoration:none;background:#263244;border:1px solid rgba(148,163,184,.22);padding:10px 12px;border-radius:10px;min-height:40px;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.topbar a:hover{background:#334155}
h1{margin:0 0 6px 0;font-size:32px;letter-spacing:0}.subtitle{color:var(--muted);line-height:1.45}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
.card{background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));border:1px solid rgba(148,163,184,.18);border-radius:12px;padding:16px;box-shadow:0 18px 34px rgba(0,0,0,.22)}
.card h2{margin-top:0;font-size:18px}.value{font-size:28px;font-weight:bold;margin:8px 0}.label{color:var(--muted);font-size:14px;line-height:1.4}
.button{display:block;background:#263244;color:white;text-decoration:none;padding:12px;border:1px solid rgba(148,163,184,.22);border-radius:10px;margin:8px 0;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.button:hover,button:hover{background:#334155}
.warning{background:rgba(127,29,29,.62);border:1px solid rgba(248,113,113,.28);padding:12px;border-radius:10px;margin-top:20px;color:#fecaca}
.small{color:var(--muted);font-size:13px;margin-top:14px}
input,select{width:100%;padding:10px;border-radius:10px;border:1px solid rgba(148,163,184,.20);margin-top:10px;box-sizing:border-box;background:#101827;color:white}
button{width:100%;padding:10px;border-radius:10px;border:1px solid rgba(148,163,184,.22);margin-top:8px;background:#263244;color:white;cursor:pointer}
.safe{background:linear-gradient(180deg,rgba(6,78,59,.92),rgba(15,23,42,.94));border-color:rgba(34,197,94,.35)}.caution{background:linear-gradient(180deg,rgba(120,53,15,.90),rgba(15,23,42,.94));border-color:rgba(250,204,21,.35)}.danger{background:linear-gradient(180deg,rgba(127,29,29,.90),rgba(15,23,42,.94));border-color:rgba(239,68,68,.36)}
.search-wrap{position:relative}.suggestions{display:none;position:absolute;left:0;right:0;top:calc(100% + 6px);z-index:6;background:#101827;border:1px solid rgba(148,163,184,.24);border-radius:12px;overflow:hidden;box-shadow:0 18px 34px rgba(0,0,0,.35)}.suggestions.visible{display:block}.suggestion{padding:11px 12px;border-top:1px solid rgba(148,163,184,.14);cursor:pointer}.suggestion:first-child{border-top:0}.suggestion:hover{background:#162338}.suggestion strong{display:block;font-size:14px}.suggestion span{display:block;color:var(--muted);font-size:12px;margin-top:3px;line-height:1.35}
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
    background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));
    border:1px solid rgba(148,163,184,.18);
    border-radius:12px;
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
    background:rgba(15,23,42,.90);
    border:1px solid rgba(148,163,184,.18);
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

:root{--bg:#0f0d0d;--panel:#211918;--panel2:#151112;--line:rgba(203,144,124,.28);--text:#fff7f0;--muted:#c8afa4;--soft:#eadbd4;--blue:#d59a84;--accent:#d59a84;--accent-strong:#f0b8a2}
body{background:radial-gradient(circle at 18% -5%,rgba(213,154,132,.22),transparent 34%),radial-gradient(circle at 84% 8%,rgba(246,226,209,.08),transparent 28%),linear-gradient(180deg,#0e0c0c,#171211 46%,#0e0c0c)}
.brand-heading{display:flex;align-items:center;gap:12px;min-width:0}
.brand-logo{width:52px;height:52px;border-radius:50%;border:1px solid rgba(213,154,132,.42);background:#f2dfcf;box-shadow:0 16px 34px rgba(0,0,0,.28);flex:0 0 auto}
.brand-copy{min-width:0}
h1{color:#fff4ec}.subtitle{color:var(--muted)}
.topbar a,.button,button{background:rgba(64,45,42,.92);border-color:var(--line)}
.topbar a:hover,.button:hover,button:hover{background:rgba(87,61,56,.96);border-color:rgba(213,154,132,.42)}
.card,.battery-section{background:linear-gradient(180deg,rgba(42,31,29,.94),rgba(18,14,14,.96));border-color:var(--line);box-shadow:0 18px 34px rgba(0,0,0,.25)}
input,select,.suggestions{background:#151112;border-color:var(--line)}
.suggestion{border-top-color:rgba(203,144,124,.18)}.suggestion:hover{background:#241a18}
.drone-pill,.battery{background:rgba(21,17,18,.92);border:1px solid rgba(203,144,124,.20)}
.drone-pill.active{border-color:var(--accent)}
.drone-meta{color:var(--muted)}
.battery-slider::-webkit-slider-runnable-track{background:linear-gradient(to right,var(--accent) 0%,var(--accent) var(--battery-level),rgba(99,74,70,.95) var(--battery-level),rgba(99,74,70,.95) 100%)}
.battery-slider::-moz-range-progress{background:var(--accent)}

@media(max-width:700px){
    .battery-header{grid-template-columns:1fr}
    .drone-row{display:block}
    .drone-row button{width:100%}
    .custom-grid{grid-template-columns:1fr}
    .topbar{display:block}
    .brand-logo{width:44px;height:44px}
    .topbar a{display:inline-block;margin-top:10px}
}
</style>
</head>

<body>

<div class="topbar">
<div class="brand-heading">
<img class="brand-logo" src="/static/niwa-logo.png" alt="">
<div class="brand-copy">
<h1>🚁 NIWA Drone Panel</h1>
<div class="subtitle">Meteo operativo, batterie, checklist e sicurezza drone.</div>
</div>
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
<div class="search-wrap">
<input id="placeInput" placeholder="Es. Napoli">
<div id="placeSuggestions" class="suggestions"></div>
</div>
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
let SELECTED_PLACE = null;
let suggestTimer = null;
let latestSuggestQuery = '';

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
        category: profile.category || '',
        maxWind: Number(profile.max_wind_kmh || profile.maxWind || 0),
        maxWindMs: Number(profile.max_wind_ms || 0),
        source: profile.source || '',
        sourceQuality: profile.source_quality || '',
        sourceUrl: profile.source_url || '',
        uncertainty: profile.uncertainty || '',
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
    if(!value){
        return;
    }

    if(SELECTED_PLACE && SELECTED_PLACE.display_name === value){
        saveSelectedPlace(SELECTED_PLACE);
        return;
    }

    fetchPlaceSuggestions(value).then((places)=>{
        if(places.length){
            saveSelectedPlace(places[0]);
        }else{
            localStorage.setItem('niwa_place', value);
            localStorage.removeItem('niwa_place_name');
            localStorage.removeItem('niwa_place_lat');
            localStorage.removeItem('niwa_place_lon');
            loadWeather();
        }
    }).catch(()=>{
        localStorage.setItem('niwa_place', value);
        localStorage.removeItem('niwa_place_name');
        localStorage.removeItem('niwa_place_lat');
        localStorage.removeItem('niwa_place_lon');
        loadWeather();
    });
}

function saveSelectedPlace(place){
    SELECTED_PLACE = place;
    document.getElementById('placeInput').value = place.display_name;
    document.getElementById('placeSuggestions').classList.remove('visible');
    localStorage.setItem('niwa_place', place.display_name);
    localStorage.setItem('niwa_place_name', place.name);
    localStorage.setItem('niwa_place_lat', place.latitude);
    localStorage.setItem('niwa_place_lon', place.longitude);
    loadWeather();
}

async function fetchPlaceSuggestions(query){
    const res = await fetch(`/api/places?q=${encodeURIComponent(query)}&_=${Date.now()}`, {cache:'no-store'});
    const data = await res.json();
    if(data.error){ throw new Error(data.error); }
    return data.results || [];
}

function escapeHtml(value){
    return String(value).replace(/[&<>"']/g, (char)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
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
        saveSelectedPlace(place);
    }
}

function queuePlaceSuggestions(){
    const query = document.getElementById('placeInput').value.trim();
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
            if(document.getElementById('placeInput').value.trim() === latestSuggestQuery){
                renderPlaceSuggestions(places);
            }
        }catch(e){
            if(document.getElementById('placeInput').value.trim() === latestSuggestQuery){
                renderPlaceSuggestions([]);
            }
        }
    }, 300);
}

function clearPlace(){
    localStorage.removeItem('niwa_place');
    localStorage.removeItem('niwa_place_name');
    localStorage.removeItem('niwa_place_lat');
    localStorage.removeItem('niwa_place_lon');
    document.getElementById('placeInput').value = '';
    renderPlaceSuggestions([]);
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

function displayValue(value, suffix=''){
    if(value === null || value === undefined || value === ''){
        return '--';
    }
    return `${value}${suffix}`;
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

    if(d.weather_comparison && d.weather_comparison.high_uncertainty){
        level = 'caution';
        text = '🟡 INCERTEZZA';
        msg = 'Fonti meteo discordanti su vento, raffiche o pioggia. Valuta manualmente e controlla app ufficiali prima del volo.';
    }

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
        const savedLat = localStorage.getItem('niwa_place_lat');
        const savedLon = localStorage.getItem('niwa_place_lon');
        const savedName = localStorage.getItem('niwa_place_name') || savedPlace;

        if(savedLat && savedLon){
            url = `/api/weather?lat=${encodeURIComponent(savedLat)}&lon=${encodeURIComponent(savedLon)}&place=${encodeURIComponent(savedName || savedPlace || 'Luogo selezionato')}&source=manual`;
        }else if(savedPlace){
            url = `/api/weather?place=${encodeURIComponent(savedPlace)}&source=manual`;
        }

        const res = await fetch(url);
        const d = await res.json();

        if(d.error){ throw new Error(d.error); }

        document.getElementById('place').textContent = d.place;
        document.getElementById('coords').textContent = `Coordinate: ${d.lat}, ${d.lon}`;
        const confidence = d.weather_confidence ? ` - incertezza ${d.weather_confidence}` : '';
        const status = d.weather_status ? ` - ${d.weather_status}` : '';
        document.getElementById('source').textContent = `Fonte: ${d.source}${status}${confidence}`;

        document.getElementById('temp').textContent = displayValue(d.temperature, ' °C');
        document.getElementById('humidity').textContent = displayValue(d.humidity, ' %');
        document.getElementById('wind10').textContent = displayValue(d.wind10, ' km/h');
        document.getElementById('wind80').textContent = displayValue(d.wind80, ' km/h');
        document.getElementById('wind120').textContent = displayValue(d.wind120, ' km/h');
        document.getElementById('gusts').textContent = displayValue(d.gusts, ' km/h');
        document.getElementById('rain').textContent = displayValue(d.rain, ' mm');
        document.getElementById('direction').textContent = displayValue(d.direction, '°');
        const warning = d.warning ? ` - ${d.warning}` : '';
        document.getElementById('updated').textContent = 'Aggiornamento: ' + d.updated + warning;

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
    const savedPlace = localStorage.getItem('niwa_place');
    if(savedPlace){
        document.getElementById('placeInput').value = savedPlace;
    }
    loadWeather();
}

init();
setInterval(loadWeather, 10 * 60 * 1000);
document.getElementById('placeInput').addEventListener('input', queuePlaceSuggestions);
document.addEventListener('click', (event)=>{
    if(!event.target.closest('.search-wrap')){
        document.getElementById('placeSuggestions').classList.remove('visible');
    }
});
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
:root{color-scheme:dark;--bg:#0b1220;--panel:#172033;--panel2:#101827;--line:#334155;--text:#f8fafc;--muted:#94a3b8;--soft:#cbd5e1;--blue:#38bdf8;--green:#22c55e;--red:#ef4444}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:radial-gradient(circle at 24% 0%,rgba(56,189,248,.10),transparent 32%),linear-gradient(180deg,#0b1220,#0f172a 42%,#0b1220);color:var(--text);padding:20px}
h1{margin:0 0 6px 0;font-size:32px;letter-spacing:0}.subtitle{color:var(--muted);margin-bottom:20px;line-height:1.45}
.topbar{display:flex;gap:14px;align-items:flex-start;justify-content:space-between;margin-bottom:18px}
.topbar a{display:inline-flex;align-items:center;justify-content:center;color:white;text-decoration:none;background:#263244;border:1px solid rgba(148,163,184,.22);padding:10px 12px;border-radius:10px;min-height:40px;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,360px);gap:16px}
.card{background:linear-gradient(180deg,rgba(30,41,59,.92),rgba(15,23,42,.94));border:1px solid rgba(148,163,184,.18);border-radius:12px;padding:16px;box-shadow:0 18px 34px rgba(0,0,0,.22)}
.card h2{margin-top:0;font-size:18px}.label{color:var(--muted);font-size:14px;line-height:1.4}.small{color:var(--muted);font-size:13px;margin-top:10px}
input,select{width:100%;padding:10px;border-radius:10px;border:1px solid rgba(148,163,184,.20);margin-top:10px;box-sizing:border-box;background:#101827;color:white}
button{padding:10px 12px;border-radius:10px;border:1px solid rgba(148,163,184,.22);background:#263244;color:white;cursor:pointer;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
button:hover,.topbar a:hover{background:#334155}.primary{background:#0369a1}.danger-btn{background:#7f1d1d}
.toolbar{display:grid;grid-template-columns:minmax(180px,280px) 1fr;gap:12px;align-items:end;margin-bottom:14px}
.drone-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.drone-card{background:rgba(15,23,42,.90);border-radius:10px;padding:14px;border:1px solid rgba(148,163,184,.18)}
.drone-card.mine{border-color:#3b82f6}.drone-card.owned{border-color:#22c55e}.drone-card h3{margin:0 0 6px 0;font-size:17px}
.meta{color:var(--muted);font-size:13px;line-height:1.4}.actions{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.source-link{display:inline-flex;margin-top:8px;color:#7dd3fc;text-decoration:none;font-size:13px}.source-link:hover{text-decoration:underline}
.quality-pill{display:inline-flex;align-items:center;margin-top:8px;padding:4px 8px;border-radius:999px;background:rgba(14,165,233,.12);border:1px solid rgba(125,211,252,.22);color:#bae6fd;font-size:12px}
.quality-pill.medium{background:rgba(245,158,11,.12);border-color:rgba(251,191,36,.28);color:#fde68a}
.owned-label{color:#86efac;font-size:13px;font-weight:bold;margin-top:12px}
.custom-grid{display:grid;grid-template-columns:1fr;gap:8px}.status{min-height:18px}
:root{--bg:#0f0d0d;--panel:#211918;--panel2:#151112;--line:rgba(203,144,124,.28);--text:#fff7f0;--muted:#c8afa4;--soft:#eadbd4;--blue:#d59a84;--accent:#d59a84;--accent-strong:#f0b8a2}
body{background:radial-gradient(circle at 18% -5%,rgba(213,154,132,.22),transparent 34%),radial-gradient(circle at 84% 8%,rgba(246,226,209,.08),transparent 28%),linear-gradient(180deg,#0e0c0c,#171211 46%,#0e0c0c)}
.brand-heading{display:flex;align-items:center;gap:12px;min-width:0}.brand-logo{width:52px;height:52px;border-radius:50%;border:1px solid rgba(213,154,132,.42);background:#f2dfcf;box-shadow:0 16px 34px rgba(0,0,0,.28);flex:0 0 auto}.brand-copy{min-width:0}
h1{color:#fff4ec}.subtitle{color:var(--muted)}
.topbar a,button{background:rgba(64,45,42,.92);border-color:var(--line)}
.topbar a:hover,button:hover{background:rgba(87,61,56,.96);border-color:rgba(213,154,132,.42)}
.primary{background:linear-gradient(180deg,#d59a84,#9f6f63);border-color:rgba(240,184,162,.45)}
.card{background:linear-gradient(180deg,rgba(42,31,29,.94),rgba(18,14,14,.96));border-color:var(--line);box-shadow:0 18px 34px rgba(0,0,0,.25)}
input,select,.drone-card{background:#151112;border-color:var(--line)}
.source-link{color:#f0b8a2}.quality-pill{background:rgba(213,154,132,.13);border-color:rgba(213,154,132,.30);color:#ffe0d1}
.drone-card.mine{border-color:var(--accent)}.drone-card.owned{border-color:#86efac}
@media(max-width:850px){.layout{grid-template-columns:1fr}.toolbar{grid-template-columns:1fr}.topbar{display:block}.brand-logo{width:44px;height:44px}.topbar a{display:inline-block;margin-top:10px}}
</style>
</head>
<body>
<div class="topbar">
<div class="brand-heading">
<img class="brand-logo" src="/static/niwa-logo.png" alt="">
<div class="brand-copy">
<h1>Gestione Droni</h1>
<div class="subtitle">Libreria locale, droni posseduti e profili custom.</div>
</div>
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
<div class="label" id="libraryStats"></div>
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
        category: profile.category || '',
        maxWind: Number(profile.max_wind_kmh || profile.maxWind || 0),
        maxWindMs: Number(profile.max_wind_ms || 0),
        source: profile.source || '',
        sourceQuality: profile.source_quality || '',
        sourceUrl: profile.source_url || '',
        uncertainty: profile.uncertainty || '',
        notes: profile.notes || ''
    };
}

function setStatus(message){
    document.getElementById('managerStatus').textContent = message || '';
}

function readableToken(value){
    return String(value || '').replaceAll('_', ' ');
}

function sourceSummary(drone){
    const quality = readableToken(drone.sourceQuality || drone.source || 'fonte non indicata');
    const uncertainty = drone.uncertainty ? `incertezza ${readableToken(drone.uncertainty)}` : 'incertezza non indicata';
    return `${quality} - ${uncertainty}`;
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
    updateLibraryStats();
    renderDroneLibrary();
    renderMyDrones();
}

function populateBrandFilter(){
    const select = document.getElementById('brandFilter');
    const current = select.value;
    const brands = [...new Set(Object.values(DRONES).map((drone)=>drone.brand || 'Custom'))].sort();

    select.innerHTML = '';
    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = 'Tutte le marche';
    select.appendChild(allOption);

    brands.forEach((brand)=>{
        const option = document.createElement('option');
        option.value = brand;
        option.textContent = brand;
        select.appendChild(option);
    });

    if(brands.includes(current)){
        select.value = current;
    }else{
        select.value = '';
    }
}

function updateLibraryStats(){
    const stats = document.getElementById('libraryStats');
    const brands = new Set(Object.values(DRONES).map((drone)=>drone.brand || 'Custom'));
    stats.textContent = `${Object.keys(DRONES).length} modelli in libreria, ${brands.size} marche. Usa il filtro per restringere la lista.`;
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
            : '<div class="label">Nessun drone trovato.</div>';
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
            <div class="quality-pill ${drone.uncertainty === 'medium' ? 'medium' : ''}">${sourceSummary(drone)}</div>
            <div class="meta">${drone.notes || ''}</div>
            ${drone.sourceUrl ? `<a class="source-link" href="${drone.sourceUrl}" target="_blank" rel="noopener">Fonte</a>` : ''}
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
    lat_query = request.args.get("lat")
    lon_query = request.args.get("lon")

    if lat_query and lon_query:
        lat = str(lat_query)
        lon = str(lon_query)
    elif place_query:
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

    cache_key = weather_cache_key(lat, lon)
    weather_cache = load_json_file(WEATHER_CACHE_FILE, {}, create_if_missing=False)
    cached_entry = weather_cache.get(cache_key, {}) if isinstance(weather_cache, dict) else {}

    try:
        data = fetch_open_meteo_drone_weather(lat, lon)
        place = place_query if lat_query and lon_query and place_query else reverse_geocode(lat, lon)
        payload = build_open_meteo_payload(data, lat, lon, source, place)
        payload["source"] = "Open-Meteo"
        payload["weather_status"] = "meteo live"
        payload["weather_confidence"] = "non verificata"
        payload["weather_comparison"] = compare_drone_weather(payload, None)
        payload["warning"] = None

        secondary_data = None
        try:
            secondary_data = fetch_metno_drone_weather(lat, lon)
            comparison = compare_drone_weather(payload, secondary_data)
            payload["weather_comparison"] = comparison
            payload["weather_confidence"] = comparison["uncertainty"]
            if comparison["high_uncertainty"]:
                payload["weather_status"] = "meteo live - incertezza alta"
                payload["warning"] = "Open-Meteo e MET Norway divergono: verifica vento e pioggia prima del volo."
        except requests.RequestException as exc:
            payload["weather_confidence"] = "non verificata"
            payload["weather_comparison"]["error"] = str(exc)
            payload["warning"] = "Seconda fonte meteo non disponibile: confronto non eseguito."

        weather_cache[cache_key] = {
            "updated": utc_now_label(),
            "payload": payload,
            "primary_weather": data,
            "secondary_weather": secondary_data,
        }
        save_json_file(WEATHER_CACHE_FILE, weather_cache)
        return jsonify(payload)

    except requests.RequestException as exc:
        cached_payload = cached_entry.get("payload") if isinstance(cached_entry, dict) else None
        if isinstance(cached_payload, dict):
            cached_payload = copy.deepcopy(cached_payload)
            age = cache_age_hours(cached_entry.get("updated"))
            cached_payload["weather_status"] = "meteo cache"
            cached_payload["weather_confidence"] = "cache"
            cached_payload["cache_age_hours"] = round(age, 1) if age is not None else None
            cached_payload["warning"] = "Meteo online non disponibile: uso ultimo dato salvato."
            return jsonify(cached_payload)
        return jsonify({"error": f"Meteo non disponibile e nessuna cache locale: {exc}"}), 500
    except Exception as e:
        cached_payload = cached_entry.get("payload") if isinstance(cached_entry, dict) else None
        if isinstance(cached_payload, dict):
            cached_payload = copy.deepcopy(cached_payload)
            cached_payload["weather_status"] = "meteo cache"
            cached_payload["weather_confidence"] = "cache"
            cached_payload["warning"] = "Errore meteo: uso ultimo dato salvato."
            return jsonify(cached_payload)
        return jsonify({"error": str(e)}), 500


@app.route("/api/places")
def api_places():
    query = request.args.get("q", "").strip()
    if len(query) < 3:
        return jsonify({"results": [], "source": "cache"})

    cached_locations = load_json_file(DRONE_LOCATIONS_CACHE_FILE, {}, create_if_missing=False)
    cache_id = query.casefold()

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
            save_json_file(DRONE_LOCATIONS_CACHE_FILE, cached_locations)
        return jsonify(payload)
    except requests.RequestException as exc:
        cached = cached_locations.get(cache_id)
        if cached:
            cached = dict(cached)
            cached["warning"] = f"Ricerca luoghi online non disponibile: uso cache locale. Dettaglio: {exc}"
            return jsonify(cached)
        return jsonify({"error": f"Ricerca luoghi non disponibile e nessuna cache locale: {exc}"}), 502


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
