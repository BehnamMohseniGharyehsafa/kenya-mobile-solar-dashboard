"""Solar geometry, physical tracker limits, optical/thermal PV conversion."""
import numpy as np
import pandas as pd
import pvlib

from .config import Config


def _move(current, target, max_step, deadband, circular=False):
    delta = (target - current + 180) % 360 - 180 if circular else target - current
    if abs(delta) < deadband:
        return current, 0.0
    travel = float(np.clip(delta, -max_step, max_step))
    return (current + travel) % 360 if circular else current + travel, abs(travel)


def orientation(weather, solar, c):
    """Ephemeris tracking with deadband, slew limit, wind latch and fault priority."""
    n = len(weather)
    daylight = solar["apparent_elevation"].to_numpy() > 0
    if c.tracking == "Single axis":
        ideal = pvlib.tracking.singleaxis(solar.apparent_zenith, solar.azimuth,
            axis_azimuth=c.axis_azimuth_deg, axis_tilt=0, max_angle=c.max_rotation_deg,
            backtrack=c.backtracking, gcr=c.gcr)
        target_theta = ideal.tracker_theta.fillna(0).to_numpy()
    else:
        target_theta = np.zeros(n)
    tilt, azimuth, rotation, motor, states = [], [], [], [], []
    latch = False
    recovery_minutes = 0.0
    theta_now, tilt_now, az_now = 0.0, 0.0, c.fixed_azimuth_deg
    for i, (gust, fault) in enumerate(zip(weather.gust_proxy_ms.to_numpy(), weather.fault_active.to_numpy())):
        sensor_fault = bool(fault and c.fault == "Anemometer fault")
        jam = bool(fault and c.fault == "Tracker jam")
        if gust >= c.stow_on_ms or sensor_fault:
            latch, recovery_minutes = True, 0.0
        elif latch:
            recovery_minutes = recovery_minutes + c.step_minutes if gust <= c.stow_off_ms else 0.0
            if recovery_minutes >= c.stow_hold_minutes:
                latch = False
        if c.tracking == "Fixed tilt":
            tilt_now, az_now, travel = c.fixed_tilt_deg, c.fixed_azimuth_deg, 0.0
            state = "FIXED"
        else:
            state = "TRACKING" if daylight[i] else "NIGHT PARK"
            if latch:
                state = "SENSOR STOW" if sensor_fault else "WIND STOW"
            slew = c.slew_deg_per_min * c.step_minutes
            if c.tracking == "Single axis":
                target = c.stow_tilt_deg if latch else target_theta[i] if daylight[i] else 0.0
                if jam:
                    travel = 0.0
                else:
                    theta_now, travel = _move(theta_now, target, slew, c.tracker_deadband_deg)
                # Horizontal axis: the normal faces axis azimuth +/-90 degrees.
                tilt_now = abs(theta_now)
                az_now = (c.axis_azimuth_deg + (90 if theta_now > 0 else -90)) % 360
            else:
                target_tilt = c.stow_tilt_deg if latch else min(float(solar.apparent_zenith.iloc[i]), c.max_rotation_deg) if daylight[i] else 0.0
                target_az = az_now if latch or not daylight[i] else float(solar.azimuth.iloc[i])
                if jam:
                    travel = 0.0
                else:
                    tilt_now, a = _move(tilt_now, target_tilt, slew, c.tracker_deadband_deg)
                    az_now, b = _move(az_now, target_az, slew, c.tracker_deadband_deg, circular=True)
                    travel = a + b
            if jam:
                state = "TRACKER JAM"
        tilt.append(tilt_now)
        azimuth.append(az_now)
        rotation.append(theta_now if c.tracking == "Single axis" else tilt_now)
        # Aggregate motor power averaged over the interval, including park/stow moves.
        duty = min(travel / (c.slew_deg_per_min * c.step_minutes), 1.0)
        motor.append(0.0 if c.tracking == "Fixed tilt" else c.tracker_standby_kw + c.tracker_kw * duty)
        states.append(state)
    return pd.DataFrame({"surface_tilt_deg": tilt, "surface_azimuth_deg": azimuth,
        "tracker_rotation_deg": rotation, "tracker_kw": motor, "tracker_state": states}, index=weather.index)


def simulate_pv(weather, c, pose_override=None):
    c.validate()
    solar_times = pd.DatetimeIndex(weather.solar_time)
    solar = pvlib.solarposition.get_solarposition(solar_times, c.latitude, c.longitude,
        altitude=c.altitude_m, pressure=weather.pressure.to_numpy(),
        temperature=weather.temp_air.to_numpy(), method="nrel_numpy")
    solar.index = weather.index
    pose = orientation(weather, solar, c) if pose_override is None else pose_override.copy()
    extra = pvlib.irradiance.get_extra_radiation(solar_times).to_numpy()
    airmass = pvlib.atmosphere.get_relative_airmass(solar.apparent_zenith).fillna(0)
    poa = pvlib.irradiance.get_total_irradiance(pose.surface_tilt_deg, pose.surface_azimuth_deg,
        solar.apparent_zenith, solar.azimuth, weather.dni, weather.ghi, weather.dhi,
        dni_extra=extra, airmass=airmass, albedo=c.albedo, model="perez")
    poa = poa.fillna(0).clip(lower=0)
    poa.loc[solar.apparent_elevation <= 0, :] = 0
    aoi = pvlib.irradiance.aoi(pose.surface_tilt_deg, pose.surface_azimuth_deg,
        solar.apparent_zenith, solar.azimuth)
    iam = np.nan_to_num(pvlib.iam.ashrae(aoi, b=0.05), nan=0.0)
    shading = np.zeros(len(weather))
    if c.tracking == "Single axis":
        shading = np.nan_to_num(pvlib.shading.shaded_fraction1d(solar.apparent_zenith,
            solar.azimuth, c.axis_azimuth_deg, pose.tracker_rotation_deg,
            collector_width=2.278, pitch=2.278 / c.gcr,
            shading_row_rotation=pose.tracker_rotation_deg), nan=0.0)
        shading = np.clip(shading, 0, 1)
    effective = (poa.poa_direct * iam * (1 - shading) + poa.poa_diffuse).clip(lower=0)
    module_wind = weather.wind_speed * (c.module_wind_height_m / 10.0) ** c.wind_shear_exponent
    cell_temp = pvlib.temperature.faiman(poa.poa_global, weather.temp_air, module_wind,
        u0=c.faiman_u0, u1=c.faiman_u1)
    reference_dc = effective / 1000 * c.array_kwp
    thermal_dc = pvlib.pvsystem.pvwatts_dc(effective, cell_temp, c.array_kwp, c.gamma_pdc).clip(lower=0)
    soil_dc = thermal_dc * (1 - c.soiling_pct / 100)
    wire_dc = soil_dc * (1 - c.wiring_pct / 100) * (1 - c.mismatch_pct / 100)
    available_dc = wire_dc * c.availability_pct / 100
    vmp = c.series_modules * c.vmp_v * (1 + c.beta_vmp * (cell_temp - 25))
    voc = c.series_modules * c.voc_v * (1 + c.beta_voc * (cell_temp - 25))
    current = available_dc * 1000 / np.maximum(vmp, 1)
    current_factor = np.minimum(c.mppt_max_current_a / np.maximum(current, 1e-6), 1)
    valid_voltage = (vmp >= c.mppt_min_v) & (vmp <= c.mppt_max_v) & (voc < c.dc_abs_max_v)
    limited_dc = available_dc * current_factor * valid_voltage.astype(float)
    forced_outage = weather.fault_active & (c.fault == "PV outage")
    limited_dc = limited_dc.where(~forced_outage, 0.0)
    bus = limited_dc * c.mppt_eff
    result = pose.copy()
    values = {"sun_elevation_deg": solar.apparent_elevation, "sun_azimuth_deg": solar.azimuth,
        "aoi_deg": aoi, "poa_wm2": poa.poa_global, "effective_wm2": effective,
        "beam_shade_fraction": shading, "cell_temp_c": cell_temp, "module_wind_ms": module_wind,
        "dc_reference_kw": reference_dc, "pv_dc_kw": bus,
        "pv_temperature_loss_kw": reference_dc - thermal_dc,
        "pv_soiling_loss_kw": thermal_dc - soil_dc,
        "pv_wiring_mismatch_loss_kw": soil_dc - wire_dc,
        "pv_availability_loss_kw": wire_dc - available_dc,
        "pv_input_limit_loss_kw": available_dc - limited_dc,
        "mppt_loss_kw": limited_dc - bus, "string_vmp_v": vmp, "string_voc_v": voc}
    for key, value in values.items():
        result[key] = np.asarray(value)
    return result


def string_checks(c):
    cold_voc = c.series_modules * c.voc_v * (1 + c.beta_voc * (c.dc_design_min_c - 25))
    hot_vmp = c.series_modules * c.vmp_v * (1 + c.beta_vmp * (c.dc_design_max_cell_c - 25))
    cold_vmp = c.series_modules * c.vmp_v * (1 + c.beta_vmp * (c.dc_design_min_c - 25))
    parallel = c.modules // c.series_modules
    checks = [
        ("Cold string Voc", cold_voc, "V", c.dc_abs_max_v, cold_voc < c.dc_abs_max_v),
        ("Hot string Vmp (minimum)", hot_vmp, "V", c.mppt_min_v, hot_vmp >= c.mppt_min_v),
        ("Cold string Vmp (maximum)", cold_vmp, "V", c.mppt_max_v, cold_vmp <= c.mppt_max_v),
        ("Aggregate STC operating current", parallel * c.imp_a, "A", c.mppt_max_current_a, parallel * c.imp_a <= c.mppt_max_current_a),
        ("1.25 × aggregate Isc screening", 1.25 * parallel * c.isc_a, "A", c.mppt_max_current_a, 1.25 * parallel * c.isc_a <= c.mppt_max_current_a),
    ]
    return pd.DataFrame(checks, columns=["Check", "Calculated", "Unit", "Limit", "Pass"])
