import numpy as np
import pandas as pd
import pytest

from solar_model.config import Config
from solar_model.field_controller import FieldController
from solar_model.mechanics import hatch_angle, module_poses, phase
from tests.weather_fixture import forecast_fixture


@pytest.mark.parametrize("tool,action",[("Orbit","Rotate"),("Pan","Pan"),("Zoom","Zoom")])
def test_interaction_tools_bind_left_drag_and_keep_wheel_zoom(tool,action):
    from solar_model.field_view import interaction_settings
    settings=interaction_settings(tool)
    assert settings[0]=={"button":1,"action":action}
    assert any(s.get("scrollEnabled") and s["action"]=="Zoom" and s["button"]==3 for s in settings)


@pytest.mark.parametrize("progress,angle",[(0,0),(.06,54),(.12,108),(.5,108),(.84,108),(.92,54),(1,0)])
def test_roof_opens_for_extraction_and_closes_after_installation(progress,angle):
    assert hatch_angle(progress)==pytest.approx(angle)


def test_panels_stay_clear_while_roof_closes_and_reopens():
    c=Config()
    installed=np.concatenate([p.vertices for p in module_poses(c,1,25,90)])
    for progress in np.linspace(.84,1,15):
        vertices=np.concatenate([p.vertices for p in module_poses(c,progress,25,90)])
        assert vertices==pytest.approx(installed)
        assert np.abs(vertices[:,1]).min()>c.dimensions[1]/2
    assert phase(.9)=="CLOSE ROOF HATCHES"


def test_hold_reverse_and_roof_closed_generation_interlock():
    wall=[0.]
    c=FieldController(Config(),monotonic=lambda:wall[0])
    frame,meta=forecast_fixture()
    c.set_feed(frame,meta)
    noon=frame.index[36]
    c.set_mode("Manual sun study",noon)
    c.manual=noon
    c.step_plant(noon)
    c.weather["gust_ms"]=0
    assert c.command(1)
    wall[0]=2
    c.step_motion()
    assert c.progress==pytest.approx(1/3)
    c.hold()
    wall[0]=5
    c.step_motion()
    assert c.progress==pytest.approx(1/3)
    c.hold()
    wall[0]=8.8
    c.step_motion()
    assert .84<c.progress<1
    c.step_plant(noon)
    assert c.model["pv_dc_kw"]==0  # Closing roof is still part of installation.
    wall[0]=10
    c.step_motion()
    c.step_plant(noon)
    assert c.deployed and hatch_angle(c.progress)==0
    assert c.model["pv_dc_kw"]>0
    assert c.command(0)
    wall[0]=10.6
    c.step_motion()
    assert c.progress==pytest.approx(.9)
    assert hatch_angle(c.progress)>0
    c.step_plant(noon)
    assert c.model["pv_dc_kw"]==0
    wall[0]=17
    c.step_motion()
    assert c.progress==0 and hatch_angle(c.progress)==0


def test_unknown_weather_inhibits_new_deployment():
    c=FieldController(Config())
    assert not c.command(1)
    assert c.target==0


def test_viewer_service_is_loopback_only_and_stops(monkeypatch):
    import time
    from dash import html
    import requests
    import solar_model.viewer_service as viewer_service
    from solar_model.viewer_service import ViewerService

    class StubView:
        def __init__(self,*args):
            self.last_used=time.monotonic()

        def layout(self,session):
            return html.Div("Viewer service integration check")

        def close(self):
            pass

    monkeypatch.setattr(viewer_service,"FieldView",StubView)
    service=ViewerService()
    try:
        url=service.register(Config(),"Europe/Dublin")
        assert url.startswith("http://127.0.0.1:")
        assert service.register(Config(),"Europe/Dublin")==url
        response=requests.get(url,timeout=10)
        response.raise_for_status()
        assert "Kenya" in response.text
        assert service.server.server_address[0]=="127.0.0.1"
        assert service.app._callback_list[0]["running"]["running"]=={"tick.disabled":True}
        assert service.app._callback_list[0]["running"]["runningOff"]=={"tick.disabled":False}
    finally:
        service.close()
        service.thread.join(timeout=5)
    assert not service.thread.is_alive()
