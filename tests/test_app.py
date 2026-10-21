from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_pages_and_controls(monkeypatch):
    # UI integration needs a representative weather window; full-year physics
    # and scenarios are validated separately by the model checks/script.
    import solar_model.weather as weather
    original = weather.load_bundled
    monkeypatch.setattr(weather, "load_bundled", lambda c: (original(c)[0].iloc[:168], original(c)[1]))
    import solar_model.live_ui as live_ui
    monkeypatch.setattr(live_ui,"workspace_url",lambda *a,**kw:"http://127.0.0.1:9999/")
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert any("Mobile solar lab" in x.value for x in app.title)
    for page in ["Overview", "Sun & tracking", "Storage & cooling", "Controls & faults", "Container design", "Literature & model", "Data & export"]:
        app.selectbox(key="main_page").set_value(page).run()
        assert not app.exception, f"Page failed: {page}"
    # Applied form values should reach the actual model and survive navigation.
    for select in app.selectbox:
        if select.label == "Array orientation":
            select.set_value("Dual axis")
    for button in app.button:
        if button.label == "Apply design & simulate":
            button.click()
            break
    app.run()
    assert not app.exception
    assert app.session_state.design.tracking == "Dual axis"


def test_persistent_field_view_controls_and_camera():
    import json
    from dash._utils import to_json
    from solar_model.field_view import FieldView
    from solar_model.config import Config
    from tests.weather_fixture import forecast_fixture
    view=FieldView(Config(),feed=forecast_fixture())
    try:
        layout=view.layout('integration-session')
        assert 'cameraPosition' in to_json(layout)
        window=view.scene.plotter.ren_win
        assert view.scene.module_mesh.n_points==36*view.scene.module_template.n_points
        assert len(view.scene.modules)==1  # One browser draw call contains every panel.
        assert len(view.dynamic_indices)==6
        assert not view.scene.sun.GetUseBounds()
        assert not view.scene.shadow_actor.GetUseBounds()
        view.controller.weather={'gust_ms':0}
        result=view.step('deploy','Live site clock',None,600,6,['shadows','landscape'],'power')
        assert view.controller.target==1
        view.controller.last_motion-=7
        result=view.step('tick','Live site clock',None,600,6,['shadows','landscape'],'power')
        assert view.controller.deployed
        assert '100% deployed' in result[1]
        assert 'Roof 0.0' in result[7]
        assert window is view.scene.plotter.ren_win
        patch=to_json(result[0])
        assert 'cameraPosition' not in patch and 'triggerResetCamera' not in patch
        assert 'userMatrix' in patch
        assert 'polys' not in patch and 'rgb' not in patch
        view.step('retract','Live site clock',None,600,6,['shadows','landscape'],'power')
        view.controller.last_motion-=7
        view.step('tick','Live site clock',None,600,6,['shadows','landscape'],'power')
        assert view.controller.progress==0
        assert view.controller.snapshot()['hatch_angle_deg']==0
    finally:
        view.close()
