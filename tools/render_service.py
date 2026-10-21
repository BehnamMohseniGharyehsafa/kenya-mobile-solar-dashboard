"""Turn the owner's Render service on/off without putting credentials in Git.

Examples: python -m tools.render_service status --service-id srv-...
          python -m tools.render_service off --service-id srv-...
          python -m tools.render_service on --service-id srv-...

RENDER_API_KEY is read from the environment or requested using a hidden prompt.
RENDER_SERVICE_ID may supply --service-id. The public app never receives the key.
"""
import argparse
import getpass
import json
import os
import re

import requests

API="https://api.render.com/v1/services"
SERVICE_NAME="behnamproject-pvforafrica"


def manage(action, service_id, api_key, client=None):
    if action not in {"status","on","off"}:
        raise ValueError("Choose status, on or off.")
    if not re.fullmatch(r"srv-[a-z0-9]+",service_id or ""):
        raise ValueError("Supply the Render service ID, beginning with srv-.")
    if not api_key or not api_key.strip():
        raise ValueError("A Render API key is required.")
    client=client or requests.Session()
    headers={"Authorization":f"Bearer {api_key.strip()}","Accept":"application/json"}
    url=f"{API}/{service_id}"
    response=client.get(url,headers=headers,timeout=30)
    response.raise_for_status()
    service=response.json()
    if service.get("name")!=SERVICE_NAME:
        raise ValueError("This ID belongs to a different service. No change was made.")
    if action!="status":
        operation={"on":"resume","off":"suspend"}[action]
        response=client.post(f"{url}/{operation}",headers=headers,timeout=30)
        response.raise_for_status()
        response=client.get(url,headers=headers,timeout=30)
        response.raise_for_status()
        service=response.json()
    return {"name":service.get("name"),"suspended":service.get("suspended"),
        "url":service.get("serviceDetails",{}).get("url"),"action":action}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["status","on","off"])
    parser.add_argument("--service-id",default=os.environ.get("RENDER_SERVICE_ID"))
    args=parser.parse_args()
    key=os.environ.get("RENDER_API_KEY") or getpass.getpass("Render API key (hidden): ")
    try:
        result=manage(args.action,args.service_id,key)
    except (ValueError,requests.RequestException) as exc:
        # Request errors print URL/status, never the authorization header.
        parser.exit(1,f"Render control failed: {exc}\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
