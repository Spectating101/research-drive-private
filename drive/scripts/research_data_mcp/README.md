# Production-only package boundary

The runnable `research_data_mcp` package does **not** live in this public repository.

Canonical production source:

```text
Spectating101/research-drive-private
drive/scripts/research_data_mcp/
```

This directory exists only to make the public/private boundary explicit. Do not copy production MCP, gateway, chat, registry, acquisition, or Synthesis execution modules here.

Public equivalents belong in one of these forms:

- product/data-shape documentation under `docs/product/`;
- frontend normalization and fixtures under `drive/src/v2/` and `e2e/`;
- dependency-free interoperability behavior under root `scripts/yzu_cluster/`;
- sanitized golden payload fixtures after live acceptance.

A public Python facade that imports absent private packages is false completeness and must fail repository-boundary review.
