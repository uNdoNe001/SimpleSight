import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { AlertsResponse, ChangeEvent } from "../api/types";

interface Props {
  alerts: AlertsResponse;
  canWrite: boolean;
  onChanged: () => void;
}

function describe(a: ChangeEvent): string {
  if (a.change_type === "finding_severity_changed") {
    const d = a.detail as { from?: string; to?: string };
    return `Severity escalated (${d.from} → ${d.to})`;
  }
  return "New finding";
}

export function AlertsBanner({ alerts, canWrite, onChanged }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (alerts.alerts.length === 0) return null;

  async function acknowledge(id: string) {
    setBusy(id);
    setError(null);
    try {
      await api.post(`/alerts/${id}/acknowledge`, {});
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to acknowledge");
    } finally {
      setBusy(null);
    }
  }

  const unacked = alerts.alerts.filter((a) => !a.acknowledged_at);

  return (
    <div className="card alerts-banner">
      <div className="alerts-banner-head">
        <span className="alert-bell" aria-hidden>
          ⚠
        </span>
        <strong>
          {alerts.unacknowledged > 0
            ? `${alerts.unacknowledged} new alert${alerts.unacknowledged > 1 ? "s" : ""}`
            : "Alerts"}
        </strong>
        <span className="muted" style={{ fontSize: "0.85rem" }}>
          Material changes since a prior run — high / critical findings.
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      <ul className="alerts-list">
        {(unacked.length > 0 ? unacked : alerts.alerts).map((a) => (
          <li key={a.id} className={`alert-item ${a.acknowledged_at ? "acked" : ""}`}>
            {a.severity && <span className={`badge sev-${a.severity}`}>{a.severity}</span>}
            <span className="alert-desc">{describe(a)}:</span>
            <span className="mono">{a.title}</span>
            {canWrite && !a.acknowledged_at && (
              <button
                className="btn secondary alert-ack"
                disabled={busy === a.id}
                onClick={() => acknowledge(a.id)}
              >
                {busy === a.id ? "…" : "Acknowledge"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
