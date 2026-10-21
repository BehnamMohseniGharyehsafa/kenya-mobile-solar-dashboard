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


def test_animation_http_response_updates_buffers_without_scene_children(monkeypatch):
    """Exercise Dash's actual wildcard-output serialization, not just Python state."""
    import time
    from dash import no_update, html
    import solar_model.viewer_service as viewer_service
    from solar_model.field_view import SceneUpdate

    class StubView:
        def __init__(self,*args):
            self.last_used=time.monotonic()
            self.interval_ms=50

        def layout(self,session):
            return html.Div('Callback transport check')

        def step(self,*args):
            scene=SceneUpdate(no_update,[[1.,2.,3.]]+[no_update]*7,[no_update]*8,123.)
            return scene,'DEPLOYING',25.,*(no_update,)*11

        def close(self):
            pass

    monkeypatch.setattr(viewer_service,'FieldView',StubView)
    service=viewer_service.ViewerService()
    service.sessions['transport-test']=StubView()
    try:
        key=next(iter(service.app.callback_map))
        callback=service.app.callback_map[key]
        outputs=[]
        for output in callback['output']:
            if isinstance(output.component_id,dict):
                outputs.append([{'id':{'type':output.component_id['type'],'slot':i},
                    'property':output.component_property} for i in range(8)])
            else:
                outputs.append({'id':output.component_id,'property':output.component_property})
        values=[1,1,0,0,0,'Live site clock','2026-10-21 12:00',600,6,['shadows','landscape'],'power']
        inputs=[{**item,'value':value} for item,value in zip(callback['inputs'],values)]
        client=service.app.server.test_client()
        response=client.post('/_dash-update-component',json={'output':key,'outputs':outputs,
            'inputs':inputs,'state':[{'id':'session','property':'data','value':'transport-test'}],
            'changedPropIds':['deploy.n_clicks']})
        assert response.status_code==200, response.text
        result=response.get_json()['response']
        assert result['vtk']=={'triggerRender':123.}
        assert result['tick']=={'interval':50}
        assert 'children' not in result['vtk']
        moving=[v for k,v in result.items() if 'moving-mesh' in k]
        assert moving==[{'points':[1.,2.,3.]}]
        assert len(response.data)<1000
    finally:
        service.close()
