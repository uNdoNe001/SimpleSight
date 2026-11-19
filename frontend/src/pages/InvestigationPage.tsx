import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Asset, Finding, Investigation } from "../api/types";
import { StatusBadge } from "../components/Layout";
import { FindingsSection } from "../components/FindingsSection";
import { useAuth } from "../auth/AuthContext";

const TERMINAL = ["success", "complete", "partial", "failed"];

export function InvestigationPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const canWrite = user?.role !== "readonly";

  const [inv, setInv] = useState<Investigation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [authBy, setAuthBy] = useState("");
  const [authScope, setAuthScope] = useState("");

  // asset filters
  const [typeFilter, setTypeFilter] = useState("all");
  const [minConf, setMinConf] = useState(0);

  function load() {
    if (id) api.get<Investigation>(`/investigations/${id}`).then(setInv).catch(() => {});
  }
  useEffect(load, [id]);

  // poll for updates while a run is in progress
  useEffect(() => {
    if (inv?.status !== "running") return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [inv?.status, id]);

  async function authorize(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post(`/investigations/${id}/authorize`, {
        authorized_by: authBy,
        authorization_scope: authScope,
      });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to authorize");
    }
  }

  async function run() {
    setError(null);
    try {
      await api.post(`/investigations/${id}/run`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start run");
    }
  }

  const assets: Asset[] = inv?.assets ?? [];
  const findings: Finding[] = inv?.findings ?? [];
  const types = useMemo(
    () => Array.from(new Set(assets.map((a) => a.asset_type))).sort(),
    [assets],
  );
  const filtered = assets.filter(
    (a) => (typeFilter === "all" || a.asset_type === typeFilter) && a.confidence >= minConf,
  );

  if (!inv) return <p className="muted">Loading…</p>;

  const isDraft = inv.status === "draft";
  const authorized = Boolean(inv.authorized_by);

  return (
    <>
      <h1>
        Investigation <span className="mono" style={{ fontSize: "1rem" }}>{inv.id.slice(0, 8)}</span>{" "}
        <StatusBadge status={inv.status} />
      </h1>

      <div className="card">
        <div className="row">
          <div><label>Assessment type</label><div>{inv.assessment_type}</div></div>
          <div><label>Authorized by</label><div>{inv.authorized_by ?? <span className="muted">— not yet —</span>}</div></div>
          <div><label>Authorization scope</label><div>{inv.authorization_scope ?? <span className="muted">—</span>}</div></div>
        </div>
        {error && <p className="error">{error}</p>}

        {canWrite && isDraft && !authorized && (
          <form onSubmit={authorize} style={{ marginTop: "1rem", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
            <strong>Authorization attestation</strong>
            <p className="muted" style={{ margin: "0.25rem 0 0.5rem" }}>
              Collection cannot run until an authorization is recorded.
            </p>
            <div className="row">
              <div>
                <label>Authorized by</label>
                <input value={authBy} onChange={(e) => setAuthBy(e.target.value)} required />
              </div>
              <div>
                <label>Scope</label>
                <input value={authScope} onChange={(e) => setAuthScope(e.target.value)} required />
              </div>
              <div style={{ flex: "0 0 auto" }}>
                <button className="btn">Record authorization</button>
              </div>
            </div>
          </form>
        )}

        {canWrite && authorized && inv.status !== "running" && (
          <div style={{ marginTop: "1rem" }}>
            <button className="btn" onClick={run}>
              {TERMINAL.includes(inv.status) ? "Re-run collection" : "Run collection"}
            </button>
          </div>
        )}
        {inv.status === "running" && <p className="muted" style={{ marginTop: "1rem" }}>Collection running… this page updates automatically.</p>}
      </div>

      <FindingsSection findings={findings} canWrite={canWrite} onChanged={load} />

      <h2>Discovered assets ({assets.length})</h2>
      {assets.length > 0 && (
        <div className="row" style={{ marginBottom: "0.75rem" }}>
          <div style={{ flex: "0 0 auto" }}>
            <label>Type</label>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
              <option value="all">All types</option>
              {types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div style={{ flex: "0 0 auto" }}>
            <label>Min confidence: {minConf.toFixed(2)}</label>
            <input type="range" min={0} max={1} step={0.05} value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} />
          </div>
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="muted">No assets to show.</p>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr><th>Type</th><th>Value</th><th>Confidence</th><th>Sources</th></tr>
            </thead>
            <tbody>
              {filtered.map((a, i) => (
                <tr key={`${a.asset_type}:${a.value}:${i}`}>
                  <td><span className="badge draft">{a.asset_type}</span></td>
                  <td className="mono">{a.value}</td>
                  <td>
                    <span className="confbar" style={{ width: `${Math.round(a.confidence * 60)}px` }} />{" "}
                    {a.confidence.toFixed(2)}
                  </td>
                  <td className="muted">{a.sources.map((s) => s.source).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
