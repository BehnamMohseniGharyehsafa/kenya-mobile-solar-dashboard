"""Render the same Python scene into a portable deployment/retraction preview."""
from io import BytesIO
from pathlib import Path
import sys

import numpy as np
from PIL import Image

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from solar_model.config import Config
from solar_model.scene import CAMERAS
from solar_model.interactive_scene import InteractiveScene
from solar_model.mechanics import phase, smoothstep

if __name__=="__main__":
    output=root/"outputs"
    output.mkdir(exist_ok=True)
    images=[]
    scene=InteractiveScene(Config())
    scene.plotter.window_size=(960,540)
    path=list(np.linspace(0,1,14))+[1,1,1]+list(np.linspace(1,0,14))+[0,0]
    for i,p in enumerate(path):
        scene.update(float(p),20,90,48,315)
        mix=smoothstep((p-.28)/.52)
        position=(1-mix)*np.array(CAMERAS['Container detail'][0])+mix*np.array(CAMERAS['Site overview'][0])
        scene.plotter.camera_position=[position,(0,0,1.7),(0,0,1)]
        scene.plotter.add_text(f"{phase(p)} / {p*100:.0f}% DEPLOYED",name="sequence-label",font_size=12)
        images.append(Image.open(scene.png(size=(960,540))).convert("RGB"))
        if i%8==0:
            print(f"Rendered {i+1}/{len(path)}",flush=True)
    images[0].save(output/"deployment-sequence.gif",save_all=True,append_images=images[1:],duration=170,loop=0,optimize=False)
    scene.close()
    print(output/"deployment-sequence.gif",flush=True)
