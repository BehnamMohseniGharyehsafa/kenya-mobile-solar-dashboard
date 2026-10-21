"""Bounded, single-process safeguards for the public, anonymous demonstration.

These protect application resources, not an uptime or attack-proof guarantee.
No IP/proxy header is trusted for identity, and no additional database is needed.
"""
from collections import OrderedDict
import math
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from flask import g,jsonify,request
from itsdangerous import BadSignature,SignatureExpired,URLSafeTimedSerializer

from .scene import CAMERAS

COOKIE="pv_visitor"
CLOCKS={"Live site clock","Accelerated solar day","Manual sun study"}


class Buckets:
    """Token buckets with a fixed memory ceiling; rejected calls do not queue."""
    def __init__(self,clock=time.monotonic):
        self.clock=clock
        self.items=OrderedDict()
        self.lock=threading.Lock()

    def allow(self,key,rate,capacity):
        now=self.clock()
        with self.lock:
            tokens,last=self.items.pop(key,(capacity,now))
            tokens=min(capacity,tokens+max(0,now-last)*rate)
            allowed=tokens>=1
            self.items[key]=(tokens-1 if allowed else tokens,now)
            while len(self.items)>2048:
                self.items.popitem(last=False)
        return allowed


def bounded_value(value,depth=0,budget=None):
    """Reject non-finite numbers and oversized nested browser-controlled values."""
    budget=[160] if budget is None else budget
    budget[0]-=1
    if depth>5 or budget[0]<0:
        return False
    if value is None or isinstance(value,bool):
        return True
    if isinstance(value,int):
        return abs(value)<=2**31
    if isinstance(value,float):
        return math.isfinite(value) and abs(value)<=2**31
    if isinstance(value,str):
        return len(value)<=256
    if isinstance(value,list):
        return len(value)<=32 and all(bounded_value(v,depth+1,budget) for v in value)
    if isinstance(value,dict):
        return len(value)<=24 and all(isinstance(k,str) and len(k)<=64 and bounded_value(v,depth+1,budget)
            for k,v in value.items())
    return False


def valid_control(identity,prop,value):
    if not bounded_value(value):
        return False
    if prop in {"n_clicks","n_intervals"}:
        return value is None or (type(value) is int and value>=0)
    if identity=="clock":
        return isinstance(value,str) and value in CLOCKS
    if identity=="speed":
        return type(value) in (int,float) and value in {60,120,300,600,1200}
    if identity=="duration":
        return type(value) in (int,float) and 2<=value<=20
    if identity=="options":
        return isinstance(value,list) and len(value)<=3 and all(isinstance(v,str) and v in {"shadows","landscape","cutaway"} for v in value)
    if identity=="detail-tab":
        return isinstance(value,str) and value in {"power","mechanism","weather","export"}
    if identity=="camera":
        return isinstance(value,str) and value in CAMERAS
    if identity=="tool":
        return isinstance(value,str) and value in {"Orbit","Pan","Zoom"}
    if identity=="export-size":
        return value=="1080p"
    if identity=="manual":
        # A partly edited text field must not halt unrelated live-clock ticks.
        # FieldView reports invalid study dates while retaining its valid clock.
        return isinstance(value,str) and len(value)<=32
    if identity=="session":
        return isinstance(value,str) and re.fullmatch(r"[a-f0-9]{32}",value) is not None
    if identity=="fan-rotor":
        if not isinstance(value,dict) or not set(value)<={"userMatrix","orientation","origin","position","visibility","useBounds"}:
            return False
        return all(isinstance(value[k],list) and len(value[k])==n and
            all(type(x) in (int,float) and math.isfinite(x) and abs(x)<=1000 for x in value[k])
            for k,n in (("userMatrix",16),("orientation",3),("origin",3),("position",3)) if k in value)
    if identity=="vtk" and prop=="clickInfo":
        return value is None or isinstance(value,dict)
    return False


def valid_outputs(actual,declared):
    if isinstance(declared,list):
        return isinstance(actual,list) and len(actual)==len(declared) and all(
            valid_outputs(a,d) for a,d in zip(actual,declared))
    identity=declared.component_id
    if isinstance(identity,dict):
        if not isinstance(actual,list) or len(actual)>64:
            return False
        return all(isinstance(item,dict) and item.get("property")==declared.component_property and
            isinstance(item.get("id"),dict) and set(item["id"])==set(identity) and
            item["id"].get("type")==identity.get("type") and type(item["id"].get("slot")) is int and
            0<=item["id"]["slot"]<64 for item in actual)
    return isinstance(actual,dict) and actual.get("id")==identity and actual.get("property")==declared.component_property


class CloudGuard:
    def __init__(self,service):
        self.service=service
        self.signer=URLSafeTimedSerializer(secrets.token_bytes(32),salt="pv-public-browser")
        self.buckets=Buckets()
        self.work=threading.BoundedSemaphore(2)
        self.native=threading.BoundedSemaphore(1)

    @staticmethod
    def reject(code,message,retry=None):
        response=jsonify(error=message)
        response.status_code=code
        if retry is not None:
            response.headers["Retry-After"]=str(retry)
        return response

    def acquire(self,gate):
        if not gate.acquire(blocking=False):
            return False
        g.pv_gates.append(gate)
        return True

    def before(self):
        g.pv_gates=[]
        g.viewer_owner=None
        g.pv_new_cookie=False
        try:
            owner=self.signer.loads(request.cookies.get(COOKIE,""),max_age=43200)
            if isinstance(owner,str) and re.fullmatch(r"[a-f0-9]{32}",owner):
                g.viewer_owner=owner
        except (BadSignature,SignatureExpired):
            pass
        dynamic=request.path in {"/","/_dash-layout","/_dash-update-component"}
        if request.method=="GET" and request.path in {"/","/_dash-layout"} and g.viewer_owner is None:
            g.viewer_owner=secrets.token_hex(16)
            g.pv_new_cookie=True
        if dynamic and not self.buckets.allow("global-page" if request.method=="GET" else "global-callback",60,90):
            return self.reject(429,"The demonstration is busy. Please try again shortly.",2)
        if request.path=="/_dash-layout":
            if not self.buckets.allow("layout:"+g.viewer_owner,.1,2):
                return self.reject(429,"Please wait before reloading the simulation again.",10)
            if not self.buckets.allow("global-layout",.2,4) or not self.acquire(self.native):
                return self.reject(503,"A scene is loading. Please try again shortly.",3)
        if request.path!="/_dash-update-component":
            return None
        if request.method!="POST" or g.viewer_owner is None:
            return self.reject(403,"Refresh the dashboard to establish a browser session.")
        origin=request.headers.get("Origin")
        try:
            parsed=urlsplit(origin) if origin else None
            wrong_origin=parsed is not None and (parsed.netloc.lower()!=request.host.lower() or parsed.scheme not in {"http","https"})
        except ValueError:
            wrong_origin=True
        if request.headers.get("Sec-Fetch-Site")=="cross-site" or wrong_origin:
            return self.reject(403,"Cross-site simulation commands are not accepted.")
        if not request.is_json:
            return self.reject(415,"Simulation commands must use JSON.")
        try:
            body=request.get_json()
        except (ValueError,RecursionError):
            return self.reject(400,"Invalid simulation command.")
        if not isinstance(body,dict) or not isinstance(body.get("output"),str):
            return self.reject(400,"Invalid simulation command.")
        callback=self.service.app.callback_map.get(body["output"])
        if callback is None or "callback" not in callback:
            return self.reject(400,"Unknown simulation command.")
        if not valid_outputs(body.get("outputs"),callback["output"]):
            return self.reject(400,"Invalid simulation response target.")
        values={}
        for section in ("inputs","state"):
            actual=body.get(section,[])
            expected=callback[section]
            if not isinstance(actual,list) or len(actual)!=len(expected):
                return self.reject(400,"Invalid simulation controls.")
            for item,spec in zip(actual,expected):
                if not isinstance(item,dict) or item.get("id")!=spec["id"] or item.get("property")!=spec["property"] or not valid_control(spec["id"],spec["property"],item.get("value")):
                    return self.reject(400,"Invalid simulation control value.")
                values[spec["id"]]=item.get("value")
        changed=body.get("changedPropIds",[])
        allowed={item["id"]+"."+item["property"] for item in callback["inputs"]}
        if not isinstance(changed,list) or len(changed)>4 or any(not isinstance(x,str) or x not in allowed for x in changed):
            return self.reject(400,"Invalid simulation action.")
        view=None
        if "session" in values:
            sid=values["session"]
            view=self.service.sessions.get(sid)
            if view is None or self.service.owners.get(sid)!=g.viewer_owner:
                return self.reject(403,"This simulation belongs to another or expired browser session.")
        if not self.buckets.allow("callback:"+g.viewer_owner,30,50):
            return self.reject(429,"Too many simulation commands. Please pause briefly.",2)
        if "refresh.n_clicks" in changed and not self.buckets.allow("weather-refresh",1/30,2):
            return self.reject(429,"Weather was refreshed recently. Please wait a moment.",30)
        if "export-png.n_clicks" in changed:
            if not self.buckets.allow("png",1/15,1):
                return self.reject(429,"Please wait before exporting another image.",15)
            if not self.acquire(self.native):
                return self.reject(503,"The image renderer is busy. Please try again shortly.",3)
        elif "export.n_clicks" in changed and not self.buckets.allow("json-export:"+g.viewer_owner,1/5,1):
            return self.reject(429,"Please wait before exporting another snapshot.",5)
        if not self.acquire(self.work):
            return self.reject(503,"The demonstration is busy. Please try again shortly.",2)
        if view is not None and not self.acquire(view.request_gate):
            return self.reject(429,"A command for this simulation is already running.",1)

    def after(self,response):
        if getattr(g,"pv_new_cookie",False):
            local=request.environ.get("HTTP_HOST","").split(":",1)[0] in {"localhost","127.0.0.1"}
            response.set_cookie(COOKIE,self.signer.dumps(g.viewer_owner),max_age=43200,
                secure=not local,httponly=True,samesite="Lax")
        return response

    @staticmethod
    def release(error=None):
        for gate in reversed(g.pop("pv_gates",[])):
            gate.release()
