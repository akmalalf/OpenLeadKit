"""Shared Streamlit startup, styling, and database helpers."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from html import escape
from pathlib import Path
from urllib.parse import quote

import streamlit as st
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from openleadkit.config import Settings, get_settings
from openleadkit.database import (
    DatabaseHealth,
    build_engine,
    inspect_database,
    session_scope,
)
from openleadkit.exceptions import DatabaseError


def _lucide_data_uri(elements: str) -> str:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' "
        "viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' "
        "stroke-linecap='round' stroke-linejoin='round'>"
        f"{elements}</svg>"
    )
    return f"data:image/svg+xml,{quote(svg, safe='')}"


LUCIDE_SIDEBAR_ICONS = {
    "__OLK_ICON_DASHBOARD__": _lucide_data_uri(
        "<rect width='7' height='9' x='3' y='3' rx='1'/>"
        "<rect width='7' height='5' x='14' y='3' rx='1'/>"
        "<rect width='7' height='9' x='14' y='12' rx='1'/>"
        "<rect width='7' height='5' x='3' y='16' rx='1'/>"
    ),
    "__OLK_ICON_SEARCH__": _lucide_data_uri(
        "<circle cx='11' cy='11' r='8'/><path d='m21 21-4.3-4.3'/>"
    ),
    "__OLK_ICON_RESULTS__": _lucide_data_uri(
        "<path d='M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 21H5a2 2 0 0 1-2-2v-4"
        "'/><path d='M9 21h10a2 2 0 0 0 2-2v-4M3 12h18M12 3v18'/>"
    ),
    "__OLK_ICON_REVIEW__": _lucide_data_uri(
        "<rect width='14' height='18' x='5' y='3' rx='2'/><path d='M9 3V1h6v2m-6 10 2 2 4-4'/>"
    ),
    "__OLK_ICON_DUPLICATES__": _lucide_data_uri(
        "<rect width='14' height='14' x='8' y='8' rx='2'/>"
        "<path d='M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2'/>"
    ),
    "__OLK_ICON_EXPORT__": _lucide_data_uri(
        "<path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/>"
        "<path d='M14 2v6h6M12 18v-6m-3 3 3 3 3-3'/>"
    ),
    "__OLK_ICON_HISTORY__": _lucide_data_uri(
        "<path d='M3 12a9 9 0 1 0 3-6.7L3 8'/><path d='M3 3v5h5m4-1v5l3 2'/>"
    ),
    "__OLK_ICON_SETTINGS__": _lucide_data_uri(
        "<path d='M4 21v-7m0-4V3m8 18v-9m0-4V3m8 18v-5m0-4V3'/><path d='M1 14h6m2-6h6m2 8h6'/>"
    ),
}

CSS = """
<style>
:root {
  --olk-canvas:#f7f8f4;
  --olk-surface:#ffffff;
  --olk-surface-muted:#eef2ec;
  --olk-ink:#18231d;
  --olk-muted:#657269;
  --olk-line:#dce4dd;
  --olk-line-strong:#bdc9c0;
  --olk-accent:#246b49;
  --olk-accent-strong:#174f35;
  --olk-accent-soft:#dcece2;
  --olk-warning:#8a5d18;
  --olk-danger:#a43e37;
  --olk-shadow:0 1rem 2.6rem rgba(32, 72, 49, .08);
  --olk-radius-sm:.45rem;
  --olk-radius-md:.75rem;
  --olk-radius-lg:1.15rem;
}
html { scroll-behavior:smooth; }
html, body {
  color:var(--olk-ink);
  font-family:"Source Sans", ui-sans-serif, system-ui, sans-serif;
}
[data-testid="stAppViewContainer"] {
  color:var(--olk-ink);
  font-family:"Source Sans", ui-sans-serif, system-ui, sans-serif;
}
body {
  font-feature-settings:"kern" 1, "liga" 1;
  text-rendering:optimizeLegibility;
}
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 82% -12%, rgba(36,107,73,.08), transparent 31rem),
    var(--olk-canvas);
}
[data-testid="stHeader"] {
  background:rgba(247,248,244,.84);
  backdrop-filter:blur(12px);
}
[data-testid="stSidebar"] {
  background:var(--olk-surface-muted);
  border-right:1px solid var(--olk-line);
}
[data-testid="stSidebarContent"] {
  display:flex;
  flex-direction:column;
  min-height:100%;
}
[data-testid="stSidebarHeader"] {
  min-height:4rem;
}
[data-testid="stSidebarLogo"] {
  aspect-ratio:5 / 1;
  height:2rem !important;
  object-fit:contain;
  object-position:left center;
  width:10rem;
}
[data-testid="stSidebarNav"] { padding-top:0; }
[data-testid="stSidebarNav"] ul {
  gap:.1rem;
}
[data-testid="stSidebarNav"] li a {
  align-items:center;
  color:#526057;
  display:flex;
  font-size:.84rem;
  gap:.55rem;
  min-height:2.75rem;
  overflow:hidden;
  padding:.55rem .65rem;
  transition:
    background-color .12s ease,
    color .12s ease;
}
[data-testid="stSidebarNav"] li a::before {
  background-color:currentColor;
  content:"";
  flex:0 0 1.05rem;
  height:1.05rem;
  mask-image:var(--olk-nav-icon);
  mask-position:center;
  mask-repeat:no-repeat;
  mask-size:contain;
  width:1.05rem;
  -webkit-mask-image:var(--olk-nav-icon);
  -webkit-mask-position:center;
  -webkit-mask-repeat:no-repeat;
  -webkit-mask-size:contain;
}
[data-testid="stSidebarNav"] li a[href$="/"]::before {
  --olk-nav-icon:url("__OLK_ICON_DASHBOARD__");
}
[data-testid="stSidebarNav"] li a[href$="/Business_Search"]::before {
  --olk-nav-icon:url("__OLK_ICON_SEARCH__");
}
[data-testid="stSidebarNav"] li a[href$="/Search_Results"]::before {
  --olk-nav-icon:url("__OLK_ICON_RESULTS__");
}
[data-testid="stSidebarNav"] li a[href$="/Lead_Review"]::before {
  --olk-nav-icon:url("__OLK_ICON_REVIEW__");
}
[data-testid="stSidebarNav"] li a[href$="/Duplicates"]::before {
  --olk-nav-icon:url("__OLK_ICON_DUPLICATES__");
}
[data-testid="stSidebarNav"] li a[href$="/CRM_Export"]::before {
  --olk-nav-icon:url("__OLK_ICON_EXPORT__");
}
[data-testid="stSidebarNav"] li a[href$="/History"]::before {
  --olk-nav-icon:url("__OLK_ICON_HISTORY__");
}
[data-testid="stSidebarNav"] li a[href$="/Settings"]::before {
  --olk-nav-icon:url("__OLK_ICON_SETTINGS__");
}
[data-testid="stSidebarNav"] li a:hover {
  background:rgba(24,35,29,.045);
  color:var(--olk-ink);
}
[data-testid="stSidebarNav"] li a[aria-current="page"] {
  background:rgba(24,35,29,.075);
  box-shadow:none;
  color:var(--olk-ink);
  font-weight:600;
}
[data-testid="stSidebarNav"] li a:focus-visible {
  box-shadow:none;
  outline:2px solid #657269;
  outline-offset:2px;
}
[data-testid="stSidebarNavSeparator"] {
  color:#59675e;
  font-size:.68rem;
  font-weight:650;
  letter-spacing:.1em;
  margin-top:1rem;
  text-transform:uppercase;
}
[data-testid="stSidebarUserContent"] {
  margin-top:auto;
  padding-bottom:1.75rem;
}
[data-testid="stMainBlockContainer"] {
  max-width:84rem;
  padding-top:3.5rem;
  padding-bottom:5rem;
}
h1, h2, h3 { text-wrap:balance; }
h1 {
  font-size:clamp(2.35rem, 5vw, 4rem) !important;
  font-weight:650 !important;
  letter-spacing:-.055em !important;
  line-height:.98 !important;
}
h2 {
  font-size:1.55rem !important;
  font-weight:600 !important;
  letter-spacing:-.035em !important;
}
h3 {
  font-size:1.12rem !important;
  font-weight:600 !important;
  letter-spacing:-.02em !important;
}
p { text-wrap:pretty; }
a { color:var(--olk-accent-strong); }
code, pre, [data-testid="stMetricValue"] {
  font-family:ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace !important;
  font-variant-numeric:tabular-nums;
}
.olk-skip {
  background:var(--olk-ink);
  border-radius:0 0 var(--olk-radius-sm) var(--olk-radius-sm);
  color:white !important;
  left:1rem;
  padding:.55rem .8rem;
  position:fixed;
  top:-4rem;
  transition:top .18s ease;
  z-index:3;
}
.olk-skip:focus { top:0; }
.olk-sidebar-foot {
  border-top:1px solid var(--olk-line);
  color:#526057;
  display:grid;
  font-size:.75rem;
  gap:.25rem;
  line-height:1.5;
  margin:.5rem .35rem 0;
  padding:.9rem 0 0;
}
.olk-sidebar-foot strong {
  color:#46534a;
  font-weight:600;
}
.olk-page-head {
  border-bottom:1px solid var(--olk-line);
  margin-bottom:2rem;
  padding-bottom:1.75rem;
}
.olk-page-head--action {
  border-bottom:0;
  margin-bottom:0;
  padding-bottom:0;
}
.olk-page-head-rule {
  border-bottom:1px solid var(--olk-line);
  margin-bottom:2rem;
  padding-top:1.5rem;
}
.olk-kicker {
  align-items:center;
  color:var(--olk-accent);
  display:flex;
  font-family:ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace;
  font-size:.68rem;
  font-weight:500;
  gap:.55rem;
  letter-spacing:.11em;
  margin-bottom:.75rem;
  text-transform:uppercase;
}
.olk-kicker::before {
  background:var(--olk-accent);
  content:"";
  height:1px;
  width:1.6rem;
}
.olk-page-title {
  color:var(--olk-ink);
  font-size:clamp(2.35rem, 5vw, 4rem);
  font-weight:650;
  letter-spacing:-.055em;
  line-height:.98;
  margin:0;
}
.olk-lead {
  color:var(--olk-muted);
  font-size:1.03rem;
  line-height:1.6;
  margin-top:1rem;
  max-width:64ch;
}
.olk-section-head {
  align-items:end;
  display:flex;
  gap:1rem;
  justify-content:space-between;
  margin:2.5rem 0 1rem;
}
.olk-section-title {
  color:var(--olk-ink);
  font-size:1.22rem;
  font-weight:600;
  letter-spacing:-.025em;
  line-height:1.2;
  margin:0;
}
.olk-section-copy {
  color:var(--olk-muted);
  font-size:.86rem;
  line-height:1.45;
  margin-top:.3rem;
  max-width:60ch;
}
.olk-section-tag {
  color:var(--olk-muted);
  flex:none;
  font-family:ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace;
  font-size:.68rem;
  letter-spacing:.05em;
}
.olk-empty {
  background:rgba(255,255,255,.58);
  border:1px dashed var(--olk-line-strong);
  border-radius:var(--olk-radius-lg);
  margin-top:1rem;
  padding:2.1rem;
}
.olk-empty-mark {
  align-items:center;
  background:var(--olk-accent-soft);
  border-radius:.6rem;
  color:var(--olk-accent-strong);
  display:flex;
  font-family:ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace;
  font-size:.68rem;
  height:2.25rem;
  justify-content:center;
  letter-spacing:.08em;
  margin-bottom:1.2rem;
  width:2.25rem;
}
.olk-empty-title {
  font-size:1.05rem;
  font-weight:600;
  letter-spacing:-.018em;
}
.olk-empty-copy {
  color:var(--olk-muted);
  font-size:.9rem;
  line-height:1.55;
  margin-top:.35rem;
  max-width:55ch;
}
.olk-metric-grid {
  display:grid;
  gap:.75rem;
  grid-template-columns:repeat(auto-fit, minmax(min(100%, 10.5rem), 1fr));
}
.olk-metric {
  background:rgba(255,255,255,.64);
  border:1px solid var(--olk-line);
  border-radius:var(--olk-radius-md);
  min-width:0;
  padding:1rem 1.05rem 1.1rem;
  transition:border-color .2s ease, box-shadow .2s ease, transform .2s ease;
}
.olk-metric:hover {
  border-color:var(--olk-line-strong);
  box-shadow:var(--olk-shadow);
  transform:translateY(-2px);
}
.olk-metric-label {
  color:var(--olk-muted);
  font-size:.78rem;
  letter-spacing:.015em;
  line-height:1.35;
  min-height:2.1em;
  overflow-wrap:anywhere;
}
.olk-metric-value {
  color:var(--olk-ink);
  font-family:ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace;
  font-size:clamp(1.4rem, 3vw, 1.75rem);
  font-variant-numeric:tabular-nums;
  font-weight:500;
  letter-spacing:-.055em;
  line-height:1.15;
  margin-top:.65rem;
  overflow-wrap:anywhere;
}
[data-testid="stMetric"] {
  background:rgba(255,255,255,.64);
  border:1px solid var(--olk-line);
  border-radius:var(--olk-radius-md);
  min-height:7.2rem;
  padding:1rem 1.05rem;
  transition:border-color .2s ease, box-shadow .2s ease, transform .2s ease;
}
[data-testid="stMetric"]:hover {
  border-color:var(--olk-line-strong);
  box-shadow:var(--olk-shadow);
  transform:translateY(-2px);
}
[data-testid="stMetricLabel"] {
  color:var(--olk-muted);
  font-size:.78rem;
  letter-spacing:.015em;
}
[data-testid="stMetricValue"] {
  color:var(--olk-ink);
  font-size:1.75rem;
  letter-spacing:-.055em;
}
.stButton button, .stDownloadButton button, .stLinkButton a {
  border-color:var(--olk-line-strong);
  border-radius:var(--olk-radius-sm);
  box-shadow:none;
  font-weight:600;
  letter-spacing:-.01em;
  min-height:2.55rem;
  transition:
    background-color .18s ease,
    border-color .18s ease,
    box-shadow .18s ease,
    color .18s ease,
    transform .18s ease;
}
.stButton button:hover, .stDownloadButton button:hover, .stLinkButton a:hover {
  border-color:var(--olk-accent);
  color:var(--olk-accent-strong);
  transform:translateY(-1px);
}
.stButton button:active, .stDownloadButton button:active, .stLinkButton a:active {
  transform:translateY(1px) scale(.985);
}
.stButton button:focus-visible, .stDownloadButton button:focus-visible,
.stLinkButton a:focus-visible {
  box-shadow:0 0 0 .2rem rgba(36,107,73,.22);
  outline:2px solid var(--olk-accent);
  outline-offset:2px;
}
.stButton button[kind="primary"] {
  background:var(--olk-accent);
  border-color:var(--olk-accent);
  color:white;
}
.stButton button[kind="primary"]:hover {
  background:var(--olk-accent-strong);
  border-color:var(--olk-accent-strong);
  color:white;
}
.stButton button:disabled, .stDownloadButton button:disabled {
  transform:none;
}
[data-baseweb="input"] > div, [data-baseweb="select"] > div,
[data-baseweb="textarea"] > div, [data-testid="stNumberInputContainer"] {
  background:rgba(255,255,255,.82);
  border-color:var(--olk-line-strong) !important;
  border-radius:var(--olk-radius-sm) !important;
  transition:border-color .18s ease, box-shadow .18s ease;
}
[data-baseweb="input"] > div:focus-within, [data-baseweb="select"] > div:focus-within,
[data-baseweb="textarea"] > div:focus-within, [data-testid="stNumberInputContainer"]:focus-within {
  border-color:var(--olk-accent) !important;
  box-shadow:0 0 0 .18rem rgba(36,107,73,.12);
}
[data-testid="stWidgetLabel"] p {
  color:#46534a;
  font-size:.8rem;
  font-weight:500;
}
[data-testid="stExpander"] {
  background:rgba(255,255,255,.56);
  border-color:var(--olk-line);
  border-radius:var(--olk-radius-md);
  overflow:hidden;
}
[data-testid="stVerticalBlockBorderWrapper"] {
  background:rgba(255,255,255,.66);
  border-color:var(--olk-line) !important;
  border-radius:var(--olk-radius-lg);
  box-shadow:0 .75rem 2rem rgba(32,72,49,.045);
}
[data-testid="stAlert"] {
  border:none;
  border-left:.24rem solid currentColor;
  border-radius:var(--olk-radius-sm);
}
[data-testid="stDataFrame"], [data-testid="stTable"] {
  border:1px solid var(--olk-line);
  border-radius:var(--olk-radius-md);
  box-shadow:0 .6rem 1.8rem rgba(32,72,49,.04);
  overflow:hidden;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  border-bottom:1px solid var(--olk-line);
  gap:1.2rem;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  color:var(--olk-muted);
  font-weight:500;
  padding-left:0;
  padding-right:0;
}
[data-testid="stTabs"] [aria-selected="true"] { color:var(--olk-accent-strong); }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background:var(--olk-accent); }
[data-testid="stProgress"] > div > div { background:var(--olk-accent); }
[data-testid="stStatusWidget"] {
  border-color:var(--olk-line);
  border-radius:var(--olk-radius-md);
}
hr {
  border-color:var(--olk-line) !important;
  margin:2.5rem 0 !important;
}
.olk-note {
  background:var(--olk-accent-soft);
  border-left:3px solid var(--olk-accent);
  border-radius:0 var(--olk-radius-sm) var(--olk-radius-sm) 0;
  padding:.75rem 1rem;
}
.olk-pager-status {
  align-items:center;
  display:flex;
  flex-direction:column;
  justify-content:center;
  min-height:2.55rem;
  text-align:center;
}
.olk-pager-status strong {
  color:var(--olk-ink);
  font-family:ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace;
  font-size:.9rem;
  font-variant-numeric:tabular-nums;
  font-weight:500;
}
.olk-pager-status span {
  color:var(--olk-muted);
  font-size:.68rem;
  letter-spacing:.06em;
  text-transform:uppercase;
}
.olk-visually-hidden {
  height:1px;
  margin:-1px;
  overflow:hidden;
  padding:0;
  position:absolute;
  width:1px;
  clip:rect(0 0 0 0);
  white-space:nowrap;
}
.olk-search-table-wrap {
  background:rgba(255,255,255,.62);
  border:1px solid var(--olk-line);
  border-radius:var(--olk-radius-md);
  margin-top:.4rem;
  overflow-x:auto;
  scrollbar-color:var(--olk-line-strong) transparent;
}
.olk-search-table {
  border-collapse:collapse;
  min-width:43rem;
  table-layout:fixed;
  width:100%;
}
.olk-search-table th {
  background:rgba(238,242,236,.72);
  border-bottom:1px solid var(--olk-line);
  color:var(--olk-muted);
  font-size:.66rem;
  font-weight:600;
  letter-spacing:.065em;
  padding:.68rem .75rem;
  text-align:left;
  text-transform:uppercase;
}
.olk-search-table th:first-child { width:2.6rem; }
.olk-search-table th:nth-child(2) { width:21%; }
.olk-search-table th:nth-child(3) { width:28%; }
.olk-search-table th:nth-child(4) { width:21%; }
.olk-search-table th:nth-child(5) { width:24%; }
.olk-search-table td {
  border-bottom:1px solid var(--olk-line);
  color:var(--olk-ink);
  font-size:.78rem;
  line-height:1.35;
  overflow-wrap:anywhere;
  padding:.78rem .75rem;
  vertical-align:middle;
}
.olk-search-table tbody tr:last-child td { border-bottom:0; }
.olk-search-table tbody tr {
  transition:background-color .18s ease;
}
.olk-search-table tbody tr:hover {
  background:rgba(220,236,226,.32);
}
.olk-search-index {
  color:var(--olk-accent);
  font-family:ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace;
  font-size:.7rem;
}
.olk-search-category { font-weight:600; }
.olk-search-area { color:var(--olk-muted) !important; }
.olk-search-results {
  display:grid;
  gap:.08rem .38rem;
  grid-template-columns:auto 1fr;
}
.olk-search-results strong {
  color:var(--olk-ink);
  font-family:ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace;
  font-size:.72rem;
  font-variant-numeric:tabular-nums;
  font-weight:500;
  text-align:right;
}
.olk-search-results span {
  color:var(--olk-muted);
  font-size:.68rem;
}
.olk-search-time {
  display:grid;
  gap:.12rem;
}
.olk-search-time strong {
  color:var(--olk-ink);
  font-size:.73rem;
  font-weight:500;
}
.olk-search-time span {
  color:var(--olk-muted);
  font-family:ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace;
  font-size:.65rem;
  font-variant-numeric:tabular-nums;
}
@media (max-width: 50rem) {
  [data-testid="stMainBlockContainer"] { padding-top:2.25rem; }
  .olk-page-head { margin-bottom:1.5rem; padding-bottom:1.35rem; }
  .olk-section-head { align-items:start; flex-direction:column; gap:.4rem; }
  [data-testid="stMetric"] { min-height:6.3rem; }
  .olk-search-table-wrap { margin-right:-.35rem; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior:auto; }
  *, *::before, *::after {
    scroll-behavior:auto !important;
    transition-duration:.01ms !important;
  }
}
</style>
"""

for icon_placeholder, icon_data_uri in LUCIDE_SIDEBAR_ICONS.items():
    CSS = CSS.replace(icon_placeholder, icon_data_uri)


def setup_page(
    kicker: str,
    title: str,
    description: str,
    *,
    action_label: str | None = None,
    action_key: str | None = None,
) -> bool:
    action_modifier = " olk-page-head--action" if action_label else ""
    header_markup = (
        '<a class="olk-skip" href="#olk-main">Skip to content</a>'
        f'<header class="olk-page-head{action_modifier}" id="olk-main">'
        f'<div class="olk-kicker">{escape(kicker)}</div>'
        f'<h1 class="olk-page-title">{escape(title)}</h1>'
        f'<div class="olk-lead">{escape(description)}</div>'
        "</header>"
    )
    if not action_label:
        st.markdown(header_markup, unsafe_allow_html=True)
        return False

    heading, action = st.columns([5, 1], gap="large", vertical_alignment="center")
    heading.markdown(header_markup, unsafe_allow_html=True)
    clicked = action.button(
        action_label,
        key=action_key,
        use_container_width=True,
    )
    st.markdown('<div class="olk-page-head-rule"></div>', unsafe_allow_html=True)
    return clicked


def render_sidebar_footer(version: str) -> None:
    st.sidebar.markdown(
        f"""
        <footer class="olk-sidebar-foot">
          <strong>OpenLeadKit v{escape(version)}</strong>
          <span>Data © OpenStreetMap contributors</span>
          <span>Open source · Apache-2.0</span>
        </footer>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, description: str | None = None, tag: str | None = None) -> None:
    copy = f'<div class="olk-section-copy">{escape(description)}</div>' if description else ""
    tag_markup = f'<div class="olk-section-tag">{escape(tag)}</div>' if tag else ""
    st.markdown(
        (
            '<div class="olk-section-head">'
            "<div>"
            f'<h2 class="olk-section-title">{escape(title)}</h2>'
            f"{copy}"
            "</div>"
            f"{tag_markup}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def empty_state(title: str, description: str, marker: str = "—") -> None:
    st.markdown(
        (
            '<section class="olk-empty">'
            f'<div class="olk-empty-mark" aria-hidden="true">{escape(marker)}</div>'
            f'<div class="olk-empty-title">{escape(title)}</div>'
            f'<div class="olk-empty-copy">{escape(description)}</div>'
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def metric_grid(metrics: Sequence[tuple[str, object]]) -> None:
    items = []
    for label, value in metrics:
        formatted_value = f"{value:,}" if isinstance(value, int) else str(value)
        items.append(
            '<article class="olk-metric">'
            f'<div class="olk-metric-label">{escape(label)}</div>'
            f'<div class="olk-metric-value">{escape(formatted_value)}</div>'
            "</article>"
        )
    st.markdown(
        f'<section class="olk-metric-grid">{"".join(items)}</section>',
        unsafe_allow_html=True,
    )


def load_settings_or_stop() -> Settings:
    if not Path(".env").exists():
        st.error(
            "The `.env` file is missing. Copy `.env.example` to `.env`, "
            "then configure the database connection."
        )
        st.code("cp .env.example .env")
        st.stop()
    try:
        return get_settings()
    except ValidationError as exc:
        st.error("The `.env` configuration is invalid.")
        st.code(safe_validation_error(exc))
        st.stop()
        raise AssertionError("unreachable") from exc


def safe_validation_error(error: ValidationError) -> str:
    """Format validation failures without echoing credential-bearing input values."""
    messages: list[str] = []
    for item in error.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "configuration"
        messages.append(f"{location}: {item['msg']}")
    return "\n".join(messages)


@st.cache_resource(show_spinner=False)
def get_database_engine(database_url: str) -> Engine:
    """Reuse the SQLAlchemy pool across Streamlit page reruns."""
    return build_engine(database_url)


@st.cache_data(ttl=30, show_spinner=False)
def get_database_health(database_url: str) -> DatabaseHealth:
    """Avoid repeating extension and migration checks during rapid reruns."""
    return inspect_database(get_database_engine(database_url))


@contextmanager
def db_session() -> Iterator[Session]:
    settings = load_settings_or_stop()
    try:
        engine = get_database_engine(settings.database_url)
        health = get_database_health(settings.database_url)
        if health.missing_extensions:
            st.error(
                "Required PostgreSQL extensions are missing: "
                + ", ".join(sorted(health.missing_extensions))
            )
            st.code("alembic upgrade head")
            st.stop()
        if not health.migrations_current:
            st.error("The database migrations are not current.")
            st.code("alembic upgrade head")
            st.stop()
        with session_scope(engine) as session:
            yield session
    except DatabaseError:
        st.error(
            f"The database is not accessible through `{settings.masked_database_url}`. "
            "Run the following check:"
        )
        st.code("python scripts/check_database.py")
        st.stop()


def format_error(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


def commit_and_rerun(session: Session) -> None:
    """Persist a UI mutation before Streamlit interrupts execution for a rerun."""
    session.commit()
    st.rerun()
