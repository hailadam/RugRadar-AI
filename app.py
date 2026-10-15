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
styles = (Path(__file__).parent / "assets" / "dashboard.css").read_text()
hero_data = base64.b64encode((Path(__file__).parent / "assets" / "hero.png").read_bytes()).decode("ascii")
st.markdown(f"<style>{styles}</style>", unsafe_allow_html=True)

st.markdown(f"""
<header class="brand-header" id="top">
    <a class="brand" href="#top" aria-label="RugRadar AI home">
        <img class="brand-icon" src="data:image/png;base64,{logo_data}" alt="" width="28" height="45">
        <div><div class="brand-name">RugRadar <span>AI</span></div>
            <div class="brand-note">A CLEARER PERSPECTIVE</div></div>
    </a>
    <nav class="header-links" aria-label="Main navigation">
        <a href="#top">Overview</a><a href="#scanner">Token scanner</a><a href="#approach">Our approach</a>
    </nav>
    <div class="network-pill"><span class="network-dot" aria-hidden="true"></span>{active_network.name.upper()} MAINNET</div>
</header>
<section class="hero" aria-labelledby="hero-title">
    <div class="hero-copy">
        <p class="eyebrow">TOKEN RESEARCH, WITH PERSPECTIVE</p>
        <h1 id="hero-title">Look closer.<br><em>See the signals.</em></h1>
        <p class="hero-description">Explore liquidity, market activity, and contract warnings across eight networks. A clearer place to begin your research.</p>
        <a class="hero-link" href="#scanner">Explore a token <span aria-hidden="true">↗</span></a>
    </div>
    <div class="hero-art">
        <img src="data:image/png;base64,{hero_data}" alt="" width="768" height="512">
        <span class="hero-art-note">A LITTLE MORE PERSPECTIVE.</span>
    </div>
</section>
<div class="trust-strip" aria-label="Research features">
    <span><span class="trust-mark" aria-hidden="true">◈</span> Eight supported networks</span>
    <span><span class="trust-mark" aria-hidden="true">↗</span> Read-only research</span>
    <span><span class="trust-mark" aria-hidden="true">◎</span> No wallet connection</span>
</div>
<div class="section-heading" id="scanner">
    <div><p class="eyebrow">01 / THE TOKEN DESK</p><h2>Start with an address.</h2></div>
    <p class="section-note">Choose a network and explore the available evidence. Every signal in its proper context.</p>
</div>
""", unsafe_allow_html=True)

selected_network = st.selectbox("Network", list(NETWORKS), format_func=lambda key: NETWORKS[key].name,
                                key="network", on_change=clear_result)
active_network = get_network(selected_network)
st.caption("Select the token’s network. An address can identify different contracts on different networks.")

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
        <div class="empty-icon" aria-hidden="true">↗</div>
        <div><div class="empty-title">A fresh perspective starts here.</div>
        <div class="empty-description">Your results will appear after analysis. Unavailable signals remain unknown.</div></div>
    </div>''', unsafe_allow_html=True)

st.markdown(f"""
<section class="research-story" id="approach" aria-labelledby="approach-title">
    <div class="story-visual" aria-hidden="true">
        <div class="orbit">
            <img class="orbit-logo" src="data:image/png;base64,{logo_data}" alt="" width="42" height="70">
            <span class="orbit-point one"></span><span class="orbit-point two"></span><span class="orbit-point three"></span>
        </div>
        <div class="story-visual-label">MARKET SIGNALS / CONTRACT OBSERVATIONS</div>
    </div>
    <div class="story-copy">
        <p class="eyebrow">02 / A MORE CONSIDERED APPROACH</p>
        <h2>Signals, with context.</h2>
        <p>One score never tells the whole story. Review the evidence behind each observation, see where data is missing, and return to saved scans as your research develops.</p>
        <div class="network-list" aria-label="Supported networks">
            {''.join(f'<span>{network.name}</span>' for network in NETWORKS.values())}
        </div>
    </div>
</section>
<footer class="dashboard-footer">
    <div class="footer-brand">Stay curious. Look closer.</div>
    <div class="footer-note">A research tool, with limits. Warning scores are experimental; a low score does not certify safety.</div>
</footer>
""", unsafe_allow_html=True)
