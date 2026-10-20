"""Cache an attributable Open-Meteo response for the Nairobi scene."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from solar_model.config import Config
from solar_model.live_weather import fetch_feed

if __name__=="__main__":
    frame,meta=fetch_feed(Config())
    print(meta)
    print(frame.head(2).to_string())
