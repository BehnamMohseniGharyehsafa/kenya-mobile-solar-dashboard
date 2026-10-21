"""Python-authored presentation styles; the fan uses a local animation clock."""

VIEWER_CSS="""
* { box-sizing: border-box; }
body { margin:0; background:#0b141b; color:#e8f1ee; font-family:'Segoe UI',Arial,sans-serif; }
button, input { font:inherit; }
button:focus-visible, input:focus-visible { outline:2px solid #f2c16b; outline-offset:3px; }
.viewer-shell { max-width:1800px; margin:0 auto; padding:16px 24px 28px;
 background:radial-gradient(ellipse at 12% 0%,#19343a 0,transparent 45%),#0e1a22; min-height:100vh; }
.developer-banner { display:flex; flex-direction:column; gap:3px; padding:0 0 12px; margin-bottom:13px;
 border-bottom:1px solid #345057; font-size:12px; line-height:1.5; color:#a9c7c2; }
.developer-banner strong { color:#edf4e9; font-size:14px; font-weight:600; }
.developer-banner a { width:fit-content; overflow-wrap:anywhere; }
.viewer-heading { display:flex; justify-content:space-between; gap:18px; align-items:center; margin-bottom:12px; }
.eyebrow { color:#8bb4b0; font-size:10px; font-weight:700; letter-spacing:2.4px; margin:0 0 6px; }
.viewer-heading h2 { font-size:25px; font-weight:600; letter-spacing:-.8px; margin:0; color:#f0f5ed; }
.viewer-heading h2 span { color:#78cbb4; }
.site-chip { border:1px solid #3d5a60; border-radius:9px; padding:7px 13px; background:#14272e;
 font-size:11px; color:#b7ccc8; line-height:1.5; text-align:right; }
.site-chip strong { color:#eef2e7; font-weight:600; }
.control { transition:background-color .12s,border-color .12s; font-weight:600; }
.control:hover:enabled { background:#314c55!important; border-color:#86b8b2!important; }
.control:disabled { opacity:.38; cursor:default!important; }
#deploy { background:#72d8b4!important; color:#092a24!important; border-color:#72d8b4!important; }
#deploy:hover:enabled { background:#9ae9cc!important; }
#retract { color:#f0cf92!important; border-color:#6d6147!important; }
.command-row { display:flex; flex-wrap:wrap; gap:9px; align-items:center; margin-bottom:10px; }
.view-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:10px 15px; padding:6px 0;
 border-top:1px solid #2b4047; border-bottom:1px solid #2b4047; }
.view-toolbar label { color:#8fa9aa; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:1px; }
.drag-tools { display:flex; align-items:center; gap:12px; margin-left:auto; }
.drag-tools label { text-transform:none; letter-spacing:0; font-size:13px; cursor:pointer; }
.drag-tools input { accent-color:#80dbb9; margin-right:5px; }
.camera-help { color:#8ba5a6; font-size:11px; margin:6px 0; }
.mechanism-status { display:flex; flex-wrap:wrap; justify-content:space-between; gap:8px; padding:2px 0 6px;
 font-size:11px; letter-spacing:.3px; }
#status { color:#b4ead7; font-weight:600; }
#roof-state { color:#9eb2b0; }
#progress { display:block; width:100%; height:4px; border:0; border-radius:3px; overflow:hidden; accent-color:#77dcb8; }
#progress::-webkit-progress-bar { background:#243a40; }
#progress::-webkit-progress-value { background:#77dcb8; }
.scene-frame { position:relative; height:clamp(420px,64vh,880px); border:1px solid #486069;
 border-radius:12px; overflow:hidden; margin-top:10px; box-shadow:0 14px 40px #0003; }
.scene-label { position:absolute; top:14px; left:16px; z-index:1; pointer-events:none;
 background:#0c202bcf; color:#e5eee2; border:1px solid #9bb3ad55; border-radius:5px;
 font-size:10px; letter-spacing:1.4px; padding:7px 10px; }
.scene-note { position:absolute; bottom:12px; right:14px; z-index:1; pointer-events:none;
 font-size:10px; color:#f0f4e8; background:#172e38c9; padding:5px 9px; border-radius:4px; }
.equipment-inspector { position:absolute; right:13px; top:13px; z-index:4; width:292px;
 max-height:calc(100% - 58px); overflow:auto; scrollbar-width:thin; }
.equipment-inspector>summary { cursor:pointer; list-style:none; float:right; padding:9px 12px;
 background:#14282fea; border:1px solid #718d89; color:#b6eddb; border-radius:6px;
 font-size:10px; font-weight:700; letter-spacing:1px; }
.equipment-inspector[open]>summary { float:none; border-radius:8px 8px 0 0; background:#203b41; }
.equipment-inspector:not([open]) { pointer-events:none; }
.equipment-inspector>summary { pointer-events:auto; }
.hmi-enclosure { padding:13px; border:1px solid #7f9898; border-top:0; border-radius:0 0 9px 9px;
 background:linear-gradient(125deg,#3b5158,#23373f 55%,#30454c); box-shadow:0 12px 26px #0008; }
.hmi-brand { display:flex; align-items:center; justify-content:space-between; margin:0 2px 10px; }
.hmi-brand strong { color:#e1eae5; font-size:12px; letter-spacing:1px; }
.hmi-brand small { color:#9eb7b6; font-size:8px; }
.hmi-lcd { border:6px solid #102127; border-radius:5px; padding:8px 10px;
 background:linear-gradient(135deg,#153c30,#0d291f); color:#b9ffda; box-shadow:inset 0 0 16px #0008;
 font-family:Consolas,monospace; }
.hmi-state { font-size:10px; font-weight:700; letter-spacing:.6px; color:#e3f9bf;
 border-bottom:1px solid #548365; padding-bottom:7px; margin-bottom:5px; }
.hmi-reading { display:grid; grid-template-columns:1fr auto 40px; align-items:baseline; gap:7px; padding:3px 0; }
.hmi-reading>span { font-size:9px; color:#8ac6a8; }
.hmi-reading strong { font-size:18px; font-weight:400; line-height:1.1; }
.hmi-reading small { color:#90c8ad; font-size:10px; }
.hmi-contactor { border-top:1px solid #548365; margin-top:5px; padding-top:6px; font-size:9px; color:#a4d8b5; }
.hmi-buttons { display:flex; justify-content:space-around; padding:10px 0 5px; gap:8px; }
.hmi-button { background:none; border:0; padding:0; color:#e2e9e5; cursor:pointer; width:70px; font-size:9px; font-weight:700; }
.hmi-button>span:last-child { display:block; margin-top:8px; letter-spacing:.6px; }
.push-cap { display:block; width:34px; height:34px; margin:auto; border-radius:50%; border:4px solid #14262d;
 background:radial-gradient(circle at 30% 25%,#acffd4,#45bd82 60%,#278157); box-shadow:0 4px 0 #0b191e,0 5px 6px #0008,inset 0 2px 3px #ffffff55; }
.hmi-hold .push-cap { background:radial-gradient(circle at 30% 25%,#ffeaa3,#eeb63e 60%,#9f751d); }
.hmi-stop .push-cap { border-color:#e3b73f; background:radial-gradient(circle at 30% 25%,#ffada3,#e95345 60%,#a72d27); }
.hmi-button:active .push-cap { transform:translateY(3px); box-shadow:0 1px 0 #0b191e,inset 0 1px 5px #0006; }
.hmi-button:disabled { cursor:default; color:#799295; }
.hmi-button:disabled .push-cap { filter:saturate(.45) brightness(.75); }
.hmi-stop:disabled .push-cap { transform:translateY(3px); filter:none; box-shadow:0 1px 0 #0b191e; }
.hmi-cooling { display:flex; align-items:center; gap:12px; margin-top:6px; padding:7px 8px; border:1px solid #597478;
 border-radius:6px; background:#182d34; font-size:9px; color:#9ec1bb; }
.hmi-cooling strong { display:block; margin-bottom:4px; font-size:10px; color:#d1e6db; }
.fan-indicator { width:48px; height:48px; position:relative; flex-shrink:0; border:3px solid #779292;
 border-radius:6px; background:radial-gradient(circle,#243a40 60%,#102127 63%); box-shadow:inset 0 0 10px #0008; }
.fan-blades { width:40px; height:40px; position:absolute; left:1px; top:1px; will-change:transform; }
.fan-blades i { display:block; position:absolute; height:19px; width:12px; border-radius:65% 15% 60% 35%;
 background:linear-gradient(130deg,#c9dcda,#617d85); left:14px; top:1px; transform-origin:6px 19px; }
.fan-blades i:nth-child(2) { transform:rotate(120deg); }.fan-blades i:nth-child(3) { transform:rotate(240deg); }
.fan-hub { position:absolute; width:10px; height:10px; border-radius:50%; left:16px; top:16px; background:#d7e4de; }
.hmi-notice { font-size:10px; line-height:1.45; padding:9px 0 0; margin:0; color:#e1d7b5; }
.hmi-footnote { display:block; font-size:8px; line-height:1.4; margin-top:8px; color:#9fb7b4; }
#clocks { font:11px 'Consolas',monospace; color:#95b1b2; padding:3px 0; }
#clocks p { margin:10px 0 13px; }
.metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
.metric-card { border:1px solid #304951; border-radius:10px; background:linear-gradient(140deg,#1b333c,#13252d);
 padding:15px 18px; min-width:0; }
.metric-label { display:block; color:#93b1b0; text-transform:uppercase; font-size:10px; letter-spacing:1.3px; font-weight:600; }
.metric-value { display:block; color:#f0f5e9; font-size:29px; font-weight:600; letter-spacing:-.9px; line-height:1.55; }
.metric-unit { color:#8dd8bc; font-size:13px; font-weight:400; letter-spacing:0; margin-left:6px; }
.metric-caption { color:#9fb4b3; font-size:11px; }
.plant-caption { color:#8ca8a8; font-size:11px; margin:10px 0 14px; }
#weather { font-size:12px; color:#abc1bf; padding:13px 16px; border:1px solid #304951;
 border-left:3px solid #72c9b2; border-radius:7px; background:#13262e; line-height:1.6; }
#weather p { margin:0 0 5px; } #weather p:last-child { margin:0; }
a { color:#8bdbc3; text-decoration:none; } a:hover { text-decoration:underline; }
.settings { margin:16px 0 20px; border:1px solid #304951; border-radius:8px; padding:13px 16px;
 background:#12242c; color:#a7bfbd; font-size:12px; }
.settings summary { color:#dfebe1; cursor:pointer; font-size:12px; font-weight:600; }
.settings[open] summary { margin-bottom:18px; }
.settings p { font-size:11px; color:#8ca6a6; }
.settings input[type=text] { border:1px solid #4a666b; border-radius:5px; background:#0e2029; color:#d9e9e2; }
.settings input[type=checkbox] { accent-color:#7cd4b7; margin:0 6px 0 0; }
#options { display:flex; flex-wrap:wrap; gap:13px 22px; margin-top:15px; }
#technical { margin:20px 0 16px; color:#adc3c0; font-size:12px; line-height:1.7; }
#technical table { width:100%; border-collapse:collapse; }
#technical th { text-align:left; color:#87b8ad; font-size:10px; text-transform:uppercase; letter-spacing:1px;
 padding:10px 14px; background:#172e36; border-bottom:1px solid #3b565d; }
#technical td { padding:9px 14px; border-bottom:1px solid #263e46; }
#technical tr:nth-child(even) { background:#132730; }
.export-row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; border-top:1px solid #304951; padding-top:18px; }
.export-row label { font-size:11px; color:#9bb5b1; }
.viewer-footer { color:#708f91; font-size:10px; line-height:1.7; margin:18px 0 0; letter-spacing:.3px; }
@media(max-width:780px) {
 .viewer-shell { padding:14px; } .viewer-heading h2 { font-size:21px; }
 .site-chip { display:none; } .metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
 .drag-tools { margin-left:0; } .scene-frame { min-height:400px; }
 .equipment-inspector { width:258px; right:8px; top:8px; }.hmi-enclosure { padding:10px; }
}
"""


def index_template():
    # Dash owns rendering; its local fan helper is served through the assets API.
    return """<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>
{%favicon%}{%css%}<style>"""+VIEWER_CSS+"""</style></head><body>
{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""
