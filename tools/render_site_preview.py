"""Render reproducible concept geometry for visual verification."""
from pathlib import Path
import sys
import time

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from solar_model.config import Config
from solar_model.scene import render_scene

if __name__=="__main__":
    output=root/"outputs"
    output.mkdir(exist_ok=True)
    for name,p,camera,cutaway in [("site-deployed",1,"Site overview",False),
        ("container-packed",0,"Container detail",False),
        ("container-cutaway",.60,"Mechanism inspection",True)]:
        t=time.perf_counter()
        image=render_scene(Config(),p,20,90,48,315,camera=camera,cutaway=cutaway,
            stamp="CONCEPT GEOMETRY  /  EXPLICIT TEST SUN 48° ELEVATION",condition="Daylight study")
        (output/f"{name}.png").write_bytes(image)
        print(name,round(time.perf_counter()-t,2),flush=True)
