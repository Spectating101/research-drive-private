# Academic Validation Outreach

Date: 2026-05-20

Purpose: use professors/research institutes as validation and collaboration channels for the Sharpe data inventory. This is not the same as selling to data vendors. Professors rarely buy a dataset from a cold email. They can still provide credibility, usage feedback, collaboration routes, citations, referrals, and sometimes funded RA/data work.

## Confidence

Packaging confidence: high.

The repo already has enough raw inventory to package a serious sample: Asia market panels, IDX legacy history, ETF-holdings-based universes, crypto/DeFi history, OpenSea metadata/image deliverables, and planned GDELT/news-shock layers. The packaging job is mostly catalog, data dictionary, provenance, sample rows, and one or two proof charts.

Conversion confidence: unproven.

Cold academic outreach is not guaranteed. A realistic test is:

1. 20 highly relevant targets.
2. 20 customized emails.
3. Success is not "payment"; success is a sample request, call, collaboration suggestion, or clear technical rejection.
4. If 3-5 targets ask for a sample, the dataset has external pull.
5. If nobody asks for a sample, the product is still too vague or not differentiated enough.

## Rule

Do not write:

> I am working on data vendorship and might have data you need. Let me know if interested.

That is too broad.

Write:

> I am building a reproducible public-source dataset on [specific subject]. I saw your work on [specific paper/topic]. I am trying to validate whether this schema would be useful for research on [specific question]. Could I send a 2-page data note and a 50-row sample for feedback?

## What To Send

For academics, prepare a research-facing pack:

```text
deliverables/academic_validation_sample_pack/
  00_two_page_data_note.md
  01_data_dictionary.csv
  02_50_row_sample.csv
  03_provenance_and_limitations.md
  04_research_questions.md
  05_one_chart_or_case_study.png
```

The key is to make the use obvious in five minutes.

## Outreach Lanes

### Lane A: Online Work / Job Listings / Platform Economy

Best for the Upwork/job-insight dataset and any 104/online labor market data.

| Priority | Target | Public route | Why relevant | First ask |
|---|---|---|---|---|
| 1 | Upwork Research Institute | `researchInstitute@upwork.com` | Upwork explicitly says it uses platform data, survey research, partnerships, and academic collaborations to study workforce shifts. | Ask whether a public-source job listing / platform work schema is useful for collaboration or benchmarking. |
| 2 | John J. Horton, MIT Sloan | `jjhorton@mit.edu` | Works on labor economics, market design, information systems; MIT page notes prior staff economist role at oDesk. | Ask for feedback on whether the job-market schema is research-useful. |
| 3 | Fabian Stephany, Oxford / INET | `fabian.stephany@oii.ox.ac.uk` | Co-creator of the Online Labour Observatory; works on AI skills, platform work, labor market transitions. | Ask whether the dataset can complement Online Labour Observatory-style measures. |
| 4 | Vili Lehdonvirta, Oxford/Aalto | `vili@lehdonvirta.com` | Studies digital labor, online economies, platform work; involved in Online Labour Index work. | Ask for feedback on regional platform labor coverage and taxonomy. |

### Lane B: News Shock / Economic Uncertainty / Macro Finance

Best for the GDELT/news taxonomy and ASEAN/EM risk signal idea.

| Priority | Target | Public route | Why relevant | First ask |
|---|---|---|---|---|
| 1 | Nicholas Bloom, Stanford | `nbloom@stanford.edu` | Works on uncertainty, EPU/WUI, remote work, management, productivity; public email listed by Stanford/NBER. | Ask whether LLM-classified news shock taxonomy is a useful complement to EPU/WUI. |
| 2 | Scott R. Baker, Wisconsin School of Business | `scott.baker@wisc.edu` | Coauthor on EPU and policy news/stock market volatility; works on empirical macro/finance. | Ask for feedback on schema and benchmark comparison to keyword indices. |
| 3 | Steven J. Davis, Hoover/Chicago Booth emeritus | Contact via personal website / Booth page | Co-creator of EPU indices and macro/labor data work; Booth page notes EPU and Asian Monetary Policy Forum connection. | Ask whether ASEAN/EM news taxonomy has a clear incremental measurement angle. |
| 4 | Tarek A. Hassan, Boston University | `thassan@bu.edu` | Works on text, global risk, and economics/finance applications. | Ask whether entity-linked news text signals could support macro/asset pricing research. |

### Lane C: Asia / Emerging Markets / Practitioner-Academic Bridge

Best for the Sharpe Asia-market + news-risk panel.

For this lane, do not start with famous global names. Start with:

1. professors at Taiwan/Singapore/HK/Indonesia schools who publish on ASEAN, emerging markets, macro-finance, or textual analysis;
2. research centers with "Asia", "emerging markets", "financial stability", or "digital economy" mandates;
3. your existing university/professor network.

The pitch should be:

> I am building an ASEAN/Asia market stress panel that links market data, country/entity metadata, and news shock signals. I am looking for feedback on research usefulness and validation design.

## Email Template: Academic Validation

Subject: Feedback request: [ASEAN news shock / online labor] dataset schema

Hi Professor [Name],

I am Chris Ongko, a student at Yuan Ze University. I am building a reproducible public-source dataset on [specific topic], and I found your work on [specific paper/topic] directly relevant.

The current dataset is not a finished paper yet. I am trying to validate whether the schema is actually useful for research. The core output is [one sentence: e.g., country-month news shock indices mapped to ASEAN market returns and FX, with article-level provenance].

Could I send a short 2-page data note and a 50-row sample for feedback? I am especially trying to understand whether the coverage, taxonomy, and identifiers are useful enough for academic work, or whether the design is missing something important.

Best,
Chris Ongko
Yuan Ze University

## Email Template: Upwork / Platform Work

Subject: Feedback request: public-source online labor dataset schema

Hi [Name/Team],

I am Chris Ongko, a student at Yuan Ze University. I am building a public-source online labor/job listing dataset and noticed your work on platform work and labor market measurement.

The aim is not to resell platform data. I am trying to build a research-facing panel of job postings, skills, prices/budgets, geography, and category shifts over time, with a reproducible methodology and clear limitations.

Could I send a short 2-page data note and 50-row schema sample for feedback? I am trying to determine whether this would be useful as a research dataset, and where it would be weak compared with established Online Labour Index / platform data approaches.

Best,
Chris Ongko

## Email Template: News Shock / Uncertainty

Subject: Feedback request: LLM-classified news shock index schema

Hi Professor [Name],

I am Chris Ongko, a student at Yuan Ze University. I am building a research dataset that classifies public news into country-month shock categories such as political instability, governance/corruption, financial stress, trade policy, health, and geopolitical risk.

The motivation is to test whether a structured LLM taxonomy adds useful information beyond scalar keyword-based indices such as EPU/WUI/GPR, especially for ASEAN and emerging markets where category-level interpretation may matter.

Could I send a short 2-page data note and 50-row sample for feedback? I am not asking for a commitment; I am trying to validate whether the measurement design is research-useful before scaling it further.

Best,
Chris Ongko

## Tracker Fields

Track every message:

```csv
date,target_name,target_type,email_or_route,dataset_lane,custom_hook,sent,reply,sample_requested,call_requested,rejection_reason,next_action
```

Do not send more than one follow-up unless there is a real reason.

## Interpretation

Strong signal:

1. They ask for the sample.
2. They suggest a missing variable or benchmark.
3. They ask about coverage, identifiers, update cadence, or source rights.
4. They forward it to an RA, colleague, center, or data platform.

Weak signal:

1. "Interesting, thanks."
2. No answer after one follow-up.
3. They ask only broad questions but do not request the sample.

## Source Links

- Upwork Research Institute collaboration email and research focus: https://www.upwork.com/research/about
- John J. Horton MIT Sloan profile and email: https://mitsloan.mit.edu/faculty/directory/john-j-horton
- Fabian Stephany INET/Oxford profile: https://www.inet.ox.ac.uk/people/fabian-stephany
- Online Labour Index 2020 article with corresponding author email: https://ora.ox.ac.uk/objects/uuid%3Aee2011a4-8ed8-46d2-8644-ee099ac60c62/files/s2z10wr056
- Nicholas Bloom Stanford profile: https://economics.stanford.edu/people/nicholas-bloom
- Scott R. Baker Wisconsin profile: https://business.wisc.edu/directory/profile/scott-r-baker/
- Steven J. Davis Chicago Booth profile: https://www.chicagobooth.edu/faculty/emeriti/steven-j-davis
- Tarek Hassan contact page: https://www.tarekhassan.net/about-me
