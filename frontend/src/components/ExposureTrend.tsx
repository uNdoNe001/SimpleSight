import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ExposureHistoryPoint } from "../api/types";

const W = 300;
const H = 48;
const PAD = 4;

/** A compact sparkline of an investigation's exposure score over its runs (SMPLSGHT-65).
 *  Renders nothing until there are at least two assessed runs to connect. */
export function ExposureTrend({ investigationId }: { investigationId: string }) {
  const [points, setPoints] = useState<ExposureHistoryPoint[]>([]);

  useEffect(() => {
    api
      .get<ExposureHistoryPoint[]>(`/investigations/${investigationId}/exposure-history`)
      .then(setPoints)
      .catch(() => setPoints([]));
  }, [investigationId]);

  if (points.length < 2) return null;

  const n = points.length;
  const x = (i: number) => PAD + (i / (n - 1)) * (W - 2 * PAD);
  const y = (score: number) => PAD + (1 - score / 100) * (H - 2 * PAD);
  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");

  const first = points[0].score;
  const last = points[n - 1].score;
  const delta = last - first;
  const trend =
    delta > 0 ? `up ${delta}` : delta < 0 ? `down ${Math.abs(delta)}` : "unchanged";

  return (
    <div className="exposure-trend">
      <div className="muted" style={{ fontSize: "0.82rem", marginBottom: "0.25rem" }}>
        Exposure trend · {n} runs · {trend} since first ({first} → {last})
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
           aria-label={`Exposure score over ${n} runs, ${trend}`}>
        <polyline className="spark-line" points={line} vectorEffect="non-scaling-stroke" />
        {points.map((p, i) => (
          <circle key={i} className="spark-dot" cx={x(i)} cy={y(p.score)} r={2.5}
                  vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
    </div>
  );
}
