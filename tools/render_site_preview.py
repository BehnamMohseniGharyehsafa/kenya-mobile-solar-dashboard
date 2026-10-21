"""Render reproducible concept geometry for visual verification."""
from pathlib import Path
import sys
import time

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from solar_model.config import Config
from solar_model.interactive_scene import InteractiveScene

if __name__=="__main__":
    output=root/"outputs"
    output.mkdir(exist_ok=True)
    scene=InteractiveScene(Config())
    try:
        for name,p,camera,cutaway in [("site-deployed",1,"Site overview",False),
            ("container-packed",0,"Container detail",False),
            ("container-cutaway",.60,"Mechanism inspection",True)]:
            t=time.perf_counter()
            scene.set_options(True,cutaway)
            scene.set_camera(camera)
            scene.update(p,20,90,48,315)
            scene.plotter.add_text("NAIROBI / FIELD SYSTEM 01",name="site-label",position="upper_left",font_size=14,color="#f0f0df")
            scene.plotter.add_text("CONCEPT GEOMETRY / EXPLICIT TEST SUN 48° ELEVATION",name="sun-label",position="lower_left",font_size=11,color="#f0f0df")
            (output/f"{name}.png").write_bytes(scene.png().getvalue())
            print(name,round(time.perf_counter()-t,2),flush=True)
    finally:
        scene.close()
