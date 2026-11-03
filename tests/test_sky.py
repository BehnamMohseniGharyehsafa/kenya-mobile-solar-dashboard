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


def test_world_lighting_tracks_sun_and_dims_for_cloud_and_night():
    from solar_model.sky import world_lighting
    east=world_lighting(30,90)
    west=world_lighting(30,270)
    assert east['position'][0]>0 and west['position'][0]<0
    assert np.linalg.norm(east['position'])==pytest.approx(100)
    assert world_lighting(30,90,90)['intensity']<east['intensity']
    night=world_lighting(-20,90)
    assert night['intensity']<east['intensity'] and night['fill']<east['fill']
    assert night['color'][2]>night['color'][0]
    assert world_lighting(6,90)['color'][2]<east['color'][2]


@pytest.mark.skipif(shutil.which('node') is None,reason='Node checks the browser lighting adapter')
def test_browser_world_lights_update_without_reallocating_or_following_camera():
    from solar_model.vtk_sky import _LIGHT
    script="""
const assert=require('node:assert/strict');
let data={position:[80,0,60],color:[1,.96,.88],intensity:1,fill:.38};
const node={getAttribute:()=>JSON.stringify(data)};
const document={getElementById:()=>node};
let created=0,cleared=0;
const lights=[];
const r={renderer:{removeAllLights:()=>{cleared++;},makeLight:()=>{
 created++; const l={};
 l.setLightTypeToSceneLight=()=>{l.world=true;};
 l.setFocalPoint=(...v)=>{l.focus=v;};l.setPositional=v=>{l.positional=v;};
 l.setPosition=(...v)=>{l.position=v;};l.setColor=(...v)=>{l.color=v;};
 l.setIntensity=v=>{l.intensity=v;};return l;
},addLight:l=>lights.push(l)}};
function update(){
"""+_LIGHT+"""
}
update();update();
assert.equal(created,2);assert.equal(cleared,1);
assert.equal(lights[0].world,true);assert.equal(lights[0].positional,false);
assert.deepEqual(lights[0].position,[80,0,60]);
data={position:[-80,0,60],color:[.54,.65,.82],intensity:.18,fill:.16};
update();
assert.equal(created,2);assert.deepEqual(lights[0].position,[-80,0,60]);
assert.equal(lights[0].intensity,.18);assert.equal(lights[1].intensity,.16);
"""
    result=subprocess.run([shutil.which('node'),'-e',script],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
