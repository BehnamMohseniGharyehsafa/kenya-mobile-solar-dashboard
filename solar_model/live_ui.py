"""Streamlit entry point for the persistent Python/Dash VTK field workspace."""
import streamlit as st

from .viewer_service import ViewerService


@st.cache_resource(show_spinner="Starting the interactive 3D workspace…")
def viewer_service():
    return ViewerService()


def workspace_url(config, operator_zone):
    return viewer_service().register(config,operator_zone)


def render_live_site(config):
    st.caption("FIELD SYSTEM 01 / CONTAINER DIGITAL MODEL")
    st.title("Kenya · Container field lab")
    st.write(f"**{config.site}** · {config.container_ft} ft high cube · {config.modules} modules · "
        f"{config.array_kwp:.1f} kWp · {config.battery_kwh:g} kWh LFP")
    url=workspace_url(config,st.context.timezone or "Europe/Dublin")
    st.link_button("Open full-size interactive workspace",url)
    st.iframe(url,height=1500)
