export function EmptyRailState({
  title = "No dataset selected",
  hint = "",
  minimal = false,
}) {
  return (
    <div
      className={`rd-v2-rail-empty-state${minimal ? " rd-v2-rail-empty-state--minimal" : ""}`}
      role="status"
      data-testid="rail-empty"
    >
      {!minimal ? (
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
      ) : null}
      <p className="rd-v2-rail-empty-title">{title}</p>
      {hint ? <p className="rd-v2-rail-empty-hint">{hint}</p> : null}
    </div>
  );
}
