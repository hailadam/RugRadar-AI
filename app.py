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
assets_path = Path(__file__).parent / "assets"
styles = (assets_path / "dashboard.css").read_text()
hero_data = base64.b64encode((assets_path / "hero-scene.png").read_bytes()).decode("ascii")
scanner_art = base64.b64encode((assets_path / "hero.png").read_bytes()).decode("ascii")
detail_art = base64.b64encode((assets_path / "detail.png").read_bytes()).decode("ascii")
st.markdown(f"<style>{styles}</style>", unsafe_allow_html=True)

st.markdown(f"""
<div class="announcement-bar" id="top"><span>INDEPENDENT SIGNALS. A CLEARER PERSPECTIVE.</span><span>Read-only token research <span aria-hidden="true">↗</span></span></div>
<header class="brand-header">
    <a class="brand" href="#top" aria-label="RugRadar AI home">
        <img class="brand-icon" src="data:image/png;base64,{logo_data}" alt="" width="28" height="45">
        <div><div class="brand-name">RugRadar <span>AI</span></div>
            <div class="brand-note">RESEARCH WITH PERSPECTIVE</div></div>
    </a>
    <nav class="header-links" aria-label="Main navigation">
        <a href="#scanner">Token scanner</a><a href="#signals">Market signals</a><a href="#approach">Our approach</a>
    </nav>
    <div class="network-pill"><span class="network-dot" aria-hidden="true"></span>{active_network.name.upper()} MAINNET</div>
</header>
<section class="hero" aria-labelledby="hero-title">
    <img class="hero-backdrop" src="data:image/png;base64,{hero_data}" alt="" width="1536" height="1024">
    <div class="hero-copy">
        <p class="eyebrow">A LITTLE MORE CLARITY, BEFORE YOUR NEXT MOVE</p>
        <h1 id="hero-title">Look closer.<br><em>See the signals.</em></h1>
        <p class="hero-description">An informed perspective starts with the details. Explore market activity, liquidity, and contract observations across eight networks.</p>
        <a class="pill-link" href="#scanner">Explore a token <span aria-hidden="true">↗</span></a>
    </div>
    <div class="hero-footnote">EIGHT NETWORKS <span aria-hidden="true">/</span> ONE PLACE TO BEGIN</div>
</section>
""", unsafe_allow_html=True)

with st.container(key="scanner_section"):
    scanner_col, visual_col = st.columns([1, 1], gap="large", vertical_alignment="center")
    with scanner_col:
        st.markdown('''<div class="scanner-heading" id="scanner">
            <p class="eyebrow">01 / START YOUR RESEARCH</p>
            <h2>Small details.<br>A clearer picture.</h2>
            <p class="section-note">Every token has a context. Choose its network, enter an address, and take a closer look at the available evidence.</p>
        </div>''', unsafe_allow_html=True)
        selected_network = st.selectbox("Network", list(NETWORKS), format_func=lambda key: NETWORKS[key].name,
                                        key="network", on_change=clear_result,
                                        help="Choose the token’s issuing network. The same address can identify different contracts on different networks.")
        active_network = get_network(selected_network)
        with st.form("scan_form"):
            address = st.text_input("Contract address" if active_network.evm else "Token mint address",
                                    placeholder="0x… · token contract" if active_network.evm else "Solana token mint address",
                                    key="contract_address")
            submitted = st.form_submit_button("Analyze Token", type="primary")
            with st.expander("Analysis options"):
                check_security = st.checkbox("Request GoPlus contract-security data", value=active_network.goplus_chain_id is not None,
                                              disabled=active_network.goplus_chain_id is None,
                                              help="Available on the supported EVM networks. Solana uses market data and optional configured blockchain reads. Provider data can be incomplete or unavailable.")
                st.caption(f"Optional direct blockchain lookup: configure {active_network.rpc_env} in your local .env file. It is read-only.")
    with visual_col:
        st.markdown(f'''<div class="scanner-art" aria-hidden="true">
            <img src="data:image/png;base64,{scanner_art}" alt="" width="768" height="768">
            <span class="art-caption">A CLOSER LOOK CHANGES YOUR PERSPECTIVE.</span>
        </div>''', unsafe_allow_html=True)

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
    st.markdown('<p class="overview-label" id="signals">TOKEN OVERVIEW</p>', unsafe_allow_html=True)
    st.subheader(f"{snapshot.name} ({snapshot.symbol})")
    st.caption(f"{active_network.name} · {snapshot.dex} · {snapshot.captured_at}")
    st.code(snapshot.address, language=None)
    if not report.is_complete:
        st.warning("Assessment incomplete. Some checks have no usable data; a low warning score does not establish safety.")
else:
    snapshot = report = None
    st.markdown('<p class="overview-label" id="signals">MARKET OVERVIEW</p>', unsafe_allow_html=True)

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
    <div class="story-visual">
        <img src="data:image/png;base64,{detail_art}" alt="" width="768" height="768">
    </div>
    <div class="story-copy">
        <p class="eyebrow">02 / THE BIGGER PICTURE</p>
        <h2>Every signal<br>has a story.</h2>
        <p>Liquidity. Trading activity. Contract observations. Consider them together, with the evidence behind each finding.</p>
        <p>See what is known, understand what is missing, and revisit saved scans as your research develops. A single score is only a starting point.</p>
        <a class="text-link" href="#signals">Explore the signals <span aria-hidden="true">↗</span></a>
    </div>
</section>
<section class="perspective-banner" aria-labelledby="perspective-title">
    <img src="data:image/png;base64,{hero_data}" alt="" width="1536" height="1024">
    <div class="banner-copy">
        <p class="eyebrow">STAY CURIOUS. KEEP YOUR PERSPECTIVE.</p>
        <h2 id="perspective-title">Better questions.<br>A clearer place to start.</h2>
        <p>Eight networks. Available evidence.<br>Space to make your own assessment.</p>
        <a class="pill-link light" href="#scanner">Start your research <span aria-hidden="true">↗</span></a>
    </div>
</section>
<footer class="site-footer">
    <div class="footer-grid">
        <div class="footer-intro">
            <a class="brand" href="#top" aria-label="RugRadar AI home">
                <img class="brand-icon" src="data:image/png;base64,{logo_data}" alt="" width="28" height="45">
                <span class="brand-name">RugRadar <span>AI</span></span>
            </a>
            <h2>A little clarity.<br>A wider perspective.</h2>
        </div>
        <div class="footer-links">
            <h3>Explore</h3>
            <a href="#scanner">Token scanner</a>
            <a href="#signals">Market signals</a>
            <a href="#approach">Our approach</a>
        </div>
        <div class="footer-networks">
            <h3>Across networks</h3>
            <div class="network-list">{''.join(f'<span>{network.name}</span>' for network in NETWORKS.values())}</div>
        </div>
        <div class="footer-about">
            <h3>Research, with context</h3>
            <p>Warning scores are experimental. Missing information remains unknown, and a low score does not certify safety.</p>
            <span class="footer-readonly"><span class="network-dot" aria-hidden="true"></span> Read-only. No wallet required.</span>
        </div>
    </div>
    <div class="footer-bottom"><span>RugRadar AI / Token research</span><a href="#top">Back to top <span aria-hidden="true">↑</span></a></div>
</footer>
""", unsafe_allow_html=True)
