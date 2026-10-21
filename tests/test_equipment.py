import json
from pathlib import Path
import shutil
import subprocess

from dash._utils import to_json
import numpy as np
import pytest

from solar_model.config import Config
from solar_model.equipment import cooling_rpm,display_lines,display_colors,fan_centre,rotor_matrix
from solar_model.field_controller import FieldController
from solar_model.field_view import FieldView
from tests.weather_fixture import forecast_fixture


def test_emergency_stop_freezes_motion_and_reset_does_not_restart():
    wall=[0.]
    c=FieldController(Config(),monotonic=lambda:wall[0])
    c.set_feed(*forecast_fixture())
    noon=c.frame.index[36]
    c.set_mode("Manual sun study",noon)
    c.manual=noon
    c.step_plant(noon)
    assert c.start_or_reset()
    wall[0]=3
    c.step_motion()
    assert c.progress==pytest.approx(.5)
    c.emergency_stop()
    stopped=c.progress
    wall[0]=12
    c.step_motion()
    assert c.progress==stopped and not c.moving
    assert not c.command(0) and not c.command(1)
    assert not c.start_or_reset()  # Reset only, with no automatic restart.
    wall[0]=20
    c.step_motion()
    assert c.progress==stopped and c.restart_required
    assert c.start_or_reset()
    wall[0]=23
    c.step_motion()
    assert c.deployed and c.pv_connected


def test_installed_stop_isolates_pv_freezes_tracking_and_preserves_cooling():
    c=FieldController(Config())
    frame,meta=forecast_fixture()
    frame.temp_air=36.
    c.set_feed(frame,meta)
    noon=frame.index[36]
    c.set_mode("Manual sun study",noon)
    c.manual=noon
    c.progress=c.target=1.
    c.step_plant(noon)
    before=c.model
    assert before["pv_dc_kw"]>0 and before["cooling_kw"]>0
    c.emergency_stop()
    c.manual=noon.replace(hour=14)
    c.step_plant(noon)
    assert c.deployed and not c.pv_connected
    assert c.model["pv_dc_kw"]==0 and c.model["tracker_kw"]==0
    assert c.model["tilt"]==before["tilt"] and c.model["azimuth"]==before["azimuth"]
    assert c.model["cooling_kw"]>0 and abs(c.model["dc_balance_residual_kw"])<1e-9
    assert c.snapshot()["operator"]["emergency_stop"]
    assert not c.start_or_reset()
    c.step_plant(noon)
    assert c.model["pv_dc_kw"]==0 and c.model["state"]=="RESTART REQUIRED"
    assert c.start_or_reset()
    c.step_plant(noon)
    assert c.pv_connected and c.model["pv_dc_kw"]>0


def test_rotor_is_one_rigid_transform_with_no_physics_or_mesh_rebuild():
    view=FieldView(Config(),feed=forecast_fixture())
    try:
        points=view.scene.fan_actor.mapper.dataset.points.copy()
        first={"userMatrix":rotor_matrix(fan_centre(view.config),10),"useBounds":False}
        second={"userMatrix":rotor_matrix(fan_centre(view.config),20),"useBounds":False}
        assert first!=second and len(to_json(second))<600
        assert set(second)=={"userMatrix","useBounds"}
        assert np.array_equal(view.scene.fan_actor.mapper.dataset.points,points)
        centre=np.r_[fan_centre(view.config),1]
        matrix=np.array(second["userMatrix"]).reshape(4,4,order="F")
        assert matrix@centre==pytest.approx(centre)
        assert matrix[:3,:3].T@matrix[:3,:3]==pytest.approx(np.eye(3))
    finally:
        view.close()


def test_display_updates_only_small_color_array_and_button_picks_are_explicit():
    view=FieldView(Config(),feed=forecast_fixture())
    try:
        view.step("tick","Live site clock",None,600,6,["landscape","shadows"],"power")
        updates=view.take_instrument_changes()
        assert "hmi-pv" in updates and "fan-command" in updates
        assert len(to_json(updates["fan-command"]))<160
        assert len(to_json(updates.get("hmi-segments",{})))<1500
        assert view.scene.display_actor.mapper.dataset.n_cells==160
        assert FieldView.pick_action({"representationId":"world-stop"})=="panel-stop"
        assert FieldView.pick_action({"representationId":"world-panel"})=="inspect"
        assert FieldView.pick_action({"representationId":"world-panel","worldPosition":[3.2,.36,1.42]})=="panel-start"
        assert FieldView.pick_action({"representationId":"world-panel","worldPosition":[3.2,.88,1.37]})=="panel-stop"
        assert FieldView.pick_action({"representationId":"part-0"})=="pick"
        view.update_instruments()
        assert not view.take_instrument_changes()  # Identical labels are not resent.
        encoded=to_json(view.layout("hmi-test"))
        assert "hmi-start" in encoded and "pickingModes" in encoded and "fan-rotor" in encoded
        assert "camera-bounds" in encoded
        assert "fan-tick" not in encoded
    finally:
        view.close()


def test_fan_indication_requires_delivered_cooling_and_unknown_values_are_visible():
    assert cooling_rpm({"cooling_state":"COMPRESSOR","cooling_kw":1.2})==900
    assert cooling_rpm({"cooling_state":"FREE COOLING","cooling_kw":.2})==600
    assert cooling_rpm({"cooling_state":"COMPRESSOR","cooling_kw":0})==0
    assert cooling_rpm({"cooling_state":"FAULT","cooling_kw":1.2})==0
    lines=display_lines({"pv_dc_kw":None,"soc":.5},0)
    assert lines[0]=="-----" and lines[2]=="-----"
    assert display_colors(lines).shape==(160,3)


def test_fan_animation_is_local_and_asset_is_served_without_a_session():
    from solar_model.viewer_service import ViewerService
    service=ViewerService(start_server=False)
    try:
        dependencies=service.app.server.test_client().get("/_dash-dependencies").get_json()
        callback=next(item for item in dependencies if item["output"]=="fan-runtime.data")
        assert callback["clientside_function"]=={"namespace":"pv_fan","function_name":"configure"}
        assert callback["inputs"]==[{"id":"fan-command","property":"data"}]
        assert not any("fan-rotor.actor" in key for key in service.app.callback_map)
        response=service.app.server.test_client().get("/assets/fan_animation.js")
        assert response.status_code==200,response.text
        assert "requestAnimationFrame" in response.text and "fetch(" not in response.text
        assert not service.sessions
    finally:
        service.close()


@pytest.mark.skipif(shutil.which("node") is None,reason="Node is only needed for browser-helper tests")
def test_browser_fan_timing_and_lifecycle():
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([shutil.which("node"),"--test","tests/fan_animation.test.cjs"],
        cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
