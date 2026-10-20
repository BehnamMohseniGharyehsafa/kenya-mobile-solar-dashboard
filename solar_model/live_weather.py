"""Attributable current model weather and instantaneous solar forecasts.

Network data are never silently replaced by synthetic or historical climate.
The returned timestamps and cache age remain visible to the operator.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

import numpy as np
import pandas as pd
import requests

API_URL = "https://api.open-meteo.com/v1/forecast"
CACHE = Path(__file__).resolve().parents[1] / ".weather-cache"
VARIABLES = {
    "temperature_2m": "temp_air", "relative_humidity_2m": "relative_humidity",
    "surface_pressure": "pressure", "wind_speed_10m": "wind_speed",
    "wind_gusts_10m": "gust_ms", "wind_direction_10m": "wind_direction_deg",
    "cloud_cover": "cloud_pct", "precipitation": "precipitation_mm",
    "weather_code": "weather_code", "shortwave_radiation_instant": "ghi",
    "direct_normal_irradiance_instant": "dni", "diffuse_radiation_instant": "dhi",
}


def cache_path(c):
    return CACHE / f"open_meteo_{c.latitude:.4f}_{c.longitude:.4f}.json"


def parse_feed(payload, c):
    if payload.get("timezone") != c.timezone:
        raise ValueError("Weather timezone does not match the site timezone.")
    hourly = payload["hourly"]
    idx = pd.to_datetime(hourly["time"]).tz_localize(c.timezone)
    frame = pd.DataFrame({target: hourly[source] for source, target in VARIABLES.items()}, index=idx, dtype=float)
    frame["pressure"] *= 100  # API hPa -> model Pa
    if not frame.index.is_monotonic_increasing or not frame.index.is_unique or len(frame) < 24:
        raise ValueError("Incomplete or unordered forecast times.")
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError("Weather response contains missing values.")
    for col in ("ghi", "dni", "dhi", "wind_speed", "gust_ms"):
        if (frame[col] < 0).any():
            raise ValueError(f"Weather has negative {col} values.")
    current = payload.get("current", {})
    current_time = pd.Timestamp(current["time"], tz=c.timezone) if current.get("time") else None
    meta = {"provider": "Open-Meteo", "source_url": "https://open-meteo.com/en/docs",
        "model": "Best Match / global numerical weather models for Kenya",
        "retrieved_utc": payload["retrieval"]["retrieved_utc"],
        "request_url": payload["retrieval"]["url"], "current_time": current_time.isoformat() if current_time else None,
        "current": current, "latitude": payload["latitude"], "longitude": payload["longitude"],
        "elevation": payload.get("elevation"), "timezone": c.timezone,
        "note": "Modelled current conditions, not a local sensor measurement. Instantaneous hourly solar forecasts are linearly interpolated for the display."}
    return frame, meta


def fetch_feed(c, timeout=12):
    current = ["temperature_2m", "relative_humidity_2m", "surface_pressure", "wind_speed_10m",
        "wind_gusts_10m", "wind_direction_10m", "cloud_cover", "precipitation", "weather_code"]
    response = requests.get(API_URL, params={"latitude": c.latitude, "longitude": c.longitude,
        "timezone": c.timezone, "wind_speed_unit": "ms", "past_days": 1,
        "forecast_days": 3, "hourly": ",".join(VARIABLES), "current": ",".join(current)}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    payload["retrieval"] = {"retrieved_utc": datetime.now(timezone.utc).isoformat(), "url": response.url}
    frame, meta = parse_feed(payload, c)
    CACHE.mkdir(exist_ok=True)
    cache_path(c).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return frame, {**meta, "cache_status": "Fetched from provider"}


def load_feed(c, now=None, force=False):
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now).tz_convert("UTC")
    path = cache_path(c)
    cached = None
    if path.exists():
        try:
            cached = parse_feed(json.loads(path.read_text(encoding="utf-8")), c)
            age = (now - pd.Timestamp(cached[1]["retrieved_utc"])).total_seconds()
            if not force and 0 <= age < 900:
                return cached[0], {**cached[1], "cache_status": "Provider response cached <15 min"}
        except (ValueError, KeyError, TypeError):
            cached = None
    try:
        return fetch_feed(c)
    except (requests.RequestException, ValueError, KeyError) as exc:
        if cached:
            return cached[0], {**cached[1], "cache_status": "OFFLINE cached response", "error": str(exc)}
        raise RuntimeError(f"Current weather unavailable: {exc}") from exc


def sample_weather(frame, meta, when, live=False):
    when = pd.Timestamp(when)
    if when.tz is None:
        raise ValueError("Simulation timestamp requires a timezone.")
    when = when.tz_convert(frame.index.tz)
    if when < frame.index[0] or when > frame.index[-1]:
        raise ValueError("Selected time is outside the downloaded weather window. Refresh weather or return to live time.")
    times = (frame.index - frame.index[0]).total_seconds().to_numpy()
    x = (when - frame.index[0]).total_seconds()
    sample = {col: float(np.interp(x, times, frame[col].to_numpy())) for col in frame}
    current_time = pd.Timestamp(meta["current_time"]) if meta.get("current_time") else None
    if live and current_time is not None and abs((when-current_time).total_seconds()) <= 1800:
        current = meta["current"]
        for source, target in VARIABLES.items():
            if source in current and current[source] is not None:
                sample[target] = float(current[source]) * (100 if target == "pressure" else 1)
    sample["timestamp"] = when
    sample["weather_code"] = int(frame.weather_code.iloc[np.argmin(np.abs(times-x))])
    return sample


def weather_label(code):
    if code == 0:
        return "Clear sky"
    if code in (1, 2):
        return "Partly cloudy"
    if code == 3:
        return "Overcast"
    if code in (45, 48):
        return "Fog"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "Rain / showers"
    if code >= 95:
        return "Thunderstorm"
    return "Variable conditions"
