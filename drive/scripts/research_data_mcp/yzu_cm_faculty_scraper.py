#!/usr/bin/env python3
"""Scrape YZU College of Management faculty profiles one-by-one and build procure profiles."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from sharpe_kernel.paths import repo_root_from_file

BASE = "https://www.cm.yzu.edu.tw"
GROUP_PAGES = [
    ("Finance", f"{BASE}/EN/Page/Faculty.aspx?Group=Finance&ItemId=288"),
    ("Marketing", f"{BASE}/EN/Page/Faculty.aspx?Group=Marketing&ItemId=289"),
    ("Accounting", f"{BASE}/EN/Page/Faculty.aspx?Group=Accounting&ItemId=290"),
    ("OrgMgt", f"{BASE}/EN/Page/Faculty.aspx?Group=OrgMgt&ItemId=291"),
    ("TechMgt", f"{BASE}/EN/Page/Faculty.aspx?Group=TechMgt&ItemId=21"),
    ("IntBiz", f"{BASE}/EN/Page/Faculty.aspx?Group=IntBiz&ItemId=292"),
    ("DigitalFinance", f"{BASE}/EN/Page/Faculty.aspx?Group=DigitalFinance&ItemId=393"),
]

# Also scrape the master roster to catch anyone missing from group pages.
ROSTER_PAGE = f"{BASE}/EN/Page/Faculty.aspx?ItemId=283"

TAG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("equities", re.compile(r"\b(stock|equity|equities|asset pricing|portfolio|return)\b", re.I)),
    ("derivatives", re.compile(r"\b(derivative|option|futures|hedging)\b", re.I)),
    ("crypto", re.compile(r"\b(bitcoin|crypto|blockchain)\b", re.I)),
    ("fx", re.compile(r"\b(foreign exchange|fx|carry trade|currency)\b", re.I)),
    ("banking", re.compile(r"\b(bank|banking|credit|loan|deposit)\b", re.I)),
    ("corporate_finance", re.compile(r"\b(corporate finance|merger|acquisition|m&a|ipo|governance|earnings)\b", re.I)),
    ("real_estate", re.compile(r"\b(real estate|property|housing|reit|mortgage)\b", re.I)),
    ("econometrics", re.compile(r"\b(econometric|time series|panel data|bayesian|semiparametric)\b", re.I)),
    ("machine_learning", re.compile(r"\b(machine learning|deep learning|artificial intelligence|neural|big data)\b", re.I)),
    ("fintech", re.compile(r"\b(fintech|quantitative trading|algorithmic)\b", re.I)),
    ("accounting", re.compile(r"\b(accounting|audit|accrual|financial statement|esg|disclosure)\b", re.I)),
    ("taxation", re.compile(r"\b(tax|taxation|fiscal)\b", re.I)),
    ("marketing_consumer", re.compile(r"\b(consumer|brand|retail|shopping|purchase)\b", re.I)),
    ("social_media", re.compile(r"\b(social media|youtube|instagram|tiktok|facebook|influencer|streaming|line)\b", re.I)),
    ("digital_marketing", re.compile(r"\b(digital marketing|e-commerce|ecommerce|advertising|mar tech)\b", re.I)),
    ("green_marketing", re.compile(r"\b(green|sustainable|sustainability|esg consumption)\b", re.I)),
    ("org_behavior", re.compile(r"\b(organizational|leadership|team|hrm|human resource|workplace|career)\b", re.I)),
    ("psychology_survey", re.compile(r"\b(psycholog|survey|scale|stress|coping|personality)\b", re.I)),
    ("patents", re.compile(r"\b(patent|uspto|invention|citation)\b", re.I)),
    ("innovation", re.compile(r"\b(innovation|entrepreneur|startup|technology transfer|rnd)\b", re.I)),
    ("forecasting", re.compile(r"\b(forecast|foresight|diffusion|scenario)\b", re.I)),
    ("international_business", re.compile(r"\b(international|fdi|diversification|global|cross-cultural)\b", re.I)),
    ("strategy", re.compile(r"\b(strategy|competitive|venture|business model)\b", re.I)),
    ("supply_chain", re.compile(r"\b(supply chain|logistics|procurement)\b", re.I)),
    ("taiwan_market", re.compile(r"\b(taiwan|taiwanese|twse|mops)\b", re.I)),
    ("asia_pacific", re.compile(r"\b(asia|pacific|china|chinese)\b", re.I)),
    ("energy", re.compile(r"\b(wind|solar|semiconductor|energy|power)\b", re.I)),
    ("healthcare", re.compile(r"\b(health|medical|hospital|patient)\b", re.I)),
    ("hospitality", re.compile(r"\b(leisure|tourism|hospitality|farm)\b", re.I)),
]

DATASET_RULES: list[tuple[str, set[str], list[str]]] = [
    (
        "taiwan_equity_panel",
        {"equities", "corporate_finance", "accounting", "taiwan_market"},
        [
            "TWSE listed firm daily prices and fundamentals panel",
            "Taiwan MOPS financial statements cross-section",
            "Corporate governance index for Taiwan listed companies",
        ],
    ),
    (
        "factor_asset_pricing",
        {"equities", "econometrics", "fx"},
        [
            "Ken French factor returns Asia-Pacific",
            "CRSP-style monthly stock returns replication package",
            "FX carry trade return panel",
        ],
    ),
    (
        "crypto_macro",
        {"crypto", "econometrics", "fintech"},
        [
            "Bitcoin daily returns and volatility panel",
            "Economic policy uncertainty vs crypto returns dataset",
            "CoinGecko historical crypto market cap panel",
        ],
    ),
    (
        "banking_credit",
        {"banking", "corporate_finance"},
        [
            "Taiwan bank financial ratios panel",
            "Credit risk and loan performance academic replication data",
            "Household finance survey microdata DOI package",
        ],
    ),
    (
        "real_estate_panel",
        {"real_estate"},
        [
            "Taiwan housing price index time series",
            "Real estate investment trust returns panel",
            "Mortgage and property transaction government open data",
        ],
    ),
    (
        "accounting_esg",
        {"accounting", "green_marketing"},
        [
            "ESG disclosure dataset Asia listed firms",
            "Earnings management empirical replication panel",
            "Audit quality and internal control survey data",
        ],
    ),
    (
        "social_media_scrape",
        {"social_media", "digital_marketing"},
        [
            "YouTube/TikTok influencer engagement time series scrape",
            "Brand community social media post corpus",
            "Platform advertising performance benchmark dataset",
        ],
    ),
    (
        "consumer_survey",
        {"marketing_consumer", "green_marketing", "psychology_survey"},
        [
            "Consumer behavior survey replication package (DataCite)",
            "Retail e-commerce clickstream anonymized panel",
            "Green consumption attitude survey dataset",
        ],
    ),
    (
        "patent_analytics",
        {"patents", "innovation", "forecasting"},
        [
            "USPTO/TIPO patent citation bulk by technology class",
            "Patent value assessment benchmark dataset",
            "Technology diffusion forecast academic panel",
        ],
    ),
    (
        "innovation_ecosystem",
        {"innovation", "strategy", "forecasting"},
        [
            "Startup funding and venture database scrape",
            "Open innovation survey replication data",
            "Technology foresight scenario workshop datasets",
        ],
    ),
    (
        "org_hr_surveys",
        {"org_behavior", "psychology_survey"},
        [
            "Organizational behavior validated scale repository",
            "Workplace team dynamics survey panel",
            "Leadership and HRM cross-cultural survey data",
        ],
    ),
    (
        "international_trade",
        {"international_business", "strategy", "supply_chain"},
        [
            "FDI flows and firm internationalization panel",
            "UN Comtrade bilateral trade flows",
            "Global supply chain disruption event dataset",
        ],
    ),
    (
        "ml_fintech_alt",
        {"machine_learning", "fintech", "econometrics"},
        [
            "ML finance benchmark order book sample",
            "Alternative data for quantitative trading tutorial set",
            "High-frequency return prediction open dataset",
        ],
    ),
    (
        "energy_tech_policy",
        {"energy", "forecasting", "patents"},
        [
            "Wind/solar patent landscape citation network",
            "Taiwan semiconductor industry patent panel",
            "Energy technology assessment scenario datasets",
        ],
    ),
    (
        "public_finance_micro",
        {"taxation"},
        [
            "Taiwan household expenditure survey microdata summary",
            "Local public finance and taxation panel",
            "Applied microeconometrics replication package",
        ],
    ),
    (
        "news_events_macro",
        {"econometrics", "corporate_finance"},
        [
            "GDELT news shock cross-asset panel (when event study needed)",
            "Macro announcement surprise dataset",
            "Policy uncertainty index time series",
        ],
    ),
]


@dataclass
class FacultyLink:
    slug: str
    name: str
    discipline: str
    profile_url: str
    title_hint: str = ""


@dataclass
class FacultyProfile:
    slug: str
    name_en: str
    discipline: str
    title: str = ""
    email: str = ""
    profile_url: str = ""
    specialties: list[str] = field(default_factory=list)
    journal_papers: list[str] = field(default_factory=list)
    research_keywords: list[str] = field(default_factory=list)
    domain_tags: list[str] = field(default_factory=list)
    method_tags: list[str] = field(default_factory=list)
    recommended_datasets: list[dict[str, str]] = field(default_factory=list)
    starter_prompts: list[str] = field(default_factory=list)
    preferred_sources: list[str] = field(default_factory=list)
    scrape_notes: str = ""


def _html_to_text(html: str) -> str:
    """Preserve line breaks so section boundaries survive."""
    h = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    h = re.sub(r"<br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"</li>", "\n", h, flags=re.I)
    h = re.sub(r"</p>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    h = unescape(h)
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"\n\s*\n+", "\n", h)
    return h.strip()


def _clean_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fetch(client: httpx.Client, url: str, retries: int = 3) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = client.get(url, timeout=45.0, follow_redirects=True)
            r.raise_for_status()
            return r.text
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def _parse_group_page(html: str, discipline: str) -> list[FacultyLink]:
    links: list[FacultyLink] = []
    pattern = re.compile(
        r'<h1>\s*<a href=["\']Teacher\.aspx\?ID=([^"\']+)["\'][^>]*>([^<]+)</a>',
        re.I,
    )
    for m in pattern.finditer(html):
        slug = m.group(1).strip()
        name = _clean_inline(m.group(2))
        tail = html[m.end() : m.end() + 2500]
        title_m = re.search(r"Title:\s*(?:</?[^>]+>\s*)*([^<\n]+)", tail, re.I)
        spec_m = re.search(
            r"Speciality:\s*(?:</?[^>]+>\s*)*(.+?)(?:</p>|</div>|<h1>)",
            tail,
            re.I | re.S,
        )
        title_hint = _clean_inline(title_m.group(1))[:200] if title_m else ""
        spec_hint = _clean_inline(re.sub(r"<[^>]+>", " ", spec_m.group(1)))[:300] if spec_m else ""
        links.append(
            FacultyLink(
                slug=slug,
                name=name,
                discipline=discipline,
                profile_url=f"{BASE}/EN/Page/Teacher.aspx?ID={slug}",
                title_hint=title_hint,
            )
        )
        if spec_hint and links:
            # stash group-page specialty hint on title field suffix for fallback
            links[-1].title_hint = f"{title_hint} | {spec_hint}" if title_hint else spec_hint
    return links


_TAB_NAV = re.compile(
    r"^(Journal Papers|Conference Papers|Research Grants|Books/Pub\.|Industrial Grants|"
    r"Courses|Dissertation|Awards & Certificates|Pro\. Membership|Other Contributions|"
    r"PhD Thesis Titles|International Experiences)$",
    re.I,
)


def _parse_journal_papers(text: str) -> list[str]:
    """Papers live after tab headers; lines include (YYYY) or , YYYY,."""
    anchor = text.find("Journal Papers")
    if anchor < 0:
        return []
    chunk = text[anchor:]
    stop = chunk.find("Professor Login")
    if stop > 0:
        chunk = chunk[:stop]
    lines = [ln.strip() for ln in chunk.split("\n")]
    papers: list[str] = []
    for line in lines:
        if not line or _TAB_NAV.match(line):
            continue
        if len(line) < 35:
            continue
        if re.search(r"\(\d{4}\)", line) or re.search(r",\s*20\d{2}\s*,", line) or re.search(
            r"\b20\d{2}\b", line
        ):
            if re.search(r"\b(CM\d|Course|PhD Technology Management Theory)\b", line, re.I):
                continue
            # Require publication-like cues, not bare years in course codes.
            if not re.search(
                r"(Journal|Review|Finance|Accounting|Management|Letters|Quarterly|Science|"
                r"Marketing|Paper|accepted|SSCI|SCI|TSSCI|Vol\.|Volume|pp\.)",
                line,
                re.I,
            ):
                continue
            papers.append(line[:500])
    return papers


def _extract_section(text: str, start_label: str, stop_labels: list[str]) -> str:
    start = text.find(start_label)
    if start < 0:
        return ""
    chunk = text[start + len(start_label) :]
    stops = [chunk.find(lbl) for lbl in stop_labels if chunk.find(lbl) >= 0]
    end = min(stops) if stops else len(chunk)
    return chunk[:end].strip()


def _parse_teacher_page(html: str, link: FacultyLink) -> FacultyProfile:
    text = _html_to_text(html)

    name = link.name
    blocks = text.split("Professor Info")
    if len(blocks) > 1:
        block = blocks[-1]
        name_m = re.search(r"^\s*([^\n]{2,120}?)\s+Title\s+", block, flags=re.M)
        if name_m:
            candidate = _clean_inline(name_m.group(1))
            if candidate and "Discipline of" not in candidate and "Home >>" not in candidate:
                name = candidate

    title = link.title_hint
    title_m = re.search(r"Title\s+(.+?)\s+Speciality\s+", text, flags=re.S)
    if title_m:
        title = _clean_inline(title_m.group(1))

    specialties: list[str] = []
    spec_block = _extract_section(
        text,
        "Speciality",
        ["Academic BG.", "Experience", "Journal Papers", "Professor Login"],
    )
    if spec_block:
        for line in spec_block.split("\n"):
            part = _clean_inline(line.strip(" -,"))
            if part and len(part) > 2:
                specialties.append(part)

    email = ""
    email_m = re.search(r"Email:\s*([A-Za-z0-9._%+-]+@saturn\.yzu\.edu\.tw)", text, re.I)
    if email_m:
        email = email_m.group(1).lower()

    papers = _parse_journal_papers(text)

    corpus = " ".join(specialties + papers[:25]).lower()
    domain_tags = sorted({tag for tag, pat in TAG_PATTERNS if pat.search(corpus)})

    method_tags: list[str] = []
    if re.search(r"\b(econometric|time series|panel|semiparametric|bayesian)\b", corpus):
        method_tags.append("econometrics_panel")
    if re.search(r"\b(survey|scale|questionnaire|interview)\b", corpus):
        method_tags.append("survey")
    if re.search(r"\b(scrape|web|social media|online|digital)\b", corpus):
        method_tags.append("scrape_text")
    if re.search(r"\b(patent|citation|bibliometric)\b", corpus):
        method_tags.append("patent_analytics")
    if re.search(r"\b(forecast|foresight|scenario|delphi)\b", corpus):
        method_tags.append("forecasting")
    if re.search(r"\b(experiment|lab study|randomized)\b", corpus):
        method_tags.append("experiment")
    if not method_tags:
        method_tags.append("empirical_secondary")

    research_keywords = _top_keywords(corpus)

    recommended = _recommend_datasets(domain_tags, method_tags, specialties, papers)
    prompts = [d["prompt"] for d in recommended[:5]]
    sources = _preferred_sources(domain_tags, method_tags)

    notes = ""
    if not email:
        notes = "email_not_found_on_page"
    if not papers:
        notes = (notes + ";no_journal_papers_parsed").strip(";")

    discipline = link.discipline
    disc_m = re.search(
        r"Professor Login\s+Professor Info\s+.+?\s+(Finance|Marketing|Accounting|OrgMgt|TechMgt|IntBiz|DigitalFinance)\s",
        text,
        flags=re.S,
    )
    if disc_m:
        discipline = disc_m.group(1)

    return FacultyProfile(
        slug=link.slug,
        name_en=name,
        discipline=discipline,
        title=title,
        email=email,
        profile_url=link.profile_url,
        specialties=specialties,
        journal_papers=papers[:30],
        research_keywords=research_keywords,
        domain_tags=domain_tags,
        method_tags=method_tags,
        recommended_datasets=recommended,
        starter_prompts=prompts,
        preferred_sources=sources,
        scrape_notes=notes,
    )


def _top_keywords(corpus: str, limit: int = 12) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9-]{3,}", corpus)
    stop = {
        "with",
        "from",
        "that",
        "this",
        "their",
        "using",
        "study",
        "analysis",
        "research",
        "journal",
        "paper",
        "management",
        "business",
        "university",
        "taiwan",
        "international",
        "review",
        "impact",
        "factor",
        "case",
        "model",
        "based",
        "approach",
        "evidence",
        "effects",
        "role",
        "between",
        "through",
        "social",
    }
    freq: dict[str, int] = {}
    for t in tokens:
        if t in stop:
            continue
        freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return [w for w, _ in ranked[:limit]]


def _recommend_datasets(
    domain_tags: list[str],
    method_tags: list[str],
    specialties: list[str],
    papers: list[str],
) -> list[dict[str, str]]:
    tagset = set(domain_tags)
    scored: list[tuple[float, str, str, str]] = []
    for family_id, req_tags, datasets in DATASET_RULES:
        overlap = len(tagset & req_tags)
        if overlap == 0:
            continue
        score = overlap + 0.1 * len(req_tags)
        for ds in datasets:
            scored.append((score, family_id, ds, _to_prompt(ds, specialties, papers)))

    scored.sort(key=lambda x: (-x[0], x[2]))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for score, family_id, ds, prompt in scored:
        if ds in seen:
            continue
        seen.add(ds)
        out.append(
            {
                "family": family_id,
                "dataset": ds,
                "prompt": prompt,
                "score": f"{score:.1f}",
            }
        )
        if len(out) >= 8:
            break
    if not out:
        out.append(
            {
                "family": "general_academic",
                "dataset": "Open replication datasets matching your keywords (DataCite search)",
                "prompt": _to_prompt("replication dataset for my research area", specialties, papers),
                "score": "0.1",
            }
        )
    return out


def _to_prompt(dataset: str, specialties: list[str], papers: list[str]) -> str:
    hint = specialties[0] if specialties else ""
    if papers:
        paper_hint = re.sub(r"\s+", " ", papers[0])[:120]
        return f"Source {dataset} for work on {hint or paper_hint}"
    return f"Source {dataset}" + (f" ({hint})" if hint else "")


def _preferred_sources(domain_tags: list[str], method_tags: list[str]) -> list[str]:
    sources = ["datacite", "yzu_submit_job"]
    tagset = set(domain_tags)
    if tagset & {"equities", "crypto", "fx", "fintech", "econometrics"}:
        sources.extend(["yfinance", "fred"])
    if "taiwan_market" in tagset or "accounting" in tagset or "corporate_finance" in tagset:
        sources.append("twse_openapi")
    if "social_media" in tagset or "scrape_text" in method_tags:
        sources.append("cluster_scrape")
    if "patents" in tagset:
        sources.append("patent_bulk")
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def scrape_all(*, delay_s: float = 0.35) -> list[FacultyProfile]:
    by_slug: dict[str, FacultyLink] = {}
    with httpx.Client(headers={"User-Agent": "Sharpe-Renaissance/yzu-faculty-scraper"}) as client:
        for discipline, url in GROUP_PAGES:
            html = _fetch(client, url)
            for link in _parse_group_page(html, discipline):
                by_slug.setdefault(link.slug, link)

        # Only full-time faculty from discipline pages (skip part-time roster noise).

        profiles: list[FacultyProfile] = []
        for i, slug in enumerate(sorted(by_slug), 1):
            link = by_slug[slug]
            print(f"[{i}/{len(by_slug)}] {link.name} ({slug}) …", flush=True)
            try:
                html = _fetch(client, link.profile_url)
                profiles.append(_parse_teacher_page(html, link))
            except Exception as exc:  # noqa: BLE001
                profiles.append(
                    FacultyProfile(
                        slug=slug,
                        name_en=link.name,
                        discipline=link.discipline,
                        profile_url=link.profile_url,
                        scrape_notes=f"fetch_failed:{exc}",
                    )
                )
            time.sleep(delay_s)
    return profiles


def profiles_to_json(profiles: list[FacultyProfile]) -> dict[str, Any]:
    return {
        "source": "https://www.cm.yzu.edu.tw/EN/Page/Faculty.aspx?ItemId=283",
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(profiles),
        "faculty": [
            {
                "slug": p.slug,
                "name_en": p.name_en,
                "email": p.email,
                "discipline": p.discipline,
                "title": p.title,
                "profile_url": p.profile_url,
                "specialties": p.specialties,
                "journal_papers": p.journal_papers,
                "paper_count_parsed": len(p.journal_papers),
                "research_keywords": p.research_keywords,
                "domain_tags": p.domain_tags,
                "method_tags": p.method_tags,
                "preferred_sources": p.preferred_sources,
                "recommended_datasets": p.recommended_datasets,
                "starter_prompts": p.starter_prompts,
                "scrape_notes": p.scrape_notes,
            }
            for p in sorted(profiles, key=lambda x: (x.discipline, x.name_en))
        ],
    }


def main() -> None:
    repo = repo_root_from_file(__file__)
    out_path = repo / "config" / "yzu_cm_faculty_registry.json"
    profiles = scrape_all()
    payload = profiles_to_json(profiles)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ok = sum(1 for p in profiles if p.email and p.journal_papers)
    print(f"Wrote {len(profiles)} profiles to {out_path} ({ok} with email+papers)")


if __name__ == "__main__":
    main()
