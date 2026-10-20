from dataclasses import replace
from io import StringIO
import json

import numpy as np
import pandas as pd
import pytest

from solar_model.config import Config, MODES, SITES
from solar_model.weather import demo_weather, load_bundled, parse_pvgis, parse_weather_csv, prepare_weather, validate_weather, DATA, weather_key
from solar_model.pv import simulate_pv, string_checks
from solar_model.dispatch import simulate_dispatch
from solar_model.simulation import simulate


@pytest.fixture
def example():
    c = Config()
    w,m = demo_weather(c, 4)
    return c,w,m


@pytest.mark.parametrize("mode", MODES)
def test_energy_balance_and_operating_bounds(example, mode):
    c,w,m = example
    c = replace(c, tracking=mode)
    r,s = simulate(w,m,c)
    assert abs(s["balance_residual_kwh"]) < 1e-8
    assert r.dc_balance_residual_kw.abs().max() < 1e-10
    assert r.battery_balance_residual_kwh.abs().max() < 1e-10
    assert r.soc.between(c.soc_min-1e-10, c.soc_max+1e-10).all()
    assert not ((r.battery_charge_kw > 1e-9) & (r.battery_discharge_kw > 1e-9)).any()
    assert (r.user_served_kw <= r.critical_demand_kw+r.flex_demand_kw+1e-10).all()
    assert np.isfinite(r.select_dtypes(include="number")).all().all()


def test_no_sun_and_empty_usable_storage_cannot_generate(example):
    c,w,m = example
    w[["ghi","dni","dhi"]] = 0.0
    c = replace(c, soc_initial=c.soc_min)
    r,s = simulate(w,m,c)
    assert s["pv_dc_kwh"] == 0
    assert s["user_served_kwh"] == 0
    assert s["renewable_user_kwh"] == 0
    assert s["unserved_kwh"] == pytest.approx(s["user_demand_kwh"])


def test_initial_battery_energy_is_not_called_renewable(example):
    c,w,m = example
    w[["ghi","dni","dhi"]] = 0.0
    r,s = simulate(w,m,c)
    assert s["user_served_kwh"] > 0
    assert s["renewable_user_kwh"] == 0
    assert s["initial_energy_user_kwh"] == pytest.approx(s["user_served_kwh"])
    assert s["battery_loss_kwh"] > 0
    assert abs(s["balance_residual_kwh"]) < 1e-8


def test_renewable_provenance_never_exceeds_delivery(example):
    c,w,m = example
    r,s = simulate(w,m,c)
    assert (r.renewable_user_kw >= -1e-12).all()
    assert (r.renewable_user_kw <= r.user_served_kw + 1e-12).all()
    assert s["renewable_user_kwh"] <= s["user_served_kwh"]
    assert (r.renewable_user_kw + r.initial_energy_user_kw).to_numpy() == pytest.approx(r.user_served_kw.to_numpy())


def test_wind_stow_latch_and_recovery(example):
    c,w,m = example
    weather = prepare_weather(w,m,c)
    weather["gust_proxy_ms"] = 0
    weather.iloc[40:44, weather.columns.get_loc("gust_proxy_ms")] = 15
    pv = simulate_pv(weather,c)
    assert (pv.tracker_state.iloc[40:44] == "WIND STOW").all()
    assert pv.tracker_state.iloc[44] == "WIND STOW"  # first 15 min of 20 min hold
    assert pv.tracker_state.iloc[45] != "WIND STOW"
    assert pv.surface_tilt_deg.iloc[41] == pytest.approx(c.stow_tilt_deg)
    movement = pv.tracker_rotation_deg.diff().abs().dropna()
    assert movement.max() <= c.slew_deg_per_min*c.step_minutes+1e-9


def test_jam_holds_position_even_during_wind(example):
    c,w,m = example
    c = replace(c, fault="Tracker jam",fault_start_day=1,fault_days=2,forced_gust_ms=20)
    weather = prepare_weather(w,m,c)
    pv = simulate_pv(weather,c)
    jam = weather.fault_active
    assert (pv.tracker_state[jam] == "TRACKER JAM").all()
    assert pv.tracker_rotation_deg[jam].nunique() == 1


def test_anemometer_failure_commands_stow(example):
    c,w,m = example
    c = replace(c, fault="Anemometer fault", fault_start_day=1, fault_days=1)
    r,s = simulate(w,m,c)
    assert (r.tracker_state[r.fault_active] == "SENSOR STOW").all()


def test_bms_fault_removes_battery_but_keeps_solar(example):
    c,w,m = example
    c = replace(c, fault="BMS trip", fault_start_day=1, fault_days=2)
    r,s = simulate(w,m,c)
    mask = r.fault_active
    assert r.battery_charge_kw[mask].sum() == 0
    assert r.battery_discharge_kw[mask].sum() == 0
    assert r.pv_dc_kw[mask].sum() > 0
    assert r.user_served_kw[mask].sum() > 0


def test_hot_battery_trips(example):
    c,w,m = example
    w["temp_air"] = 55.0
    c = replace(c,cooling_mode="Passive")
    r,s = simulate(w,m,c)
    assert r.battery_trip.all()
    assert r.battery_discharge_kw.sum() == 0
    assert r.battery_charge_kw.sum() == 0


def test_hybrid_cooling_consumes_power_and_reduces_heat(example):
    c,w,m = example
    w["temp_air"] = 38.0
    c = replace(c,shell_u_w_m2k=0.8,roof_shade_fraction=0,critical_kw=0.2,flexible_kw=0.1)
    passive,sp = simulate(w,m,replace(c,cooling_mode="Passive"))
    hybrid,sh = simulate(w,m,replace(c,cooling_mode="Hybrid HVAC"))
    assert sh["cooling_kwh"] > 0
    assert sp["cooling_kwh"] == 0
    assert hybrid.room_temp_c.mean() < passive.room_temp_c.mean()
    assert hybrid.battery_temp_c.mean() < passive.battery_temp_c.mean()


def test_hvac_failure_is_applied(example):
    c,w,m = example
    w["temp_air"] = 37.0
    c = replace(c,fault="HVAC failure",fault_start_day=1,fault_days=2)
    r,s = simulate(w,m,c)
    assert (r.cooling_kw[r.fault_active] == 0).all()
    assert (r.cooling_state[r.fault_active] == "FAULT").all()


def test_voltage_limit_blocks_incompatible_string(example):
    c,w,m = example
    c = replace(c,mppt_min_v=900)
    r,s = simulate(w,m,c)
    assert s["pv_dc_kwh"] == 0
    assert not string_checks(c).Pass.all()


def test_pvgis_chronology_provenance_and_local_time():
    c = Config()
    raw_payload = json.loads((DATA/weather_key(c)).read_text(encoding="utf-8"))
    w,m = parse_pvgis(raw_payload,c)
    assert len(w) == 8760
    assert w.index[0].hour == 0
    assert w.index[-1].strftime("%m-%d %H:%M") == "12-31 23:00"
    assert w.index.is_unique and w.index.is_monotonic_increasing
    assert m["kind"] == "TMY"
    assert m["irradiance_time_offset_h"] >= 0
    raw_rows = raw_payload["outputs"]["tmy_hourly"]
    assert w.temp_air.iloc[0] == raw_rows[-3]["T2m"]
    assert w.temp_air.iloc[3] == raw_rows[0]["T2m"]
    assert w.ghi.sum() == pytest.approx(sum(row["G(h)"] for row in raw_rows))


@pytest.mark.parametrize("site", list(SITES))
def test_bundled_sites_are_valid_and_attributed(site):
    lat,lon,alt = SITES[site]
    c = replace(Config(),site=site,latitude=lat,longitude=lon,altitude_m=alt)
    w,m = load_bundled(c)
    validate_weather(w)
    assert m["retrieval"]["url"].startswith("https://re.jrc.ec.europa.eu/")


def test_csv_timezone_and_missing_data_rejection(example):
    c,w,m = example
    text = w.iloc[:12].to_csv(index_label="timestamp")
    loaded,meta = parse_weather_csv(StringIO(text),c)
    assert len(loaded) == 12
    with pytest.raises(ValueError,match="offset"):
        parse_weather_csv(StringIO(text.replace("+03:00", "")),c)
    bad = w.copy()
    bad.iloc[0,0] = np.nan
    with pytest.raises(ValueError,match="non-finite"):
        validate_weather(bad)
    daily = w.iloc[::24]
    with pytest.raises(ValueError,match="one hour"):
        validate_weather(daily)


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        replace(Config(),soc_min=0.5,soc_reserve=0.4).validate()
    with pytest.raises(ValueError):
        replace(Config(),modules=35).validate()


def test_time_step_convergence_is_bounded(example):
    c,w,m = example
    _,s5 = simulate(w,m,replace(c,step_minutes=5))
    _,s15 = simulate(w,m,replace(c,step_minutes=15))
    assert abs(s5["pv_dc_kwh"]-s15["pv_dc_kwh"])/s5["pv_dc_kwh"] < .05


def test_bigger_battery_reduces_cloud_period_shortfall(example):
    c,w,m = example
    c = replace(c,irradiance_scale=.25)
    _,small = simulate(w,m,replace(c,battery_kwh=20))
    _,large = simulate(w,m,replace(c,battery_kwh=160))
    assert large["critical_unserved_kwh"] <= small["critical_unserved_kwh"]
