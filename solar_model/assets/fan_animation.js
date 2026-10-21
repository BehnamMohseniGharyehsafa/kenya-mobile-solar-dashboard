/* Visual motion only. Cooling demand, safety logic and energy remain Python.
 * The public Dash set_props API updates the resident rotor, never the scene.
 * No network calls, React/VTK internals, or extra rendering library are used.
 */
(function (root) {
    "use strict";
    // Exact integration of a first-order visual drive. Angle and acceleration
    // depend on elapsed time, not display refresh rate or callback arrival time.
    function advance(state, target, dt) {
        const tau = target > state.speed ? 0.35 : 0.55;
        const decay = Math.exp(-dt / tau);
        state.angle = (state.angle + target * dt +
            (state.speed - target) * tau * (1 - decay)) % (2 * Math.PI);
        state.speed = target + (state.speed - target) * decay;
        if (target === 0 && state.speed < 0.002) state.speed = 0;
    }

    function createAnimator(env) {
        const state = {angle: 0, speed: 0};
        let command = null, frame = null, previous = null, painted = null;
        let visible = true, disposed = false, frames = 0;
        function active() {
            return !disposed && visible && !env.hidden() && !env.reduced() && command &&
                (command.visual_rpm > 0 || state.speed > 0);
        }
        function wake() {
            if (frame === null && active()) frame = env.request(tick);
        }
        function pause() {
            if (frame !== null) env.cancel(frame);
            frame = null;
            previous = painted = null;
        }
        function tick(now) {
            frame = null;
            if (!active() || !env.mounted()) { pause(); return; }
            // No hidden-tab catch-up, multi-turn jumps, or queued server frames.
            const dt = previous === null ? 0 : Math.min(0.05, Math.max(0, (now - previous) / 1000));
            previous = now;
            advance(state, command.visual_rpm * 2 * Math.PI / 60, dt);
            // Cap 120/144 Hz displays at 60 updates/s; normal 60 Hz stays smooth.
            if (painted === null || now - painted >= 1000 / 60 - 0.75 || !state.speed) {
                painted = now;
                env.paint({orientation: [state.angle * 180 / Math.PI, 0, 0], origin: command.centre,
                    position: [0, 0, 0], useBounds: false, visibility: true}, state.angle, ++frames);
            }
            wake();
        }
        return {
            configure(next) {
                if (!next || !Array.isArray(next.centre) || next.centre.length !== 3 ||
                    !next.centre.every(Number.isFinite) || !Number.isFinite(next.visual_rpm)) return;
                if (command && command.session !== next.session) { pause(); state.angle = state.speed = 0; }
                command = {...next, visual_rpm: Math.max(0, Math.min(30, next.visual_rpm))};
                wake();
            },
            visibility(value) { visible = value; pause(); wake(); },
            refresh() { pause(); wake(); },
            dispose() { disposed = true; pause(); },
            snapshot() { return {...state, frames, scheduled: frame !== null}; }
        };
    }

    if (typeof module !== "undefined" && module.exports) module.exports = {advance, createAnimator};
    if (!root || !root.document) return;
    let animator = null, observer = null, element = null, indicator = null;
    const reduced = root.matchMedia("(prefers-reduced-motion: reduce)");
    let retry = null, ready = false, latest = null;
    function configure(command, session, attempt = 0) {
        if (retry !== null) { root.clearTimeout(retry); retry = null; }
        const view = root.document.getElementById("vtk");
        if (!view) {
            // dash-vtk loads its renderer asynchronously on the first visit.
            if (attempt < 100) retry = root.setTimeout(() => configure(command, session, attempt + 1), 100);
            return root.dash_clientside.no_update;
        }
        if (view !== element) {
            if (animator) animator.dispose();
            if (observer) observer.disconnect();
            element = view;
            ready = false;
            indicator = root.document.querySelector("#fan-indicator .fan-blades");
            animator = createAnimator({
                request: callback => root.requestAnimationFrame(callback),
                cancel: handle => root.cancelAnimationFrame(handle),
                hidden: () => root.document.hidden,
                reduced: () => reduced.matches,
                mounted: () => element.isConnected,
                paint: (pose, angle, frames) => {
                    // GeometryRepresentation already requests a native render
                    // after an actor update. Updating View again would double
                    // draws and needlessly touch all its children.
                    root.dash_clientside.set_props("fan-rotor", {actor: pose});
                    if (indicator && indicator.getClientRects().length) indicator.style.transform = "rotate(" + angle + "rad)";
                    // Cheap, inspectable counters: no per-frame Dash Store or HTTP.
                    element.dataset.fanFrames = String(frames);
                }
            });
            if (root.IntersectionObserver) {
                observer = new root.IntersectionObserver(entries => animator.visibility(entries[0].isIntersecting));
                observer.observe(element);
            }
        }
        latest = {...command, session};
        // Let Dash finish asynchronously mounting the static VTK datasets and
        // controls before starting continuous local updates.
        if (!ready) retry = root.setTimeout(() => { ready = true; retry = null; animator.configure(latest); }, 1500);
        else animator.configure(latest);
        return root.dash_clientside.no_update;
    }
    root.document.addEventListener("visibilitychange", () => { if (animator) animator.refresh(); });
    reduced.addEventListener("change", () => { if (animator) animator.refresh(); });
    root.addEventListener("pagehide", () => {
        if (animator) animator.visibility(false);
        if (retry !== null) root.clearTimeout(retry);
    });
    root.addEventListener("pageshow", () => { if (animator) animator.visibility(true); });
    root.dash_clientside = root.dash_clientside || {};
    root.dash_clientside.pv_fan = {configure};
})(typeof window === "undefined" ? null : window);
