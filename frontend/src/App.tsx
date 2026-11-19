import { useEffect, useState } from "react";

export function App() {
  const [health, setHealth] = useState<string>("checking…");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => setHealth(d.status ?? "unknown"))
      .catch(() => setHealth("unreachable"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 640 }}>
      <h1>SimpleSight</h1>
      <p>Open-Source Intelligence &amp; Digital Footprint Intelligence Platform</p>
      <p style={{ color: "#666" }}>See What Others Miss.</p>
      <p>
        Backend health: <strong>{health}</strong>
      </p>
    </main>
  );
}
