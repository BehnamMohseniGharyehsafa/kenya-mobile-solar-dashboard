"""Kenya mobile PV dashboard. Run: python -m streamlit run app.py"""
from dataclasses import fields, replace
from datetime import date
from io import BytesIO
from pathlib import Path
import json
import platform
import zipfile

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pvlib
import streamlit as st

from solar_model.config import Config, MODES, SITES
from solar_model.weather import load_bundled, fetch_pvgis, demo_weather, parse_weather_csv
from solar_model.simulation import simulate, compare_trackers
from solar_model.pv import string_checks
from solar_model import charts
from solar_model.branding import DEVELOPER,QUALIFICATION,EMAIL

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Kenya | Mobile solar lab", page_icon="☀️", layout="wide",initial_sidebar_state="collapsed")
st.markdown(f"**Developer: {DEVELOPER}**  \n{QUALIFICATION}  \n[{EMAIL}](mailto:{EMAIL})")


@st.cache_data(show_spinner=False)
def calculate(raw, meta, config):
    return simulate(raw, meta, config)


@st.cache_data(show_spinner=False)
def comparisons(raw, meta, config):
    return compare_trackers(raw, meta, config)


def metric_row(items):
    columns = st.columns(len(items))
    for column, (label, value, context) in zip(columns, items):
        with column:
            st.metric(label, value, border=True)
            if context:
                st.caption(context)


def line_chart(df, columns, y_title, height=350):
    fig = go.Figure()
    for col, label in columns:
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=label, mode="lines"))
    fig.update_xaxes(title="Local time · EAT (UTC+3)")
    st.plotly_chart(charts.style(fig, height, y_title), width="stretch")


def sidebar():
    if "design" not in st.session_state:
        st.session_state.design = Config()
    active = st.session_state.design
    with st.sidebar:
        st.title("☀ Mobile solar lab")
        st.caption("KENYA · CONTAINER ENERGY SYSTEM")
        with st.form("design_form"):
            st.subheader("Design inputs")
            site = st.selectbox("Site", list(SITES) + ["Custom coordinates"], index=0)
            with st.expander("Custom site coordinates"):
                lat = st.number_input("Latitude (°)", -4.8, 5.1, -1.2864, format="%.4f")
                lon = st.number_input("Longitude (°)", 33.8, 42.0, 36.8172, format="%.4f")
                alt = st.number_input("Elevation (m)", 0.0, 5000.0, 1795.0)
            tracking = st.selectbox("Array orientation", MODES, index=1)
            with st.expander("PV array & electrical", expanded=False):
                strings = st.number_input("Parallel strings", 1, 24, 4)
                series = st.number_input("Modules per string", 3, 24, 9)
                module_wp = st.number_input("Module rating (Wp)", 100.0, 800.0, 550.0, 10.0)
                inverter = st.number_input("Inverter AC rating (kW)", 2.0, 200.0, 20.0)
                soiling = st.slider("Soiling loss (%)", 0.0, 30.0, 5.0, 0.5)
                with st.container():
                    st.caption("Module and converter detail")
                    area = st.number_input("Module surface (m²)", 0.5, 4.0, 2.583252, format="%.4f")
                    gamma = st.number_input("Power temperature coefficient (%/°C)", -0.7, -0.1, -0.35, 0.01)
                    voc = st.number_input("Module Voc at STC (V)", 10.0, 100.0, 49.8)
                    vmp = st.number_input("Module Vmp at STC (V)", 10.0, 100.0, 41.8)
                    max_current = st.number_input("Aggregate MPPT operating-current limit (A)", 10.0, 1000.0, 70.0)
                    inv_eff = st.slider("Nominal inverter efficiency (%)", 85.0, 99.0, 96.0, 0.5)
                    mppt_eff = st.slider("MPPT converter efficiency (%)", 90.0, 99.9, 98.5, 0.1)
                    wire = st.slider("Wiring loss (%)", 0.0, 10.0, 2.0, 0.25)
                    mismatch = st.slider("Mismatch loss (%)", 0.0, 10.0, 1.5, 0.25)
            with st.expander("Tracker mechanics & wind"):
                tilt = st.slider("Fixed-array tilt (°)", 0.0, 60.0, 10.0)
                az = st.slider("Fixed-array azimuth (° clockwise from north)", 0.0, 359.0, 0.0)
                rotation = st.slider("Maximum tracking tilt / rotation (°)", 10.0, 85.0, 60.0)
                gcr = st.slider("Ground coverage ratio", 0.15, 0.70, 0.35, 0.01)
                backtrack = st.checkbox("Single-axis backtracking", True)
                wind_on = st.number_input("Wind stow trigger (gust proxy, m/s)", 5.0, 30.0, 12.0)
                wind_off = st.number_input("Wind recovery threshold (m/s)", 2.0, 25.0, 9.0)
                hold = st.number_input("Recovery hold time (min)", 5.0, 120.0, 20.0)
                stow_angle = st.slider("Stow tilt / signed rotation (°)", 0.0, 60.0, 0.0)
                deadband = st.number_input("Tracker deadband (°)", 0.1, 10.0, 1.0)
                slew = st.number_input("Maximum slew rate (°/min)", 0.5, 10.0, 3.0)
                motor = st.number_input("Aggregate actuator power while moving (kW)", 0.01, 2.0, 0.12)
                st.caption("Wind settings are scenario assumptions. Stow geometry and anchorage require a tracker-specific structural design.")
            with st.expander("Battery & energy management"):
                battery_kwh = st.number_input("Nominal LFP storage (kWh)", 5.0, 1000.0, 80.0, 5.0)
                battery_kw = st.number_input("Battery DC power limit (kW)", 1.0, 200.0, 20.0)
                initial = st.slider("Initial SOC (%)", 5, 100, 50)
                minimum = st.slider("Minimum SOC (%)", 0, 40, 15)
                reserve = st.slider("Critical-load reserve SOC (%)", 10, 70, 30)
                maximum = st.slider("Maximum SOC (%)", 60, 100, 95)
                roundtrip = st.slider("Battery DC round-trip efficiency (%)", 75.0, 99.0, 92.16, 0.1)
                soh = st.slider("Battery state of health (%)", 50, 100, 100)
                derate = st.number_input("Battery temperature derating begins (°C)", 30.0, 48.0, 40.0)
                trip = st.number_input("Battery temperature trip (°C)", 42.0, 65.0, 50.0)
                st.caption("Initial charge has unknown origin. Renewable energy to users excludes that contribution.")
            with st.expander("Site loads"):
                critical = st.number_input("Continuous critical load (kW)", 0.0, 40.0, 1.5, 0.1)
                flexible = st.number_input("Daytime discretionary load (kW)", 0.0, 80.0, 3.0, 0.25)
                evening = st.number_input("Additional 18:00–23:00 load (kW)", 0.0, 20.0, 0.5, 0.1)
                start = st.slider("Daytime load starts (hour EAT)", 0, 22, 8)
                end = st.slider("Daytime load stops (hour EAT)", 1, 24, 18)
                controls = st.number_input("Controls / communications (kW)", 0.01, 1.0, 0.06, 0.01)
            with st.expander("Container, heat & cooling"):
                container = st.selectbox("High-cube container length", [20, 40], format_func=lambda x: f"{x} ft")
                cooling = st.selectbox("Cooling strategy", ["Hybrid HVAC", "Ventilation only", "Passive"])
                cooling_capacity = st.number_input("Cooling capacity (kW thermal)", 0.5, 30.0, 4.5, 0.5)
                cop = st.number_input("Rated cooling COP", 1.5, 6.0, 3.2, 0.1)
                setpoint = st.slider("Container setpoint (°C)", 20.0, 35.0, 27.0, 0.5)
                uvalue = st.number_input("Insulated shell U-value (W/m²K)", 0.15, 6.0, 0.45, 0.05)
                shade = st.slider("Roof shaded by independent canopy (%)", 0, 100, 65)
                absorptivity = st.slider("Shell solar absorptivity", 0.10, 0.95, 0.30, 0.05)
                airflow = st.number_input("Filtered ventilation airflow (m³/h)", 100.0, 4000.0, 700.0, 50.0)
                fan = st.number_input("Ventilation fan power (kW)", 0.01, 2.0, 0.09, 0.01)
                with st.container():
                    st.caption("Thermal model coefficients")
                    room_capacity = st.number_input("Room effective thermal capacity (kJ/K)", 500.0, 50000.0, 5000.0, 500.0)
                    battery_ua = st.number_input("Battery-to-room conductance (kW/K)", 0.02, 2.0, 0.12, 0.01)
                    infiltration = st.number_input("Uncontrolled infiltration (air changes/h)", 0.0, 5.0, 0.25, 0.05)
                    u0 = st.number_input("Faiman U₀ (W/m²K)", 10.0, 50.0, 25.0)
                    u1 = st.number_input("Faiman U₁ (W/m²K per m/s)", 0.0, 15.0, 6.84, 0.1)
            with st.expander("Weather stresses & fault injection"):
                irradiance = st.slider("Irradiance multiplier", 0.0, 1.2, 1.0, 0.05)
                temperature_delta = st.slider("Ambient-temperature change (°C)", -5.0, 20.0, 0.0, 0.5)
                gust = st.slider("Minimum imposed gust proxy (m/s)", 0.0, 30.0, 0.0, 0.5)
                fault = st.selectbox("Injected fault", ["None", "Anemometer fault", "Tracker jam", "HVAC failure", "PV outage", "BMS trip"])
                fault_day = st.slider("Fault starts on nominal day of year", 1, 365, 172)
                fault_duration = st.slider("Fault duration (days)", 1, 14, 2)
                step = st.select_slider("Energy/control time step (min)", [5, 15, 60], value=15)
            submitted = st.form_submit_button("Apply design & simulate", type="primary", width="stretch")
        if submitted:
            latitude, longitude, altitude = (SITES[site] if site in SITES else (lat, lon, alt))
            try:
                if end <= start:
                    raise ValueError("Daytime load stop hour must be after its start hour.")
                candidate = replace(Config(), site=site, latitude=latitude, longitude=longitude, altitude_m=altitude,
                    modules=int(strings*series), series_modules=int(series), module_wp=module_wp, module_area_m2=area,
                    gamma_pdc=gamma/100, voc_v=voc, vmp_v=vmp, mppt_max_current_a=max_current,
                    inverter_kw=inverter, inverter_eff=inv_eff/100, mppt_eff=mppt_eff/100,
                    wiring_pct=wire, mismatch_pct=mismatch, soiling_pct=soiling, tracking=tracking,
                    fixed_tilt_deg=tilt, fixed_azimuth_deg=az, max_rotation_deg=rotation, gcr=gcr,
                    backtracking=backtrack, stow_on_ms=wind_on, stow_off_ms=wind_off,
                    stow_hold_minutes=hold, stow_tilt_deg=stow_angle, tracker_deadband_deg=deadband,
                    slew_deg_per_min=slew, tracker_kw=motor, battery_kwh=battery_kwh, battery_kw=battery_kw,
                    soc_initial=initial/100, soc_min=minimum/100, soc_reserve=reserve/100, soc_max=maximum/100,
                    eta_charge=np.sqrt(roundtrip/100), eta_discharge=np.sqrt(roundtrip/100), battery_soh=soh/100,
                    battery_derate_c=derate, battery_trip_c=trip, critical_kw=critical, flexible_kw=flexible,
                    evening_kw=evening, operating_start_h=start, operating_end_h=end, controls_kw=controls,
                    container_ft=container, cooling_mode=cooling, cooling_capacity_kw=cooling_capacity,
                    cooling_cop=cop, cooling_setpoint_c=setpoint, shell_u_w_m2k=uvalue,
                    roof_shade_fraction=shade/100, shell_absorptivity=absorptivity, fan_airflow_m3h=airflow,
                    fan_kw=fan, room_capacity_kj_k=room_capacity, battery_ua_kw_k=battery_ua,
                    infiltration_ach=infiltration, faiman_u0=u0, faiman_u1=u1,
                    irradiance_scale=irradiance, ambient_delta_c=temperature_delta,
                    forced_gust_ms=gust, fault=fault, fault_start_day=fault_day,
                    fault_days=fault_duration, step_minutes=step)
                candidate.validate()
                st.session_state.design = candidate
                active = candidate
            except ValueError as exc:
                st.error(str(exc))
        st.divider()
        weather_mode = st.selectbox("Weather source", ["Cached PVGIS typical year", "Upload weather CSV", "Synthetic demonstration"])
        uploaded = st.file_uploader("Weather CSV", type="csv") if weather_mode == "Upload weather CSV" else None
        if st.button("Download / refresh PVGIS for applied site", width="stretch"):
            try:
                with st.spinner("Downloading public PVGIS climate data…"):
                    fetch_pvgis(active)
                st.success("Raw TMY and provenance saved.")
            except Exception as exc:
                st.error(f"Weather download failed: {exc}")
        st.caption("Python application · local simulation · no live equipment connection")
    return active, weather_mode, uploaded


c, weather_mode, uploaded = sidebar()
page = st.selectbox("Workspace", ["Container simulator", "Overview", "Sun & tracking", "Storage & cooling", "Controls & faults", "Container design", "Literature & model", "Data & export"],label_visibility="collapsed",key="main_page")
if page == "Container simulator":
    from solar_model.live_ui import render_live_site
    render_live_site(c)
    st.stop()

try:
    if weather_mode == "Synthetic demonstration":
        raw, meta = demo_weather(c)
    elif weather_mode == "Upload weather CSV":
        if uploaded is None:
            st.info("Upload a weather CSV, or choose the cached Nairobi PVGIS data.")
            st.stop()
        raw, meta = parse_weather_csv(uploaded, c)
    else:
        raw, meta = load_bundled(c)
except (ValueError, FileNotFoundError, KeyError) as exc:
    st.error(str(exc))
    st.info("Download weather for the applied site, upload a CSV, or explicitly choose Synthetic demonstration.")
    st.stop()

with st.spinner("Solving solar geometry, storage dispatch and container temperatures…"):
    result, summary = calculate(raw, meta, c)

st.caption("RENEWABLE SYSTEMS / ENGINEERING EXPLORER")
st.title("Kenya · Mobile solar lab")
st.write(f"**{c.site}** · {c.array_kwp:.1f} kWp deployable PV · {c.battery_kwh:.0f} kWh LFP · {c.container_ft} ft container · {c.tracking.lower()}")
st.caption(f"{meta['source']} · {c.latitude:.4f}°, {c.longitude:.4f}° · {c.step_minutes}-minute model · EAT (UTC+3)")
if meta["kind"] == "Synthetic":
    st.warning("SYNTHETIC WEATHER — illustrative results only; these are not measured or climate-calibrated Kenyan yields.")
else:
    st.caption("Historical typical-year simulation. The 2025 calendar labels stitched months; it is not live production or a weather forecast.")
if abs(c.irradiance_scale-1)>1e-6 or c.ambient_delta_c or c.forced_gust_ms or c.fault != "None":
    st.info(f"Scenario active: irradiance ×{c.irradiance_scale:.2f}; ambient {c.ambient_delta_c:+.1f}°C; imposed gust ≥{c.forced_gust_ms:.1f} m/s; fault: {c.fault}.")
if summary["aux_unserved_kwh"] > 0.01:
    st.warning(f"Controls / cooling have {summary['aux_unserved_kwh']:.1f} kWh unmet demand. Tracking assumes a protected control UPS; this design needs that backup verified before its yield is relied on.")
if summary["critical_unserved_kwh"] > 0.1:
    st.warning(f"Critical-load shortfall: {summary['critical_unserved_kwh']:.1f} kWh over {summary['critical_outage_hours']:.1f} h. Increase supply/storage or reduce demand.")

metric_row([
    ("PV generated · DC bus", f"{summary['pv_dc_kwh']/1000:,.2f} MWh", f"Over {summary['hours']/24:.0f} simulated days; after MPPT and PV losses"),
    ("Renewable energy to users", f"{summary['renewable_user_kwh']/1000:,.2f} MWh", "AC delivered; excludes controls/cooling and unknown initial charge"),
    ("User demand covered", f"{summary['load_coverage_fraction']*100:.1f}%", f"{summary['unserved_kwh']:,.0f} kWh unserved; no grid or generator"),
    ("Cooling electricity", f"{summary['cooling_kwh']:,.0f} kWh", f"Battery maximum {summary['battery_max_c']:.1f}°C")])

date_options = list(dict.fromkeys(result.index.date))
default_date = date(2025, 6, 21)
selected_date = st.select_slider("Inspect a typical-year day · EAT", options=date_options,
    value=default_date if default_date in date_options else date_options[0], format_func=lambda x: x.strftime("%d %b"))
day = result[np.array(result.index.date) == selected_date]
instant = st.select_slider("Snapshot time · EAT", options=list(range(len(day))),
    value=min(12*60//c.step_minutes, len(day)-1), format_func=lambda i: day.index[i].strftime("%H:%M"))
row = day.iloc[instant]
st.caption(f"SNAPSHOT · {row.name.strftime('%d %b %Y · %H:%M')} EAT · PV {row.pv_dc_kw:.2f} kW DC · SOC {row.soc*100:.1f}% · {row.tracker_state}")

if page == "Overview":
    st.subheader("A day in operation")
    st.plotly_chart(charts.energy_profile(day), width="stretch")
    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Energy goes somewhere")
        st.plotly_chart(charts.energy_flow(summary), width="stretch")
        st.caption("Whole simulation. Storage draw/increase is a net change; conversion losses include battery and inverter losses.")
    with right:
        st.subheader("Storage & temperature")
        st.plotly_chart(charts.storage_temperature(day, c), width="stretch")
    st.subheader("Seasonal energy balance")
    st.plotly_chart(charts.monthly_energy(result), width="stretch")
    st.caption("PV DC, user AC and curtailment are distinct quantities. Battery capacity is storage, not additional renewable generation.")

elif page == "Sun & tracking":
    a, b = st.columns([1.25, 1])
    with a:
        st.subheader("Deployable tracking table")
        st.plotly_chart(charts.deployment(c, row), width="stretch")
        st.caption("Representative 6-module table beside the container. Schematic only; repeated tables form the full array. Drag to rotate.")
    with b:
        st.subheader("Sun and panel normal")
        st.plotly_chart(charts.sun_path(day, row), width="stretch")
    metric_row([("Sun elevation", f"{row.sun_elevation_deg:.1f}°", "Above the horizon"),
        ("Panel tilt / azimuth", f"{row.surface_tilt_deg:.1f}° / {row.surface_azimuth_deg:.0f}°", "Azimuth clockwise from north"),
        ("Plane-of-array irradiance", f"{row.poa_wm2:.0f} W/m²", f"Incidence angle {row.aoi_deg:.1f}°")])
    line_chart(day, [("surface_tilt_deg", "Panel tilt"), ("tracker_rotation_deg", "Signed single-axis rotation"),
        ("sun_elevation_deg", "Sun elevation")], "Angle (°)")
    st.write("Single-axis tracking rotates about a horizontal north–south axis. Backtracking uses row spacing to reduce beam shading. Dual-axis tracking follows both tilt and azimuth within its tilt, slew and deadband limits.")
    st.caption("Dual-axis results omit inter-table shading and can overstate yield if tables are packed too tightly. GCR is only a footprint estimate for that geometry.")
    if st.button("Compare fixed, single-axis & dual-axis", type="primary"):
        with st.spinner("Rerunning the complete model for all three tracking modes…"):
            compare = comparisons(raw, meta, c)
        st.session_state.tracker_comparison = (c.to_dict(), meta, compare)
    saved = st.session_state.get("tracker_comparison")
    if saved and saved[0] == c.to_dict() and saved[1] == meta:
        compare = saved[2]
        st.dataframe(compare, hide_index=True, width="stretch", column_config={k: st.column_config.NumberColumn(format="%.1f") for k in compare if k != "Tracking"})
        st.caption("Identical weather, module count and load. Each case reruns storage and thermal control. PV gain is calculated here, not a promised literature percentage.")

elif page == "Storage & cooling":
    metric_row([("Usable SOC-window energy", f"{c.battery_kwh*c.battery_soh*(c.soc_max-c.soc_min):.1f} kWh", "Before discharge and inverter losses"),
        ("Critical-load autonomy screening", f"{c.battery_kwh*c.battery_soh*(c.soc_max-c.soc_min)*c.eta_discharge*c.inverter_eff/max(c.critical_kw+c.controls_kw, .001):.1f} h", "Full battery; excludes cooling and other auxiliary demand"),
        ("Equivalent full cycles", f"{summary['equivalent_full_cycles']:.1f}", "Chemical throughput / (2 × current capacity)"),
        ("Battery power derating", f"{summary['battery_derating_hours']:.1f} h", "Includes thermal trip or low-temperature inhibition")])
    st.plotly_chart(charts.storage_temperature(day, c), width="stretch")
    a,b = st.columns(2)
    with a:
        st.subheader("Cooling electrical demand")
        line_chart(day, [("cooling_kw", "Cooling electricity"), ("aux_request_kw", "All auxiliary demand")], "Electrical power (kW)")
    with b:
        st.subheader("Cooling and solar heat")
        line_chart(day, [("cooling_thermal_kw", "Heat removed"), ("solar_envelope_kw", "Solar heat admitted through shell")], "Thermal power (kW)")
    st.write("The room and battery are separate thermal nodes. The room exchanges heat with outdoor air and the battery; the shell admits solar heat, while inverter and control losses add internal heat. Battery conversion losses heat the battery. Cooling demand is dispatched before user loads.")
    st.write("Hybrid control uses filtered outdoor air when it is at least 2°C cooler and relative humidity is below 85%. Otherwise a hysteresis thermostat enables the compressor. Its electrical demand equals thermal capacity divided by ambient-adjusted COP. Cooling is reduced in proportion to supplied auxiliary power.")
    st.info("Thermal parameters and protection temperatures are editable engineering assumptions. This lumped model does not resolve rack hot spots, condensation, refrigerant dynamics, thermal runaway or fire propagation.")
    if st.button("Compare cooling strategies", type="primary"):
        table = []
        with st.spinner("Solving passive, ventilation and hybrid cases…"):
            for mode in ["Passive", "Ventilation only", "Hybrid HVAC"]:
                _, s = calculate(raw, meta, replace(c, cooling_mode=mode))
                table.append({"Strategy": mode, "Cooling kWh": s["cooling_kwh"], "Battery max °C": s["battery_max_c"],
                    "Container max °C": s["room_max_c"], "User served kWh": s["user_served_kwh"],
                    "Critical shortfall kWh": s["critical_unserved_kwh"]})
        st.dataframe(pd.DataFrame(table).round(2), hide_index=True, width="stretch")

elif page == "Controls & faults":
    a,b,d = st.columns(3)
    with a:
        st.metric("Tracker state", row.tracker_state, border=True)
    with b:
        st.metric("Energy manager", row.ems_state, border=True)
    with d:
        st.metric("Cooling controller", row.cooling_state, border=True)
    st.plotly_chart(charts.controller_timeline(day), width="stretch")
    control_table = pd.DataFrame([
        ["Tracker safety", f"Gust proxy ≥{c.stow_on_ms:g} m/s or anemometer fault", f"Command {c.stow_tilt_deg:g}° stow; rate limit still applies", f"Below {c.stow_off_ms:g} m/s for {c.stow_hold_minutes:g} min"],
        ["Battery protection", f"Battery ≥{c.battery_trip_c:g}°C, <0°C, or BMS fault", "Inhibit charge and discharge; PV may supply AC directly", f"Temperature ≤{c.battery_recover_c:g}°C and no fault"],
        ["Battery derating", f"Battery above {c.battery_derate_c:g}°C", "Linearly reduce DC power limit to zero at trip", "Automatic with temperature"],
        ["Reserve protection", f"SOC ≤{c.soc_reserve*100:g}%", "Discretionary loads use spare PV only", f"SOC ≥{min(c.soc_reserve+.05,c.soc_max)*100:g}%"],
        ["Cooling", f"Room ≥{c.cooling_setpoint_c+c.cooling_deadband_c/2:g}°C", "Free cooling if eligible; else compressor", f"Room ≤{c.cooling_setpoint_c-c.cooling_deadband_c/2:g}°C"],
        ["Inverter derating", f"Room above {c.inverter_derate_start_c:g}°C", f"Reduce AC limit; zero at {c.inverter_trip_c:g}°C", "Automatic with temperature"],
        ["Tracker jam", "Injected fault window", "Hold current angle; do not pretend stow succeeded", "Fault window ends"],
    ], columns=["Controller", "Trigger", "Action", "Recovery"])
    st.dataframe(control_table, hide_index=True, width="stretch")
    st.subheader("Control hierarchy")
    st.write("Hardware protection → BMS power permission → wind/sensor safety → thermal control → critical-load reserve → discretionary load. Sun tracking uses solar ephemeris, not light-seeking sensors. The energy manager operates a DC-coupled battery and grid-forming AC inverter.")
    st.write("In an implementation, a PLC would supervise limit switches, encoders, an anemometer, electrical meters, module/ambient/rack temperature sensors, smoke and water ingress signals. A BMS would retain independent contactor authority. Use a protected DC control supply, local logging and store-and-forward telemetry for intermittent mobile connectivity.")
    st.caption("The implemented controllers simulate energy and slow supervisory states. MPPT is represented by available maximum power and an efficiency; PWM, current loops, DC-link stability, motor torque and fault-clearing transients are not simulated. Storm stow uses a mean-wind-derived gust proxy, not measured gust extremes.")
    display_cols = ["tracker_state","ems_state","cooling_state","soc","battery_power_limit_kw","inverter_limit_kw","unserved_critical_kw","aux_unserved_kw"]
    with st.expander("Inspect controller log"):
        st.dataframe(day[display_cols], width="stretch")

elif page == "Container design":
    length, width, height = c.dimensions
    roof = length*width
    deployed = c.surface_m2/c.gcr
    module_mass = c.modules*c.module_mass_kg
    battery_mass = c.battery_kwh*c.battery_mass_kg_per_kwh
    metric_row([("PV surface", f"{c.surface_m2:.1f} m²", f"{c.modules} modules × {c.module_wp:g} Wp"),
        ("Indicative array ground area", f"{deployed:.0f} m²", "PV surface / GCR; add container, aisles and fencing"),
        ("Container roof area", f"{roof:.1f} m²", f"{length:.3f} × {width:.3f} × {height:.3f} m exterior"),
        ("Modules + battery mass only", f"{(module_mass+battery_mass)/1000:.2f} t", "Excludes shell, racking, ballast, cooling and converters")])
    st.plotly_chart(charts.deployment(c,row), width="stretch")
    st.write(f"The {c.array_kwp:.1f} kWp array has {c.surface_m2:.1f} m² of module surface, compared with a {roof:.1f} m² container roof. It therefore deploys beside the enclosure. Container mobility, folding deployment and daily sun tracking are separate mechanical functions; the fold-out products in the literature do not establish that this tracking mechanism is transport-qualified.")
    st.subheader("Conceptual equipment schedule")
    schedule = [
        ["PV generator", f"{c.modules} generic {c.module_wp:g} Wp modules; {c.modules//c.series_modules} parallel × {c.series_modules} series", "Replace generic module values with an OEM datasheet; retain connectors and strain relief during folding"],
        ["Tracking structure", f"{c.tracking}; ±{c.max_rotation_deg:g}° single-axis / {c.max_rotation_deg:g}° dual-axis tilt limit", "Detachable tracking tables, transport locks, encoders, end stops, ground anchors and service clearances"],
        ["Power electronics", f"{c.inverter_kw:g} kW AC grid-forming inverter + MPPT DC/DC", "Confirm black-start, overload, short-circuit protection, earthing, lightning and surge coordination"],
        ["Storage", f"{c.battery_kwh:g} kWh nominal LFP; {c.battery_kw:g} kW DC limit", "Compartment separation, independent BMS, DC isolation, rack temperature instrumentation and a protected control supply"],
        ["Thermal envelope", f"U={c.shell_u_w_m2k:g} W/m²K; absorptivity {c.shell_absorptivity:g}", "Insulation, reflective exterior, an independently supported shade canopy and sealed cable penetrations"],
        ["Cooling", f"{c.cooling_mode}; {c.cooling_capacity_kw:g} kW thermal; COP {c.cooling_cop:g}", "Filtered airflow, serviceable dust screens, high-temperature condenser rating; coastal corrosion assessment"],
        ["Logistics", f"{c.container_ft} ft high-cube envelope", "Verify actual mass, centre of gravity, axle loads, packed volume, lift points and modified-container transport approval"],
    ]
    st.dataframe(pd.DataFrame(schedule,columns=["Subsystem","Applied concept","Engineering characteristics"]),hide_index=True,width="stretch")
    st.subheader("String voltage and current screening")
    checks = string_checks(c)
    st.dataframe(checks.round(2), hide_index=True, width="stretch")
    st.caption(f"Generic module coefficients; design ambient minimum {c.dc_design_min_c:g}°C and hot cell {c.dc_design_max_cell_c:g}°C. Aggregate-current screen is not a substitute for per-MPPT allocation, fuse, conductor or protective-device design.")
    if not checks.Pass.all():
        st.warning("At least one electrical sizing screen fails. Adjust stringing/converter limits and verify against chosen equipment.")
    with st.expander("User-supplied visual concept"):
        image = ROOT / "assets" / "concept-reference.png"
        if image.exists():
            st.image(str(image), caption="User reference: compact remote service unit with a PV canopy. The illustration does not provide measured Kenyan site or equipment specifications.")

elif page == "Literature & model":
    st.subheader("Evidence behind the design")
    st.write("The model combines published solar-performance methods with explicit conceptual equipment assumptions. Vendor deployment examples inform packaging; they are not evidence of tracking gains or a certified design for this container.")
    sources = json.loads((ROOT / "literature.json").read_text(encoding="utf-8"))
    for source in sources:
        with st.expander(f"[{source['id']}] {source['title']} · {source['type']}"):
            st.write(source["finding"])
            st.write("**Model/design implication:** " + source["application"])
            st.markdown(f"[Open primary source]({source['url']})")
    st.subheader("Implemented equations")
    st.latex(r"G_{\rm eff}=G_{\rm beam}IAM(1-f_{\rm shade})+G_{\rm diffuse}")
    st.latex(r"T_{\rm PV}=T_a+\frac{G_{\rm POA}}{U_0+U_1v_{\rm module}}")
    st.latex(r"P_{\rm PV}=P_{\rm STC}\frac{G_{\rm eff}}{1000}[1+\gamma(T_{\rm PV}-25)]\prod_i(1-L_i)\eta_{\rm MPPT}")
    st.latex(r"E_{t+1}=E_t+\left(\eta_cP_c-\frac{P_d}{\eta_d}\right)\Delta t")
    st.latex(r"C_r\dot T_r=UA(T_a-T_r)+Q_{\rm solar}+Q_{\rm equipment}+UA_b(T_b-T_r)-Q_{\rm HVAC}-Q_{\rm vent}")
    st.latex(r"C_b\dot T_b=Q_{\rm battery\ loss}-UA_b(T_b-T_r),\quad P_{\rm HVAC}=Q_{\rm HVAC}/COP")
    st.latex(r"E_{\rm PV,DC}=E_{\rm users,AC}+E_{\rm auxiliaries,AC}+E_{\rm curtailed}+E_{\rm conversion\ losses}+\Delta E_{\rm battery}")
    st.caption("Current and voltage limits, converter clipping, protection states and charge/discharge power limits are applied in addition to these equations. Thermal integration uses substeps ≤30 s; energy control uses the selected interval.")
    st.subheader("Scope and calibration")
    st.write("This is a detailed energy and supervisory-control model for design exploration. It is not validated hardware control, a structural calculation or a transient electrical simulation. Calibrate module data, battery efficiency/thermal coefficients, enclosure U-value, COP and load profiles to the actual equipment before procurement.")
    st.write("Excluded effects include bifacial rear irradiance, spectral mismatch, dynamic dust deposition, tree/building shading, rack hot spots, battery ageing predictions, humidity/condensation, fire behaviour, transport packing validation and generator/grid operation. Average availability is a uniform derating. A single TMY cannot establish P90 yield or extreme wind design loads.")
    st.write("A protected tracker/control UPS is assumed mechanically available. Its consumption is included in auxiliary demand, but its own storage is not resolved. Cases with unmet auxiliaries are flagged as requiring control-supply verification. Initial battery charge is tracked separately and not labelled renewable.")
    st.download_button("Download detailed engineering notes", (ROOT / "ENGINEERING_NOTES.md").read_bytes(), "ENGINEERING_NOTES.md", "text/markdown")

elif page == "Data & export":
    st.subheader("Reproduce the result")
    a,b,d = st.columns(3)
    with a:
        st.metric("Whole-period energy residual", f"{summary['balance_residual_kwh']:.2e} kWh", border=True)
    with b:
        st.metric("Maximum DC-bus residual", f"{summary['max_dc_residual_kw']:.2e} kW", border=True)
    with d:
        st.metric("Unknown initial energy → users", f"{summary['initial_energy_user_kwh']:.2f} kWh", border=True)
    st.json(meta, expanded=False)
    for note in meta.get("quality_notes", []):
        st.info(note)
    with st.expander("Applied parameters · all model assumptions"):
        st.json(c.to_dict())
    st.caption("These are the applied settings. Sidebar edits take effect only after Apply design & simulate.")
    package = {"config": c.to_dict(), "weather_provenance": meta, "summary": summary,
        "runtime": {"python": platform.python_version(), "pvlib": pvlib.__version__,
            "streamlit": st.__version__, "pandas": pd.__version__, "numpy": np.__version__}}
    st.download_button("Download results & assumptions JSON", json.dumps(package, indent=2), "mobile_pv_results.json", "application/json")
    csv = result.to_csv(index_label="timestamp")
    st.download_button("Download full simulation CSV", csv, "mobile_pv_timeseries.csv", "text/csv")
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("results.json", json.dumps(package, indent=2))
        archive.writestr("timeseries.csv", csv)
        archive.writestr("input_weather.csv", raw.to_csv(index_label="timestamp"))
        archive.writestr("ENGINEERING_NOTES.md", (ROOT / "ENGINEERING_NOTES.md").read_bytes())
        archive.writestr("literature.json", (ROOT / "literature.json").read_bytes())
    st.download_button("Download complete scenario bundle (.zip)", stream.getvalue(), "mobile_pv_scenario.zip", "application/zip", type="primary")
    st.subheader("Upload a custom design")
    st.caption("Upload an exported results JSON or a plain Config object. Every parameter can be changed here, including advanced coefficients. The applied JSON is authoritative; sidebar fields retain their displayed draft values.")
    design_upload = st.file_uploader("Design JSON", type="json", key="design_upload")
    if st.button("Apply uploaded design") and design_upload:
        try:
            payload = json.load(design_upload)
            values = payload.get("config", payload)
            allowed = {f.name for f in fields(Config)}
            if set(values) - allowed:
                raise ValueError("Unknown config fields: " + ", ".join(sorted(set(values)-allowed)))
            new_config = Config(**values)
            new_config.validate()
            st.session_state.design = new_config
            st.rerun()
        except (ValueError, TypeError) as exc:
            st.error(str(exc))
    st.subheader("Weather CSV schema")
    st.code("timestamp,ghi,dni,dhi,temp_air,wind_speed,relative_humidity,pressure\n2025-01-01T00:00:00+03:00,0,0,0,16.0,2.0,65.0,82000", language="text")
    st.caption("Irradiance W/m²; air temperature °C; 10 m wind m/s; relative humidity %; pressure Pa. Regular hourly or subhourly intervals; explicit timestamp offsets required. Uploads use sample-instant solar geometry, with no additional time offset.")
    with st.expander("Inspect selected day data"):
        st.dataframe(day, width="stretch")

st.divider()
st.caption("Concept design · Literature-linked assumptions · Historical weather · All dashboard and model source authored in Python")
