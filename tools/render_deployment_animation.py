"""Render the same Python scene into a portable deployment/retraction preview."""
from io import BytesIO
from pathlib import Path
import sys

import numpy as np
from PIL import Image

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from solar_model.config import Config
from solar_model.scene import render_scene
from solar_model.mechanics import phase

if __name__=="__main__":
    output=root/"outputs"
    output.mkdir(exist_ok=True)
    images=[]
    path=list(np.linspace(0,1,14))+[1,1,1]+list(np.linspace(1,0,14))+[0,0]
    for i,p in enumerate(path):
        data=render_scene(Config(),float(p),20,90,48,315,camera="Deployment camera",
            size=(960,540),stamp=f"{phase(p)}  /  {p*100:.0f}% DEPLOYED",condition="Concept sequence / test sun")
        images.append(Image.open(BytesIO(data)).convert("RGB"))
        if i%8==0:
            print(f"Rendered {i+1}/{len(path)}",flush=True)
    images[0].save(output/"deployment-sequence.gif",save_all=True,append_images=images[1:],duration=170,loop=0,optimize=False)
    print(output/"deployment-sequence.gif",flush=True)
