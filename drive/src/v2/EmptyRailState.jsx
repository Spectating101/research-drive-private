export function EmptyRailState({
  title = "No dataset selected",
  hint = "Select a row in the catalog to inspect metadata, preview rows, or ask about procurement.",
}) {
  return (
    <div className="rd-v2-rail-empty-state" role="status">
      <svg
        className="rd-v2-rail-empty-icon"
        width="40"
        height="40"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
      </svg>
      <p className="rd-v2-rail-empty-title">{title}</p>
      <p className="rd-v2-rail-empty-hint">{hint}</p>
    </div>
  );
}
