"""Narrow compatibility adapter for the pinned Dash VTK 0.0.9 camera.

Dash VTK does not expose a clipping-range property. Preload its existing lazy
chunk with its public vtkRenderer depth-reset event used to preserve the fitted near
plane while allowing the sky proxy beyond the installation. No package files,
extra rendering library or frame loop are modified/added. The render hook uses
public vtkRenderer/vtkLight APIs to match the browser's lighting to the model sun.
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

_RENDER_ANCHOR = 'r.renderView=function(){r.updateCubeBounds(),r.renderWindow.render()}'
_LIGHT = """/* solar-world-light */
var node=document.getElementById("scene-environment");
if(node){
 var signature=node.getAttribute("data-light");
 if(signature&&signature!==r.solarLightSignature){
  var light=JSON.parse(signature);
  if(!r.solarLights){
   r.renderer.removeAllLights();
   r.solarLights=[r.renderer.makeLight(),r.renderer.makeLight()];
   r.solarLights.forEach(function(l){l.setLightTypeToSceneLight();l.setFocalPoint(0,0,0);l.setPositional(false);r.renderer.addLight(l);});
  }
  r.solarLights[0].setPosition.apply(null,light.position);
  r.solarLights[0].setColor.apply(null,light.color);
  r.solarLights[0].setIntensity(light.intensity);
  r.solarLights[1].setPosition(-35,-25,50);
  r.solarLights[1].setColor(.73,.84,.92);
  r.solarLights[1].setIntensity(light.fill);
  r.solarLightSignature=signature;
 }
}
"""


@lru_cache(maxsize=1)
def sky_bundle():
    source = files("dash_vtk").joinpath("async-ReactVTK.js").read_text(encoding="utf-8")
    if version("dash-vtk") != "0.0.9" or source.count(_ANCHOR) != 1 or source.count(_RENDER_ANCHOR) != 1:
        raise RuntimeError("Review the sky clipping adapter before changing Dash VTK.")
    source=source.replace(_ANCHOR, _ANCHOR + _CLIP)
    return source.replace(_RENDER_ANCHOR,
        'r.renderView=function(){'+_LIGHT+'r.updateCubeBounds();r.renderWindow.render()}').encode("utf-8")


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
