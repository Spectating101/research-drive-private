const DOI_URL = /^https?:\/\/(?:dx\.)?doi\.org\/(10\.\d{4,9}\/[-._;()/:a-z0-9]+)$/i;
const BARE_DOI = /^(10\.\d{4,9}\/[-._;()/:a-z0-9]+)$/i;

export function classifyLibraryIntakeTarget(value) {
  const target = String(value || "").trim();
  if (!target) return null;

  const doiFromUrl = target.match(DOI_URL)?.[1];
  if (doiFromUrl) return { doi: doiFromUrl, url: "" };
  if (BARE_DOI.test(target)) return { doi: target, url: "" };

  try {
    const url = new URL(target);
    if (url.protocol === "http:" || url.protocol === "https:") {
      return { doi: "", url: url.toString() };
    }
  } catch {
    // A helpful caller message is more useful than throwing while the user types.
  }
  return null;
}
