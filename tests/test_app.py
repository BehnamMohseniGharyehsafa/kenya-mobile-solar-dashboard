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
        patch=to_json(result[0].to_dict())
        from dash import no_update
        assert result[0].children is no_update  # Never walk/redraw static actors on a motion tick.
        assert len(result[0].points)==8
        assert 'cameraPosition' not in patch and 'triggerResetCamera' not in patch
        assert 'userMatrix' in patch
        assert 'polys' not in patch and 'rgb' not in patch
        # A detail-tab click must not wait for an unnecessary plant solve.
        from unittest.mock import patch as mock_patch
        import time
        view.last_physics=time.monotonic()
        with mock_patch.object(view.controller,'step_plant',side_effect=AssertionError('Unnecessary solve on tab click')):
            detail=view.step('detail-tab','Live site clock',None,600,6,['shadows','landscape'],'mechanism')
        assert 'Roof hatches' in detail[6]
        assert detail[0].children is no_update
        assert all(p is no_update for p in detail[0].points)
        assert detail[0].render is no_update
        assert view.interval_ms==1000
        view.step('retract','Live site clock',None,600,6,['shadows','landscape'],'power')
        assert view.interval_ms==50
        view.controller.last_motion-=7
        view.step('tick','Live site clock',None,600,6,['shadows','landscape'],'power')
        assert view.controller.progress==0
        assert view.controller.snapshot()['hatch_angle_deg']==0
        # While only the hatches move, panel coordinates remain browser-side.
        view.controller.weather={'gust_ms':0}
        view.step('deploy','Live site clock',None,600,6,['shadows','landscape'],'power')
        view.controller.last_motion-=.3
        opening=view.step('tick','Live site clock',None,600,6,['shadows','landscape'],'power')
        module_slot=view.stream_slots[view.dynamic_indices[0]]
        assert opening[0].points[module_slot] is no_update
        assert any(p is not no_update for p in opening[0].points)
        # Repeated cutaway/landscape toggles reuse the renderer and resident
        # meshes. Only actor visibility may cross the wire for these controls.
        view.controller.held=True
        view.scene.update(view.controller.progress,view.controller.model['tilt'],
            view.controller.model['azimuth'],view.controller.model['sun_elevation'],
            view.controller.model['sun_azimuth'],view.controller.weather['cloud_pct'])
        for options in (['shadows','cutaway'],['shadows','landscape'],['shadows','cutaway']):
            view.last_physics=time.monotonic()
            result=view.step('options','Live site clock',None,600,6,options,'power')
            assert view.scene.plotter.ren_win is window
            assert result[0].children is no_update
            assert all(p is no_update for p in result[0].points)
            assert any(a is not no_update for a in result[0].actors)
            assert all(a.visibility==('landscape' in options) for a in view.scene.landscape_actors)
            assert all(a.visibility==('cutaway' not in options) for a in view.scene.cover_actors)
    finally:
        view.close()
