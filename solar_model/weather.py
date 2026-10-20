"""PVGIS weather retrieval, validation, provenance, and explicit demonstration mode."""
from datetime import datetime, timezone
from pathlib import Path
import json

import numpy as np
import pandas as pd
import pvlib
import requests

from .config import Config

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/tmy"
REQUIRED = ["ghi", "dni", "dhi", "temp_air", "wind_speed", "relative_humidity", "pressure"]


def weather_key(c):
    return f"pvgis_{c.latitude:.4f}_{c.longitude:.4f}.json"


def fetch_pvgis(c, timeout=90):
    """Save raw, attributable public TMY. Never silently replace failures with demo data."""
    response = requests.get(PVGIS_URL, params={"lat": c.latitude, "lon": c.longitude,
        "outputformat": "json", "usehorizon": 1}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    parse_pvgis(payload, c)  # validate before saving
    payload["retrieval"] = {"retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "url": response.url, "site_label": c.site}
    DATA.mkdir(exist_ok=True)
    (DATA / weather_key(c)).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return parse_pvgis(payload, c)


def parse_pvgis(payload, c):
    rows = payload["outputs"]["tmy_hourly"]
    if len(rows) != 8760:
        raise ValueError("Expected 8,760 hourly rows in the non-leap PVGIS TMY.")
    raw = pd.DataFrame(rows)
    time_col = "time(UTC)" if "time(UTC)" in raw else "time"
    original = pd.to_datetime(raw[time_col], format="%Y%m%d:%H%M", utc=True)
    # Each TMY month can originate in a different source year. Construct a continuous
    # modelling year by month/day/hour, rather than sorting the original years.
    nominal = pd.DatetimeIndex([t.replace(year=2025) for t in original])
    raw.index = nominal
    raw["source_year"] = original.dt.year.to_numpy()
    raw = raw.sort_index()
    expected_utc = pd.date_range("2025-01-01", periods=8760, freq="h", tz="UTC")
    if not raw.index.equals(expected_utc):
        raise ValueError("TMY timestamps must cover every UTC hour exactly once.")
    rename = {"G(h)": "ghi", "Gb(n)": "dni", "Gd(h)": "dhi", "T2m": "temp_air",
        "WS10m": "wind_speed", "RH": "relative_humidity", "SP": "pressure"}
    out = raw.rename(columns=rename)[REQUIRED + ["source_year"]].astype(float)
    # Rotate 3 hours to create a complete local Nairobi calendar year, preserving
    # the original UTC hour-of-day. Kenya has no daylight-saving transitions.
    local_idx = pd.date_range("2025-01-01", periods=8760, freq="h", tz=c.timezone)
    offset = int(local_idx[0].utcoffset().total_seconds() / 3600)
    out = pd.DataFrame(np.roll(out.to_numpy(), offset, axis=0), index=local_idx, columns=out.columns)
    # A small negative reanalysis wind value occurs in the retrieved Lodwar TMY
    # (-0.32 m/s). Preserve raw JSON; clip only values in [-0.5, 0) with a count.
    minor_negative_wind = out.wind_speed.between(-0.5, 0, inclusive="left")
    wind_corrections = int(minor_negative_wind.sum())
    out.loc[minor_negative_wind, "wind_speed"] = 0.0
    loc = payload["inputs"]["location"]
    if abs(float(loc["latitude"]) - c.latitude) > 0.01 or abs(float(loc["longitude"]) - c.longitude) > 0.01:
        raise ValueError("Weather coordinates do not match the chosen site.")
    meteo = payload["inputs"].get("meteo_data", {})
    irradiation_offset = loc.get("irradiance_time_offset")
    if irradiation_offset is None:
        raise ValueError("PVGIS irradiance time offset is missing; refresh the TMY using API 5.3.")
    meta = {"source": "JRC PVGIS 5.3 typical meteorological year", "kind": "TMY",
        "radiation_db": meteo.get("radiation_db", "PVGIS default"),
        "year_min": meteo.get("year_min"), "year_max": meteo.get("year_max"),
        "months_selected": payload["outputs"].get("months_selected", []),
        "latitude": float(loc["latitude"]), "longitude": float(loc["longitude"]),
        "elevation": loc.get("elevation"), "irradiance_time_offset_h": float(irradiation_offset),
        "retrieval": payload.get("retrieval", {}),
        "quality_notes": [f"{wind_corrections} small negative wind samples in [-0.5, 0) m/s set to zero; raw JSON retained."] if wind_corrections else [],
        "note": "2025 is a non-leap calendar label for stitched historical months, not an actual 2025 record or a forecast."}
    validate_weather(out)
    return out, meta


def load_bundled(c):
    path = DATA / weather_key(c)
    if not path.exists():
        raise FileNotFoundError(f"No cached TMY for {c.site}. Download PVGIS or select explicit demo mode.")
    return parse_pvgis(json.loads(path.read_text(encoding="utf-8")), c)


def validate_weather(df):
    missing = set(REQUIRED) - set(df)
    if missing:
        raise ValueError(f"Missing weather columns: {', '.join(sorted(missing))}")
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
        raise ValueError("Weather timestamps must include a timezone.")
    if not df.index.is_monotonic_increasing or not df.index.is_unique or len(df) < 2:
        raise ValueError("Weather timestamps must increase without duplicates.")
    intervals = (df.index[1:] - df.index[:-1]).total_seconds().to_numpy() / 3600
    if not np.allclose(intervals, intervals[0]) or intervals[0] > 1:
        raise ValueError("Weather intervals must be regular and no longer than one hour.")
    a = df[REQUIRED].to_numpy(dtype=float)
    if not np.isfinite(a).all():
        raise ValueError("Weather contains missing or non-finite values.")
    bounds = {"ghi": (0, 1500), "dni": (0, 1500), "dhi": (0, 1500), "temp_air": (-40, 65),
        "wind_speed": (0, 80), "relative_humidity": (0, 100), "pressure": (40000, 110000)}
    for col, (lo, hi) in bounds.items():
        if not df[col].between(lo, hi).all():
            raise ValueError(f"{col} is outside expected physical bounds [{lo}, {hi}].")


def parse_weather_csv(file, c):
    df = pd.read_csv(file)
    if "timestamp" not in df:
        raise ValueError("CSV needs a timestamp column with UTC or explicit timezone offsets.")
    if not df["timestamp"].astype(str).str.contains(r"(?:Z|[+-]\d\d:\d\d)$", regex=True).all():
        raise ValueError("Every CSV timestamp must include Z or an explicit UTC offset.")
    df.index = pd.to_datetime(df.pop("timestamp"), utc=True).dt.tz_convert(c.timezone)
    validate_weather(df)
    return df, {"source": "User-supplied weather CSV", "kind": "Uploaded",
        "irradiance_time_offset_h": 0.0, "latitude": c.latitude, "longitude": c.longitude,
        "note": "User responsible for site match and measurement provenance; timestamps represent sample instants."}


def demo_weather(c, days=365):
    """Reproducible synthetic exploration, deliberately labelled uncalibrated."""
    idx = pd.date_range("2025-01-01", periods=days * 24, freq="h", tz=c.timezone)
    loc = pvlib.location.Location(c.latitude, c.longitude, tz=c.timezone, altitude=c.altitude_m)
    clear = loc.get_clearsky(idx + pd.Timedelta(minutes=30))
    rng = np.random.default_rng(47)
    daily = rng.uniform(0.45, 0.95, size=days)
    cloud = np.repeat(daily, 24) * (0.9 + 0.1 * np.sin(np.arange(len(idx)) / 3) ** 2)
    ghi = clear["ghi"].to_numpy() * cloud
    dni = clear["dni"].to_numpy() * cloud**1.8
    zenith = loc.get_solarposition(idx + pd.Timedelta(minutes=30))["apparent_zenith"].to_numpy()
    dhi = np.maximum(ghi - dni * np.maximum(np.cos(np.radians(zenith)), 0), 0)
    mean_temp = 19 if c.altitude_m > 1000 else 29
    temp = mean_temp + 6 * np.cos(2 * np.pi * (idx.hour.to_numpy() - 15) / 24)
    out = pd.DataFrame({"ghi": ghi, "dni": dni, "dhi": dhi, "temp_air": temp,
        "wind_speed": rng.uniform(0.5, 5.5, len(idx)), "relative_humidity": 60.0,
        "pressure": pvlib.atmosphere.alt2pres(c.altitude_m)}, index=idx)
    return out, {"source": "SYNTHETIC demonstration: clear sky with artificial cloud and weather",
        "kind": "Synthetic", "irradiance_time_offset_h": 0.5, "latitude": c.latitude,
        "longitude": c.longitude, "note": "Not calibrated to Kenya climate. Do not use for yield or sizing decisions."}


def prepare_weather(df, meta, c):
    validate_weather(df)
    base_minutes = (df.index[1] - df.index[0]).total_seconds() / 60
    if c.step_minutes > base_minutes:
        raise ValueError("Choose a simulation time step no coarser than the uploaded weather.")
    # Zero-order hold: conserves input energy of each hourly interval. No claim
    # of measured subhourly weather or gusts is made.
    n = int(round(base_minutes / c.step_minutes))
    if not np.isclose(n * c.step_minutes, base_minutes):
        raise ValueError("Simulation time step must evenly divide the weather interval.")
    idx = pd.date_range(df.index[0], periods=len(df) * n, freq=f"{c.step_minutes}min")
    out = df.reindex(idx, method="ffill").copy()
    out[["ghi", "dni", "dhi"]] *= c.irradiance_scale
    out["temp_air"] += c.ambient_delta_c
    out["gust_proxy_ms"] = np.maximum(out["wind_speed"] * c.gust_factor, c.forced_gust_ms)
    out["fault_active"] = ((idx.dayofyear >= c.fault_start_day) &
        (idx.dayofyear < c.fault_start_day + c.fault_days))
    out["solar_time"] = idx + pd.to_timedelta(meta.get("irradiance_time_offset_h", 0), unit="h")
    return out
