from __future__ import annotations

import json
import zipfile
from pathlib import Path
from urllib.request import Request

import pytest

from scripts.cluster_agent.network_policy import validate_public_http_url
from scripts.cluster_agent.remote_collect import PublicOnlyRedirectHandler, collect_manifest


def _resolver(*addresses: str):
    def resolve(host: str, port: int, *, type: int):  # noqa: A002
        del host, port, type
        return [(2, 1, 6, "", (address, 443)) for address in addresses]

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://10.0.0.8/private",
        "http://100.64.0.1/tailscale",
        "http://100.127.141.44/desk",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/admin",
        "http://metadata.google.internal/computeMetadata/v1/",
    ],
)
def test_rejects_literal_and_named_internal_targets(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_http_url(url)


def test_rejects_hostname_resolving_to_private_address() -> None:
    with pytest.raises(ValueError, match="non-public"):
        validate_public_http_url(
            "https://public-looking.example/data.json",
            resolver=_resolver("192.168.1.20"),
        )


def test_rejects_mixed_public_private_dns_answers() -> None:
    with pytest.raises(ValueError, match="non-public"):
        validate_public_http_url(
            "https://mixed.example/data.json",
            resolver=_resolver("8.8.8.8", "10.10.10.10"),
        )


def test_accepts_public_resolution_and_returns_evidence() -> None:
    out = validate_public_http_url(
        "https://data.example/data.json",
        resolver=_resolver("8.8.8.8", "2606:4700:4700::1111"),
    )
    assert out["host"] == "data.example"
    assert out["resolved_addresses"] == ["2606:4700:4700::1111", "8.8.8.8"]


def test_redirect_handler_blocks_private_target_before_follow() -> None:
    handler = PublicOnlyRedirectHandler()
    with pytest.raises(ValueError):
        handler.redirect_request(
            Request("https://8.8.8.8/start"),
            None,
            302,
            "Found",
            {},
            "http://127.0.0.1/internal",
        )


def test_manifest_rejects_private_target_without_attempting_download(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    artifact = tmp_path / "artifact.zip"
    manifest.write_text(
        json.dumps({"job_id": "ssrf-canary", "items": [{"url": "http://127.0.0.1/private"}]}),
        encoding="utf-8",
    )

    code, report = collect_manifest(manifest, artifact, retries=0, delay=0)

    assert code == 1
    assert report["succeeded"] == 0
    assert report["failed"] == 1
    assert report["items"][0]["attempts"] == 0
    assert "not public" in report["items"][0]["error"]
    assert not artifact.exists()


def test_manifest_preserves_declared_repository_filename(monkeypatch, tmp_path: Path) -> None:
    """An opaque ``/content`` URL must still land as the declared CSV name."""
    from scripts.cluster_agent import remote_collect

    source = tmp_path / "payload"
    source.write_text("id,value\n1,alpha\n", encoding="utf-8")

    def fake_download(item, *, index, name, output_dir, **_kwargs):
        target = output_dir / name
        target.write_bytes(source.read_bytes())
        return remote_collect.ItemResult(
            index=index,
            url=str(item["url"]),
            name=name,
            ok=True,
            attempts=1,
            bytes=target.stat().st_size,
            local_path=str(target),
        )

    monkeypatch.setattr(remote_collect, "_download_item", fake_download)
    manifest = tmp_path / "manifest.json"
    artifact = tmp_path / "artifact.zip"
    manifest.write_text(
        json.dumps(
            {
                "job_id": "filename-canary",
                "items": [
                    {
                        "url": "https://zenodo.org/api/records/1/files/panel.csv/content",
                        "filename": "panel.csv",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    code, report = collect_manifest(manifest, artifact, retries=0, delay=0)

    assert code == 0
    assert report["items"][0]["name"] == "panel.csv"
    with zipfile.ZipFile(artifact) as archive:
        assert "raw/panel.csv" in archive.namelist()


def test_pick_pinned_address_prefers_ipv4():
    from scripts.cluster_agent.network_policy import pick_pinned_address

    pinned = pick_pinned_address(
        {"resolved_addresses": ["2606:4700:4700::1111", "8.8.8.8"]}
    )
    assert pinned == "8.8.8.8"
