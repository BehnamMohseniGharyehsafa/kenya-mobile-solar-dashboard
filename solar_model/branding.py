"""Developer attribution shared by the local and public dashboards."""
from dash import html

DEVELOPER="Behnam Mohseni Gharyehsafa"
QUALIFICATION="PhD in Electronic Engineering"
EMAIL="Mohseni.Gharyehsafa.Behnam@gmail.com"


def developer_banner():
    return html.Header([html.Strong("Developer: "+DEVELOPER),html.Span(QUALIFICATION),
        html.A(EMAIL,href="mailto:"+EMAIL)],className="developer-banner")
