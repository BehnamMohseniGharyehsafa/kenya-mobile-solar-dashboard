# Validation record

Date: 21 October 2026. Runtime: Python 3.13.7; pvlib 0.16.1; Streamlit 1.66.0; Dash 4.4.1; Dash VTK 0.0.9. Model and app layout/controls are Python; the approved fan-only browser helper is JavaScript.

## Developer attribution and public resource safeguards

The complete security run passed **85 tests in 21.53 s**. A subsequent
manual-date regression also passed in the 26-check equipment/security subset;
the final 14-check security request suite and real local cloud smoke passed. Added HTTP checks cover
signed/Secure/HttpOnly/SameSite cookies, host and origin rejection, malformed and
oversized JSON, unknown callbacks and response targets, browser-owned simulation
IDs, refresh reuse, bounded rate-limiter storage, concurrent-work rejection while
health remains available, and rejecting forged public 4K requests. Actual browser
checks confirmed the three-line developer attribution, normal deployment,
restoration of the deployed model after refresh and no CSP console errors.

An exact-version PyPI advisory lookup covered 110 installed/cloud package entries.
Only the installed Pillow 12.3.0 was flagged (eight advisories, fixed in 13.0.0).
The cloud requirements now omit unused Streamlit and pin Pillow 13.0.0; the local
Streamlit dependency bound remains compatible. The public app does not decode
uploaded images/PDFs. Advisory lookup is not proof of exploitability or absence
of unknown flaws. The cloud CI smoke also exercises a real Full HD PNG export
and the official PyPA audit checks the resolved cloud requirements.

## Automated verification

The smooth-fan update removes the former 100 ms server callback. New actual
Node runtime checks exercise frame-rate independence (30/60/144 Hz), acceleration,
coast-down, one loop after repeated commands, offscreen/hidden/reduced-motion
pause/resume, high-refresh capping and stall recovery. Dash integration checks
verify the helper is served locally, the fan callback is clientside, commands
stay small, and PNG export receives the browser's actual rotor pose. Earlier
10 Hz HTTP payload timings below describe the superseded release, not browser
smoothness. Final local regression: **71 passed in 38.13 s**, including seven
JavaScript runtime timing/lifecycle scenarios through the Node test runner.

A 120-frame desktop geometry/encoding sample measured 4.30 ms median and 5.40 ms
p95, with the existing 53 actors / 93,103 triangles / 203.54 KiB update unchanged.
Fan animation adds zero per-frame server requests; a state-change command is
64 bytes before callback framing. These are CPU/transport checks, not an FPS
guarantee. A browser sample during deployment plus a concurrent full Python
test run averaged 46 local pose updates/s; device/GPU load affects the cadence.
Actual browser checks retained the container close-up during rotation, reached
100% deployment with a closed roof, and isolated PV while cooling continued
under the simulated emergency stop. A cold first visit exposed lazy renderer initialization racing the frame loop.
The helper now waits for the actual canvas, complete geometry count and mounted
datasets before starting; a dedicated runtime case tests partial readiness. An actual browser test on a
fresh local origin delayed the lazy VTK renderer by six seconds and verified
that the full scene and equipment close-up remained intact while the fan ran.
The affected equipment/callback suite then passed 23 checks.
Server counters recorded only plant ticks,
camera changes and explicit operator actions, with no fan interval requests.


The operator-panel/fan release adds checks for stop/reset/restart sequencing,
PV isolation with protective cooling retained, frozen tracker pose during a stop,
rigid fan transforms, a stopped fan at zero delivered cooling power, unknown LCD
values, stable 160-cell display topology, duplicate-reading suppression, explicit
3D button picks and the fan's actual HTTP callback. Full-suite and Linux container
results are recorded in GitHub Actions.

The HMI/fan release passed **70 checks** in Linux CI. Its Docker test loaded two
independent scenes and a real plant callback within a 512 MB memory cap, recording
267.7 MiB with no OOM termination. The `/healthz` endpoint on the public service
reported `hmi-fan-v1`. Actual browser checks on Render verified live LCD readings,
the physical green start and red stop buttons, PV isolation with cooling retained,
reset without automatic restart, and an explicit successful restart. The amber
hold/resume sequence was also exercised in the local browser. These are functional
and resource checks, not a cloud frame-rate or concurrency guarantee.

Fresh 120-frame desktop comparison (same Python environment, no active browser
preview): the prior release measured 10.09 ms median / 14.00 ms p95 for Python
animation plus geometry encoding; the HMI release measured 6.26 / 10.10 ms.
The unchanged geometry update payload was about 203.54 KiB. This is a sampled
CPU benchmark, not a browser FPS or internet-latency guarantee. A rotor-only
update measured 0.014 ms and 191 bytes for the transform; its complete HTTP
response is checked to remain below 700 bytes. The initial scene is 53 actors,
93,103 triangles and 3.47 MiB of initial JSON, within the existing actor/triangle
budget. Static landscape and the eight deployment/shadow coordinate buffers
remain resident; rotor animation does not rebuild or resend them.

Latest visual-quality run: **58 passed in 46.87 s**. This includes the original model checks, packing/shadows, live clocks/weather, stateful dispatch, VTK rendering, both roof-closed endpoints, reversible deployment/hold, direct-buffer callback transport, repeated landscape/cutaway toggles, static geometry budgets, highland/arid grass colours and 1440p export with renderer-size restoration. Provider data are mocked in automated tests; actual Nairobi data were fetched and inspected separately. The initial mesh encoder emits upstream VTK deprecation notices; the checks complete successfully.

Original annual-dashboard baseline: **26 passed in 21.58 s**.

- 25 model/parameter/data checks passed, including all three tracker modes, per-step DC balance, chemical battery balance, SOC and power limits, no concurrent charging/discharging, initial-energy provenance, zero-sun outages, wind latch/recovery, jam behaviour, sensor/BMS/HVAC faults, thermal response, voltage screening, six cached sites, timestamp conversion, CSV validation and time-step sensitivity.
- Streamlit integration test passed: all seven pages rendered without exceptions and applying dual-axis tracking updated the actual model configuration. A representative seven-day input keeps the UI test small; whole-year physics is checked separately.
- The actual running app was opened in the browser, its overview metrics were verified, and its 3D tracking page was inspected. The app runs on local port 8507 because another application already uses 8501.
- Streamlit's Windows asynchronous socket setup required execution outside the restricted process sandbox. This was an execution-environment restriction, not an application error.

## Default Nairobi whole-year result

Input is the downloaded PVGIS SARAH3 TMY for −1.2864°, 36.8172°. Configuration: 19.8 kWp, 80 kWh nominal battery, 20 kW inverter, single-axis tracking, 15-minute energy control.

| Output | Model result |
|---|---:|
| PV accepted at DC bus | 40,529.52 kWh |
| User load served, AC | 24,303.28 kWh |
| PV-origin energy delivered to users, AC | 24,269.07 kWh |
| User demand | 25,002.50 kWh |
| User demand coverage | 97.20% |
| Unserved user demand | 699.22 kWh |
| Critical unserved demand | 300.68 kWh |
| Curtailed DC energy | 13,020.26 kWh |
| Cooling electricity served | 208.64 kWh |
| Maximum battery temperature | 31.12°C |
| Whole-run electrical balance residual | 2.96 × 10⁻¹² kWh |
| Maximum per-step DC-bus residual | 2.67 × 10⁻¹⁵ kW |

Unknown-origin initial charge contributes 34.21 kWh to served user loads and is excluded from renewable delivery. The default case has 11.42 kWh of unmet auxiliaries, which is displayed with the protected-control-supply limitation described in the engineering notes. A balanced energy ledger does not validate tracker UPS availability or field performance.

## Tracking comparison

Each case reruns the same solar, electrical, storage, thermal and supervisory model under the same weather and load.

| Orientation | PV DC kWh | PV increase over fixed | AC user energy served kWh |
|---|---:|---:|---:|
| Fixed tilt, 10° north-facing | 32,775.11 | baseline | 24,063.53 |
| Horizontal N–S single axis | 40,529.52 | 23.66% | 24,303.28 |
| Dual axis with 60° tilt limit | 43,173.28 | 31.73% | 24,430.41 |

These are deterministic model comparisons, not promised equipment gains. Fixed/dual inter-table shading is omitted. Curtailed production and storage limitations explain why increases in PV generation do not produce proportional increases in served energy.

Additional cases cover larger storage, passive cooling, a +10°C ambient stress, continuous wind stow, HVAC failure, Lodwar and Mombasa. Machine-readable results are generated by `tools/validate_model.py` in `outputs/`. The full model notes describe omitted phenomena and the absence of field calibration.

## Container scene and live workspace

- All 36 default modules have distinct packed positions with their vertices inside the closed shell. Deployed corners remain inside the illustrated fence. Intermediate geometry is finite and above the ground plane.
- Shadow projection is checked against a known 45° sun case, including correct direction and zero night shadow.
- UTC and EAT timestamps produce the same solar position for the same instant.
- Weather interpolation and out-of-window rejection are checked without external network calls.
- Packed/moving arrays deliver zero accepted DC power. The drive load remains a floating-point electrical load during motion; browser testing identified and corrected an integer-dtype assignment error.
- The live wind-stow latch requires the configured recovery hold. Stored energy and temperature states match the corresponding continuous dispatch run when it is split into chunks.
- Manual views with no elapsed time do not create session energy. Charge/discharge and DC balance are also checked in live steps.
- PyVista renders an actual scene image during the test suite. Linux CI uses Xvfb and OpenGL/EGL libraries. The default compound, packed enclosure and intermediate cutaway were also rendered at 1440 × 810 for visual review.
- The main interactive viewport is tested with actual Dash VTK component definitions. Every default module is represented in a single batched mesh, with six moving geometry groups. Routine animation outputs target individual coordinate buffers, never View.children; camera/reset properties, connectivity and cell colours are excluded. The render window remains the same across deploy/retract and repeated landscape/cutaway changes. Unchanged panel buffers are not sent during hatch-only motion. A detail-tab click is checked with the plant solver prohibited, to guard against unnecessary solves in that path.
- A Flask/Dash HTTP callback test exercises the actual wildcard-output response. Only a changed moving buffer and an explicit render instruction cross the wire; the response excludes scene children. This covers the transport/component mapping rather than merely checking internal controller state.
- Roof-angle checks cover opening, extraction, closing and both endpoints. Modules stay clear of the roof envelope throughout the last 16% of deployment; reverse motion opens the roof before repacking. Accepted PV remains zero until the full sequence finishes.
- The loopback-only viewer service starts and shuts down in an integration check. Callback metadata verifies that the animation interval is disabled while a prior request is running, preventing overlapping updates from accumulating.

- The live browser view displayed Nairobi's model weather and the correct EAT/Dublin clock relationship. The operator-facing scene is expressly labelled as a simulated plant; annual TMY results remain separate.

The reproducible 60-frame benchmark (`python -m tools.benchmark_viewer`) measures animation plus geometry JSON encoding, with weather held deterministic and the separate 1 Hz plant/5 s chart schedules excluded. On the same Windows/Python environment, the previous implementation measured a median **53.33 ms** (95th percentile **142.03 ms**); the final optimized implementation measured **12.81 ms** (95th percentile **18.24 ms**), approximately **4.2× faster** at the median. Median geometry payload changed from **214.9 KiB** to **205.7 KiB**. The largest browser improvement comes from avoiding parent-tree updates and redundant representation renders, not a large bandwidth reduction. These CPU/encoding timings exclude initial loading, plant solves, network and browser drawing; they do not establish a client FPS guarantee.

The vectorized module trajectories were also compared directly against the preceding Git version for 101 deployment positions at 9, 36 and 72 modules, with nontrivial 37° tilt/213° azimuth: all corners and centres agree within 2 × 10⁻¹⁴ m. The browser visibly completed deployment with roof 0°, selected camera tools promptly, and toggled cutaway/vegetation without reloading the scene. A camera-tool selection round trip, including automation overhead, was about 0.46 s; this is an observed check rather than a latency guarantee. The earlier 40-frame benchmark used a different timing scope and should not be compared directly with these values.

The subsequent landscape/UI upgrade retains the same animation protocol. The same 60-frame local animation/encoding benchmark measured **11.99 ms median / 18.22 ms p95** before the visual change and **9.93 ms / 14.15 ms** afterwards; ordinary timing variation is expected, and these figures do not measure browser FPS. Median geometry transfer remains approximately **205.7 KiB**. The final default scene has **51 actors** (previously 53) and **86,539 triangles** (previously 92,724); the added static detail is limited by regression checks to 55 actors and 150,000 triangles. Initial Dash layout JSON, including static normals and all geometry, is **3.29 MiB**. The landscape itself is batched into at most five materials and remains below 70,000 triangles. Static normals are present at loading and absent from animation responses. Separate tests check clear equipment ground, greener highland grass, the dry-site palette, and an oversized compound that leaves no room for near grass. Export is checked at 2560 × 1440 pixels and must restore the original render-window size afterwards.

The final camera-bound correction also passed five focused scene/landscape/export checks in 18.52 s. The HTTP export callback verifies the selected 3840 × 2160 resolution and camera preset; camera-reset review confirms whole trees remain visible.

These checks do not certify structural loads, actuator forces, collision clearance, safety controls, weather observations or field energy performance. See section 12 of the engineering notes for the model's exact scope.
