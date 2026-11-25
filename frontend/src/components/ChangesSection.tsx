import { useMemo } from "react";
import type { ChangeEvent, ChangeType } from "../api/types";

interface Props {
  changes: ChangeEvent[];
}

const LABEL: Record<ChangeType, string> = {
  finding_appeared: "New finding",
  finding_resolved: "Resolved",
  finding_severity_changed: "Severity changed",
  asset_added: "New asset",
  asset_removed: "Removed asset",
};

// Marker color class per change type (styled in styles.css).
const TONE: Record<ChangeType, string> = {
  finding_appeared: "chg-up",
  finding_resolved: "chg-down",
  finding_severity_changed: "chg-up",
  asset_added: "chg-neutral",
  asset_removed: "chg-neutral",
};

function fmtRun(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ChangesSection({ changes }: Props) {
  // Group by run_at, preserving the server's newest-first ordering.
  const runs = useMemo(() => {
    const order: string[] = [];
    const byRun = new Map<string, ChangeEvent[]>();
    for (const c of changes) {
      if (!byRun.has(c.run_at)) {
        byRun.set(c.run_at, []);
        order.push(c.run_at);
      }
      byRun.get(c.run_at)!.push(c);
    }
    return order.map((run_at) => ({ run_at, events: byRun.get(run_at)! }));
  }, [changes]);

  if (changes.length === 0) return null;

  return (
    <>
      <h2>What changed ({changes.length})</h2>
      {runs.map(({ run_at, events }, idx) => (
        <div key={run_at} className="card changes-run">
          <div className="changes-run-head">
            <strong>{idx === 0 ? "Latest run" : "Run"}</strong>
            <span className="muted">{fmtRun(run_at)}</span>
          </div>
          <ul className="changes-list">
            {events.map((c) => {
              const dir = c.detail as { from?: string; to?: string };
              return (
                <li key={c.id} className={`change-item ${TONE[c.change_type]}`}>
                  <span className="change-label">{LABEL[c.change_type]}</span>
                  {c.severity && <span className={`badge sev-${c.severity}`}>{c.severity}</span>}
                  <span className="change-title mono">{c.title}</span>
                  {c.change_type === "finding_severity_changed" && dir.from && (
                    <span className="muted">
                      {" "}
                      {dir.from} → {dir.to}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </>
  );
}
