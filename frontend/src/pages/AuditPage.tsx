import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { AuditEntry } from "../api/types";

export function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [actionFilter, setActionFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<AuditEntry[]>("/audit?limit=500")
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);

  const actions = useMemo(
    () => Array.from(new Set(entries.map((e) => e.action))).sort(),
    [entries],
  );
  const visible = entries.filter((e) => actionFilter === "all" || e.action === actionFilter);

  function summarize(detail: Record<string, unknown>): string {
    const keys = Object.keys(detail);
    if (keys.length === 0) return "";
    return keys
      .map((k) => `${k}: ${typeof detail[k] === "object" ? JSON.stringify(detail[k]) : String(detail[k])}`)
      .join(" · ");
  }

  if (loading) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Audit log</h1>
      <p className="muted">Auth and collection activity for your tenant. Admin-only, read-only.</p>

      {entries.length === 0 ? (
        <p className="muted">No audit entries.</p>
      ) : (
        <>
          <div className="row" style={{ marginBottom: "0.75rem" }}>
            <div style={{ flex: "0 0 auto" }}>
              <label>Action</label>
              <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)}>
                <option value="all">All actions ({entries.length})</option>
                {actions.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
          </div>

          <div className="card" style={{ padding: 0 }}>
            <table>
              <thead>
                <tr><th>When (UTC)</th><th>Action</th><th>Target</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {visible.map((e) => (
                  <tr key={e.id}>
                    <td className="mono" style={{ whiteSpace: "nowrap" }}>
                      {e.created_at.replace("T", " ").slice(0, 19)}
                    </td>
                    <td><span className="badge draft">{e.action}</span></td>
                    <td className="mono">{e.target ? e.target.slice(0, 8) : "—"}</td>
                    <td className="muted" style={{ fontSize: "0.8rem" }}>{summarize(e.detail)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
