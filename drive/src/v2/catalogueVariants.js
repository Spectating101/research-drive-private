/**
 * Collapse catalogue variants of one dataset into a single row.
 *
 * A stablecoin query returned "Etherscan Stablecoin Catalog (Full Sweep)",
 * "(Medium Crawl A)", "(Small Crawl A)" and "(Medium Crawl C)" as four separate
 * results. They are one dataset captured at four crawl scales; which scale you
 * want is a download-time choice, not four things to evaluate. Four near
 * identical rows also push genuinely different results below the fold.
 *
 * Grouping is on the literal title before a trailing parenthetical — a display
 * concern about strings the desk authored, not an inference about content. Rows
 * without a parenthetical are never grouped, and a group of one renders exactly
 * as it did before.
 */
export function groupCatalogueVariants(rows = []) {
  const order = [];
  const groups = new Map();
  for (const row of rows) {
    const title = String(row?.display_name || row?.title || row?.dataset_id || "");
    const cut = title.lastIndexOf(" (");
    const base = cut > 0 && title.endsWith(")") ? title.slice(0, cut) : title;
    const variant = base === title ? "" : title.slice(cut + 2, -1);
    if (!groups.has(base)) {
      groups.set(base, { ...row, _base: base, _variants: [] });
      order.push(base);
    }
    if (variant) groups.get(base)._variants.push({ label: variant, row });
  }
  return order.map((base) => groups.get(base));
}

