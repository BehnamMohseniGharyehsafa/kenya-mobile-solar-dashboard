"""Display-scale sky geometry; astronomical angles remain in live_simulation.

The scene uses metres, so a finite distant marker represents the solar disc.
Its direction is the site's east/north/up vector, with no artificial elevation
offset. This drawing distance is not an estimate of the Earth--Sun distance.
"""
import numpy as np
import pyvista as pv

from .mechanics import sun_vector


# Keep the proxy beyond the compound but inside vtk.js's automatically fitted
# depth range. An astronomical-distance mesh would be clipped by the camera.
SUN_DISPLAY_DISTANCE_M = 60.0
SUN_ANGULAR_DIAMETER_DEG = 0.533
SUN_DISPLAY_RADIUS_M = SUN_DISPLAY_DISTANCE_M * np.sin(np.radians(SUN_ANGULAR_DIAMETER_DEG / 2))


def sun_display_position(elevation, azimuth):
    return SUN_DISPLAY_DISTANCE_M * sun_vector(elevation, azimuth)


def add_sun(plotter, elevation, azimuth):
    actor = plotter.add_mesh(pv.Sphere(radius=SUN_DISPLAY_RADIUS_M,
        theta_resolution=16, phi_resolution=12), color="#ffe4a0", lighting=False,
        name="sky-sun", pickable=False)
    actor.position = sun_display_position(elevation, azimuth)
    actor.visibility = elevation > 0
    actor.SetUseBounds(False)
    return actor
