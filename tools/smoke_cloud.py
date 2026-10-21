"""Exercise a running container's real scene and callbacks, without a browser.

Usage: python -m tools.smoke_cloud http://127.0.0.1:10000
"""
import argparse
import time

import requests


def components(node):
    if isinstance(node,dict):
        if "props" in node and "type" in node:
            yield node
        for value in node.values():
            yield from components(value)
    elif isinstance(node,list):
        for value in node:
            yield from components(value)


def smoke(url):
    url=url.rstrip("/")
    client=requests.Session()
    deadline=time.monotonic()+90
    while True:
        try:
            response=client.get(url+"/healthz",timeout=5)
            response.raise_for_status()
            break
        except requests.RequestException:
            if time.monotonic()>deadline:
                raise
            time.sleep(1)
    page=client.get(url+"/",timeout=15)
    page.raise_for_status()
    assert "BehnamProject-PVforAfrica" in page.text
    started=time.monotonic()
    response=client.get(url+"/_dash-layout",timeout=120)
    response.raise_for_status()
    layout=response.json()
    nodes=list(components(layout))
    props={n["props"]["id"]:n["props"] for n in nodes if isinstance(n["props"].get("id"),str)}
    assert "vtk" in props and "session" in props, "The actual 3D scene did not load."
    dependencies=client.get(url+"/_dash-dependencies",timeout=15).json()
    callback=next(d for d in dependencies if "moving-mesh" in d["output"])
    outputs=[]
    for spec in callback["output"].strip(".").split("..."):
        identity,prop=spec.rsplit(".",1)
        if identity.startswith("{"):
            import json
            pattern=json.loads(identity)
            outputs.append([{"id":n["props"]["id"],"property":prop} for n in nodes
                if isinstance(n["props"].get("id"),dict) and n["props"]["id"].get("type")==pattern["type"]])
        else:
            outputs.append({"id":identity,"property":prop})
    inputs=[dict(item,value=props[item["id"]].get(item["property"])) for item in callback["inputs"]]
    state=[dict(item,value=props[item["id"]].get(item["property"])) for item in callback["state"]]
    response=client.post(url+"/_dash-update-component",json={"output":callback["output"],
        "outputs":outputs,"inputs":inputs,"state":state,"changedPropIds":["tick.n_intervals"]},timeout=120)
    response.raise_for_status()
    assert "status" in response.json()["response"]
    refreshed=client.get(url+"/_dash-layout",timeout=120)
    refreshed.raise_for_status()
    refreshed_session=next(n["props"]["data"] for n in components(refreshed.json()) if n["props"].get("id")=="session")
    assert refreshed_session==props["session"]["data"], "Refreshing allocated another scene."
    other=requests.Session()
    other.get(url+"/",timeout=15).raise_for_status()
    second=other.get(url+"/_dash-layout",timeout=120)
    second.raise_for_status()
    second_nodes=list(components(second.json()))
    second_session=next(n["props"]["data"] for n in second_nodes if n["props"].get("id")=="session")
    assert second_session!=props["session"]["data"], "Visitors shared a simulation session."
    visitor=requests.Session()
    visitor.get(url+"/",timeout=15).raise_for_status()
    third=visitor.get(url+"/_dash-layout",timeout=30)
    third.raise_for_status()
    assert "currently full" in third.text, "The cloud session cap was not enforced."
    forbidden=other.post(url+"/_dash-update-component",json={"output":callback["output"],
        "outputs":outputs,"inputs":inputs,"state":state,"changedPropIds":["tick.n_intervals"]},timeout=30)
    assert forbidden.status_code==403, "Another browser could operate the first browser's simulation."
    # Exercise the public, memory-bounded PNG path with the cloud Pillow pin.
    from io import BytesIO
    from PIL import Image
    download=client.post(url+"/_dash-update-component",json={"output":"download.data",
        "outputs":{"id":"download","property":"data"},
        "inputs":[{"id":"export","property":"n_clicks","value":0},{"id":"export-png","property":"n_clicks","value":1}],
        "state":[{"id":"session","property":"data","value":props["session"]["data"]},
            {"id":"export-size","property":"value","value":"1080p"},
            {"id":"camera","property":"value","value":"Control panel & fan"},
            {"id":"fan-rotor","property":"actor","value":{}}],
        "changedPropIds":["export-png.n_clicks"]},timeout=120)
    download.raise_for_status()
    import base64
    payload=download.json()["response"]["download"]["data"]
    image=Image.open(BytesIO(base64.b64decode(payload["content"])))
    assert image.size==(1920,1080) and image.format=="PNG"
    print(f"Cloud smoke passed: real 3D layout and plant callback; {time.monotonic()-started:.2f} s initial load.")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    smoke(parser.parse_args().url)
