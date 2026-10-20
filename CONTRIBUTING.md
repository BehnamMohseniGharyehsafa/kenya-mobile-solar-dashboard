# Working on the dashboard

Use Python 3.12 or newer; the reference runtime is Python 3.13. Create an isolated environment and install `requirements-dev.txt`.

```sh
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead:
# .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m streamlit run app.py
```

The application opens at http://127.0.0.1:8507. Cached weather permits development and testing without external API access.

Before submitting a change, run:

```sh
python -m pytest -q
```

For changes to the physics or control model, also regenerate the whole-year reference scenarios:

```sh
python tools/validate_model.py
```

Check the energy balances and update the assumptions and validation record when results change. Preserve the distinction between DC generation, AC delivery, auxiliary demand, curtailment and stored energy. Keep synthetic weather clearly identified, retain weather provenance and cite primary sources for new modelling methods.

Generated scenarios and local environments are excluded from Git. The raw public climate responses in `data/` are intentional project inputs. Refresh them with `python tools/download_weather.py --site all` and review provenance/data-quality changes before committing.

All dashboard and model source is Python. Keep application changes within that implementation approach.
