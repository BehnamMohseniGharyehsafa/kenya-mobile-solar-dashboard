"""Exercise actual request boundaries, ownership and bounded work admission."""
import threading
import time

from dash import html
import pytest

from cloud_app import create_app
from solar_model.config import Config
from solar_model.cloud_security import Buckets,bounded_value
import solar_model.viewer_service as viewer_module


@pytest.fixture
def secured(monkeypatch):
    class View:
        def __init__(self,*args):
            self.config=Config()
            self.last_used=time.monotonic()
            self.closed=False
        def layout(self,sid):
            return html.Div(sid,id="session-id")
        def camera_bounds_actor(self,name):
            return {"useBounds":True}
        def close(self):
            self.closed=True
    monkeypatch.setattr(viewer_module,"FieldView",View)
    app=create_app()
    yield app,app.extensions["field_viewer"],app.extensions["cloud_guard"]
    app.extensions["field_viewer"].close()


def tool_body(value="Orbit"):
    return {"output":"vtk.interactorSettings","outputs":{"id":"vtk","property":"interactorSettings"},
        "inputs":[{"id":"tool","property":"value","value":value}],"state":[],"changedPropIds":["tool.value"]}


def camera_body(service,sid,name="Site overview"):
    key=next(key for key in service.app.callback_map if "camera-bounds.actor" in key)
    return {"output":key,"outputs":[{"id":"camera-bounds","property":"actor"},
        {"id":"vtk","property":"cameraPosition"},{"id":"vtk","property":"triggerResetCamera"}],
        "inputs":[{"id":"camera","property":"value","value":name},{"id":"reset-view","property":"n_clicks","value":1}],
        "state":[{"id":"session","property":"data","value":sid}],"changedPropIds":["camera.value"]}


def test_signed_browser_cookie_headers_and_host_validation(secured):
    app,service,guard=secured
    client=app.test_client()
    response=client.get("/",base_url="https://behnamproject-pvforafrica.onrender.com")
    cookie=response.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert response.headers["X-Frame-Options"]=="DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    scripts=next(x for x in response.headers["Content-Security-Policy"].split(";") if "script-src" in x)
    assert "sha256-" in scripts and "unsafe-inline" not in scripts
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    assert client.get("/",headers={"Host":"attacker.invalid"}).status_code==400
    assert not service.sessions


def test_no_cookie_cross_site_and_unknown_commands_are_rejected(secured):
    app,service,guard=secured
    client=app.test_client()
    assert client.post("/_dash-update-component",json=tool_body()).status_code==403
    client.get("/")
    assert client.post("/_dash-update-component",json=tool_body(),headers={"Origin":"https://attacker.invalid"}).status_code==403
    assert client.post("/_dash-update-component",json=tool_body(),headers={"Origin":"http://["}).status_code==403
    assert client.post("/_dash-update-component",json=tool_body(),headers={"Sec-Fetch-Site":"cross-site"}).status_code==403
    assert client.post("/_dash-update-component",json=tool_body(),headers={"Origin":"http://localhost"}).status_code==200
    body=tool_body(); body["output"]="unknown.callback"
    assert client.post("/_dash-update-component",json=body).status_code==400
    body=tool_body(); body["outputs"]["property"]="children"
    assert client.post("/_dash-update-component",json=body).status_code==400


@pytest.mark.parametrize("value",["<script>alert(1)</script>",{},[],None,float("nan"),float("inf"),10**1000])
def test_malformed_control_values_are_rejected_without_callback_execution(secured,value):
    app,service,guard=secured
    client=app.test_client(); client.get("/")
    assert client.post("/_dash-update-component",json=tool_body(value)).status_code==400
    assert not service.sessions


def test_large_json_and_content_types_are_bounded(secured):
    app,service,guard=secured
    client=app.test_client(); client.get("/")
    assert client.post("/_dash-update-component",data="x"*70000,content_type="application/json").status_code==413
    assert client.post("/_dash-update-component",data="tool=Orbit").status_code==415
    assert not bounded_value([[[[[[[1]]]]]]])


def test_other_browser_cannot_operate_or_export_a_session_and_reload_reuses_it(secured):
    app,service,guard=secured
    alice=app.test_client(); bob=app.test_client()
    first=alice.get("/_dash-layout").get_json()
    sid=first["props"]["children"]
    assert alice.get("/_dash-layout").get_json()==first
    bob.get("/_dash-layout")
    assert len(service.sessions)==2
    assert bob.post("/_dash-update-component",json=camera_body(service,sid)).status_code==403
    export={"output":"download.data","outputs":{"id":"download","property":"data"},
        "inputs":[{"id":"export","property":"n_clicks","value":1},{"id":"export-png","property":"n_clicks","value":0}],
        "state":[{"id":"session","property":"data","value":sid},{"id":"export-size","property":"value","value":"1080p"},
            {"id":"camera","property":"value","value":"Site overview"},{"id":"fan-rotor","property":"actor","value":{}}],
        "changedPropIds":["export.n_clicks"]}
    assert bob.post("/_dash-update-component",json=export).status_code==403
    assert alice.post("/_dash-update-component",json=camera_body(service,sid)).status_code==200
    assert alice.post("/_dash-update-component",json=camera_body(service,sid,"invalid-camera")).status_code==400
    assert len(set(service.owners.values()))==2


def test_work_saturation_rejects_instead_of_queuing_and_health_still_works(secured):
    app,service,guard=secured
    client=app.test_client(); client.get("/")
    assert guard.work.acquire(False) and guard.work.acquire(False)
    try:
        response=client.post("/_dash-update-component",json=tool_body())
        assert response.status_code==503 and response.headers.get("Retry-After")
        assert client.get("/healthz").status_code==200
    finally:
        guard.work.release(); guard.work.release()
    assert client.post("/_dash-update-component",json=tool_body()).status_code==200


def test_rate_limit_is_enforced_and_limiter_storage_is_bounded(secured):
    app,service,guard=secured
    guard.buckets.clock=lambda:0.
    client=app.test_client(); client.get("/")
    codes=[client.post("/_dash-update-component",json=tool_body()).status_code for _ in range(55)]
    assert codes.count(200)==50 and codes[-1]==429
    buckets=Buckets(clock=lambda:0.)
    for i in range(2500):
        buckets.allow(str(i),1,2)
    assert len(buckets.items)==2048


def test_cloud_image_resolution_cannot_be_escalated_by_forging_browser_state(secured):
    app,service,guard=secured
    client=app.test_client(); layout=client.get("/_dash-layout").get_json()
    sid=layout["props"]["children"]
    body={"output":"download.data","outputs":{"id":"download","property":"data"},
        "inputs":[{"id":"export","property":"n_clicks","value":0},{"id":"export-png","property":"n_clicks","value":1}],
        "state":[{"id":"session","property":"data","value":sid},{"id":"export-size","property":"value","value":"4K"},
            {"id":"camera","property":"value","value":"Site overview"},{"id":"fan-rotor","property":"actor","value":{}}],
        "changedPropIds":["export-png.n_clicks"]}
    assert client.post("/_dash-update-component",json=body).status_code==400
