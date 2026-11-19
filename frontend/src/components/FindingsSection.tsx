import { useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Finding, FindingSeverity, FindingStatus } from "../api/types";

const SEVERITY_ORDER: FindingSeverity[] = ["critical", "high", "medium", "low", "info"];
const STATUSES: FindingStatus[] = ["open", "triaged", "dismissed"];

interface Props {
  findings: Finding[];
  canWrite: boolean;
  onChanged: () => void;
}

export function FindingsSection({ findings, canWrite, onChanged }: Props) {
  const [sevFilter, setSevFilter] = useState<"all" | FindingSeverity>("all");
  const [showDismissed, setShowDismissed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of findings) c[f.severity] = (c[f.severity] ?? 0) + 1;
    return c;
  }, [findings]);

  const visible = findings
    .filter((f) => (sevFilter === "all" ? true : f.severity === sevFilter))
    .filter((f) => (showDismissed ? true : f.status !== "dismissed"));

  async function setStatus(f: Finding, status: FindingStatus) {
    setBusy(f.id);
    setError(null);
    try {
      await api.patch(`/findings/${f.id}`, { status });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update finding");
    } finally {
      setBusy(null);
    }
  }

  if (findings.length === 0) {
    return (
      <>
        <h2>Findings</h2>
        <p className="muted">No findings yet. Run collection to derive findings from assets.</p>
      </>
    );
  }

  return (
    <>
      <h2>Findings ({findings.length})</h2>
      <div className="row" style={{ marginBottom: "0.75rem", alignItems: "center" }}>
        <div style={{ flex: "0 0 auto" }}>
          <label>Severity</label>
          <select value={sevFilter} onChange={(e) => setSevFilter(e.target.value as typeof sevFilter)}>
            <option value="all">All severities</option>
            {SEVERITY_ORDER.filter((s) => counts[s]).map((s) => (
              <option key={s} value={s}>{s} ({counts[s]})</option>
            ))}
          </select>
        </div>
        <label style={{ flex: "0 0 auto", display: "flex", alignItems: "center", gap: "0.4rem", margin: 0 }}>
          <input
            type="checkbox"
            style={{ width: "auto" }}
            checked={showDismissed}
            onChange={(e) => setShowDismissed(e.target.checked)}
          />
          Show dismissed
        </label>
      </div>

      {error && <p className="error">{error}</p>}

      {visible.length === 0 ? (
        <p className="muted">No findings match the current filter.</p>
      ) : (
        visible.map((f) => (
          <div key={f.id} className={`card finding sev-${f.severity} ${f.status}`}>
            <div className="finding-head">
              <span className="title">{f.title}</span>
              <span className={`badge sev-${f.severity}`}>{f.severity}</span>
              <span className={`badge ${f.classification}`}>{f.classification}</span>
              <span className={`badge ${f.status}`}>{f.status}</span>
            </div>
            <p className="desc">{f.description}</p>
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              Confidence {f.confidence.toFixed(2)} · {f.finding_type}
            </div>

            {f.evidence.length > 0 && (
              <details className="evidence">
                <summary>Evidence ({f.evidence.length})</summary>
                <ul>
                  {f.evidence.map((e, i) => (
                    <li key={`${e.asset_type}:${e.value}:${i}`}>
                      <span className="badge draft">{e.asset_type}</span>{" "}
                      <span className="mono">{e.value}</span>{" "}
                      <span className="muted">
                        — {e.sources.join(", ")} (conf {e.confidence.toFixed(2)})
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {canWrite && (
              <div className="triage" style={{ marginTop: "0.6rem" }}>
                <label style={{ margin: 0 }}>Triage</label>
                <select
                  value={f.status}
                  disabled={busy === f.id}
                  onChange={(e) => setStatus(f, e.target.value as FindingStatus)}
                >
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            )}
          </div>
        ))
      )}
    </>
  );
}
