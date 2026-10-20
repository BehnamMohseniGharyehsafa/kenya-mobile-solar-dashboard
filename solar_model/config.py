"""Explicit conceptual-design assumptions, not vendor-certified specifications."""
from dataclasses import asdict, dataclass

SITES = {
    "Nairobi": (-1.2864, 36.8172, 1795.0),
    "Lodwar / Turkana": (3.1191, 35.5973, 477.0),
    "Garissa": (-0.4532, 39.6461, 151.0),
    "Mombasa": (-4.0435, 39.6682, 50.0),
    "Marsabit": (2.3284, 37.9899, 1300.0),
    "Kisumu": (-0.0917, 34.7680, 1131.0),
}
MODES = ("Fixed tilt", "Single axis", "Dual axis")


@dataclass(frozen=True)
class Config:
    site: str = "Nairobi"
    latitude: float = -1.2864
    longitude: float = 36.8172
    altitude_m: float = 1795.0
    timezone: str = "Africa/Nairobi"
    step_minutes: int = 15
    # Generic 550 W silicon module; replace with a selected manufacturer's data.
    modules: int = 36
    module_wp: float = 550.0
    module_area_m2: float = 2.278 * 1.134
    module_mass_kg: float = 28.0
    gamma_pdc: float = -0.0035
    voc_v: float = 49.8
    vmp_v: float = 41.8
    isc_a: float = 13.98
    imp_a: float = 13.16
    beta_voc: float = -0.0028
    beta_vmp: float = -0.0035
    series_modules: int = 9
    mppt_min_v: float = 180.0
    mppt_max_v: float = 850.0
    dc_abs_max_v: float = 1000.0
    mppt_max_current_a: float = 70.0  # aggregate input, not per MPPT
    dc_design_min_c: float = 0.0
    dc_design_max_cell_c: float = 75.0
    tracking: str = "Single axis"
    fixed_tilt_deg: float = 10.0
    fixed_azimuth_deg: float = 0.0  # north-facing, south of equator
    axis_azimuth_deg: float = 180.0
    max_rotation_deg: float = 60.0
    backtracking: bool = True
    gcr: float = 0.35
    stow_on_ms: float = 12.0
    stow_off_ms: float = 9.0
    stow_hold_minutes: float = 20.0
    stow_tilt_deg: float = 0.0
    gust_factor: float = 1.5
    tracker_deadband_deg: float = 1.0
    slew_deg_per_min: float = 3.0
    tracker_kw: float = 0.12  # aggregate drive power for the array
    tracker_standby_kw: float = 0.008
    albedo: float = 0.20
    soiling_pct: float = 5.0
    wiring_pct: float = 2.0
    mismatch_pct: float = 1.5
    availability_pct: float = 99.0
    mppt_eff: float = 0.985
    faiman_u0: float = 25.0
    faiman_u1: float = 6.84
    module_wind_height_m: float = 2.0
    wind_shear_exponent: float = 0.14
    # DC-coupled storage; AC loads supplied by one grid-forming inverter.
    inverter_kw: float = 20.0
    inverter_eff: float = 0.96
    inverter_idle_kw: float = 0.025
    inverter_derate_start_c: float = 45.0
    inverter_trip_c: float = 60.0
    battery_kwh: float = 80.0
    battery_kw: float = 20.0
    battery_soh: float = 1.0
    eta_charge: float = 0.96
    eta_discharge: float = 0.96
    soc_initial: float = 0.50
    soc_min: float = 0.15
    soc_max: float = 0.95
    soc_reserve: float = 0.30
    battery_derate_c: float = 40.0
    battery_trip_c: float = 50.0
    battery_recover_c: float = 38.0
    battery_mass_kg_per_kwh: float = 9.0
    battery_cp_kj_kgk: float = 0.95
    battery_ua_kw_k: float = 0.12
    critical_kw: float = 1.5
    flexible_kw: float = 3.0
    operating_start_h: int = 8
    operating_end_h: int = 18
    evening_kw: float = 0.5
    controls_kw: float = 0.06
    container_ft: int = 20
    shell_u_w_m2k: float = 0.45
    shell_absorptivity: float = 0.30
    roof_shade_fraction: float = 0.65
    room_capacity_kj_k: float = 5000.0
    infiltration_ach: float = 0.25
    cooling_mode: str = "Hybrid HVAC"
    cooling_capacity_kw: float = 4.5  # heat removal, NOT electrical input
    cooling_cop: float = 3.2
    cooling_setpoint_c: float = 27.0
    cooling_deadband_c: float = 2.0
    fan_airflow_m3h: float = 700.0
    fan_kw: float = 0.09
    internal_heat_kw: float = 0.08
    # Scenario stresses, applied only when enabled in the UI.
    irradiance_scale: float = 1.0
    ambient_delta_c: float = 0.0
    forced_gust_ms: float = 0.0
    fault: str = "None"
    fault_start_day: int = 172
    fault_days: int = 2

    @property
    def array_kwp(self):
        return self.modules * self.module_wp / 1000

    @property
    def surface_m2(self):
        return self.modules * self.module_area_m2

    @property
    def dimensions(self):
        return (6.058 if self.container_ft == 20 else 12.192, 2.438, 2.896)

    def to_dict(self):
        return asdict(self)

    def validate(self):
        if self.modules < 1 or self.series_modules < 1 or self.modules % self.series_modules:
            raise ValueError("Module count must be a positive multiple of modules per string.")
        if not 0 <= self.soc_min < self.soc_reserve < self.soc_max <= 1:
            raise ValueError("SOC must satisfy minimum < reserve < maximum.")
        if not self.soc_min <= self.soc_initial <= self.soc_max:
            raise ValueError("Initial SOC must lie inside the operating SOC window.")
        if not 0 < self.gcr <= 1 or self.step_minutes not in (5, 15, 60):
            raise ValueError("Invalid GCR or simulation time step.")
        if self.stow_off_ms >= self.stow_on_ms:
            raise ValueError("Wind recovery threshold must be below the stow threshold.")
        if self.battery_recover_c >= self.battery_derate_c or self.battery_derate_c >= self.battery_trip_c:
            raise ValueError("Battery recovery < derating < trip temperatures are required.")
        if self.tracking not in MODES or self.cooling_mode not in ("Hybrid HVAC", "Ventilation only", "Passive"):
            raise ValueError("Unknown tracking or cooling mode.")
        for name in ("battery_kwh", "battery_kw", "inverter_kw", "room_capacity_kj_k", "battery_ua_kw_k"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive.")
        for name in ("eta_charge", "eta_discharge", "inverter_eff", "mppt_eff", "battery_soh"):
            if not 0 < getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in (0, 1].")
