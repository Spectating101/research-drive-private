import { destinationHint } from "@/v2/vaultDestinations";

export function DiscoverDestinationField({ value, options = [], onChange, disabled = false }) {
  const hint = destinationHint(options, value);

  return (
    <div className="rd-v2-discover-dest-field">
      <label className="rd-v2-discover-dest-label" htmlFor="discover-vault-destination">
        Vault destination
      </label>
      <select
        id="discover-vault-destination"
        className="rd-v2-select rd-v2-select-block"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange?.(e.target.value)}
        data-testid="discover-destination-select"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {hint ? <p className="rd-v2-discover-dest-hint">{hint}</p> : null}
    </div>
  );
}
