import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Investigation, Organization } from "../api/types";
import { StatusBadge } from "../components/Layout";

export function DashboardPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<Organization[]>("/organizations"),
      api.get<Investigation[]>("/investigations"),
    ])
      .then(([o, i]) => {
        setOrgs(o);
        setInvestigations(i);
      })
      .finally(() => setLoading(false));
  }, []);

  const completed = investigations.filter((i) =>
    ["success", "complete", "partial"].includes(i.status),
  ).length;
  const running = investigations.filter((i) => i.status === "running").length;

  if (loading) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Dashboard</h1>
      <div className="tiles">
        <div className="tile"><div className="num">{orgs.length}</div><div className="label">Organizations</div></div>
        <div className="tile"><div className="num">{investigations.length}</div><div className="label">Investigations</div></div>
        <div className="tile"><div className="num">{completed}</div><div className="label">Completed</div></div>
        <div className="tile"><div className="num">{running}</div><div className="label">Running</div></div>
      </div>

      <h2>Recent investigations</h2>
      {investigations.length === 0 ? (
        <p className="muted">
          No investigations yet. Create an organization and start one from the{" "}
          <Link to="/organizations">Organizations</Link> page.
        </p>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr><th>Investigation</th><th>Type</th><th>Status</th><th>Created</th></tr>
            </thead>
            <tbody>
              {investigations.map((inv) => (
                <tr key={inv.id}>
                  <td><Link to={`/investigations/${inv.id}`} className="mono">{inv.id.slice(0, 8)}</Link></td>
                  <td>{inv.assessment_type}</td>
                  <td><StatusBadge status={inv.status} /></td>
                  <td className="muted">{new Date(inv.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
