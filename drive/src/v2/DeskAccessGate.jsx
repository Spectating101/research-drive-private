import { useState } from "react";
import { saveDeskToken } from "@/v2/deskSession";

/** Private-by-default entry for browsers outside the trusted Tailscale desk. */
export function DeskAccessGate({ access, busy = false, onRetry }) {
  const [token, setToken] = useState("");
  const configured = access?.server_configured;

  const connect = () => {
    const value = saveDeskToken(token);
    setToken("");
    onRetry?.({ force: true, tokenProvided: Boolean(value) });
  };

  return (
    <main className="rd-v2-access-gate" aria-labelledby="rd-access-title">
      <section className="rd-v2-access-card">
        <span className="rd-v2-access-kicker">RESEARCH DRIVE · PRIVATE DESK</span>
        <h1 id="rd-access-title">Research data stays inside the desk.</h1>
        <p>
          This browser has not established an authorized desk session. Catalog data, faculty memory,
          credentials, jobs, and worker details remain hidden until access is verified.
        </p>

        <div className="rd-v2-access-boundary" aria-label="Access boundary">
          <span><i aria-hidden="true">✓</i> Interface shell</span>
          <span><i aria-hidden="true">—</i> Research data</span>
          <span><i aria-hidden="true">—</i> Ask and collection</span>
          <span><i aria-hidden="true">—</i> Operations</span>
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            connect();
          }}
        >
          <label htmlFor="rd-access-token">Desk access token</label>
          <div className="rd-v2-access-form-row">
            <input
              id="rd-access-token"
              type="password"
              autoComplete="current-password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="Paste a reviewer or operator token"
            />
            <button type="submit" disabled={busy || !token.trim()}>
              {busy ? "Checking…" : "Connect"}
            </button>
          </div>
        </form>

        <button
          type="button"
          className="rd-v2-access-retry"
          disabled={busy}
          onClick={() => onRetry?.({ force: true, tokenProvided: false })}
        >
          Retry trusted internal entry
        </button>

        <small>
          {configured === false
            ? "This host has no desk credential configured; protected APIs fail closed."
            : access?.error
              ? "Secure access check is unavailable. The desk remains locked; retry after the service is restored."
              : "Authorized Tailscale entry normally connects automatically."}
        </small>
      </section>
    </main>
  );
}
