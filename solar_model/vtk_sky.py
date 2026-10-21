"""Narrow compatibility adapter for the pinned Dash VTK 0.0.9 camera.

Dash VTK does not expose a clipping-range property. Preload its existing lazy
chunk with its public vtkRenderer depth-reset event used to preserve the fitted near
plane while allowing the sky proxy beyond the installation. No package files,
React runtime objects, extra rendering library or frame loop are modified/added.
The queued webpack chunk is consumed by the normal Dash VTK loader, so the
original lazy chunk is not downloaded or initialized a second time.
"""
from functools import lru_cache
import hashlib
from importlib.metadata import version,distribution
from importlib.resources import files

from flask import Response

from .sky import SUN_DISPLAY_DISTANCE_M


_ANCHOR = 'r.subscriptions.push(r.renderer.onEvent((function(e){var t=e.type;'
_CLIP = """/* solar-sky-depth */if(t==="ResetCameraClippingRangeEvent"){
 var camera=r.renderer.getActiveCamera(),range=camera.getClippingRange();
 camera.setClippingRange(range[0],Math.max(range[1],__SKY_FAR__));
}""".replace("__SKY_FAR__", str(2 * SUN_DISPLAY_DISTANCE_M))


@lru_cache(maxsize=1)
def sky_bundle():
    source = files("dash_vtk").joinpath("async-ReactVTK.js").read_text(encoding="utf-8")
    if version("dash-vtk") != "0.0.9" or source.count(_ANCHOR) != 1:
        raise RuntimeError("Review the sky clipping adapter before changing Dash VTK.")
    return source.replace(_ANCHOR, _ANCHOR + _CLIP).encode("utf-8")


# Immutable, content-addressed URL: existing browser caches cannot retain a
# different camera adapter after an update, even if the package pin is unchanged.
SKY_BUNDLE_URL = "/_solar-vtk/" + hashlib.sha256(sky_bundle()).hexdigest()[:16] + ".js"


def install_sky_bundle(server):
    # Validate once at startup, rather than during a visitor's scene request.
    data = sky_bundle()

    def serve():
        response = Response(data, mimetype="application/javascript")
        response.cache_control.public = True
        response.cache_control.max_age = 31536000
        return response

    server.add_url_rule(SKY_BUNDLE_URL, "solar_vtk_sky", serve)

    def license_notice():
        return Response(distribution("dash-vtk").read_text("LICENSE"), mimetype="text/plain")

    server.add_url_rule("/_solar-vtk/async-ReactVTK.js.LICENSE.txt",
        "solar_vtk_sky_license", license_notice)
