# BehnamProject-PVforAfrica — free public simulation

**Public link: [behnamproject-pvforafrica.onrender.com](https://behnamproject-pvforafrica.onrender.com/)**

Verified on 21 October 2026: the public health check responds, the 3D workspace
loads live Nairobi model weather, the PV array deploys to 100% with the roof
closed, and the browser camera orbits the scene. Public availability follows the
owner's Suspend/Resume setting and Render's free-tier limits.

The public service runs the existing interactive Dash/VTK workspace directly,
with the default Nairobi design and full deployment, tracking, weather, camera,
thermal, technical and export controls. The local Streamlit dashboard still
provides design editing and the annual engineering studies.

The developer-attribution/security release is identified by `revision: credits-security-v1` at `/healthz`.
After that release, refresh an already-open browser tab to load the new panel,
picking controls and local browser fan animation. Press Ctrl+F5 if an older tab is cached. No additional service, paid plan, external
asset host or Python dependency is needed for this equipment update.

Public simulations now use a signed browser cookie: refreshing reuses the same
scene instead of allocating another. Two different visitor browsers can run
independent models within the free memory allowance. Public scene PNG exports
are Full HD; local QHD/4K exports remain available. See [SECURITY.md](SECURITY.md)
for exact request limits, browser protections and the remaining uptime limits.

## Deployment

`render.yaml` defines a Docker web service named `behnamproject-pvforafrica` on
the **free** plan, in Frankfurt. No database, persistent disk, paid service or
custom domain is requested. `Dockerfile` installs the Linux graphics libraries
required by VTK. `gunicorn.conf.py` serves one threaded Python process on
Render's `PORT`; all scripts, assets, layout requests and callbacks use the same
public origin. No localhost URLs are sent to visitors.

1. Sign in to [Render](https://dashboard.render.com/).
2. Connect the GitHub repository **kenya-mobile-solar-dashboard**. Keep it private;
   grant Render repository access through its normal GitHub integration.
3. Choose **New → Blueprint**, select the repository and branch `master`, and
   review the free service from `render.yaml` before creating it.
4. Wait for the build and `/healthz` check to pass, then open the address shown
   by Render and verify deployment, orbit/zoom and live telemetry.

Alternatively, open the [prepared Deploy to Render shortcut](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FBehnamMohseniGharyehsafa%2Fkenya-mobile-solar-dashboard)
in the browser where you are signed in to Render. For a private repository,
[authorize Render's GitHub app](https://github.com/apps/render/installations/new)
for **only this repository** if it is not already included. Review the proposed
service name, branch `master` and `free` plan, then submit **Deploy Blueprint**.
The shortcut is Render's setup page, not the public simulation link.

Source: [Render's deployment shortcut documentation](https://render.com/docs/deploy-to-render).

This project's verified address is `https://behnamproject-pvforafrica.onrender.com`.
If deploying another instance, Render may append a suffix when a name is already
in use. Use the actual URL on that instance's dashboard.

The page title preserves **BehnamProject-PVforAfrica**. Web addresses use lowercase.
Automatic deployments are off: future commits do not silently replace a demo.
Use **Manual Deploy → Deploy latest commit** to publish reviewed updates.
Blueprint configuration changes can still synchronize automatically; set the
Blueprint's **Auto Sync** setting to **No** if you also want to review those
changes before applying them.

## Turn the link off or on

Use your private Render dashboard, not a control exposed to visitors:

1. In the service list, select `behnamproject-pvforafrica`.
2. Choose **Suspend** to stop the public simulation. Opening the link will not
   automatically resume a manually suspended service.
3. Choose **Resume** to make it available again at the same address.

Suspending/restarting resets in-memory simulation sessions; it does not remove
the GitHub repository. Do not delete the service when you only want to turn it off.

Render documents the [Suspend/Resume controls](https://render.com/changelog/suspend-and-resume-services-in-bulk-from-the-render-dashboard).

### Optional PowerShell controls

Find the service ID (`srv-...`) on your Render service dashboard. Create an API
key in your Render account settings, then use the following commands from your
checkout. The script prompts for the key with hidden input; never commit the
key or share it with viewers.

```powershell
$env:RENDER_SERVICE_ID = "srv-REPLACE-WITH-YOUR-SERVICE-ID"

# Show whether the public service is suspended.
& .\.venv\Scripts\python.exe -m tools.render_service status

# Turn public access off.
& .\.venv\Scripts\python.exe -m tools.render_service off

# Turn it back on at the same link.
& .\.venv\Scripts\python.exe -m tools.render_service on
```

The ID must match the intended service name; the control script refuses to
suspend another service. These commands run locally and keep account credentials
outside the published application.

## Free-tier limits and verification

- Render's free service sleeps after 15 minutes without traffic, and wakes on
  the next visit, normally taking about a minute. This automatic sleep is
  separate from the owner's **Suspend** control.
- The free plan has 512 MB RAM and 0.1 CPU. Initially this deployment admits two
  active browser simulations at a time. A third tab sees a capacity message,
  rather than evicting the first viewer. Abandoned sessions expire after three
  minutes without simulation requests and are released when another viewer opens.
- `PV_MAX_SESSIONS` is adjustable, but raising it needs a memory/concurrency test.
  Each visitor retains independent state. Browser WebGL performs the drawing;
  Python still computes the model and sends geometry. Network latency and shared
  CPU affect animation speed; a desktop benchmark is not a hosted FPS guarantee.
- Weather is downloaded from Open-Meteo. This is model weather, not measurements
  from a site sensor. `PV_WEATHER_CACHE_DIR=/tmp/solar-weather` gives the non-root
  container user a writable, disposable cache. A cache write failure is reported
  but does not discard an otherwise validated provider response. Filesystem caches
  and in-memory state are disposable.
- Keep the service on the free plan. Free-tier quotas and availability follow
  [Render's current limits](https://render.com/docs/free).

The GitHub Actions `cloud-container` job builds the actual Docker image, starts
it with a 512 MB memory cap, fetches the real 3D layout and calls the model through
Dash's HTTP API. It prints container memory and OOM diagnostics. This checks a
two-session container, not Render's CPU throttling or internet performance.

For Docker installed locally:

```powershell
docker build -t solar-cloud .
docker run --rm --name solar-cloud --memory=512m -p 127.0.0.1:10000:10000 solar-cloud
```

In another PowerShell window, run
`docker exec solar-cloud python -m tools.smoke_cloud http://127.0.0.1:10000`.
Close its smoke-test session by restarting the local container before browser use.
