"""Public simulation interface, shared by the dashboard, exports and tests."""
from dataclasses import replace
import numpy as np
import pandas as pd
import pvlib

from .config import MODES
from .weather import prepare_weather
from .pv import simulate_pv
from .dispatch import simulate_dispatch, summarize


def simulate(raw_weather, metadata, config):
    config.validate()
    weather = prepare_weather(raw_weather, metadata, config)
    pv = simulate_pv(weather, config)
    dispatch = simulate_dispatch(weather, pv, config)
    result = pd.concat([weather.drop(columns=["solar_time"]), pv, dispatch], axis=1)
    # A counterfactual export-capable inverter output before load/storage limits.
    # This is not delivered energy in the off-grid DC-coupled architecture.
    result["pv_ac_potential_kw"] = np.maximum(pvlib.inverter.pvwatts(
        result.pv_dc_kw, config.inverter_kw / config.inverter_eff,
        eta_inv_nom=config.inverter_eff), 0)
    return result, summarize(result, config)


def compare_trackers(raw_weather, metadata, config):
    """Same DC capacity and weather. Full thermal/dispatch rerun for each mode."""
    metrics = []
    for mode in MODES:
        _, summary = simulate(raw_weather, metadata, replace(config, tracking=mode))
        metrics.append({"Tracking": mode, "PV DC (kWh)": summary["pv_dc_kwh"],
            "User served (kWh)": summary["user_served_kwh"],
            "Renewable to users (kWh)": summary["renewable_user_kwh"],
            "Cooling (kWh)": summary["cooling_kwh"],
            "Tracker demand (kWh)": summary["tracker_kwh"],
            "Unserved (kWh)": summary["unserved_kwh"]})
    df = pd.DataFrame(metrics)
    fixed = df.loc[df.Tracking == "Fixed tilt", "PV DC (kWh)"].iloc[0]
    df["PV gain vs fixed (%)"] = (df["PV DC (kWh)"] / fixed - 1) * 100 if fixed else 0
    return df
