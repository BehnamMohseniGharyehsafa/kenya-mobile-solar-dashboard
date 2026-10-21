"""Reproducible live-viewer geometry/transport benchmark (not browser FPS).

Run with: python -m tools.benchmark_viewer --output outputs/viewer-performance.json
Weather is deterministic and no network requests are made.
"""
import argparse
import cProfile
from dataclasses import is_dataclass
import json
from pathlib import Path
import pstats
import time

import numpy as np
from dash._utils import to_json

from solar_model.config import Config
from solar_model.field_view import FieldView
from tests.weather_fixture import forecast_fixture


def benchmark(frames=60, profile=None):
    view=FieldView(Config(),feed=forecast_fixture())
    wall=[100.]
    c=view.controller
    c.monotonic=lambda:wall[0]
    c.last_motion=wall[0]
    stamp=c.frame.index[36]
    c.set_mode("Manual sun study",stamp)
    c.manual=stamp
    arguments=(c.mode,stamp.strftime("%Y-%m-%d %H:%M"),600,6,["shadows","landscape"],"power")
    profiler=cProfile.Profile() if profile else None
    try:
        initial_layout=view.layout("benchmark")
        initial_mib=len(to_json(initial_layout).encode())/1024**2
        view.step("clock",*arguments)
        c.weather["gust_ms"]=0
        view.step("deploy",*arguments)
        # Measure animation independently of the 1 Hz physical plant and chart
        # schedules. Their frequency must not skew an old/new CPU comparison.
        view.last_physics=view.last_chart=float("inf")
        times,sizes=[],[]
        if profiler:
            profiler.enable()
        for _ in range(frames):
            wall[0]+=6/(frames+1)
            start=time.perf_counter()
            result=view.step("tick",*arguments)
            payload=result[0]
            if is_dataclass(payload):
                payload=payload.to_dict()
            sizes.append(len(to_json(payload).encode()))
            times.append((time.perf_counter()-start)*1000)
        if profiler:
            profiler.disable()
            pstats.Stats(profiler).sort_stats("cumulative").dump_stats(profile)
        return {"frames":frames,"median_python_and_encoding_ms":float(np.median(times)),
            "p95_python_and_encoding_ms":float(np.percentile(times,95)),
            "median_geometry_kib":float(np.median(sizes)/1024),
            "actors":len(view.actors),"triangles":sum(a.mapper.dataset.triangulate().n_cells for a in view.actors),
            "initial_layout_mib":initial_mib,
            "fan_per_frame_server_requests":0,
            "fan_command_bytes":len(to_json(view.fan_command(True)).encode()),
            "scope":"Animation update plus geometry JSON encoding; excludes plant solves, browser drawing and network."}
    finally:
        view.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames",type=int,default=60)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--profile")
    args=parser.parse_args()
    result=benchmark(args.frames,args.profile)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
