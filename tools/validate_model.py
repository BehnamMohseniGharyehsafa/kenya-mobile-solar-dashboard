"""Write reproducible default results and controlled design comparisons."""
from dataclasses import replace
from pathlib import Path
import json
import sys
import platform

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import pvlib
from solar_model.config import Config, SITES
from solar_model.weather import load_bundled
from solar_model.simulation import simulate, compare_trackers


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "outputs"
    output.mkdir(exist_ok=True)
    c = Config()
    w,m = load_bundled(c)
    r,s = simulate(w,m,c)
    payload = {"config":c.to_dict(),"weather":m,"summary":s,
        "runtime":{"python":platform.python_version(),"pvlib":pvlib.__version__}}
    (output/"nairobi_default.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    r.to_csv(output/"nairobi_default_timeseries.csv",index_label="timestamp")
    compare = compare_trackers(w,m,c)
    compare.to_csv(output/"tracking_comparison.csv",index=False)
    scenarios = []
    for name, design in [
        ("Nairobi default", c),
        ("Nairobi 160 kWh battery", replace(c,battery_kwh=160)),
        ("Nairobi passive", replace(c,cooling_mode="Passive")),
        ("Nairobi hotter +10C", replace(c,ambient_delta_c=10)),
        ("Nairobi forced 16 m/s gust", replace(c,forced_gust_ms=16)),
        ("Nairobi 2-day HVAC failure", replace(c,fault="HVAC failure")),
    ]:
        _,metrics = simulate(w,m,design)
        scenarios.append({"Scenario":name,**metrics})
    for name in ["Lodwar / Turkana", "Mombasa"]:
        lat,lon,alt = SITES[name]
        design = replace(c,site=name,latitude=lat,longitude=lon,altitude_m=alt)
        weather,metadata = load_bundled(design)
        _,metrics = simulate(weather,metadata,design)
        scenarios.append({"Scenario":name,**metrics})
    pd.DataFrame(scenarios).to_csv(output/"scenario_comparison.csv",index=False)
    assert abs(s["balance_residual_kwh"]) < 1e-6
    print(json.dumps(s,indent=2))
    print(compare.round(2).to_string(index=False))
    print(f"Saved {output}")
