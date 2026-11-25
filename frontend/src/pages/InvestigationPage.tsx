import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type {
  AlertsResponse,
  Asset,
  ChangeEvent,
  DiscoveryPlan,
  Finding,
  Investigation,
} from "../api/types";
import { StatusBadge } from "../components/Layout";
import { FindingsSection } from "../components/FindingsSection";
import { ChangesSection } from "../components/ChangesSection";
import { AlertsBanner } from "../components/AlertsBanner";
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

  const [plan, setPlan] = useState<DiscoveryPlan | null>(null);
  const [changes, setChanges] = useState<ChangeEvent[]>([]);
  const [alerts, setAlerts] = useState<AlertsResponse | null>(null);

  function load() {
    if (!id) return;
    api.get<Investigation>(`/investigations/${id}`).then(setInv).catch(() => {});
    api.get<ChangeEvent[]>(`/investigations/${id}/changes`).then(setChanges).catch(() => {});
    api.get<AlertsResponse>(`/investigations/${id}/alerts`).then(setAlerts).catch(() => {});
  }
  useEffect(load, [id]);

  useEffect(() => {
    if (id) api.get<DiscoveryPlan>(`/investigations/${id}/plan`).then(setPlan).catch(() => {});
  }, [id]);

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

  const [monBusy, setMonBusy] = useState(false);
  async function setMonitoring(enabled: boolean, interval: string) {
    setError(null);
    setMonBusy(true);
    try {
      await api.patch(`/investigations/${id}/monitoring`, {
        enabled,
        interval: enabled ? interval : null,
      });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update monitoring");
    } finally {
      setMonBusy(false);
    }
  }

  const [downloading, setDownloading] = useState(false);
  async function downloadReport() {
    setError(null);
    setDownloading(true);
    try {
      const blob = await api.getBlob(`/investigations/${id}/report.pdf`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `simplesight-report-${id?.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to download report");
    } finally {
      setDownloading(false);
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

      {alerts && (
        <AlertsBanner alerts={alerts} canWrite={canWrite} onChanged={load} />
      )}

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

        {(canWrite || TERMINAL.includes(inv.status)) && inv.status !== "running" && (
          <div className="row" style={{ marginTop: "1rem", flexWrap: "wrap" }}>
            {canWrite && authorized && (
              <button className="btn" style={{ flex: "0 0 auto" }} onClick={run}>
                {TERMINAL.includes(inv.status) ? "Re-run collection" : "Run collection"}
              </button>
            )}
            {TERMINAL.includes(inv.status) && (
              <button
                className="btn secondary"
                style={{ flex: "0 0 auto" }}
                onClick={downloadReport}
                disabled={downloading}
              >
                {downloading ? "Preparing…" : "Download report (PDF)"}
              </button>
            )}
          </div>
        )}
        {inv.status === "running" && <p className="muted" style={{ marginTop: "1rem" }}>Collection running… this page updates automatically.</p>}
      </div>

      {canWrite && (
        <div className="card monitoring-card">
          <label style={{ margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={inv.monitoring_enabled}
              disabled={monBusy}
              onChange={(e) =>
                setMonitoring(e.target.checked, inv.monitoring_interval ?? "daily")
              }
            />
            <strong>Continuous monitoring</strong>
          </label>
          <span className="muted" style={{ fontSize: "0.85rem" }}>
            Re-collect periodically and record what changed between runs.
          </span>
          {inv.monitoring_enabled && (
            <select
              value={inv.monitoring_interval ?? "daily"}
              disabled={monBusy}
              style={{ width: "auto" }}
              onChange={(e) => setMonitoring(true, e.target.value)}
            >
              <option value="hourly">Hourly</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </select>
          )}
        </div>
      )}

      {plan && (
        <>
          <h2>
            Planned collection{" "}
            {plan.passive_only && <span className="badge success">passive</span>}
          </h2>
          <div className="card">
            <p className="muted" style={{ marginTop: 0 }}>
              {plan.enabled_count} of {plan.steps.length} collectors will run against{" "}
              <span className="mono">{plan.target ?? "—"}</span>
              {plan.additional_targets.length > 0 &&
                ` (+${plan.additional_targets.length} more domain${plan.additional_targets.length > 1 ? "s" : ""})`}
              {plan.skipped_count > 0 && ` · ${plan.skipped_count} skipped`}.
            </p>
            <table>
              <thead>
                <tr><th>Collector</th><th>What it does</th><th>Status</th></tr>
              </thead>
              <tbody>
                {plan.steps.map((s) => (
                  <tr key={s.collector}>
                    <td className="mono">{s.collector}</td>
                    <td className="muted">{s.description}</td>
                    <td>
                      {s.enabled ? (
                        <span className="badge success">enabled</span>
                      ) : (
                        <span className="badge draft" title={s.skip_reason ?? ""}>skipped</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {inv?.exposure_score && (findings.length > 0 || inv.status === "complete" || inv.status === "partial") && (
        <>
          <h2>Exposure score</h2>
          <div className="card exposure-card">
            <div className={`exposure-dial grade-${inv.exposure_score.grade}`}>
              <span className="exposure-num">{inv.exposure_score.score}</span>
              <span className="exposure-den">/100</span>
              <span className="exposure-grade">
                {inv.exposure_score.grade} · {inv.exposure_score.label}
              </span>
            </div>
            <p className="muted exposure-rationale">
              {inv.exposure_score.rationale}{" "}
              A relative indicator from passively observed findings — not an assertion of
              overall security.
            </p>
          </div>
        </>
      )}

      <ChangesSection changes={changes} />

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
