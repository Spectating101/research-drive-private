# Refinitiv / LSEG Access Setup

Date: 2026-05-20

Purpose: make Refinitiv/LSEG access reproducible for the Sharpe research data build without putting university credentials or API keys in chat, git, logs, or scripts.

## Current Local State

- Main project venv: `.venv`, Python 3.13.5.
- Refinitiv-compatible venv: `.venv-refinitiv`, Python 3.11.14 via `uv`.
- Installed in `.venv-refinitiv`: `lseg-data==2.1.1`, `refinitiv-data==1.6.2`, `eikon==1.1.18`, `keyring`, `python-dotenv`, `pandas`, `pyarrow`.
- Existing historical exports already present in `From-refinitiv/`, including S&P 500 panel, volatility/skew fields, supply-chain/ESG files, and macro/crypto patches.

The first attempted install into Python 3.13 was stopped because the legacy Refinitiv stack tried to build older NumPy/SciPy packages from source. Keep Refinitiv access in `.venv-refinitiv`.

## Credential Rule

Do not paste university login credentials, LSEG passwords, or API keys into chat.

Use one of these local-only options:

1. Put keys in `.env`.
2. Put keys in `config/lseg-data.config.json`.
3. Use the local OS credential store/keyring.
4. Use LSEG Workspace/Eikon already logged in on this machine and let the desktop session handle authentication.

`.env` and `.env.*` are ignored by git in this repo.

## Best Access Path

Use LSEG Workspace or Eikon desktop first.

According to LSEG's Python quick start, a desktop session can authenticate through the running Workspace/Eikon desktop application. For the desktop access path, you need the desktop app running and logged in on the same machine. For platform/cloud access, a separate LSEG account/service credential and app key entitlement are required from LSEG or the institution's market-data administrator.

Practical workflow:

1. Open LSEG Workspace/Eikon locally.
2. Log in with the university account in the application, not in chat.
3. Find the App Key Generator / developer app key tool in Workspace/Eikon.
4. Create a desktop app key.
5. Copy `.env.example` to `.env`.
6. Fill:

```bash
LSEG_APP_KEY=your_desktop_app_key_here
LSEG_SESSION_NAME=desktop.workspace
EIKON_APP_KEY=your_desktop_app_key_here
```

7. Smoke-test:

```bash
.venv-refinitiv/bin/python scripts/refinitiv_access_probe.py --ric BBCA.JK --ric .JKSE
```

If this succeeds, the machine is ready for historical Refinitiv backfill scripts.

## If There Is No App Key

If the university license does not expose App Key Generator:

- Use LSEG CodeBook inside Workspace if available, export CSV/Parquet from there, then ingest into this repo.
- Use the Workspace/Excel add-in for bulk historical exports, then ingest into this repo.
- Ask the university market-data admin whether the account has desktop API entitlement or platform API entitlement.

Do not use browser automation as the first choice for bulk Refinitiv extraction. It is fragile, slower, and may violate local license rules. Browser automation is only acceptable for user-driven export assistance after the user is logged in locally and the intended export is permitted by the institution.

## What To Pull First

High-value one-time historical backfill:

- IDX equities: `.JK` RIC universe, price/volume, market cap, sector, free float, corporate actions.
- Indonesian indices: `.JKSE`, sector indices if entitled.
- Global benchmark indices: S&P 500, Nasdaq, Nikkei, Taiwan, Korea, Europe.
- Rates/FX/commodities: USDIDR, UST yields, local 10Y yields, oil, gold.
- Equity option/risk fields where entitled: implied volatility, put/call skew, short interest, analyst recommendations.
- Metadata: RIC, ISIN, exchange, country, TRBC sector/industry, delisting status.

After the paid historical pull, use cheaper daily sources for continuity where possible, with Refinitiv reserved for fields that cannot be replicated from public sources.

## References

- LSEG Data Library for Python quick start: https://developers.lseg.com/en/api-catalog/lseg-data-platform/lseg-data-library-for-python/quick-start
- LSEG Python configuration process: https://developers.lseg.com/en/article-catalog/article/configuration-process
- Eikon Data API Python troubleshooting: https://developers.lseg.com/en/article-catalog/article/eikon-data-api-python-troubleshooting-refinitiv
