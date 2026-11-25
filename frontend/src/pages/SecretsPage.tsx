import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { SecretInfo } from "../api/types";

export function SecretsPage() {
  const [secrets, setSecrets] = useState<SecretInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  function load() {
    api.get<SecretInfo[]>("/secrets")
      .then(setSecrets)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load secrets"))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function save(name: string) {
    const value = (drafts[name] ?? "").trim();
    if (!value) return;
    setBusy(name);
    setError(null);
    try {
      await api.put(`/secrets/${encodeURIComponent(name)}`, { value });
      setDrafts((d) => ({ ...d, [name]: "" }));
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save");
    } finally {
      setBusy(null);
    }
  }

  async function remove(name: string) {
    setBusy(name);
    setError(null);
    try {
      await api.del(`/secrets/${encodeURIComponent(name)}`);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to delete");
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Provider keys</h1>
      <p className="muted">
        API keys for key-gated collectors and the optional AI narrative. Admin-only. Values are
        encrypted at rest and <strong>never displayed</strong> — only set, rotated, or removed.
      </p>
      {error && <p className="error">{error}</p>}

      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr><th>Name</th><th>Status</th><th>Source</th><th style={{ width: "40%" }}>Set / rotate</th></tr>
          </thead>
          <tbody>
            {secrets.map((s) => (
              <tr key={s.name}>
                <td className="mono">{s.name}</td>
                <td>
                  {s.configured
                    ? <span className="badge success">configured</span>
                    : <span className="badge draft">unset</span>}
                </td>
                <td className="muted">{s.source}</td>
                <td>
                  <div className="secret-row">
                    <input
                      type="password"
                      placeholder="paste new value"
                      autoComplete="off"
                      value={drafts[s.name] ?? ""}
                      onChange={(e) => setDrafts((d) => ({ ...d, [s.name]: e.target.value }))}
                    />
                    <button
                      className="btn"
                      disabled={busy === s.name || !(drafts[s.name] ?? "").trim()}
                      onClick={() => save(s.name)}
                    >
                      {busy === s.name ? "…" : "Save"}
                    </button>
                    {s.configured && s.source === "tenant" && (
                      <button
                        className="btn secondary"
                        disabled={busy === s.name}
                        onClick={() => remove(s.name)}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
