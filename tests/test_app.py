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
    from PIL import Image
    from io import BytesIO
    from tests.weather_fixture import forecast_fixture
    png=BytesIO()
    Image.new("RGB",(8,8),(30,60,60)).save(png,format="PNG")
    monkeypatch.setattr(live_ui,"rendered_view",lambda *a,**kw:png.getvalue())
    monkeypatch.setattr(live_ui,"weather_feed",lambda *a,**kw:forecast_fixture())
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert any("Mobile solar lab" in x.value for x in app.title)
    assert len(app.metric) >= 4
    # A single command starts deployment; elapsed wall time completes it.
    app.button(key="field_deploy").click().run()
    assert not app.exception
    assert app.session_state.field_session["target"]==1
    session=app.session_state.field_session
    session["mechanical_last"]-=25
    app.run()
    assert not app.exception
    assert app.session_state.field_session["progress"]==1
    app.button(key="field_retract").click().run()
    assert not app.exception
    assert app.session_state.field_session["target"]==0
    session=app.session_state.field_session
    session["mechanical_last"]-=25
    app.run()
    assert not app.exception
    assert app.session_state.field_session["progress"]==0
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
