"""Read-only multi-network token research dashboard."""
from __future__ import annotations
import base64
from pathlib import Path
import sqlite3

from dotenv import load_dotenv
import streamlit as st

load_dotenv()

from rugradar.history import token_history
from rugradar.networks import NETWORKS, get_network
from rugradar.scanner import ScanResult, analyze_token

logo_path = Path(__file__).parent / "assets" / "logo.png"
logo_data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
st.set_page_config(page_title="RugRadar AI | Token Research", page_icon=str(logo_path), layout="wide")


def clear_result():
    st.session_state.pop("scan_result", None)


active_network = get_network(st.session_state.get("network", "base"))
st.markdown("""<style>
    .stApp {background: #08111F; color: #E7EEF9;}
    .block-container {max-width: 1080px; padding: 4.25rem 2.2rem 2rem;}
    [data-testid="stHeader"] {background: #08111F;}
    h1, h2, h3 {letter-spacing: -0.035em;}
    h1 {font-size: 2.65rem !important; font-weight: 650 !important; line-height: 1.15 !important;}
    h2, h3 {font-size: 1.15rem !important;}
    [data-testid="stCaptionContainer"] {color: #94A8C3;}
    .brand-header {display: flex; align-items: center; justify-content: space-between;
        gap: 1rem; padding-bottom: 1.65rem; border-bottom: 1px solid #20304A; margin-bottom: 2.6rem;}
    .brand {display: flex; align-items: center; gap: .8rem;}
    .brand-icon {display: block; width: 42px; height: 64px; flex-shrink: 0; object-fit: contain;}
    .brand-name {font-size: 1.3rem; font-weight: 650; letter-spacing: -.04em; line-height: 1.25;}
    .brand-name span {color: #71ADFF;}
    .brand-note {color: #94A8C3; font-size: .65rem; letter-spacing: .13em; margin-top: .25rem;}
    .network-pill {display: inline-flex; align-items: center; gap: .5rem;
        white-space: nowrap; border: 1px solid #284D7D; background: #102541;
        color: #97C4FF; border-radius: 999px; padding: .48rem .75rem;
        font-size: .65rem; font-weight: 600; letter-spacing: .1em;}
    .network-dot {height: 6px; width: 6px; border-radius: 50%; background: #71ADFF;}
    .eyebrow {color: #71ADFF; font-size: .68rem; letter-spacing: .16em;
        font-weight: 600; margin: 0 0 .7rem;}
    .hero-description {color: #94A8C3; font-size: .98rem; line-height: 1.7;
        max-width: 620px; margin: .1rem 0 1.6rem;}
    [data-testid="stForm"] {background: #0D1A2D; border: 1px solid #243650;
        border-radius: 16px; padding: 1.4rem;}
    [data-testid="stTextInput"] input {min-height: 46px; font-family: monospace; font-size: .9rem;}
    [data-testid="stTextInput"] [data-baseweb="input"] {background: #08111F; border-radius: 9px;}
    [data-testid="stFormSubmitButton"] button {min-height: 46px; border-radius: 9px;
        font-weight: 600; color: #FFFFFF; background: #286FE0; border: 1px solid #438EFF;}
    [data-testid="stFormSubmitButton"] button:hover {background: #357FF0;}
    [data-testid="stFormSubmitButton"] button:focus-visible {outline: 2px solid #A5CAFF; outline-offset: 3px;}
    [data-testid="stExpander"] {border-color: #243650; border-radius: 10px;}
    .overview-label {color: #94A8C3; font-size: .68rem; font-weight: 600;
        letter-spacing: .14em; margin: 1.8rem 0 .75rem;}
    .st-key-risk_card, .st-key-liquidity_card, .st-key-volume_card {
        background: #0D1A2D; border: 1px solid #243650; border-radius: 14px;
        min-height: 190px; padding: 1.2rem;}
    [data-testid="stMetricLabel"] {color: #A3B5CD; font-size: .8rem;}
    [data-testid="stMetricValue"] {font-size: 1.85rem; font-weight: 600; letter-spacing: -.04em;}
    .st-key-risk_card [data-testid="stMetricValue"] {color: #97C4FF;}
    .empty-state {border: 1px dashed #2B3D56; border-radius: 14px;
        padding: 1.5rem; margin-top: 1.25rem; text-align: center;}
    .empty-title {color: #D3E0F2; font-size: .93rem; font-weight: 500; margin-bottom: .35rem;}
    .empty-description {color: #94A8C3; font-size: .83rem; line-height: 1.6;}
    .dashboard-footer {border-top: 1px solid #20304A; margin-top: 2.3rem;
        padding-top: 1rem; color: #94A8C3; font-size: .73rem; line-height: 1.8;}
    @media (max-width: 640px) {
        .block-container {padding: 4.25rem 1rem 1.5rem;}
        .brand-header {gap: .6rem; margin-bottom: 2rem;}
        .brand-note {font-size: .55rem; letter-spacing: .07em;}
        .brand-name {font-size: 1.1rem;}
        .brand-icon {width: 36px; height: 54px;}
        .network-pill {font-size: .55rem; padding: .4rem .55rem; letter-spacing: .04em;}
        h1 {font-size: 2rem !important;}
        [data-testid="stForm"] {padding: 1rem;}
        .st-key-risk_card, .st-key-liquidity_card, .st-key-volume_card {min-height: 155px;}
    }
</style>""", unsafe_allow_html=True)

st.markdown(f"""
<div class="brand-header">
    <div class="brand">
        <img class="brand-icon" src="data:image/png;base64,{logo_data}" alt="RugRadar AI logo" width="42" height="64">
        <div><div class="brand-name">RugRadar <span>AI</span></div>
            <div class="brand-note">TOKEN RISK INTELLIGENCE</div></div>
    </div>
    <div class="network-pill"><span class="network-dot" aria-hidden="true"></span>{active_network.name.upper()} MAINNET</div>
</div>
<p class="eyebrow">MULTICHAIN TOKEN RESEARCH</p>
""", unsafe_allow_html=True)
st.title("A clearer view of token risk.")
st.markdown('<p class="hero-description">Review market signals, liquidity, and contract warnings in one place. '
            'Read-only analysis. No wallet connection required.</p>', unsafe_allow_html=True)

selected_network = st.selectbox("Network", list(NETWORKS), format_func=lambda key: NETWORKS[key].name,
                                key="network", on_change=clear_result)
active_network = get_network(selected_network)
st.caption("Choose the network where the token was issued. The same address can refer to different contracts on different networks.")

with st.form("scan_form"):
    input_col, button_col = st.columns([4, 1.35], vertical_alignment="bottom")
    with input_col:
        address = st.text_input("Contract address" if active_network.evm else "Token mint address",
                                placeholder="0x… · token contract" if active_network.evm else "Solana token mint address",
                                key="contract_address")
    with button_col:
        submitted = st.form_submit_button("Analyze Token", use_container_width=True, type="primary")
    with st.expander("Analysis options"):
        check_security = st.checkbox("Request GoPlus contract-security data", value=active_network.goplus_chain_id is not None,
                                      disabled=active_network.goplus_chain_id is None,
                                      help="Available on the supported EVM networks. Solana uses market data and optional configured blockchain reads. Provider data can be incomplete or unavailable.")
        st.caption(f"Optional direct blockchain lookup: configure {active_network.rpc_env} in your local .env file. It is read-only.")

if submitted:
    try:
        with st.spinner(f"Checking available data on {active_network.name}…"):
            st.session_state["scan_result"] = analyze_token(address, selected_network, check_security)
    except ValueError as exc:
        clear_result()
        st.error(str(exc))

result = st.session_state.get("scan_result")
if result is not None and (not isinstance(result, ScanResult) or result.snapshot.network != selected_network):
    clear_result()
    result = None

if result is not None:
    snapshot, report = result.snapshot, result.report
    st.markdown('<p class="overview-label">TOKEN OVERVIEW</p>', unsafe_allow_html=True)
    st.subheader(f"{snapshot.name} ({snapshot.symbol})")
    st.caption(f"{active_network.name} · {snapshot.dex} · {snapshot.captured_at}")
    st.code(snapshot.address, language=None)
    if not report.is_complete:
        st.warning("Assessment incomplete. Some checks have no usable data; a low warning score does not establish safety.")
else:
    snapshot = report = None
    st.markdown('<p class="overview-label">MARKET OVERVIEW</p>', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1:
    with st.container(key="risk_card"):
        risk_value = ("Incomplete" if report.score == 0 and not report.is_complete else f"{report.score}/100") if report else "—"
        st.metric("Observed warning score", risk_value)
        if report and (report.score > 0 or report.is_complete):
            st.progress(report.score / 100)
        st.caption(report.level if report else "Analyze a token to view risk signals.")
with col2:
    with st.container(key="liquidity_card"):
        st.metric("Pool liquidity", (f"${snapshot.liquidity_usd:,.0f}"
                  if snapshot.liquidity_usd is not None else "Unavailable") if snapshot else "—")
        st.caption("Selected indexed trading pair")
with col3:
    with st.container(key="volume_card"):
        st.metric("24h volume", (f"${snapshot.volume_h24_usd:,.0f}"
                  if snapshot.volume_h24_usd is not None else "Unavailable") if snapshot else "—")
        st.caption("Reported trading volume · last 24 hours")

if snapshot is not None and report is not None:
    st.caption(f"Data coverage: {report.coverage} · Heuristic score, NOT a fraud probability")
    price = f"${snapshot.price_usd:.8g}" if snapshot.price_usd is not None else "Unavailable"
    st.caption(f"Token price: {price}")
    if snapshot.market_available and not snapshot.price_is_available:
        st.info("Price data is unavailable for the requested token. Quote-side pool prices are not assigned to this token.")
    with st.container(border=True):
        st.subheader("Risk observations")
        for finding in report.findings:
            st.markdown(f"- {finding}")
    for warning in result.warnings:
        st.warning(warning)
    with st.expander("Sources and check coverage", expanded=not report.is_complete):
        st.dataframe([{"Check": source.name, "Status": source.status, "Details": source.details}
                      for source in result.sources], hide_index=True)
        st.caption("The weighted score covers configured market rules and GoPlus flags. Optional blockchain observations are listed separately. Historical rug-pull records, holder concentration, liquidity locks, and sell simulations are not assessed.")
    if snapshot.pair_url:
        st.link_button("View trading pair on DEX Screener ↗", snapshot.pair_url)

    with st.expander("Saved scan history"):
        try:
            history = token_history(snapshot.address, network=selected_network)
            risk_history = [row for row in history if row["risk_score"] is not None]
            liquidity_history = [row for row in history if row["liquidity_usd"] is not None]
            if len(risk_history) >= 2:
                st.line_chart(risk_history, x="captured_at", y="risk_score", y_label="Observed warning score")
            if len(liquidity_history) >= 2:
                st.line_chart(liquidity_history, x="captured_at", y="liquidity_usd", y_label="Liquidity (USD)")
            st.caption("History is separate for each network. Incomplete zero scores are omitted from the score chart. Liquidity trend scoring compares the same pool only.")
            if len(history) < 2:
                st.caption("Analyze this token again later to visualize changes in liquidity and warnings.")
        except (OSError, sqlite3.Error):
            st.warning("Saved history could not be read. The current provider results are still shown above.")
else:
    st.markdown('''<div class="empty-state">
        <div class="empty-title">Your next analysis starts here.</div>
        <div class="empty-description">Choose a network and enter a token address to review available evidence.<br>
        Results appear after analysis; unavailable signals remain unknown.</div>
    </div>''', unsafe_allow_html=True)

st.markdown('<div class="dashboard-footer">Research tool only · Market warnings do not prove misconduct · '
            'A low score does not certify safety</div>', unsafe_allow_html=True)
st.caption("Local SQLite history may reset on Streamlit Community Cloud; use an external database for durable hosted monitoring.")
