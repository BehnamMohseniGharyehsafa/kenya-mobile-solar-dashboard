"""Download raw PVGIS TMY data for named Kenyan sites into data/."""
import argparse
from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solar_model.config import Config, SITES
from solar_model.weather import fetch_pvgis

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="Nairobi", choices=list(SITES) + ["all"])
    args = parser.parse_args()
    for site in (SITES if args.site == "all" else [args.site]):
        lat, lon, alt = SITES[site]
        c = replace(Config(), site=site, latitude=lat, longitude=lon, altitude_m=alt)
        try:
            weather, meta = fetch_pvgis(c)
            print(f"{site}: {len(weather)} rows; {meta['radiation_db']}; GHI {weather.ghi.sum()/1000:.1f} kWh/m2/year", flush=True)
        except Exception as exc:
            print(f"{site}: download/validation failed: {exc}", flush=True)
            if args.site != "all":
                raise
