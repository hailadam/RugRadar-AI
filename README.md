# RugRadar AI — Multi-network Token Research

A read-only Streamlit dashboard for available market and contract observations. Choose a network, enter a token address, and review liquidity, volume, warning points, source status, and saved scan history.

The score is a collection of experimental rules, not a fraud probability or a validated prediction model. Missing observations are unknown. A completed check or low score does not certify safety.

## Supported mainnets

| Network | Market data | GoPlus flags | Optional blockchain lookup |
|---|---|---|---|
| Base | DEX Screener | Subject to provider coverage | Contract bytecode and metadata |
| Ethereum | DEX Screener | Subject to provider coverage | Contract bytecode and metadata |
| BNB Chain | DEX Screener | Subject to provider coverage | Contract bytecode and metadata |
| Arbitrum | DEX Screener | Subject to provider coverage | Contract bytecode and metadata |
| Optimism | DEX Screener | Subject to provider coverage | Contract bytecode and metadata |
| Polygon | DEX Screener | Subject to provider coverage | Contract bytecode and metadata |
| Avalanche C-Chain | DEX Screener | Subject to provider coverage | Contract bytecode and metadata |
| Solana | DEX Screener | No adapter in this version | SPL mint, decimals, mint/freeze authorities |

Select the correct network. EVM addresses use `0x` and 40 hexadecimal characters. Solana needs a case-sensitive base58 mint address that decodes to 32 bytes. Valid syntax alone does not establish that a token exists.

This version can attempt a report for any syntactically valid address on these networks. Providers may have no information about a token. Missing trading pairs no longer stop independent contract checks. Other networks are not yet supported.

## Run on your Mac

Open the existing project folder in VS Code. For a GitHub ZIP, copy its contents into that folder, preserving local `.env`, `.venv`, and `data/` files. Do not nest a second project inside it. Back up local edits before replacing source files.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8501
```

Open `http://localhost:8501`. Save interface edits and use Streamlit's **Rerun** button when needed. After replacing backend files, stop Streamlit with **Ctrl+C** and run the startup command again so imported modules reload. Python 3.12 is used in CI.

The interface uses a centered teal hero, alternating image-and-text sections, an ivory token scanner, compact metrics, a wide research banner, and a multi-column footer. Serif headlines and still-life artwork follow the supplied visual reference; the original RugRadar logo is retained. Edit `assets/dashboard.css` for appearance, `app.py` for page content and layout, and `.streamlit/config.toml` for native widget colors. Decorative artwork lives in `assets/`. Scanning, scoring, and storage remain in `rugradar/`.

For a new checkout:

```bash
git clone --branch interface-redesign https://github.com/hailadam/RugRadar-AI.git
cd RugRadar-AI
```

## Provider configuration

Market lookup needs Internet access to `api.dexscreener.com`. GoPlus needs `api.gopluslabs.io`; provider limits and authorization apply. GoPlus checks are requested by default on supported EVM networks and can be disabled under **Analysis options**.

Copy `.env.example` to `.env` if needed. An existing `GOPLUS_API_KEY` is reused. Enter credentials only in your local `.env` or secure environment settings; never commit them.

For optional direct blockchain lookup, set the matching mainnet endpoint:

```text
BASE_RPC_URL=
ETHEREUM_RPC_URL=
BSC_RPC_URL=
ARBITRUM_RPC_URL=
OPTIMISM_RPC_URL=
POLYGON_RPC_URL=
AVALANCHE_RPC_URL=
SOLANA_RPC_URL=
```

Use a trusted HTTPS RPC provider or a local node. The app verifies EVM chain IDs and the Solana mainnet genesis hash before account reads. Unset endpoints show **not configured**; RPC errors conceal credential-bearing URLs.

Only read methods are used. No wallets, private keys, signed transactions, or trading are required. EVM metadata does not establish ERC-20 compliance or safety. Solana authority observations appear separately and are not added to the weighted market/GoPlus score.

## Interpret results

- Market checks use one selected indexed pool: liquidity, 24-hour price change, and transaction counts. Quote-side prices stay unavailable and quote-side buy/sell direction is reversed.
- Liquidity trends compare saved observations for the same token, network, and pool. A first scan has no earlier local baseline. The app does not reconstruct older on-chain withdrawals.
- Five GoPlus flags are considered: honeypot, mintability, hidden owner, owner balance changes, and blacklist capability. Only explicit true/false values count as known. Empty, partial, and unknown responses remain incomplete.
- A positive honeypot flag produces a high-severity warning even without market data. Warning points are experimental and uncalibrated.
- A zero-point result with incomplete coverage displays **Incomplete**, rather than `0/100`. Positive findings can appear alongside incomplete coverage.
- **Sources and check coverage** identifies available, partial, unavailable, unsupported, and disabled checks. Provider failure never becomes a passed security check.

This version does not provide exhaustive token discovery, batch scanning, continuous monitoring, historical incident databases, holder concentration analysis, liquidity-lock verification, source auditing, or sell simulations. It cannot identify every scam or predict every future liquidity withdrawal.

## Local history

SQLite defaults to `data/rugradar.db`; set `RUGRADAR_DB_PATH` in `.env` to change it. Existing databases receive additive columns and retain old rows, addresses, and scores. Legacy rows belong to Base. Histories are separate by network; Solana address case is preserved. Incomplete or legacy zero scores are omitted from the score chart while their original points remain stored.

SQLite is suitable for local use. Hosted ephemeral filesystems can lose history after restart; durable background monitoring needs persistent storage and a separate scheduled collector.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use mocked providers and temporary databases. They cover network selection, address validation, pool filtering, partial failures, read-only RPC behavior, incomplete scoring, database migration, and chain/pool isolation. They verify implemented behavior rather than real-world detection accuracy. Live integration must also be checked from a network that permits the configured destinations.

## Files

```text
app.py                         Dashboard layout and interaction
assets/logo.png                Website logo and browser icon
assets/hero.png                Scanner still-life artwork
assets/hero-scene.png          Wide hero and research-banner artwork
assets/detail.png              Alternating editorial-section artwork
assets/dashboard.css           Responsive page styles
.streamlit/config.toml         Light theme and deep teal controls
rugradar/networks.py           Network registry and address validation
rugradar/market.py             Chain-specific market adapter
rugradar/security.py           EVM GoPlus adapter and flag parsing
rugradar/chain.py              Optional read-only RPC lookups
rugradar/scanner.py            Independent checks and partial reports
rugradar/scoring.py            Warning rules and explicit unknowns
rugradar/history.py            Migrating, network-aware SQLite history
tests/                         Offline regression tests
.github/workflows/tests.yml    CI tests
```

## References

- [DEX Screener API](https://docs.dexscreener.com/api/reference)
- [GoPlus token-security API](https://docs.gopluslabs.io/reference/token-security-api)
- [Ethereum JSON-RPC](https://ethereum.org/en/developers/docs/apis/json-rpc/)
- [Solana RPC](https://solana.com/docs/rpc)
- [Solana SDK mainnet genesis reference](https://github.com/solana-labs/solana/blob/master/sdk/src/genesis_config.rs)
