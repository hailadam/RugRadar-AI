"""RugRadar AI's read-only token research interface."""
from __future__ import annotations

import base64
from html import escape
from inspect import signature
from pathlib import Path
import sqlite3

from dotenv import load_dotenv
import streamlit as st

load_dotenv()

from rugradar.history import token_history
from rugradar.networks import NETWORKS, get_network
from rugradar.scanner import ScanResult, analyze_token
from ui_components import icon, risk_summary, scan_history_chart, warning_panel

ASSETS = Path(__file__).parent / "assets"
logo_path = ASSETS / "logo.png"
logo_data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
st.set_page_config(page_title="RugRadar AI | Spot the warning signs", page_icon=str(logo_path), layout="wide")
st.markdown(f'<style>{(ASSETS / "dashboard.css").read_text()}</style>', unsafe_allow_html=True)


def clear_result():
    st.session_state.pop("scan_result", None)


active_network = get_network(st.session_state.get("network", "base"))
st.markdown(f"""
<header class="brand-header" id="top">
    <a class="brand" href="#top" aria-label="RugRadar AI home">
        <span class="brand-mark"><img src="data:image/png;base64,{logo_data}" alt="" width="26" height="40"></span>
        <span class="brand-name">RugRadar <strong>AI</strong><small>A CLEARER VIEW OF TOKEN RISK</small></span>
    </a>
    <nav class="header-links" aria-label="Main navigation"><a href="#how-it-works">How it works</a><a href="#signals">What we check</a><a href="#understand">Understanding risk</a></nav>
    <span class="network-pill"><span class="network-dot" aria-hidden="true"></span>{active_network.name.upper()} MAINNET</span>
</header>
""", unsafe_allow_html=True)

with st.container(key="hero_section"):
    hero_left, hero_right = st.columns([1.5, 1], gap="large", vertical_alignment="center")
    with hero_left:
        st.markdown(f"""<div class="hero-heading" id="scanner">
            <p class="eyebrow"><span class="tiny-star" aria-hidden="true">✦</span> A LITTLE RESEARCH. A LOT MORE PERSPECTIVE.</p>
            <h1>Spot the warning signs.<br><em>Before your next move.</em></h1>
            <p class="hero-description">Scan {escape(active_network.name)} tokens and understand risk, one signal at a time. Turn market activity and contract warnings into clear, easy-to-read insights.</p>
        </div>""", unsafe_allow_html=True)
        selected_network = st.selectbox("Network", list(NETWORKS), format_func=lambda key: NETWORKS[key].name,
                                        key="network", on_change=clear_result,
                                        help="Base is selected by default. Choose the network where the token was issued; the same address can refer to different contracts on different networks.")
        active_network = get_network(selected_network)
        with st.form("scan_form"):
            address = st.text_input("Contract address" if active_network.evm else "Token mint address",
                                    placeholder="Paste a token contract address · 0x…" if active_network.evm else "Paste a Solana token mint address",
                                    key="contract_address")
            submitted = st.form_submit_button("Analyze Token", use_container_width=True, type="primary")
            with st.expander("Analysis options"):
                check_security = st.checkbox("Request GoPlus contract-security data", value=active_network.goplus_chain_id is not None,
                                              disabled=active_network.goplus_chain_id is None,
                                              help="Available on the supported EVM networks. Solana uses market data and optional configured blockchain reads. Provider data can be incomplete or unavailable.")
                st.caption(f"Optional direct blockchain lookup: configure {active_network.rpc_env} in your local .env file. It is read-only.")
        st.markdown(f'<div class="hero-trust"><span>{icon("shield")} Read-only analysis</span><span>{icon("check")} No wallet needed</span></div>', unsafe_allow_html=True)
    with hero_right:
        st.markdown(f"""<div class="hero-visual" aria-label="From token address to understandable insights">
            <div class="visual-kicker">LESS GUESSWORK. MORE CONTEXT.</div>
            <div class="orbit-art" aria-hidden="true"><div class="orbit-middle"></div><div class="orbit-core"><img src="data:image/png;base64,{logo_data}" alt="" width="40" height="65"></div><span class="orbit-dot dot-one"></span><span class="orbit-dot dot-two"></span><span class="orbit-dot dot-three"></span></div>
            <h2>Small signals.<br>A bigger picture.</h2>
            <div class="visual-tags"><span>{icon("liquidity")} Liquidity</span><span>{icon("volume")} Activity</span><span>{icon("shield")} Contract checks</span></div>
            <p>Real observations, explained simply.<br>Missing evidence stays visible.</p>
        </div>""", unsafe_allow_html=True)

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
    st.markdown(f"""<div class="result-heading" id="results">
        <div><p class="eyebrow">YOUR TOKEN, AT A GLANCE</p><h2>{escape(snapshot.name)} <span class="token-symbol">{escape(snapshot.symbol)}</span></h2></div>
        <span class="result-network">{escape(active_network.name)} · {escape(snapshot.dex)}</span>
    </div>""", unsafe_allow_html=True)
    st.caption(f"Observed at {snapshot.captured_at} · Selected indexed trading pair")
    st.code(snapshot.address, language=None)
    if not report.is_complete:
        st.warning("Assessment incomplete. Some checks have no usable data; a low warning score does not establish safety.")
    st.markdown(risk_summary(report), unsafe_allow_html=True)

    liquidity_col, volume_col, price_col = st.columns(3)
    with liquidity_col:
        with st.container(key="liquidity_card"):
            st.markdown(f'<div class="metric-icon">{icon("liquidity")}</div>', unsafe_allow_html=True)
            st.metric("Liquidity", f"${snapshot.liquidity_usd:,.0f}" if snapshot.liquidity_usd is not None else "Unavailable")
            st.caption("Funds in the selected trading pool")
    with volume_col:
        with st.container(key="volume_card"):
            st.markdown(f'<div class="metric-icon">{icon("volume")}</div>', unsafe_allow_html=True)
            st.metric("24h Volume", f"${snapshot.volume_h24_usd:,.0f}" if snapshot.volume_h24_usd is not None else "Unavailable")
            st.caption("Reported trading activity over 24 hours")
    with price_col:
        with st.container(key="price_card"):
            st.markdown(f'<div class="metric-icon">{icon("price")}</div>', unsafe_allow_html=True)
            price = f"${snapshot.price_usd:.8g}" if snapshot.price_usd is not None and snapshot.price_is_available else "Unavailable"
            change = f"{snapshot.change_h24_pct:+.1f}% · 24h" if snapshot.change_h24_pct is not None else None
            st.metric("Token Price", price, delta=change)
            st.caption("USD price of the requested token")
    if snapshot.market_available and not snapshot.price_is_available:
        st.info("Price data is unavailable for the requested token. Quote-side pool prices are not assigned to this token.")

    st.markdown(warning_panel(report), unsafe_allow_html=True)
    for warning in result.warnings:
        st.warning(warning)

    with st.container(key="history_section"):
        st.markdown(f'<div class="panel-heading">{icon("history")}<div><h3>Your saved scan history</h3><p>A little perspective on how things change.</p></div></div>', unsafe_allow_html=True)
        try:
            history = token_history(snapshot.address, network=selected_network)
            # Comparing the current pool avoids charting a pool switch as a market move.
            pool_key = lambda value: (value or "").lower() if active_network.evm else (value or "")
            history = [row for row in history if pool_key(row.get("pair_address")) == pool_key(snapshot.pair_address)]
            series = [("risk_score", "Warning points", "Observed warning score", "#315e88"),
                      ("liquidity_usd", "Pool liquidity", "Liquidity (USD)", "#3e8f89"),
                      ("price_usd", "Token price", "Price (USD)", "#6378a8")]
            available_series = [(key, title, label, color) for key, title, label, color in series
                                if sum(row.get(key) is not None for row in history) >= 2]
            if available_series:
                chart_cols = st.columns(len(available_series))
                chart_layout = ({"width": "stretch"} if "width" in signature(st.altair_chart).parameters
                                else {"use_container_width": True})
                for column, (key, title, label, color) in zip(chart_cols, available_series):
                    with column:
                        st.caption(title)
                        st.altair_chart(scan_history_chart(history, key, label, color), **chart_layout)
                st.caption("Saved observations for this token, network, and trading pair. These are scan snapshots, not a live price chart. Incomplete zero scores remain gaps.")
            else:
                st.markdown('<div class="history-empty">A story takes more than one snapshot.<br><span>Scan this token again later. Charts appear once two saved observations have usable data for the same trading pair.</span></div>', unsafe_allow_html=True)
        except (OSError, sqlite3.Error):
            st.warning("Saved history could not be read. The current provider results are still shown above.")

    with st.expander("Sources and check coverage", expanded=not report.is_complete):
        st.dataframe([{"Check": source.name, "Status": source.status, "Details": source.details}
                      for source in result.sources], hide_index=True)
        st.caption("The score covers configured market rules and GoPlus flags. Optional blockchain observations are separate. Historical rug-pull records, holder concentration, liquidity locks, and sell simulations are not assessed.")
    if snapshot.pair_url:
        st.link_button("View trading pair on DEX Screener ↗", snapshot.pair_url)
else:
    st.markdown(f"""<div class="start-hint"><span class="start-hint-icon">{icon("search")}</span><div><strong>Your next insight starts with an address.</strong><p>After your scan, you’ll see a visual warning score, key market numbers, and the evidence behind each signal.</p></div></div>""", unsafe_allow_html=True)

st.markdown(f"""
<section class="intro-section" id="how-it-works" aria-labelledby="intro-title">
    <div class="intro-copy"><p class="eyebrow">GOOD QUESTIONS START HERE</p><h2 id="intro-title">Crypto can be complex.<br><em>Your research doesn’t have to be.</em></h2><p>RugRadar AI brings available trading data and contract observations into one clear view, so you can spend less time decoding numbers and more time understanding what they mean.</p></div>
    <ol class="how-steps"><li><span>01</span><div><h3>Paste a token address</h3><p>Choose its network and enter the token’s contract.</p></div></li><li><span>02</span><div><h3>Look at the signals</h3><p>Review the warning score, liquidity, volume, and price.</p></div></li><li><span>03</span><div><h3>Understand the context</h3><p>Read each finding and check where evidence is missing.</p></div></li></ol>
</section>
<section class="signals-section" id="signals" aria-labelledby="signals-title">
    <div class="section-heading"><p class="eyebrow">SMALL DETAILS. USEFUL SIGNALS.</p><h2 id="signals-title">What goes into a scan?</h2><p>Market activity and contract observations, brought together.</p></div>
    <div class="signal-grid">
        <article class="info-card"><span class="info-icon">{icon("liquidity")}</span><h3>Liquidity &amp; price moves</h3><p>Thin trading pools and sharp daily price falls can highlight a token that deserves a closer look.</p></article>
        <article class="info-card"><span class="info-icon">{icon("volume")}</span><h3>Trading pressure</h3><p>Buy and sell transaction counts help reveal unusually heavy selling. Volume adds market context.</p></article>
        <article class="info-card"><span class="info-icon">{icon("shield")}</span><h3>Contract controls</h3><p>Available GoPlus flags check potential honeypot behavior, minting, and selected owner capabilities.</p></article>
        <article class="info-card"><span class="info-icon">{icon("history")}</span><h3>Changes over time</h3><p>Saved scans can reveal liquidity drops in the same pool. Your first scan starts the baseline.</p></article>
    </div>
</section>
<section class="interpret-section" id="understand" aria-labelledby="interpret-title">
    <div><p class="eyebrow">A SCORE IS A STARTING POINT</p><h2 id="interpret-title">Read the signs.<br><em>Keep the perspective.</em></h2><p>Warning points summarize the rules triggered by available observations. They are not a probability of fraud or a guarantee about what happens next.</p><div class="incomplete-note">{icon("search")}<span><strong>Incomplete means unknown.</strong> Missing data never becomes a clean bill of health.</span></div></div>
    <div class="risk-guide"><div><span class="risk-badge risk-low">Low</span><p>Fewer observed warning points. Safety is not verified.</p></div><div><span class="risk-badge risk-moderate">Moderate</span><p>Some warning thresholds were triggered. Review the findings.</p></div><div><span class="risk-badge risk-high">High</span><p>Significant warning signals need careful attention.</p></div><div><span class="risk-badge risk-critical">Critical</span><p>Strong warning signals warrant serious caution.</p></div></div>
</section>
<footer class="site-footer"><a class="brand footer-brand" href="#top"><span>RugRadar <strong>AI</strong></span></a><p>Research tool only. Not financial advice.<br>A low score does not certify safety.</p><a class="back-top" href="#top">Back to top ↑</a></footer>
""", unsafe_allow_html=True)
