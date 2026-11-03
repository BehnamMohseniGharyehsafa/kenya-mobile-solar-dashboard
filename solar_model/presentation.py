"""Python-authored presentation styles; the fan uses a local animation clock."""

VIEWER_CSS="""
* { box-sizing: border-box; }
html { scroll-behavior:smooth; scroll-padding-top:24px; }
body { margin:0; background:#0d1415; color:#e8ede7; font-family:'Segoe UI',Arial,sans-serif; }
button, input { font:inherit; }
button:focus-visible, input:focus-visible { outline:2px solid #f2c16b; outline-offset:3px; }
.viewer-shell { max-width:1800px; margin:0 auto; padding:0 38px 28px;
 background:radial-gradient(ellipse at 90% 10%,#1e2c252e 0,transparent 42%),#101819; min-height:100vh; }
.app-masthead { display:flex; justify-content:space-between; align-items:center; gap:24px; min-height:80px;
 border-bottom:1px solid #2b3835; margin-bottom:32px; }
.brand { display:flex; align-items:center; gap:12px; color:#eef1e6; font-size:21px; letter-spacing:-.7px; }
.brand:hover { text-decoration:none; }.brand strong { font-weight:650; }.brand strong span { font-weight:350; color:#bec7b7; }
.brand-symbol { display:grid; place-items:center; border:1px solid #81905a; color:#d6e6a5; background:#263026;
 border-radius:11px; width:40px; height:40px; font-size:29px; }
.app-masthead nav { display:flex; gap:30px; }.app-masthead nav a { font-size:12px; color:#a9b7b1; padding:30px 0; }
.app-masthead nav a:first-child { color:#d8eaa7; border-bottom:2px solid #c0d88f; }
.simulation-badge { color:#becaab; border:1px solid #46533a; border-radius:20px; padding:7px 12px;
 font-size:9px; letter-spacing:1.2px; white-space:nowrap; }
.simulation-badge:before { content:''; display:inline-block; width:5px; height:5px; border-radius:50%; background:#c6d99b; margin-right:7px; }
.developer-banner { display:flex; flex-direction:column; align-items:center; gap:3px; padding:16px 0; margin:0;
 border-bottom:1px solid #2b3835; text-align:center; font-size:13px; line-height:1.6; color:#a9b9ae; }
.developer-banner strong { color:#e2eadb; font-size:14px; font-weight:600; }
.developer-banner a { max-width:100%; width:fit-content; overflow-wrap:anywhere; }
.viewer-heading { display:flex; justify-content:space-between; gap:18px; align-items:center; margin-bottom:25px; }
.eyebrow { color:#a8b98a; font-size:9px; font-weight:600; letter-spacing:2.1px; margin:0 0 10px; }
.viewer-heading h2 { font-size:clamp(26px,2.7vw,42px); font-weight:450; letter-spacing:-1.5px; margin:0; color:#edf0e7; }
.viewer-heading h2 span { color:#87978e; font-weight:350; }
.heading-caption { color:#94a59d; font-size:12px; line-height:1.7; margin:10px 0 0; }
.site-chip { border-left:1px solid #46523f; padding:3px 0 3px 18px;
 font:10px/1.9 Consolas,monospace; color:#91a298; text-align:right; flex-shrink:0; }
.site-chip strong { color:#eef2e7; font-weight:600; }
.control { transition:background-color .12s,border-color .12s; font-weight:600; }
.control:hover:enabled { background:#314c55!important; border-color:#86b8b2!important; }
.control:disabled { opacity:.38; cursor:default!important; }
#deploy { background:#c4d99a!important; color:#1d2d1c!important; border-color:#c4d99a!important; }
#deploy:hover:enabled { background:#dcebb8!important; }
#retract { color:#f0cf92!important; border-color:#6d6147!important; }
.workspace-grid { display:grid; grid-template-columns:minmax(0,1fr) 292px; gap:20px; align-items:start; }
.workspace-stage { min-width:0; border:1px solid #35423b; border-radius:13px; background:#15201f; overflow:hidden; }
.section-heading { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:18px 20px; }
.section-heading>div,.console-heading { display:flex; align-items:center; gap:11px; }
.section-heading h3,.console-heading h3 { font-size:13px; font-weight:600; margin:0; letter-spacing:.1px; }
.section-index { color:#a8b88c; font:10px Consolas,monospace; border:1px solid #40503b; padding:4px 5px; border-radius:4px; }
.section-meta { color:#83968a; font-size:8px; letter-spacing:1.5px; }
.control-console { border:1px solid #35423b; border-radius:13px; padding:20px; background:linear-gradient(135deg,#1b2622,#16201f); }
.console-heading { padding-bottom:18px; border-bottom:1px solid #344139; margin-bottom:18px; }
.control-label { display:block; color:#a6b69d; font-size:8px; font-weight:600; letter-spacing:1.6px; margin:0 0 11px; }
.command-row { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:16px 0 10px; }
.command-row #deploy { grid-column:1/-1; text-align:left; font-size:13px!important; padding:13px 14px!important; }
.command-row .control { padding:10px 6px!important; font-size:10px!important; }
.sequence-caption { font-size:10px; line-height:1.7; color:#889d90; margin:8px 0 18px; }
.view-toolbar { display:grid; gap:10px; padding:18px 0; border-top:1px solid #344139; border-bottom:1px solid #344139; }
.view-toolbar .control { text-align:left; }.view-toolbar .control-label { margin:9px 0 0; }
.view-toolbar label { color:#8fa9aa; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:1px; }
.drag-tools { display:flex; flex-wrap:wrap; align-items:center; gap:10px; padding:9px 0; }
.drag-tools label { text-transform:none; letter-spacing:0; font-size:10px; cursor:pointer; }
.drag-tools input { accent-color:#80dbb9; margin-right:5px; }
.camera-help { color:#8ba5a6; font-size:11px; margin:6px 0; }
.mechanism-status { display:grid; gap:7px; padding:2px 0 12px; font-size:10px; line-height:1.7; letter-spacing:.3px; }
#status { color:#d0dfb0; font-weight:600; }
#roof-state { color:#9eb2b0; }
#progress { display:block; width:100%; height:4px; border:0; border-radius:3px; overflow:hidden; accent-color:#77dcb8; }
#progress::-webkit-progress-bar { background:#243a40; }
#progress::-webkit-progress-value { background:#77dcb8; }
.scene-frame { position:relative; height:clamp(440px,55vw,650px); overflow:hidden; background:#718270; }
.scene-label { position:absolute; top:14px; left:16px; z-index:1; pointer-events:none;
 background:#0c202bcf; color:#e5eee2; border:1px solid #9bb3ad55; border-radius:5px;
 font-size:10px; letter-spacing:1.4px; padding:7px 10px; }
.scene-note { position:absolute; bottom:16px; right:14px; z-index:1; pointer-events:none;
 font-size:10px; color:#f0f4e8; background:#172923cc; padding:6px 9px; border-radius:4px; }
.scene-scale { position:absolute; left:18px; bottom:16px; z-index:1; color:#eef0df; font-size:8px; letter-spacing:1.2px;
 display:flex; align-items:center; gap:9px; pointer-events:none; text-shadow:0 1px 4px #000; }
.north-marker { font:10px Consolas,monospace; padding:6px; border:1px solid #cbd9bc77; border-radius:50%; }
.scene-bottom { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:10px 18px; border-bottom:1px solid #344139; }
.scene-bottom .control { padding:7px 10px!important; font-size:10px!important; }
.system-design { padding-top:18px; }.system-design>div { display:inline-grid; margin-right:20px; gap:3px; }
.system-design strong { color:#d9e4c6; font-size:23px; font-weight:450; letter-spacing:-.7px; }
.system-design>div>span { font-size:9px; color:#96a89a; }.system-design .sequence-caption { margin-bottom:0; }
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
#clocks { font:9px/1.8 'Consolas',monospace; color:#94a99a; padding:10px 18px; }
#clocks p { margin:0; }
.metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
.metric-card { position:relative; border:1px solid #34423b; border-radius:10px; background:#182320;
 padding:18px 20px 17px; min-width:0; overflow:hidden; }
.metric-card:after { content:''; position:absolute; right:17px; top:19px; width:6px; height:6px; border:1px solid #a4b775; border-radius:2px; }
.metric-card:nth-child(2):after { border-color:#85b8a3; }.metric-card:nth-child(3):after { border-color:#9bb8c8; }
.metric-label { display:block; color:#a4b59f; text-transform:uppercase; font-size:9px; letter-spacing:1.4px; font-weight:600; }
.metric-value { display:block; color:#eef0e5; font-size:32px; font-weight:450; font-variant-numeric:tabular-nums; letter-spacing:-1px; line-height:1.65; }
.metric-unit { color:#b0c98e; font-size:11px; font-weight:400; letter-spacing:0; margin-left:7px; }
.metric-caption { color:#9fb4b3; font-size:11px; }
.plant-caption { color:#889d90; font-size:10px; margin:10px 0 22px; }
.weather-strip { margin-top:18px; padding:18px 20px; border:1px solid #34423b; border-radius:10px; background:#16211e; }
#weather { font-size:11px; color:#a6baab; line-height:1.8; overflow-wrap:anywhere; }
#weather p { margin:0 0 5px; } #weather p:last-child { margin:0; }
a { color:#c6dc9c; text-decoration:none; } a:hover { text-decoration:underline; }
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
#engineering { padding-left:0; padding-top:24px; }
#detail-tab { font-size:11px; } #detail-tab .tab { padding:15px 8px!important; }
#plot { border:1px solid #34423b; border-radius:10px; overflow:hidden; margin-bottom:20px; }
.Select-control { border-radius:7px!important; font-size:12px; }
.settings { background:#16211f; border-color:#34423b; }.settings summary { color:#d2deca; }
#technical th { background:#1b2a24; color:#b5c69e; } #technical td { border-color:#2a3a30; }
#technical tr:nth-child(even) { background:#17241f; }
@media(min-width:1600px) { .workspace-grid { grid-template-columns:minmax(0,1fr) 320px; }.scene-frame { height:720px; } }
@media(max-width:1100px) { .viewer-shell { padding:0 22px 24px; }.workspace-grid { grid-template-columns:minmax(0,1fr) 260px; gap:14px; }
 .control-console { padding:16px; }.app-masthead nav { gap:20px; }.scene-scale>span:last-child { display:none; }
 .heading-caption { max-width:440px; }.metric-card { padding:15px; }.metric-value { font-size:27px; }
}
@media(max-width:850px) {
 .workspace-grid { grid-template-columns:1fr; }.control-console { display:grid; grid-template-columns:1fr 1fr; gap:0 24px; }
 .console-heading { grid-column:1/-1; }.control-console>.control-label,.mechanism-status,.command-row,.sequence-caption { grid-column:1; }
 .control-console .view-toolbar { grid-column:2; grid-row:2/7; border-top:0; padding-top:0; }
 .system-design { grid-column:1/-1; }.site-chip { display:none; }.scene-frame { height:540px; }
 .app-masthead nav { display:none; }.viewer-heading h2 { font-size:32px; }
}
@media(max-width:520px) {
 .viewer-shell { padding:0 14px 24px; }.app-masthead { min-height:68px; margin-bottom:24px; gap:10px; }
 .brand { font-size:18px; gap:8px; }.brand-symbol { width:33px; height:33px; font-size:24px; }
 .simulation-badge { font-size:7px; padding:6px 8px; letter-spacing:.6px; }.viewer-heading h2 { font-size:29px; }
 .viewer-heading { margin-bottom:20px; }.heading-caption { font-size:11px; }
 .metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }.metric-card { padding:13px; }
 .metric-value { font-size:26px; }.metric-unit { font-size:9px; }.metric-caption { font-size:9px; line-height:1.6; display:block; }
 .metric-label { font-size:8px; letter-spacing:.9px; }.metric-card:after { right:12px; top:14px; width:4px; height:4px; }
 .scene-frame { height:420px; }.section-heading { padding:14px; }.section-meta { font-size:7px; letter-spacing:.7px; }
 .scene-label { top:12px; left:12px; font-size:8px; padding:6px; letter-spacing:1px; }
 .equipment-inspector { width:252px; right:8px; top:45px; }.hmi-enclosure { padding:10px; }
 .equipment-inspector>summary { font-size:8px; padding:7px; }.scene-note { font-size:8px; }
 .camera-help { font-size:9px; line-height:1.7; }.scene-bottom { padding:8px 12px; }
 .control-console { display:block; padding:18px; }.control-console .view-toolbar { border-top:1px solid #344139; padding-top:18px; }
 .drag-tools { gap:15px; } #detail-tab .tab { font-size:9px; padding:12px 5px!important; }
 #technical { overflow-x:auto; } #technical td { padding:9px; } .export-row .control { width:100%; text-align:left; }
 .developer-banner { flex-direction:column; gap:5px; }.weather-strip { padding:15px; }
}
@media(prefers-reduced-motion:reduce) { html { scroll-behavior:auto; }.control { transition:none; } }
"""


def index_template():
    # Dash owns rendering; its local fan helper is served through the assets API.
    return """<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>
{%favicon%}{%css%}<style>"""+VIEWER_CSS+"""</style></head><body>
{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""
