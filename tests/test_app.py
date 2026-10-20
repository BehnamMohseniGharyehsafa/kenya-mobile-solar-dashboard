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
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert any("Mobile solar lab" in x.value for x in app.title)
    assert len(app.metric) >= 4
    for page in ["Sun & tracking", "Storage & cooling", "Controls & faults", "Container design", "Literature & model", "Data & export"]:
        app.radio[0].set_value(page).run()
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
