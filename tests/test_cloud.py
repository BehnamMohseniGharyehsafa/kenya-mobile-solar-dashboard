"""Public routing, independent sessions and owner-only hosting controls."""
import time

from dash import html
import pytest

from cloud_app import create_app
import solar_model.viewer_service as viewer_module
from tools.render_service import manage, SERVICE_NAME


@pytest.fixture
def cloud(monkeypatch):
    class View:
        def __init__(self,*settings):
            self.settings=settings
            self.last_used=time.monotonic()
            self.closed=False

        def layout(self,session):
            return html.Div([html.H2(self.public_title),html.Div(session,id="session-id")])

        def close(self):
            self.closed=True

    monkeypatch.setattr(viewer_module,"FieldView",View)
    app=create_app()
    yield app,app.extensions["field_viewer"]
    app.extensions["field_viewer"].close()


def test_public_page_assets_and_health_do_not_allocate_scenes(cloud):
    app,service=cloud
    client=app.test_client()
    assert service.thread is None and service.port is None
    assert client.get("/healthz").get_json()["status"]=="ok"
    page=client.get("/")
    assert page.status_code==200 and b"BehnamProject-PVforAfrica" in page.data
    assert b"127.0.0.1" not in page.data
    assert client.get("/_dash-dependencies").status_code==200
    assert not service.sessions


def test_public_layout_loads_nairobi_and_bounds_active_sessions(cloud):
    app,service=cloud
    client=app.test_client()
    first=client.get("/_dash-layout")
    assert first.status_code==200 and b"BehnamProject-PVforAfrica" in first.data
    view=next(iter(service.sessions.values()))
    assert view.settings[0].site=="Nairobi"
    assert view.settings[1]=="Africa/Nairobi"
    assert b"currently full" in client.get("/_dash-layout").data
    assert not view.closed and len(service.sessions)==1
    view.last_used-=181
    assert b"session-id" in client.get("/_dash-layout").data
    assert view.closed and len(service.sessions)==1


class Response:
    def __init__(self,data):
        self.data=data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class RenderAPI:
    def __init__(self,name=SERVICE_NAME):
        self.data={"name":name,"suspended":"not_suspended", "serviceDetails":{
            "url":"https://example.onrender.com"}}
        self.posts=[]

    def get(self,*args,**kwargs):
        return Response(self.data.copy())

    def post(self,url,**kwargs):
        self.posts.append(url)
        self.data["suspended"]="suspended" if url.endswith("/suspend") else "not_suspended"
        return Response({})


def test_owner_can_switch_service_off_and_on():
    api=RenderAPI()
    assert manage("off","srv-example","secret",api)["suspended"]=="suspended"
    assert manage("on","srv-example","secret",api)["suspended"]=="not_suspended"
    assert api.posts==["https://api.render.com/v1/services/srv-example/suspend",
        "https://api.render.com/v1/services/srv-example/resume"]
    assert "secret" not in str(manage("status","srv-example","secret",api))


def test_control_rejects_other_services_and_invalid_ids():
    api=RenderAPI("someone-elses-service")
    with pytest.raises(ValueError,match="different service"):
        manage("off","srv-example","secret",api)
    with pytest.raises(ValueError,match="service ID"):
        manage("off","../owners","secret",api)
    assert not api.posts
