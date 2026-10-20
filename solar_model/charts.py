"""Interactive charts authored entirely through Plotly's Python API."""
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

COLORS = {"solar": "#f4b657", "battery": "#53c8a4", "load": "#73b8eb",
    "loss": "#ed817d", "muted": "#8b9da8", "purple": "#b8a0e5"}


def style(fig, height=360, y_title=None):
    fig.update_layout(template="plotly_dark", height=height, margin=dict(l=15, r=20, t=35, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial", size=12), hovermode="x unified",
        legend=dict(orientation="h", y=1.15, x=0),
        colorway=list(COLORS.values()))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(140,160,175,0.13)", title=y_title)
    return fig


def energy_profile(frame):
    fig = go.Figure()
    series = [("pv_dc_kw", "PV → DC bus", "solar"), ("user_served_kw", "User load served · AC", "load"),
        ("battery_discharge_kw", "Battery discharge · DC", "battery"),
        ("battery_charge_kw", "Battery charge · DC", "purple"),
        ("curtailed_kw", "Curtailed · DC", "muted"), ("unserved_kw", "Unserved user load · AC", "loss")]
    for col, label, color in series:
        fig.add_trace(go.Scatter(x=frame.index, y=frame[col], name=label,
            line=dict(color=COLORS[color], width=2), hovertemplate="%{y:.2f} kW<extra></extra>"))
    fig.update_xaxes(title="Local time · EAT (UTC+3)")
    return style(fig, 380, "Power (kW)")


def storage_temperature(frame, c):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=frame.index, y=frame.soc * 100, name="Battery SOC",
        line=dict(color=COLORS["battery"], width=2.5)), secondary_y=False)
    for col, name, color in [("battery_temp_c", "Battery", "solar"), ("room_temp_c", "Container", "loss"), ("temp_air", "Ambient", "muted")]:
        fig.add_trace(go.Scatter(x=frame.index, y=frame[col], name=name,
            line=dict(color=COLORS[color], width=1.5)), secondary_y=True)
    fig.add_hline(y=c.soc_reserve * 100, line_dash="dot", line_color=COLORS["battery"], secondary_y=False)
    fig.update_yaxes(title="State of charge (%)", range=[0, 100], secondary_y=False)
    fig.update_yaxes(title="Temperature (°C)", secondary_y=True)
    fig.update_xaxes(title="Local time · EAT (UTC+3)")
    return style(fig, 350)


def monthly_energy(result):
    dt = (result.index[1] - result.index[0]).total_seconds() / 3600
    monthly = result.groupby(result.index.month)[["pv_dc_kw", "user_served_kw", "unserved_kw", "cooling_kw", "curtailed_kw"]].sum() * dt
    fig = go.Figure()
    for col, name, color in [("pv_dc_kw", "PV DC", "solar"), ("user_served_kw", "Users served AC", "load"),
        ("curtailed_kw", "Curtailed DC", "muted"), ("unserved_kw", "Unserved AC", "loss")]:
        fig.add_trace(go.Bar(x=[__import__("calendar").month_abbr[i] for i in monthly.index], y=monthly[col],
            name=name, marker_color=COLORS[color]))
    fig.update_layout(barmode="group")
    return style(fig, 350, "Energy (kWh / month)")


def energy_flow(s):
    initial = max(-s["net_storage_kwh"], 0)
    stored = max(s["net_storage_kwh"], 0)
    labels = ["PV at DC bus", "Net storage draw", "System", "User loads AC", "Auxiliaries AC",
        "Curtailed DC", "Conversion losses", "Net storage increase"]
    sources = [0, 1, 2, 2, 2, 2, 2]
    targets = [2, 2, 3, 4, 5, 6, 7]
    values = [s["pv_dc_kwh"], initial, s["user_served_kwh"], s["aux_served_kwh"],
        s["curtailed_kwh"], s["inverter_loss_kwh"] + s["battery_loss_kwh"], stored]
    fig = go.Figure(go.Sankey(arrangement="snap", node=dict(label=labels, pad=20, thickness=15,
        color=[COLORS["solar"], COLORS["battery"], COLORS["muted"], COLORS["load"], COLORS["purple"], COLORS["muted"], COLORS["loss"], COLORS["battery"]]),
        link=dict(source=sources, target=targets, value=values,
            hovertemplate="%{source.label} → %{target.label}<br>%{value:.1f} kWh<extra></extra>")))
    return style(fig, 340)


def sun_path(day, row):
    fig = go.Figure()
    light = day[day.sun_elevation_deg > 0]
    fig.add_trace(go.Scatterpolar(theta=light.sun_azimuth_deg, r=90 - light.sun_elevation_deg,
        mode="lines", name="Sun path", line=dict(color=COLORS["solar"], width=3),
        customdata=light.index.strftime("%H:%M"), hovertemplate="%{customdata}<br>Azimuth %{theta:.1f}°<extra></extra>"))
    if row.sun_elevation_deg > 0:
        fig.add_trace(go.Scatterpolar(theta=[row.sun_azimuth_deg], r=[90 - row.sun_elevation_deg],
            mode="markers", marker=dict(color=COLORS["solar"], size=15), name="Sun now"))
    fig.add_trace(go.Scatterpolar(theta=[row.surface_azimuth_deg], r=[row.surface_tilt_deg],
        mode="markers", marker=dict(color=COLORS["load"], size=12, symbol="diamond"), name="Panel normal"))
    fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)",
        radialaxis=dict(range=[0, 90], tickvals=[0, 30, 60, 90], ticktext=["Zenith", "60° elev.", "30° elev.", "Horizon"]),
        angularaxis=dict(rotation=90, direction="clockwise", tickvals=[0,90,180,270], ticktext=["N", "E", "S", "W"])))
    return style(fig, 370)


def _box(fig, origin, size, color, name):
    x,y,z = origin
    a,b,h = size
    vertices = np.array([[x,y,z],[x+a,y,z],[x+a,y+b,z],[x,y+b,z],
        [x,y,z+h],[x+a,y,z+h],[x+a,y+b,z+h],[x,y+b,z+h]])
    faces = np.array([[0,1,2],[0,2,3],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
        [1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
    fig.add_trace(go.Mesh3d(x=vertices[:,0], y=vertices[:,1], z=vertices[:,2],
        i=faces[:,0], j=faces[:,1], k=faces[:,2], color=color, opacity=0.95, name=name,
        hovertemplate=name+"<extra></extra>", showlegend=False))


def deployment(c, row):
    """Illustrative detached tracking table next to the power container, not CAD."""
    fig = go.Figure()
    length, width, height = c.dimensions
    _box(fig, (-length/2, -width/2, 0), (length,width,height), "#b3c1c7", "Power container")
    _box(fig, (-length/2+0.2,-width/2-0.04,0.2), (length*0.28,0.08,2.3), COLORS["battery"], "Battery compartment · conceptual")
    tilt = np.radians(row.surface_tilt_deg)
    az = np.radians(row.surface_azimuth_deg)
    normal = np.array([np.sin(tilt)*np.sin(az), np.sin(tilt)*np.cos(az), np.cos(tilt)])
    u = np.array([np.cos(az), -np.sin(az), 0])
    v = np.cross(normal, u)
    # Representative 2x3-module table. Real array consists of repeated tables.
    center = np.array([0, width/2 + 5.0, 3.0])
    for a in range(3):
        for b in range(2):
            pos = center + (a-1)*1.16*u + (b-.5)*2.30*v
            vertices = np.array([pos + sx*.56*u + sy*1.12*v for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]])
            fig.add_trace(go.Mesh3d(x=vertices[:,0], y=vertices[:,1], z=vertices[:,2], i=[0,0], j=[1,2], k=[2,3],
                color="#3686b4", opacity=0.98, showlegend=False,
                hovertemplate=f"Representative tracking table<br>Tilt {row.surface_tilt_deg:.1f}°<extra></extra>"))
    fig.add_trace(go.Scatter3d(x=[center[0],center[0]],y=[center[1],center[1]],z=[0,center[2]],
        mode="lines",line=dict(color=COLORS["muted"],width=8),showlegend=False,hoverinfo="skip"))
    if row.sun_elevation_deg > 0:
        elev, saz = np.radians(row.sun_elevation_deg), np.radians(row.sun_azimuth_deg)
        sun = center + 7*np.array([np.cos(elev)*np.sin(saz),np.cos(elev)*np.cos(saz),np.sin(elev)])
        fig.add_trace(go.Scatter3d(x=[center[0],sun[0]],y=[center[1],sun[1]],z=[center[2],sun[2]],
            mode="lines+markers",marker=dict(size=[0,9],color=COLORS["solar"]),
            line=dict(color=COLORS["solar"],width=3,dash="dash"),name="Sun direction",showlegend=False))
    fig.update_layout(scene=dict(xaxis_title="East (m)",yaxis_title="North (m)",zaxis_title="Height (m)",
        aspectmode="data",camera=dict(eye=dict(x=1.6,y=-1.7,z=1.0)),
        xaxis=dict(showbackground=False),yaxis=dict(showbackground=False),zaxis=dict(showbackground=False)))
    return style(fig, 340)


def controller_timeline(day):
    lanes = [("tracker_state", "Tracker"), ("ems_state", "Energy management"), ("cooling_state", "Cooling")]
    fig = go.Figure()
    states = sorted(set().union(*(set(day[c]) for c,_ in lanes)))
    palette = [COLORS["battery"], COLORS["solar"], COLORS["load"], COLORS["purple"], COLORS["loss"], COLORS["muted"]]
    color_map = {s: palette[i%len(palette)] for i,s in enumerate(states)}
    for col, label in lanes:
        fig.add_trace(go.Scatter(x=day.index,y=[label]*len(day),mode="markers",
            marker=dict(color=[color_map[s] for s in day[col]],symbol="square",size=12),
            customdata=day[col],hovertemplate="%{x|%H:%M}<br>%{customdata}<extra></extra>",name=label,showlegend=False))
    return style(fig, 220)
