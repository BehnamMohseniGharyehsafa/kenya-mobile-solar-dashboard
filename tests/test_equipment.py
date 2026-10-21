import json
import time
from unittest.mock import patch

from dash import no_update
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
        view.fan_running=True
        view.fan_last=100.
        points=view.scene.fan_actor.mapper.dataset.points.copy()
        with patch.object(view.controller,"step_plant",side_effect=AssertionError("Fan invoked physics")):
            first=view.fan_frame(100.1)
            second=view.fan_frame(100.2)
        assert first!=second and len(to_json(second))<600
        assert set(second)=={"userMatrix","useBounds"}
        assert np.array_equal(view.scene.fan_actor.mapper.dataset.points,points)
        centre=np.r_[fan_centre(view.config),1]
        matrix=np.array(second["userMatrix"]).reshape(4,4,order="F")
        assert matrix@centre==pytest.approx(centre)
        assert matrix[:3,:3].T@matrix[:3,:3]==pytest.approx(np.eye(3))
        view.fan_running=False
        assert view.fan_frame(100.3) is no_update
    finally:
        view.close()


def test_display_updates_only_small_color_array_and_button_picks_are_explicit():
    view=FieldView(Config(),feed=forecast_fixture())
    try:
        view.step("tick","Live site clock",None,600,6,["landscape","shadows"],"power")
        updates=view.take_instrument_changes()
        assert "hmi-pv" in updates and "fan-tick" in updates
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


def test_fan_http_callback_is_a_small_transform_not_a_plant_update():
    from solar_model.viewer_service import ViewerService
    class View:
        def fan_frame(self):
            return {"userMatrix":rotor_matrix((3.6,-.5,1.31),20),"useBounds":False}
        def close(self):
            pass
    service=ViewerService(start_server=False)
    service.sessions["fan-test"]=View()
    try:
        callback=next(key for key in service.app.callback_map if "fan-rotor.actor" in key)
        response=service.app.server.test_client().post("/_dash-update-component",json={
            "output":callback,"outputs":[{"id":"fan-rotor","property":"actor"},{"id":"vtk","property":"triggerRender"}],
            "inputs":[{"id":"fan-tick","property":"n_intervals","value":1}],
            "state":[{"id":"session","property":"data","value":"fan-test"}],"changedPropIds":["fan-tick.n_intervals"]})
        assert response.status_code==200,response.text
        assert len(response.data)<700
        assert set(response.get_json()["response"])=={"fan-rotor","vtk"}
        assert "points" not in response.text and "children" not in response.text
    finally:
        service.close()
