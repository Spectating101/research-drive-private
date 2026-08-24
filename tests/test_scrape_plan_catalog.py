from scripts.research_data_mcp.scrape_plan import apply_probe_catalog_hints, build_generic_scrape_plan


def test_apply_probe_catalog_hints_from_pagination() -> None:
    plan = build_generic_scrape_plan("https://etherscan.io/tokens?l=Stablecoin", mode="page")
    probe = {
        "connector": {
            "spec": {
                "access_mode": "html_catalog",
                "pagination": {"type": "html_next_link", "detected": True},
            }
        }
    }
    out = apply_probe_catalog_hints(plan, probe)
    assert out["scrape_mode"] == "catalog"
    assert out["job_type"] == "scraper_run"
    assert out["catalog_max_pages"] == 2
    assert out["catalog_max_tokens"] == 5


def test_apply_probe_catalog_hints_from_source_probe() -> None:
    plan = {
        "title": "Probe public source",
        "job_type": "source_probe",
        "url": "https://etherscan.io/tokens?l=Stablecoin",
        "launchable": True,
    }
    probe = {
        "connector": {
            "spec": {
                "access_mode": "html_catalog",
                "pagination": {"detected": True},
            }
        }
    }
    out = apply_probe_catalog_hints(plan, probe)
    assert out["job_type"] == "scraper_run"
    assert out["scrape_mode"] == "catalog"
    plan = build_generic_scrape_plan("https://example.com/data", mode="page")
    probe = {"connector": {"spec": {"access_mode": "html_catalog", "pagination": {"detected": False}}}}
    assert apply_probe_catalog_hints(plan, probe)["scrape_mode"] == "page"
