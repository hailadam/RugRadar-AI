# ◉ RugRadar AI — Base Token Risk Scanner

A read-only** cryptocurrency risk-research dashboard for token contracts on **Base Mainnet (chain ID 8453)**. It fetches authentic available DEX Screener pool metrics, scores a small set of **transparent warning rules**, optionally requests GoPlus security indicators, and records scans in local SQLite.

> **Not a validated AI predictor.** The 0–100 score is an experimental *heuristic indicator*, **not a probability of fraud or a forecast of an imminent rug pull**. A low score is not a safety certification. RugRadar does not audit contracts, control funds, or trade.

## Included features

- One-field Base token address scanner (validated `0x` + 40 hex digits).
- Most-liquid Base pair selection, with protection against mislabeling the quote token's price.
- Liquidity, 24h volume and token price (where available).
- Explainable warnings for low liquidity, large daily price drops, sell-heavy transaction counts, and liquidity change since the last saved scan.
- Optional GoPlus checks (can be unavailable, rate-limited, or require API authorization).
- Local SQLite scan history and simple risk/liquidity charts after repeated scans.
- Offline unit tests and GitHub Actions CI.
- Navy Streamlit dashboard with blue accents, a Base Mainnet indicator, one contract-address input, and compact risk, liquidity, and volume cards.

## Setup on a Mac

```bash
# Clone the GitHub repository (or unzip the downloaded project and open it in VS Code)
git clone https://github.com/hailadam/RugRadar-AI.git
cd RugRadar-AI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8501
```

If the repository is private, make sure your Mac is signed into GitHub (e.g. GitHub CLI `gh auth login` or VS Code GitHub authentication).

Open the localhost URL shown in the Terminal (usually `http://localhost:8501`).

For a downloaded ZIP, unzip it once, open the existing `RugRadar-AI` folder, and start with `python3 -m venv .venv`; skip the Git clone commands above. If a project folder already exists, back it up and replace the included source files there rather than nesting another project inside it. Retain your local `.env` and `data/` files.

### Edit the interface locally

- `app.py` contains the dashboard layout and styling.
- `.streamlit/config.toml` contains the navy theme and blue accent colors.
- `assets/logo.png` is the white logo used in the header and browser tab.
- Keep Streamlit running while editing; save the file and choose **Rerun** in the browser if it does not refresh automatically.
- Optional GoPlus checks remain available under **Analysis options**, disabled by default.
- Risk, liquidity, and volume cards show placeholders until a scan completes. Missing market data is labeled unavailable.

The token scanning, API clients, scoring rules, and SQLite operations are in `rugradar/` and are separate from the interface.

### Test offline

```bash
python -m unittest discover -s tests -v
```

Use a known Base token, such as Base WETH (`0x4200000000000000000000000000000000000006`), to test API connectivity. WETH is only a **plumbing test**, not a target meme coin and not a security benchmark. A given address may lack a supported trading pair, or an upstream provider may be unavailable.

The application must be tested online for live integration: the offline unit tests use mocks rather than real requests.

## Optional security API

By default the GoPlus checkbox is unchecked. You can enable it for an individual scan. If GoPlus requires an access token in your usage tier, create `.env` locally (from `.env.example`) containing:

```text
GOPLUS_API_KEY=your_actual_key
```

Never push `.env` or keys to GitHub. API coverage and terms may change. An unavailable security response is clearly labeled unknown.

## Deploy on Streamlit Community Cloud

1. Make sure `app.py`, `requirements.txt`, `rugradar/` and `.streamlit/config.toml` are committed in your GitHub repository.
2. Open **https://share.streamlit.io/** and sign in with GitHub.
3. Select **Create app → Yup, I have an app**.
4. Repository: `hailadam/RugRadar-AI` · Branch: `main` · Main file path: `app.py`.
5. Choose Python 3.12 if offered (all bundled code is also compatible with newer versions supported by Streamlit), then click **Deploy**.
6. If your repo is **private**, authorize Streamlit's GitHub access to private repositories. The deployed app will normally be private initially. You can adjust Streamlit sharing separately.
7. Open the generated `*.streamlit.app` URL and scan a Base contract.

**Hosting limitation:** Community Cloud's local filesystem is ephemeral. The included SQLite history is reliable for **local development**, not durable multi-user cloud monitoring. Scans on the deployed app can be lost after restart or re-deployment. Use a managed persistent database and a separately scheduled collector before calling this a 24/7 alerting service. This MVP does not continuously monitor tokens in the background.

## Structure

```text
app.py                         Streamlit dashboard layout and styling
rugradar/market.py             DEX Screener client + robust pair parsing
rugradar/security.py           Optional GoPlus security client
rugradar/scoring.py            Explainable heuristics + data coverage
rugradar/history.py            Local SQLite scan history
.streamlit/config.toml         Dark UI theme
assets/logo.png                Website logo
.github/workflows/tests.yml    CI unit tests
tests/                         Fully offline test suite
```

## Future work

1. Add a data-source health section and provider caching/rate-limit handling.
2. Add scheduled background sampling **outside** Streamlit with a stable database.
3. Track liquidity and holder concentrations using verified on-chain sources.
4. Define independently verifiable rug-pull labels and train a proper model with time-based splits.
5. Evaluate false positives, precision-recall, and actual alert lead times before claiming prediction abilities.

## Data sources

- [DEX Screener official API](https://docs.dexscreener.com/api/reference) — Base token pairs.
- [GoPlus token security API](https://docs.gopluslabs.io/reference/token-security-api) — optional Base security indicators.
- [Base developer docs](https://docs.base.org/) — chain reference.

**Security:** This is an informational tool; do not submit private keys, wallet seed phrases, or trade instructions. Reuse only public contract addresses.
