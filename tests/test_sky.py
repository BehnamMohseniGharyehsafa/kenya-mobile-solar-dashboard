"""Solar marker fidelity and camera framing regressions."""
import numpy as np
import pandas as pd
import pytest

from solar_model.config import Config
from solar_model.live_simulation import solar_position
from solar_model.sky import sun_display_position, SUN_DISPLAY_DISTANCE_M, SUN_DISPLAY_RADIUS_M


def test_nairobi_clock_drives_distant_sun_without_a_false_height_offset():
    c = Config()
    for hour in (7, 12, 18):
        sun = solar_position(c, pd.Timestamp(f"2026-10-21 {hour:02d}:00", tz=c.timezone))
        position = sun_display_position(sun.apparent_elevation, sun.azimuth)
        assert np.linalg.norm(position) == pytest.approx(SUN_DISPLAY_DISTANCE_M)
        assert np.degrees(np.arcsin(position[2] / np.linalg.norm(position))) == pytest.approx(sun.apparent_elevation)
        assert np.degrees(np.arctan2(position[0], position[1])) % 360 == pytest.approx(sun.azimuth)
        # Outside the fenced installation, rather than a nearby fence lamp.
        assert np.linalg.norm(position) > 50
    assert sun_display_position(0, 90)[2] == pytest.approx(0)
    assert sun_display_position(90, 0)[2] == pytest.approx(SUN_DISPLAY_DISTANCE_M)
    assert np.degrees(2 * np.arcsin(SUN_DISPLAY_RADIUS_M / SUN_DISPLAY_DISTANCE_M)) == pytest.approx(0.533)


def test_live_and_export_sun_agree_without_changing_camera_fit():
    from solar_model.interactive_scene import InteractiveScene
    from solar_model.scene import build_plotter
    c = Config()
    scene = InteractiveScene(c)
    exported = build_plotter(c, 1, 15, 270, 8, 260, landscape=False)
    try:
        initial_bounds = tuple(scene.plotter.bounds)
        scene.update(1, 15, 270, 8, 260)
        assert scene.sun.position == pytest.approx(exported.renderer.actors["sky-sun"].position)
        assert not scene.sun.GetUseBounds()
        assert not scene.sun.GetPickable()
        assert scene.sun.visibility
        scene.update(1, 15, 270, 80, 60)
        assert tuple(scene.plotter.bounds) == pytest.approx(initial_bounds)
        scene.update(1, 15, 270, -2, 270)
        assert not scene.sun.visibility
    finally:
        scene.close()
        exported.close()
