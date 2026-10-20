# Mobile container PV system in Kenya: engineering model and design basis

Research and implementation date: 20 October 2026. Default site: Nairobi, as requested. All numerical equipment values below are conceptual assumptions unless explicitly identified as downloaded weather or manufacturer examples. The attached picture supplies visual inspiration only; text within the picture is not treated as an instruction or technical specification.

## 1. Deliverable and intended use

The dashboard is a local Python application using Streamlit, Plotly, pvlib, pandas and NumPy. All application/model/chart source is Python; there is no separately authored HTML, CSS or JavaScript frontend. Streamlit and Plotly supply their normal browser runtime internally.

It estimates renewable generation, useful AC delivery, storage operation, auxiliary consumption, reliability shortfalls and container/battery temperatures. It also exposes slow supervisory controller states, fault injection and comparisons. It does not communicate with equipment or issue live control commands.

Use it to compare designs and identify the measurements and equipment data needed for a site-specific design. It is not structural approval, procurement certification, a transient power-system study or a validated BMS/PLC implementation.

## 2. Reference system

| Item | Default conceptual choice | Rationale/status |
|---|---|---|
| Site | Nairobi, −1.2864°, 36.8172°, nominal 1,795 m | User-selected city; coordinates represent the city, not a surveyed plot |
| Solar array | 36 × 550 Wp = 19.8 kWp | Generic, editable modules; no selected product |
| Module surface | 2.278 × 1.134 m per module | Approximate large-format module geometry |
| Stringing | 4 parallel strings × 9 series modules | Editable voltage/current screening |
| Tracking | Horizontal north–south single axis, ±60°, backtracking | A conceptual detachable tracking structure |
| Storage | 80 kWh nominal LFP; 20 kW DC | Editable capacity and power, not a validated vendor package |
| Storage window | 15–95% SOC; 30% discretionary-load reserve | Supervisory control assumptions |
| Initial charge | 50% SOC, unknown provenance | Its contribution is excluded from renewable delivery |
| Inverter | 20 kW AC, 96% nominal efficiency | Grid-forming DC-coupled architecture |
| Container | 20 ft high cube, exterior 6.058 × 2.438 × 2.896 m | Indicative envelope; actual supplier drawings required |
| Cooling | 4.5 kW thermal, COP 3.2, 27°C setpoint | Temperature/humidity-dependent hybrid free cooling and compressor control |
| Enclosure | U=0.45 W/m²K, solar absorptivity 0.30, 65% roof shade | Insulated reflective-shell concept; independent shade canopy assumed |
| User demand | 1.5 kW continuous critical; 3 kW additional 08:00–18:00; 0.5 kW additional 18:00–23:00 | Illustrative service-unit profile, not measured demand |
| Auxiliary demand | Controls, actuator energy, ventilation, compressor | Accounted separately from user loads |

The application separately screens nominal operating current and 1.25 × short-circuit current against an aggregate current limit. Real equipment may have different allowable operating and short-circuit limits on each MPPT; the single aggregate comparison is conservative screening, not a design rule or a code check. Module Voc/Vmp, current and temperature coefficients must be replaced as a coherent datasheet set.

## 3. Literature findings and physical interpretation

The complete primary-source list, findings and implementation mapping is in `literature.json` and the dashboard's Literature & model page. Sources were inspected during this task. This is a targeted engineering literature review, not a systematic review or a claim of complete market coverage.

Container mobility and solar tracking are different requirements. Foldable products demonstrate compact transport and rapid deployment. They do not automatically demonstrate continuous sun tracking. The proposed tracking tables therefore need a separate mechanical architecture, structural design and transport packing study.

[SolarCont's published example](https://www.solarcontainer.one/english/home) lists up to 140 kWp, 240 modules and approximately 720 m² of deployed coverage. [solarfold's FAQ](https://www.solarfold.eu/en/faq) describes a 20 ft high-cube container and ground-dependent supports. These are manufacturer claims and packaging examples, not performance measurements for Kenya. Their deployment and storage arrangements must not be mixed into an invented single product.

At the reference configuration, module surface is approximately 93 m² and the container roof is only approximately 14.8 m². The model therefore represents arrays deployed alongside the power enclosure. Surface/GCR gives about 266 m² of indicative array ground area before aisles, fencing, the container, drainage, turning space and safe setbacks. This is not a packing/CAD calculation. The 65% roof-shade assumption requires an independent canopy or equivalent shading provision; the schematic detached tracking table does not itself establish this roof coverage.

[Schimpe et al. (2018)](https://www.sciencedirect.com/science/article/pii/S0306261917315696), DOI 10.1016/j.apenergy.2017.10.129, supports analysing converter, battery, thermal-management and auxiliary losses together. This motivates the coupled model; its prototype efficiencies are not transplanted to the generic reference system.

[Saxon et al. (2024)](https://www.nrel.gov/docs/fy24osti/89032.pdf), DOI 10.3390/batteries10040136, supports characterising thermal behaviour at cell, module and pack levels. A lumped thermal calculation can identify cooling sensitivity, but cannot demonstrate rack temperature uniformity or battery fire performance.

## 4. Weather, time and data quality

Default weather is the JRC PVGIS 5.3 TMY downloaded for the selected coordinates. Raw JSON remains in `data/`, including retrieval URL/date, API inputs and selected source months. Presets are Nairobi, Lodwar/Turkana, Garissa, Mombasa, Marsabit and Kisumu.

The [JRC TMY documentation](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/pvgis-5-tools/pvgis-typical-meteorological-year-tmy-generator_en) explains representative-month assembly and irradiance timestamp offsets. The model:

1. Validates 8,760 source hours and unique month/day/hour coverage.
2. Maps each source month onto nominal non-leap year 2025 without sorting by its original historical year.
3. Preserves the source year as a data column and the selected-month list as metadata.
4. Rotates UTC hours into a complete EAT (UTC+3) local calendar year, including the wrapped year boundary.
5. Applies the source's irradiance time offset when calculating solar position.
6. Holds hourly weather values constant within each source interval for subhourly energy integration. No new measured cloud or gust detail is claimed. Solar geometry still evolves at the simulation interval.

The nominal 2025 year is only a convenient calendar, not a 2025 observation series. Historical TMY data are neither a forecast nor real-time telemetry. Holding satellite sampling values as interval representatives is an energy-model approximation; hourly/subhourly convergence and source data uncertainty matter, particularly near sunrise/sunset.

Validation rejects missing fields, non-finite values, implausible values, duplicate/irregular timestamps and mismatched cached coordinates. The downloaded Lodwar TMY contains one −0.32 m/s wind value. Values in [−0.5,0) m/s are clipped to zero with the correction count exposed; more negative values are rejected. The raw response is retained. No wind measurements or metadata are silently fabricated.

CSV uploads require timezone-qualified timestamps and GHI, DNI, DHI (W/m²), temperature (°C), 10 m wind (m/s), RH (%) and pressure (Pa). The user is responsible for the geographic match. Synthetic demonstration mode is explicit and prominently labelled; failures never silently substitute synthetic weather.

## 5. Solar and electrical model

Solar position uses pvlib's NREL SPA implementation with site pressure and air temperature [R13]. A flat, unobstructed deployment surface is assumed; the downloaded weather may include PVGIS horizon treatment, but the model does not independently ray-trace a horizon or nearby objects.

Single-axis tracking uses `pvlib.tracking.singleaxis`, including backtracking and GCR [R03]. Dual axis targets the solar azimuth and zenith, subject to maximum tilt. Fixed mode uses the selected tilt and azimuth. Slew rate, angular deadband, night park, wind-stow latch, recovery hold and jam faults modify the realised orientation. Wind safety commands do not teleport the mechanism. A jam holds the previous angle, even if a simultaneous wind event demands stow.

Perez transposition resolves direct, sky and ground-reflected POA irradiance [R06]. An ASHRAE incidence-angle modifier with assumed b=0.05 acts on the direct component. Single-axis mutual row beam shading is estimated from actual row rotations; diffuse row masking and bypass-diode/mismatch effects caused by local shading are not resolved. Fixed/dual inter-table shading is excluded. Dense dual-axis layouts can therefore be optimistic.

Faiman's model [R04] estimates module/cell temperature:

`T_PV = T_air + G_POA / (U0 + U1 × wind_at_module)`.

Default U0=25 and U1=6.84 represent open-rack empirical values. Weather wind at 10 m is converted to nominal 2 m module height with a power-law exponent of 0.14. This height/exposure correction is an assumption, not site calibration. The formulation does not resolve thermal inertia, radiative night cooling or active PV water cooling.

PVWatts DC [R05] converts effective irradiance and temperature into power:

`P_dc = P_STC × G_eff/1000 × [1 + gamma × (T_PV − 25)]`.

Multiplicative soiling, wiring, mismatch and availability factors follow. The default 5% soiling is a sensitivity assumption, not a measured Nairobi value; [IEA PVPS](https://iea-pvps.org/fact-sheets/fs-soiling-losses/) motivates measurement and maintenance rather than a universal local percentage. Mean availability is a uniform derating rather than a stochastic outage calendar.

Approximate string Voc and Vmp vary linearly with temperature. A string outside the MPPT voltage range or above the absolute voltage limit produces zero accepted DC in the model. An aggregate operating-current limit clips input power; irradiance-dependent voltage and detailed IV curves are omitted. MPPT efficiency is constant and editable. The separately plotted AC PV potential is a counterfactual PVWatts inverter output without storage/load constraints; it is not actual off-grid delivery and is never added to PV DC generation.

## 6. Storage, dispatch and renewable provenance

Topology: PV → MPPT DC/DC → DC bus ↔ LFP storage → grid-forming inverter → AC users and auxiliaries. There is no grid or generator. No AC power is credited if DC supply or inverter capacity cannot support it. The inverter includes a simple assumed part-load efficiency curve, idle consumption and room-temperature power derating.

Energy state:

`E_next = E + [eta_charge × P_charge − P_discharge / eta_discharge] × dt`.

Charge/discharge power limits, SOC bounds, temperature derating and BMS permission apply. The algorithm cannot charge and discharge in the same interval. Charge current taper near maximum SOC, self-discharge, battery voltage dynamics, electrochemical diffusion and ageing are not modelled. State of health is an imposed capacity multiplier; equivalent full cycles are a throughput indicator, not a lifetime prediction.

Service order is auxiliaries (controls/cooling), critical user load, then discretionary load. Below the reserve threshold, discretionary loads can only consume spare instantaneous PV; they cannot drain the protected battery reserve. Load shedding has a five-percentage-point SOC recovery band. Discretionary energy is shed, not shifted or rescheduled. Unserved energy and outage-duration estimates remain visible.

The initial stored energy has unknown provenance. A separate renewable-energy inventory begins at zero, increases only with PV charging and decreases proportionally on discharge. AC energy to users is labelled renewable only in proportion to PV-origin energy at the inverter. This prevents an initially charged battery from creating fictitious renewable generation. Initial-energy contribution, net storage change, final SOC and losses are exported.

A protected tracker/controller UPS is assumed available for mechanical movement. Its average replenishment demand is included in auxiliaries; its independent finite energy storage and black-start behaviour are not resolved. Cases with unmet auxiliaries are flagged because yield and actuation feasibility require verification of that protected supply. This is a material limitation for severely undersized systems. Night tracking does not imply the array can operate with a dead protected supply.

## 7. Container and battery thermal model

Two dynamic nodes are used: room/enclosure effective mass, and battery mass. The room mass includes an assumed effective contribution of the internal fit-out; air-only thermal capacity would underrepresent inertia. Outer dimensions estimate envelope area and volume; floor heat transfer is simplified as exposure to ambient, with no soil node.

`C_room × dT_room/dt = UA_shell(T_air−T_room) + UA_infiltration(T_air−T_room) + Q_solar + Q_internal + Q_inverter + Q_controls + UA_battery(T_battery−T_room) − Q_compressor − Q_ventilation`.

`C_battery × dT_battery/dt = Q_battery_losses − UA_battery(T_battery−T_room)`.

Units are kW for thermal flux and kJ/K for capacitance; integration uses seconds. Explicit thermal substeps are at most 30 s. The battery heat source is the same conversion inefficiency counted electrically; no second arbitrary I²R source is added. These losses lump cell and battery-converter effects at the battery node. A more detailed implementation would locate converter heat in its actual compartment and use measured rack resistance/efficiency maps.

Solar gain is a reduced sol-air approximation with assumed exterior heat-transfer coefficient 15 W/m²K. Roof area receives the selected shade fraction; 25% of wall area represents an effective solar-exposed wall contribution. Shell U-value and solar absorptivity scale admitted heat. It is a predesign approximation, not a building energy simulation. The independent shade canopy is a design assumption, separate from the detached tracking tables shown in the schematic.

Uncontrolled infiltration is based on air changes per hour. Controlled ventilation uses `rho × cp × airflow × (T_room−T_air)`. Free cooling is enabled when outdoor air is at least 2°C cooler, room is above setpoint and outdoor RH is below 85%. The humidity criterion is only a simple eligibility check; the model does not calculate dew point, moisture balance, condensation or latent cooling loads.

The compressor thermostat uses a 2°C total deadband about the setpoint. Thermal cooling capacity is distinct from electrical demand; `P_electric = Q_removed / COP`. Assumed COP and cooling-capacity curves derate with ambient temperatures above 35°C. Actual high-ambient OEM performance maps should replace these curves. Fan power and compressor power are both included in dispatch. If auxiliaries are only partly served, cooling output scales with the supplied fraction.

The internal heat assumption represents an additional non-electrical sensible source, such as occupancy or heat ingress not explicitly resolved. Controls and inverter heat are added separately. Exterior tracker motor heat is not added to the enclosure.

Default battery power derates from 40°C to zero at 50°C; the hot trip latches until 38°C. Charge and discharge are conservatively inhibited below 0°C. These are control-study settings, not universal LFP limits. Inverter output derates from room 45°C to zero at 60°C. No emergency BMS, fire system or real hardware protection depends on this application.

## 8. Control implementation and fault study

The model runs slow supervisory control at 5, 15 or 60 min. It does not simulate switching MPPT, P&O perturbations, PWM, current-loop stability, motor torque, DC-link transients, AC frequency/voltage control, short circuits or contactor opening times. Its MPPT abstraction assumes maximum available power with a converter efficiency and input constraints.

| Implemented state machine | Normal action | Fault/safety response |
|---|---|---|
| Tracker | Ephemeris, mechanical limits, backtracking, deadband | Gust/sensor stow with recovery latch; jam holds last position |
| Cooling | Passive → free cooling or compressor | Failure injection removes ventilation/compressor cooling |
| Storage | PV surplus charging, deficit discharging | SOC reserve; temperature power derate; hot/BMS isolation |
| Inverter | AC load service within input/output limits | Room-temperature derating and unmet-load reporting |
| Energy manager | Auxiliaries → critical → discretionary | Shed discretionary load below reserve; report all remaining deficits |

Fault windows can represent an anemometer fault, tracker jam, HVAC failure, PV outage or BMS trip. Anemometer failure produces a conservative stow command; ephemeris calculations remain available. A BMS trip removes the battery, while PV can still serve the DC/AC path in this energy abstraction. Recovery follows the model's conditions; a physical system may require manual reset. The application allows only one injected named fault at a time, with wind/temperature stresses acting concurrently.

The gust proxy is `max(gust_factor × 10m_mean_wind, imposed_gust)`, default factor 1.5. TMY winds cannot establish design gusts or storm risk. Recovery below 9 m/s must persist for the selected hold time; a rise above recovery resets the clock. Detection and commands occur only at the model interval, so exact delays are quantized. [DNV's tracker wind investigation](https://www.dnv.com/publications/wind-speed-and-rear-glass-breakage-on-bifacial-pv-modules-mounted-on-trackers/) supports the need for a structure-specific wind/mounting assessment. A horizontal default stow angle is not presented as universally safest.

Suggested real-system control components: PLC/industrial computer; accurate local clock/GNSS; absolute encoders and end stops; anemometer with independent fault diagnostics; string/DC and AC metering; clean-reference irradiance/soiling measurements; module, ambient, room and multiple rack temperature sensors; BMS and hardwired contactor permissions; local emergency stop; separately powered detection/communications. Modbus/CAN interfaces, electrical isolation and EMC design require selected equipment. Local logging should persist through connectivity loss; remote communication may use store-and-forward cellular telemetry. These are architecture recommendations, not integrations implemented in the dashboard.

## 9. Mobile system characteristics and engineering completion

The modeled energy function should be translated into a supplier-reviewed equipment schedule. Complete the following to turn the concept into deployable hardware:

- Confirm an actual load inventory, peak/inrush power, load criticality and allowable outages; replace the generic duty profile with measured time series.
- Select module/inverter/battery products and coherent voltage/current, environmental, thermal and protection maps. Check per-MPPT string allocation, cold Voc, hot Vmp and all ratings.
- Design fold/deploy/track mechanisms independently, including cable bend radius, connector mating cycles, actuator torque, end stops, transport locks and manual recovery.
- Resolve lifting points, modified-container approvals, centre of gravity, total packed mass, axle loads, restraint, internal clearances and usable transport volume. The dashboard's modules-plus-battery mass excludes other equipment and is not shipping mass.
- Design wind resistance, tilt/stow strategy, anchorage/ballast and ground bearing using site-specific loads and structural testing/calculation. Check access, drainage, flooding, security and safe movement clearance.
- Separate battery and power-electronics compartments as required by the selected installation design; provide suitable detection, ventilation/pressure management, isolation, emergency access and response provisions based on actual equipment and the local design process.
- Verify earthing/bonding, cable protection, DC/AC disconnection, surge/lightning coordination, RCD compatibility, short-circuit and overload performance, and grid-forming behaviour with the intended loads.
- Calibrate insulation, shade and cooling curves for Nairobi; also test hotter remote/coastal cases, filter blockage and loss of cooling. Design service access and a realistic maintenance/cleaning plan for dust and corrosion exposure.
- Verify Kenyan installation, transport, permitting and equipment conformity requirements with the responsible local engineers and suppliers. No legal compliance or certification is asserted by this model.

The workflow above describes actual design completion needs; no product is certified or declared safe by a dashboard result.

## 10. Outputs and accounting

PV generated is power/energy at the accepted DC bus after modelled PV/MPPT losses. Useful renewable energy is AC delivered to user loads after storage/inverter losses and auxiliary demand, with initial charge provenance excluded. Cooling and tracker values refer to their own electrical demand. Unserved user energy includes deliberate discretionary shedding and physically unavailable power. Critical shortfall is shown separately.

For the whole run:

`PV_DC = user_AC + auxiliaries_AC + curtailed_DC + battery_loss + inverter_loss + net_battery_energy_increase`.

The DC bus is checked at every step, and the chemical storage update is checked independently. Floating-point residuals should be negligible. Equal energy balance is necessary but does not validate weather, hardware or controller assumptions.

The Sankey uses net storage change rather than gross battery cycling, which avoids double-counting storage throughput. Battery charge/discharge time series remain available in the CSV. Renewable fraction, load coverage and PV generation are distinct metrics; a large annual PV surplus does not guarantee uninterrupted off-grid service during consecutive cloudy days.

Exports include full time series, configuration, source metadata, summaries and runtime versions. Scenario ZIP files contain the input weather, engineering notes and reference catalogue. Raw PVGIS JSON files remain in the project. Default results and validation evidence are generated locally in `outputs/`; rerun the supplied scripts when model assumptions change.

## 11. Validation and uncertainty

Automated checks cover energy conservation, SOC bounds, mutually exclusive charging/discharging, zero-PV outages, unknown initial-energy provenance, wind latch and jam response, hot battery derating/trip, cooling load/temperature coupling, string-voltage constraints, PVGIS chronology/time conversion, uploaded-data rejection and the application pages/controls. Scenario comparisons use the same weather, module capacity and load profile.

These are software and physical-consistency checks. There has been no comparison to a measured container prototype. Module thermal coefficients, local soiling, converter curves, storage usable capacity, thermal conductance and load timing can all materially alter results. A TMY does not quantify interannual uncertainty, extreme storms or P90 energy. Sensitivity controls provide deterministic scenarios, not confidence intervals.

## 12. Container field lab: current weather, clock and deployment

The default workspace is now a detailed 3D container compound. The original annual energy study remains on Overview and the other analysis workspaces. The live scene does not relabel historical TMY output as current production.

### Clock and weather

Live site mode uses the computer's timezone-aware UTC clock converted to Africa/Nairobi. The browser timezone supplies the operator's local clock. Screen updates occur approximately every two seconds while enabled; sun position uses NREL SPA at the displayed site timestamp. An accelerated solar-day mode and a manual study time are explicitly labelled as simulated time. Switching clock mode or jumping backward resets the session's electrical/thermal states. Manual views with zero elapsed time accumulate no energy.

[Open-Meteo](https://open-meteo.com/en/docs) provides modelled current conditions and solar forecasts for the selected coordinates. The application requests instantaneous solar variables, converts pressure to Pa, uses m/s wind and interpolates the downloaded hourly solar series for the display. It shows provider/sample/retrieval timestamps, grid coordinates and response age. These are numerical model conditions, not measurements from the pictured installation. API requests are cached for 15 minutes; an offline cached response is labelled, and data outside its downloaded time window are rejected. Historical or synthetic data are never silently substituted in this workspace. Provider responses are cached locally outside Git.

### Geometry and visual mechanism

The scene contains a corrugated shell, two roof hatches, floor and corner fittings, battery modules, converter cabinets, cable routing, HVAC condenser grille, control cabinet, weather mast, concrete pad and steps. Its compound includes fencing, gate leaves, posts, lights, a north marker and procedural vegetation/terrain. Cutaway and camera modes expose the internal arrangement. The landscape illustrates a Kenyan highland/arid setting according to the selected site; it is not a georeferenced site survey.

Every selected module has a unique packed centre and a deployed pose. The default 36 modules stack in three discrete horizontal slots, with 75 mm vertical layer pitch, below the closed roof. Module centres and corners are exported and tested. The illustrative packing height is screened before deployment. This verifies the drawn default module stack; it does not establish total shipping mass, loading access or clearance to every ancillary component.

Deploy is one command for hatch opening, cassette lift, rail extension/unfolding, support positioning and final locking. Retract first isolates the PV path and reverses this sequence. Motion can be held or reversed. Roof angle, cassette/rail progress, support permission, PV isolation and module count are visible. The animated paths and the telescopic supports are a conceptual mechanism; no actuator torque, dynamic load, hinge fatigue or comprehensive collision analysis is claimed. Presentation duration is independent of real installation time and is not used to claim a physical deployment rate.

The adaptive camera moves from a close container view to a compound overview as deployment progresses. Fixed inspection cameras, dimensions and cutaway are available. The optional PyVista/Panel inspection scene supports orbit and zoom. Turn off automatic updates to keep its snapshot uninterrupted. PNG and JSON exports preserve the displayed state.

### Solar shadows and visual detail

Panel and enclosure shadows are projected along parallel solar rays onto the local compound plane. They change direction/length with solar azimuth/elevation and disappear below the horizon. This visual projection does not resolve distant-terrain occlusion, a radiative sky dome, diffuse penumbrae or energy loss caused by arbitrary objects. The visible sun marker is placed at an intentionally reduced distance so its direction can be inspected; the shadow calculations still use parallel rays. The separate sun-path plot retains exact angular geometry even if a selected camera does not contain the marker. Scene lighting responds to day/night and cloud cover.

### Coupling to the plant

Packed, partly deployed and retracting arrays deliver zero accepted PV power. The contactor is only enabled at full deployment with the deploy target active. Solar electrical calculations reuse the existing Perez/Faiman/PVWatts model at the realised orientation. Wind-gust stow uses on/off thresholds and the configured recovery hold; an above-threshold weather-model gust also inhibits new deployment and holds deployment in progress. This is a supervisory study, not a safety-rated weather input.

The existing battery/room dispatch solver now accepts an optional prior state and elapsed-time step. Live mode carries stored chemical energy, PV-origin inventory, temperatures and controller latches between updates. Elapsed intervals are subdivided into at most 60-second dispatch steps with thermal substeps no greater than 30 seconds. Forecast/solar power at the screen update is held over the elapsed interval; accelerated previews are an approximation and are not a replacement for the annual solver's regular weather/control steps. The model reports simulated session PV energy, supplied AC load, unmet load, cooling, DC balance and battery state. Initial charge is still not counted as renewable generation.

The new checks cover panel packing/extent, finite intermediate poses, analytical shadow direction, timezone invariance, weather interpolation/range checks, zero PV while packed, live wind-stow recovery, stateful-dispatch continuity, zero-time energy behaviour, one-command UI deployment/retraction and an actual VTK image render. These are software/geometry consistency checks; field validation remains outstanding.
