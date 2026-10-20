"""Causal off-grid dispatch with a coupled two-node thermal model.

Power is kW, energy kWh, time hours, thermal capacitance kJ/K. The battery
states are chemical energy and temperature. No grid or generator is present.
"""
import numpy as np
import pandas as pd


def _derate(temp, start, trip):
    return float(np.clip((trip - temp) / (trip - start), 0, 1))


def simulate_dispatch(weather, pv, c, initial_state=None, return_state=False, dt_hours=None):
    c.validate()
    dt = c.step_minutes / 60 if dt_hours is None else float(dt_hours)
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("Dispatch time step must be positive and finite.")
    capacity = c.battery_kwh * c.battery_soh
    energy = capacity * c.soc_initial
    green = 0.0  # provenance of initial charge is unknown; never call it renewable
    room = float(weather.temp_air.iloc[0])
    battery = room
    hvac_on, battery_trip, shed_latch = False, False, False
    if initial_state is not None:
        energy, green, room, battery = (initial_state[k] for k in ("energy", "green", "room", "battery"))
        hvac_on, battery_trip, shed_latch = (initial_state[k] for k in ("hvac_on", "battery_trip", "shed_latch"))
    length, width, height = c.dimensions
    roof_area = length * width
    shell_area = 2 * (length * width + length * height + width * height)
    volume = length * width * height
    shell_ua = c.shell_u_w_m2k * shell_area / 1000
    infiltration_ua = 1.2 * 1.006 * volume * c.infiltration_ach / 3600
    battery_capacity = c.battery_mass_kg_per_kwh * c.battery_kwh * c.battery_cp_kj_kgk
    # Outdoor sol-air approximation uses roof + 25% equivalent wall area.
    solar_area = roof_area * (1 - c.roof_shade_fraction) + 0.25 * 2 * (length + width) * height
    arrays = {col: weather[col].to_numpy() for col in ("temp_air", "ghi", "relative_humidity", "fault_active")}
    pvarr = {col: pv[col].to_numpy() for col in ("pv_dc_kw", "tracker_kw")}
    hours = weather.index.hour.to_numpy()
    rows = []
    for i in range(len(weather)):
        ta, ghi, rh = float(arrays["temp_air"][i]), float(arrays["ghi"][i]), float(arrays["relative_humidity"][i])
        active_fault = bool(arrays["fault_active"][i])
        pv_dc = float(pvarr["pv_dc_kw"][i])
        soc = energy / capacity
        if battery >= c.battery_trip_c or (active_fault and c.fault == "BMS trip"):
            battery_trip = True
        elif battery_trip and battery <= c.battery_recover_c:
            battery_trip = False
        thermal_factor = 0.0 if battery_trip or battery < 0 else _derate(battery, c.battery_derate_c, c.battery_trip_c)
        battery_limit = c.battery_kw * thermal_factor
        if soc <= c.soc_reserve:
            shed_latch = True
        elif soc >= min(c.soc_reserve + 0.05, c.soc_max):
            shed_latch = False
        critical = c.critical_kw
        flex_demand = c.flexible_kw if c.operating_start_h <= hours[i] < c.operating_end_h else c.evening_kw if 18 <= hours[i] < 23 else 0.0
        # Below reserve: discretionary loads may run directly from spare PV,
        # but may not drain storage that is reserved for controls/critical load.
        flex_allowed = flex_demand
        tracker = float(pvarr["tracker_kw"][i])
        hvac_failure = active_fault and c.fault == "HVAC failure"
        if room >= c.cooling_setpoint_c + c.cooling_deadband_c / 2:
            hvac_on = True
        elif room <= c.cooling_setpoint_c - c.cooling_deadband_c / 2:
            hvac_on = False
        free_cooling = (c.cooling_mode != "Passive" and room > c.cooling_setpoint_c
            and ta < room - 2 and rh < 85 and not hvac_failure)
        fan_request = c.fan_kw if free_cooling else 0.0
        # Ambient-dependent COP is an explicit assumed curve, not OEM test data.
        cop = max(1.2, c.cooling_cop * (1 - 0.015 * max(ta - 35, 0)))
        cooling_capacity = c.cooling_capacity_kw * max(0.5, 1 - 0.015 * max(ta - 35, 0))
        compressor_request = cooling_capacity / cop if (c.cooling_mode == "Hybrid HVAC" and hvac_on and not free_cooling and not hvac_failure) else 0.0
        aux_request = c.controls_kw + tracker + fan_request + compressor_request
        if shed_latch:
            flex_allowed = min(flex_demand, max(pv_dc * c.inverter_eff - aux_request - critical, 0))
        ac_requested = aux_request + critical + flex_allowed
        inverter_factor = _derate(room, c.inverter_derate_start_c, c.inverter_trip_c)
        inverter_limit = c.inverter_kw * inverter_factor
        ac_target = min(ac_requested, inverter_limit)
        # Simple part-load curve with explicit efficiency. At >=20% load it
        # reaches eta_nom; at zero the separate idle loss remains.
        eta = c.inverter_eff * (0.96 + 0.04 * min(ac_target / c.inverter_kw * 5, 1))
        discharge_limit = min(battery_limit, max(energy - capacity * c.soc_min, 0) * c.eta_discharge / dt)
        dc_supply = pv_dc + discharge_limit
        idle = min(c.inverter_idle_kw, dc_supply)
        ac_served = min(ac_target, max(dc_supply - idle, 0) * eta)
        dc_for_inverter = ac_served / eta + idle
        discharge = max(dc_for_inverter - pv_dc, 0)
        pv_surplus = max(pv_dc - dc_for_inverter, 0)
        charge = min(pv_surplus, battery_limit,
            max(capacity * c.soc_max - energy, 0) / (c.eta_charge * dt))
        curtailed = max(pv_surplus - charge, 0)
        before = energy
        green_fraction = min(green / energy, 1) if energy > 1e-12 else 0.0
        chemical_out = discharge / c.eta_discharge * dt
        green_out_dc = discharge * green_fraction
        energy += charge * c.eta_charge * dt - chemical_out
        green += charge * c.eta_charge * dt - chemical_out * green_fraction
        green = max(min(green, energy), 0)
        # Controls/cooling are served first, then critical, then discretionary.
        aux_served = min(aux_request, ac_served)
        critical_served = min(critical, max(ac_served - aux_served, 0))
        flex_served = min(flex_allowed, max(ac_served - aux_served - critical_served, 0))
        aux_fraction = aux_served / aux_request if aux_request > 0 else 1.0
        cooling_elec = (fan_request + compressor_request) * aux_fraction
        compressor_thermal = compressor_request * cop * aux_fraction
        fan_ua = 1.2 * 1.006 * c.fan_airflow_m3h / 3600 * aux_fraction if free_cooling else 0
        fan_thermal = fan_ua * max(room - ta, 0)
        inv_loss = dc_for_inverter - ac_served
        battery_loss = charge * (1 - c.eta_charge) + discharge * (1 / c.eta_discharge - 1)
        # The same battery conversion losses used in the electrical balance
        # become heat at the battery node. No additional I²R loss is added.
        room_source = c.internal_heat_kw * aux_fraction + c.controls_kw * aux_fraction + inv_loss
        # Reduced sol-air equivalent: outside heat transfer coefficient 15 W/m²K.
        solar_heat = c.shell_u_w_m2k * solar_area * c.shell_absorptivity * ghi / 15 / 1000
        thermal_substeps = max(1, int(np.ceil(dt * 3600 / 30)))
        ds = dt * 3600 / thermal_substeps
        for _ in range(thermal_substeps):
            battery_to_room = c.battery_ua_kw_k * (battery - room)
            envelope = (shell_ua + infiltration_ua) * (ta - room)
            ventilation = fan_ua * max(room - ta, 0)
            room += ds / c.room_capacity_kj_k * (envelope + solar_heat + room_source + battery_to_room - compressor_thermal - ventilation)
            battery += ds / battery_capacity * (battery_loss - battery_to_room)
        dc_green_to_inv = min(pv_dc, dc_for_inverter) + green_out_dc
        green_ratio = min(dc_green_to_inv / dc_for_inverter, 1) if dc_for_inverter > 0 else 0.0
        user_served = critical_served + flex_served
        mode = "CHARGING" if charge > 1e-6 else "DISCHARGING" if discharge > 1e-6 else "PV DIRECT" if ac_served > 0 else "BLACKOUT"
        if battery_trip:
            mode = "BMS ISOLATED"
        residual = pv_dc + discharge - charge - curtailed - ac_served - inv_loss
        rows.append({"soc": energy / capacity, "battery_energy_kwh": energy,
            "battery_temp_c": battery, "room_temp_c": room,
            "battery_charge_kw": charge, "battery_discharge_kw": discharge,
            "battery_loss_kw": battery_loss, "inverter_loss_kw": inv_loss,
            "curtailed_kw": curtailed, "ac_served_kw": ac_served,
            "critical_demand_kw": critical, "flex_demand_kw": flex_demand,
            "critical_served_kw": critical_served, "flex_served_kw": flex_served,
            "user_served_kw": user_served, "unserved_kw": critical + flex_demand - user_served,
            "unserved_critical_kw": critical - critical_served,
            "aux_request_kw": aux_request, "aux_served_kw": aux_served,
            "aux_unserved_kw": aux_request - aux_served,
            "cooling_kw": cooling_elec, "cooling_thermal_kw": compressor_thermal + fan_thermal,
            "cooling_cop": cop, "solar_envelope_kw": solar_heat,
            "battery_power_limit_kw": battery_limit, "inverter_limit_kw": inverter_limit,
            "renewable_user_kw": user_served * green_ratio,
            "initial_energy_user_kw": user_served * (1 - green_ratio),
            "energy_change_kwh": energy - before, "dc_balance_residual_kw": residual,
            "battery_balance_residual_kwh": energy - before - (charge * c.eta_charge - discharge / c.eta_discharge) * dt,
            "ems_state": mode, "load_shed": shed_latch,
            "battery_trip": battery_trip,
            "cooling_state": "FAULT" if hvac_failure else "FREE COOLING" if free_cooling else "COMPRESSOR" if compressor_request > 0 else "PASSIVE"})
    output = pd.DataFrame(rows, index=weather.index)
    if return_state:
        return output, {"energy": energy, "green": green, "room": room, "battery": battery,
            "hvac_on": hvac_on, "battery_trip": battery_trip, "shed_latch": shed_latch}
    return output


def summarize(result, c):
    dt = c.step_minutes / 60
    energy = lambda col: float(result[col].sum() * dt)
    demand = energy("critical_demand_kw") + energy("flex_demand_kw")
    served = energy("user_served_kw")
    net_storage = float(result.battery_energy_kwh.iloc[-1] - c.soc_initial * c.battery_kwh * c.battery_soh)
    pv = energy("pv_dc_kw")
    balance = pv - energy("ac_served_kw") - energy("curtailed_kw") - energy("inverter_loss_kw") - energy("battery_loss_kw") - net_storage
    critical_demand = energy("critical_demand_kw")
    return {"pv_dc_kwh": pv, "pv_ac_potential_kwh": float(result.pv_ac_potential_kw.sum() * dt),
        "user_served_kwh": served, "user_demand_kwh": demand,
        "renewable_user_kwh": energy("renewable_user_kw"),
        "renewable_demand_fraction": energy("renewable_user_kw") / demand if demand else 1,
        "load_coverage_fraction": served / demand if demand else 1,
        "critical_coverage_fraction": 1 - energy("unserved_critical_kw") / critical_demand if critical_demand else 1,
        "unserved_kwh": energy("unserved_kw"), "critical_unserved_kwh": energy("unserved_critical_kw"),
        "curtailed_kwh": energy("curtailed_kw"), "cooling_kwh": energy("cooling_kw"),
        "aux_served_kwh": energy("aux_served_kw"), "aux_unserved_kwh": energy("aux_unserved_kw"),
        "tracker_kwh": energy("tracker_kw"), "battery_loss_kwh": energy("battery_loss_kw"),
        "inverter_loss_kwh": energy("inverter_loss_kw"), "net_storage_kwh": net_storage,
        "initial_energy_user_kwh": energy("initial_energy_user_kw"),
        "equivalent_full_cycles": float(((result.battery_charge_kw * c.eta_charge + result.battery_discharge_kw / c.eta_discharge).sum() * dt) / (2 * c.battery_kwh * c.battery_soh)),
        "battery_max_c": float(result.battery_temp_c.max()), "room_max_c": float(result.room_temp_c.max()),
        "battery_derating_hours": float((result.battery_power_limit_kw < c.battery_kw - 1e-6).sum() * dt),
        "critical_outage_hours": float((result.unserved_critical_kw > 1e-6).sum() * dt),
        "wind_stow_hours": float(result.tracker_state.isin(["WIND STOW", "SENSOR STOW"]).sum() * dt),
        "balance_residual_kwh": float(balance), "max_dc_residual_kw": float(result.dc_balance_residual_kw.abs().max()),
        "final_soc": float(result.soc.iloc[-1]), "hours": len(result) * dt}
