# Data Vendor Sales Playbook

Date: 2026-05-20

This explains how the business motion actually works. The goal is not to email strangers asking for money. The goal is to get a qualified buyer, platform, or research channel to evaluate a small sample and tell us whether the data is worth productizing.

## The Normal Flow

1. Package the product
   - One-page overview.
   - Data dictionary.
   - Tiny sample file.
   - Methodology/provenance note.
   - Compliance note: no personal data, no MNPI, no raw third-party market-data resale.

2. Contact provider/onboarding channels
   - Use official provider forms/emails from Neudata, Eagle Alpha, BattleFin, Exabel, Monda, Smartkarma, etc.
   - Ask whether the product fits their onboarding process.
   - Do not ask for money in the first email.

3. Qualification call
   - They ask: What is the coverage? How long is the history? How often is it updated? How is it mapped to securities/countries? What is the legal right to distribute it? What is unique?
   - We ask: Who is the buyer? What use case matters? Quant backtest, discretionary dashboard, risk monitoring, academic research, or consulting?

4. Send evaluation sample
   - Send a small sample, not the full dataset.
   - Include the data dictionary and 1-2 charts/case studies.
   - The sample should be enough to judge schema and usefulness, not enough to replace the product.

5. Trial or pilot
   - For institutional data, trials are common.
   - A trial can be free if the target is high-value, or paid if there is custom work.
   - The trial should have a clear end date, clear evaluation criteria, and limited redistribution rights.

6. Due diligence
   - Serious buyers will ask for a DDQ-style package:
     - source provenance
     - collection method
     - privacy policy
     - data rights
     - update reliability
     - known limitations
     - security / delivery method
     - entity mapping quality

7. Commercial terms
   - Only discuss pricing after they understand the product and want a trial/pilot.
   - Start with a small pilot, not an institutional annual contract.

8. Delivery
   - Small stage: CSV/Parquet + README + changelog via Drive/S3.
   - Better stage: S3, SFTP, API, Snowflake, BigQuery, Databricks, or Monda-style catalog delivery.
   - Always include versioned manifests and data dictionaries.

## What To Say In The First Email

Do say:

> I am building a public-source, derived Asia/news risk signal dataset. I can share a one-page summary, data dictionary, and small sample for review. Would this fit your provider onboarding process?

Do not say:

> I have data. Can you buy it for $1,000?

The first ask is review/onboarding, not payment.

## What Buyers Usually Care About

1. Coverage
   - Which countries, tickers, markets, dates, and frequencies?

2. History
   - How many years? Is it point-in-time? Are there survivorship/lookahead problems?

3. Mapping
   - Can rows map to ticker, ISIN, FIGI, PermID, country ISO3, sector, exchange?

4. Update cadence
   - Daily, weekly, monthly? Is there a reliable job and validation log?

5. Uniqueness
   - What do they get that they cannot easily get from Bloomberg, Refinitiv, FactSet, GDELT, Yahoo, or a simple scraper?

6. Legal rights
   - Are we allowed to distribute this output?
   - Are we selling derived features rather than restricted raw source data?

7. Signal evidence
   - Does it correlate with returns, volatility, flows, spreads, drawdowns, or known crisis periods?
   - Even a weak preliminary validation chart is better than vague claims.

8. Operational readiness
   - Clean schema, stable filenames, dictionary, manifests, checksums, reproducible scripts.

## Practical First Product

The first commercially testable product should be:

**ASEAN / Asia Market Stress Monitor**

Contents:

1. Country-month news shock indices:
   - political instability
   - governance/corruption
   - macro policy
   - trade/tariff
   - financial stress
   - geopolitical

2. Market outcome layer:
   - country ETFs
   - major listed equities
   - FX
   - commodities
   - crypto beta where relevant

3. Evidence layer:
   - known event spikes
   - simple forward return/volatility relationship
   - comparison to baseline market returns

Why this product first:

1. It is derived, so it avoids most raw redistribution problems.
2. It has an obvious buyer story: country risk, early warning, EM/ASEAN monitoring.
3. It fits both research platforms and alternative data marketplaces.
4. It can be demonstrated with a small sample.

## Pricing Norms For A New Small Provider

Do not anchor too high before validation.

1. Free review sample
   - 10-50 rows, data dictionary, one chart.

2. Paid custom pilot
   - USD 500-2,000.
   - Best for a small fund, consultant, professor, or bespoke research client.

3. Small subscription
   - USD 99-299/month.
   - Best for independent researchers or small teams.

4. Institutional pilot
   - USD 2,000-10,000 for a limited pilot if the buyer is serious and wants meaningful data access.

5. Institutional annual license
   - Do not chase this first.
   - Needs legal terms, delivery reliability, support, trials, and evidence of value.

## Outreach Cadence

For each target:

1. Day 0: short email with one-page summary offer.
2. Day 5-7: one polite follow-up with a sharper use case.
3. Day 14: final short follow-up with sample availability.
4. Stop unless they respond.

Do not mass-send hundreds. Start with 10-15 targets and learn from replies.

## A Good Reply

Good signs:

1. "Can you send a sample?"
2. "What is the coverage/history?"
3. "How is it mapped to tickers?"
4. "What sources do you use?"
5. "Can you support S3/Snowflake/API?"
6. "Can you run this for [country/sector]?"
7. "What would a pilot cost?"

Bad or weak signs:

1. "Interesting, thanks."
2. "Keep us posted."
3. No question about schema, coverage, or sample.

## First Two Weeks

Day 1:
Build the sample pack.

Day 2:
Send to Neudata, Eagle Alpha, Monda, Exabel.

Day 3:
Send to BattleFin and Nomad.

Day 4:
Prepare 3 Smartkarma-style research samples.

Day 5:
Send Smartkarma inquiry.

Day 7:
Follow up with targets that did not reply.

Day 10:
If someone asked for sample, send sample and offer a 15-minute call.

Day 14:
Decide whether the product needs more evidence, a better pitch, or a narrower niche.

## The Real Norm

The buyer does not buy because we "have data." They buy because the data:

1. answers a specific investment/research question,
2. is painful for them to build internally,
3. is legally clean enough to pass compliance,
4. is mapped into their workflow,
5. has enough history to test,
6. updates reliably.

If we cannot show those six things, we are not selling yet. We are still researching.

## Source Notes

Useful public references:

- Neudata provider/contact route: https://www.neudata.co/data-provider and https://www.neudata.co/contact
- Eagle Alpha data vendor workflow and DDQ/data delivery discussion: https://www.eaglealpha.com/solutions/data-vendors/ and https://www.eaglealpha.com/alternative-data-provider-complete-guide/
- BattleFin historical data onboarding requirements: https://web.battlefin.com/hubfs/2-BF_OnePager_Ensemble_Evaluation_Staging20190315.pdf
- Exabel vendor/investor platform: https://www.exabel.com/
- Smartkarma Insight Provider process: https://assets.smartkarma.com/sk-compliance/downloads/insight-provider-recruitment-process-flowchart-20170426.pdf
