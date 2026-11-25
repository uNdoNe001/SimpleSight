import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type {
  ActivityItem,
  MonitoringHealthItem,
  PortfolioSummary,
} from "../api/types";

const GRADES = ["A", "B", "C", "D", "F"];

const CHANGE_LABELS: Record<string, string> = {
  asset_added: "Asset added",
  asset_removed: "Asset removed",
  finding_appeared: "New finding",
  finding_resolved: "Finding resolved",
  finding_severity_changed: "Severity changed",
};

function timeAgo(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export function DashboardPage() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [monitors, setMonitors] = useState<MonitoringHealthItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<PortfolioSummary>("/portfolio/summary"),
      api.get<ActivityItem[]>("/portfolio/activity?limit=12"),
      api.get<MonitoringHealthItem[]>("/portfolio/monitoring-health"),
    ])
      .then(([s, a, m]) => {
        setSummary(s);
        setActivity(a);
        setMonitors(m);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading || !summary) return <p className="muted">Loading…</p>;

  const assessed = summary.assessed_investigations;
  const attention = monitors.filter((m) => m.state === "overdue" || m.state === "due");

  return (
    <>
      <h1>Dashboard</h1>

      <div className="tiles">
        <div className="tile">
          <div className="num">{summary.organizations.total}</div>
          <div className="label">
            Organizations
            {summary.organizations.archived > 0 && ` · ${summary.organizations.archived} archived`}
          </div>
        </div>
        <div className="tile">
          <div className="num">{summary.investigations_total}</div>
          <div className="label">Investigations · {assessed} assessed</div>
        </div>
        <div className="tile">
          <div className="num" style={{ color: summary.open_alerts > 0 ? "var(--danger)" : undefined }}>
            {summary.open_alerts}
          </div>
          <div className="label">Open alerts</div>
        </div>
        <div className="tile">
          <div className="num">{summary.monitoring_enabled}</div>
          <div className="label">Monitored</div>
        </div>
      </div>

      <h2>Exposure across the portfolio</h2>
      {assessed === 0 ? (
        <p className="muted">
          No investigations have been assessed yet. Start one from the{" "}
          <Link to="/organizations">Organizations</Link> page.
        </p>
      ) : (
        <div className="card">
          <div className="grade-bars">
            {GRADES.map((g) => {
              const count = summary.exposure_distribution[g] ?? 0;
              const pct = assessed > 0 ? Math.round((count / assessed) * 100) : 0;
              return (
                <div key={g} className="grade-bar">
                  <div className={`grade-pill grade-${g}`}>{g}</div>
                  <div className="grade-track">
                    <div className={`grade-fill grade-${g}`} style={{ width: `${pct}%` }} />
                  </div>
                  <div className="grade-count muted">{count}</div>
                </div>
              );
            })}
          </div>
          {summary.highest_exposure && (
            <p className="muted" style={{ marginBottom: 0 }}>
              Most exposed:{" "}
              <Link to={`/investigations/${summary.highest_exposure.investigation_id}`} className="mono">
                {summary.highest_exposure.investigation_id.slice(0, 8)}
              </Link>{" "}
              — {summary.highest_exposure.label} ({summary.highest_exposure.score}/100, grade{" "}
              {summary.highest_exposure.grade}).
            </p>
          )}
        </div>
      )}

      <h2>Monitoring health</h2>
      {monitors.length === 0 ? (
        <p className="muted">No investigations are being monitored.</p>
      ) : (
        <>
          {attention.length > 0 && (
            <p className="muted">
              {attention.length} monitored investigation{attention.length === 1 ? "" : "s"} due or overdue.
            </p>
          )}
          <div className="card" style={{ padding: 0 }}>
            <table>
              <thead>
                <tr>
                  <th>Investigation</th>
                  <th>Organization</th>
                  <th>Cadence</th>
                  <th>State</th>
                  <th>Next due</th>
                </tr>
              </thead>
              <tbody>
                {monitors.map((m) => (
                  <tr key={m.investigation_id}>
                    <td>
                      <Link to={`/investigations/${m.investigation_id}`} className="mono">
                        {m.investigation_id.slice(0, 8)}
                      </Link>
                    </td>
                    <td>{m.organization_name || "—"}</td>
                    <td>{m.interval ?? "—"}</td>
                    <td><span className={`badge monitor-${m.state}`}>{m.state}</span></td>
                    <td className="muted">
                      {m.next_due_at ? new Date(m.next_due_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2>Recent activity</h2>
      {activity.length === 0 ? (
        <p className="muted">
          No changes recorded yet. Change events appear after an investigation is re-run.
        </p>
      ) : (
        <ul className="activity-feed">
          {activity.map((a) => (
            <li key={a.id} className={a.is_material ? "material" : ""}>
              <span className="activity-when muted">{timeAgo(a.run_at)}</span>
              <span className="activity-what">
                {a.is_material && <span className="badge sev-high">alert</span>}
                <strong>{CHANGE_LABELS[a.change_type] ?? a.change_type}</strong>
                {a.severity && <span className={`badge sev-${a.severity}`}>{a.severity}</span>}{" "}
                {a.title || a.entity_key}
              </span>
              <span className="activity-where muted">
                {a.organization_name || "—"} ·{" "}
                <Link to={`/investigations/${a.investigation_id}`} className="mono">
                  {a.investigation_id.slice(0, 8)}
                </Link>
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
