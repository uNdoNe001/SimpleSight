import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Investigation, Organization } from "../api/types";
import { useAuth } from "../auth/AuthContext";

export function OrganizationsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const canWrite = user?.role !== "readonly";

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function load() {
    api.get<Organization[]>("/organizations").then(setOrgs);
  }
  useEffect(load, []);

  async function createOrg(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.post<Organization>("/organizations", {
        name,
        primary_domain: domain || null,
      });
      setName("");
      setDomain("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create organization");
    } finally {
      setBusy(false);
    }
  }

  async function startInvestigation(org: Organization) {
    const inv = await api.post<Investigation>("/investigations", {
      organization_id: org.id,
      assessment_type: "passive-osint",
    });
    navigate(`/investigations/${inv.id}`);
  }

  return (
    <>
      <h1>Organizations</h1>

      {canWrite && (
        <div className="card">
          <form onSubmit={createOrg}>
            <div className="row">
              <div>
                <label>Name</label>
                <input value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div>
                <label>Primary domain</label>
                <input
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                  placeholder="example.com"
                />
              </div>
              <div style={{ flex: "0 0 auto" }}>
                <button className="btn" disabled={busy}>Add organization</button>
              </div>
            </div>
            {error && <p className="error">{error}</p>}
          </form>
        </div>
      )}

      {orgs.length === 0 ? (
        <p className="muted">No organizations yet.</p>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr><th>Name</th><th>Primary domain</th><th></th></tr>
            </thead>
            <tbody>
              {orgs.map((org) => (
                <tr key={org.id}>
                  <td>{org.name}</td>
                  <td className="mono">{org.primary_domain ?? <span className="muted">—</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    {canWrite && org.primary_domain && (
                      <button className="btn secondary" onClick={() => startInvestigation(org)}>
                        Start investigation
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
