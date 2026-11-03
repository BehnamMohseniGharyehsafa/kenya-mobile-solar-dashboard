"""Display-scale sky geometry; astronomical angles remain in live_simulation.

The scene uses metres, so a finite distant marker represents the solar disc.
Its direction is the site's east/north/up vector, with no artificial elevation
offset. This drawing distance is not an estimate of the Earth--Sun distance.
"""
import numpy as np
import pyvista as pv

from .mechanics import sun_vector


# A 10 km drawing radius keeps camera parallax small. The renderer's camera
# adapter extends depth clipping independently of its installation-fit bounds.
SUN_DISPLAY_DISTANCE_M = 10000.0
SUN_ANGULAR_DIAMETER_DEG = 0.533
SUN_DISPLAY_RADIUS_M = SUN_DISPLAY_DISTANCE_M * np.sin(np.radians(SUN_ANGULAR_DIAMETER_DEG / 2))


def sun_display_position(elevation, azimuth):
    return SUN_DISPLAY_DISTANCE_M * sun_vector(elevation, azimuth)


def world_lighting(elevation,azimuth,cloud=0):
    """Shared world-space sun and cool sky fill for VTK and vtk.js."""
    night=elevation<=0
    warm=np.clip((18-elevation)/15,0,1)
    return {"position":(sun_vector(max(elevation,12),azimuth)*100).tolist(),
        "color":[.54,.65,.82] if night else [1.,.96-.16*float(warm),.88-.26*float(warm)],
        "intensity":.18 if night else max(.35,1.05-cloud*.006),
        "fill":.16 if night else .38}


def add_sun(plotter, elevation, azimuth):
    actor = plotter.add_mesh(pv.Sphere(radius=SUN_DISPLAY_RADIUS_M,
        theta_resolution=16, phi_resolution=12), color="#ffe4a0", lighting=False,
        name="sky-sun", pickable=False)
    actor.position = sun_display_position(elevation, azimuth)
    actor.visibility = elevation > 0
    actor.SetUseBounds(False)
    return actor
