"""Solar marker fidelity and camera framing regressions."""
import numpy as np
import pandas as pd
import pytest
import shutil
import subprocess

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
        assert np.linalg.norm(position) > 1000
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


def test_sky_chunk_is_preloaded_once_without_allocating_a_scene():
    from solar_model.viewer_service import ViewerService
    from solar_model.vtk_sky import SKY_BUNDLE_URL
    service = ViewerService(start_server=False)
    try:
        client = service.app.server.test_client()
        response = client.get(SKY_BUNDLE_URL)
        assert response.status_code == 200
        assert response.mimetype == "application/javascript"
        assert response.cache_control.max_age == 31536000
        assert response.text.count("/* solar-sky-depth */") == 1
        assert client.get("/_solar-vtk/async-ReactVTK.js.LICENSE.txt").status_code == 200
        index = client.get("/").text
        assert index.count('src="' + SKY_BUNDLE_URL + '"') == 1
        assert index.index(SKY_BUNDLE_URL) < index.index('/_dash-component-suites/dash_vtk/')
        assert not service.sessions
    finally:
        service.close()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node validates the renderer camera adapter")
def test_camera_depth_event_preserves_near_plane_and_handles_repeated_resets():
    from solar_model.vtk_sky import _CLIP, sky_bundle
    syntax = subprocess.run([shutil.which("node"), "--check"], input=sky_bundle().decode("utf-8"),
        capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert syntax.returncode == 0, syntax.stdout + syntax.stderr
    script = """
const assert=require('node:assert/strict');
let range=[5,150];
const camera={getClippingRange:()=>range,setClippingRange:(a,b)=>{range=[a,b];}};
const r={renderer:Object.freeze({getActiveCamera:()=>camera})};
const onEvent=function(e){var t=e.type;
""" + _CLIP + """};
onEvent({type:'ComputeVisiblePropBoundsEvent'});
assert.deepEqual(range,[5,150]);
onEvent({type:'ResetCameraClippingRangeEvent'});
assert.deepEqual(range,[5,20000]);
range=[.01,35]; onEvent({type:'ResetCameraClippingRangeEvent'});
assert.deepEqual(range,[.01,20000]);
range=[500,50000]; onEvent({type:'ResetCameraClippingRangeEvent'});
assert.deepEqual(range,[500,50000]);
"""
    result = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
