# Research Drive — visual tokens

**Role:** Colors, spacing, typography only.  
**Composition & workflows:** [`RESEARCH_DRIVE_UI_CANON.md`](../RESEARCH_DRIVE_UI_CANON.md) §2.  
**Implementation:** `src/app/theme/tokens.css`

Composition (shell zones, DetailPanel, workflows) is defined in the canon — not here.

```css
:root {
  --rd-canvas: #f7f9fc;
  --rd-surface: #ffffff;
  --rd-border: #e2e8f0;
  --rd-text: #0f172a;
  --rd-muted: #64748b;
  --rd-accent: #2563eb;
  --rd-ready: #059669;
  --rd-connected: #2563eb;
  --rd-review: #d97706;
  --rd-failed: #dc2626;
  --rd-sidebar-min: 224px;
  --rd-sidebar-ideal: 18vw;
  --rd-sidebar-max: 280px;
  --rd-rail-min: 360px;
  --rd-rail-ideal: 30vw;
  --rd-rail-max: 480px;
  --rd-sidebar: clamp(var(--rd-sidebar-min), var(--rd-sidebar-ideal), var(--rd-sidebar-max));
  --rd-rail: clamp(var(--rd-rail-min), var(--rd-rail-ideal), var(--rd-rail-max));
  --rd-header-h: 56px;
  --rd-row-h: 44px;
  --rd-radius: 6px;
  --rd-font-sans: "IBM Plex Sans", system-ui, sans-serif;
  --rd-font-mono: "IBM Plex Mono", ui-monospace, monospace;
}
```

See canon for `StatusPill` mapping and component usage. No tab-specific token overrides.
