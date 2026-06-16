"use client";

import { useMemo, useState } from "react";

import type { GridBus, GridEdge, GridFlowsResponse } from "@/lib/api";

// Hand-laid (x, y) positions per bus name. Coordinates are in a
// 1000×600 viewBox; layout roughly follows geographical regions so the
// topology reads intuitively.
const LAYOUT: Record<string, [number, number]> = {
  // ERCOT (left-bottom cluster)
  ERCOT_NORTH:       [140, 380],
  ERCOT_HOUSTON:     [220, 470],
  ERCOT_WEST:        [60,  450],
  ERCOT_SOUTH:       [180, 540],
  // PJM / NYISO / ISO-NE (centre-east US cluster)
  PJM_AEP:           [320, 300],
  PJM_WESTERN_HUB:   [400, 280],
  NYISO_ZONE_G:      [480, 220],
  NYISO_ZONE_J:      [555, 200],
  ISONE_MASS_HUB:    [620, 170],
  // GB
  GB_POWER:          [720, 200],
  // Continental Europe
  EPEX_FR:           [810, 290],
  EPEX_DE:           [880, 230],
  // Nordics
  NORDPOOL_SE3:      [930, 130],
};

function pickPosition(name: string, index: number): [number, number] {
  const known = LAYOUT[name];
  if (known) return known;
  // Fallback grid for any new bus not in the layout map.
  const col = index % 5;
  const row = Math.floor(index / 5);
  return [150 + col * 180, 80 + row * 140];
}

function utilColour(util: number, binding: boolean): string {
  if (binding) return "#dc2626"; // red
  if (util > 0.7) return "#ea580c"; // orange
  if (util > 0.5) return "#d97706"; // amber
  if (util > 0.3) return "#65a30d"; // green
  return "#475569"; // slate
}

function utilStroke(util: number, binding: boolean): number {
  if (binding) return 4;
  if (util > 0.7) return 3;
  return 2;
}

function lmpColour(lmp: number, minLmp: number, maxLmp: number): string {
  const span = Math.max(maxLmp - minLmp, 1e-6);
  const t = (lmp - minLmp) / span;
  // pale-blue (cheap) to deep-amber (expensive)
  const hue = 200 - 160 * t;
  const sat = 60 + 20 * t;
  const lig = 70 - 30 * t;
  return `hsl(${hue}, ${sat}%, ${lig}%)`;
}

type Hover =
  | { kind: "bus"; bus: GridBus }
  | { kind: "edge"; edge: GridEdge }
  | null;

export function GridTopologyView({ flows }: { flows: GridFlowsResponse }) {
  const [hover, setHover] = useState<Hover>(null);

  const positions = useMemo(() => {
    const out = new Map<string, [number, number]>();
    flows.buses.forEach((b, i) => out.set(b.name, pickPosition(b.name, i)));
    return out;
  }, [flows.buses]);

  const [minLmp, maxLmp] = useMemo(() => {
    const lmps = flows.buses.map((b) => b.lmp).filter((x) => Number.isFinite(x));
    return [Math.min(...lmps), Math.max(...lmps)];
  }, [flows.buses]);

  return (
    <section className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="overflow-hidden rounded-xl border border-seam bg-bg/40">
          <svg viewBox="0 0 1000 600" className="h-[560px] w-full">
            <defs>
              <marker
                id="arrow"
                viewBox="0 -3 6 6"
                refX="5"
                refY="0"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                <path d="M0,-3 L6,0 L0,3" fill="#94a3b8" />
              </marker>
            </defs>

            {/* Edges first so buses overlay them */}
            {flows.edges.map((edge) => {
              const a = positions.get(edge.from_bus);
              const b = positions.get(edge.to_bus);
              if (!a || !b) return null;
              const stroke = utilColour(edge.utilisation, edge.binding);
              const sw = utilStroke(edge.utilisation, edge.binding);
              return (
                <g
                  key={`${edge.from_bus}-${edge.to_bus}`}
                  onMouseEnter={() => setHover({ kind: "edge", edge })}
                  onMouseLeave={() => setHover(null)}
                  style={{ cursor: "pointer" }}
                >
                  <line
                    x1={a[0]}
                    y1={a[1]}
                    x2={b[0]}
                    y2={b[1]}
                    stroke={stroke}
                    strokeWidth={sw}
                    strokeOpacity={0.85}
                    markerEnd="url(#arrow)"
                  />
                </g>
              );
            })}

            {/* Buses */}
            {flows.buses.map((bus) => {
              const p = positions.get(bus.name);
              if (!p) return null;
              const fill = lmpColour(bus.lmp, minLmp, maxLmp);
              const radius = bus.is_reference ? 14 : 10;
              return (
                <g
                  key={bus.name}
                  onMouseEnter={() => setHover({ kind: "bus", bus })}
                  onMouseLeave={() => setHover(null)}
                  style={{ cursor: "pointer" }}
                >
                  <circle
                    cx={p[0]}
                    cy={p[1]}
                    r={radius}
                    fill={fill}
                    stroke="#0f172a"
                    strokeWidth={1.5}
                  />
                  <text
                    x={p[0]}
                    y={p[1] + radius + 14}
                    textAnchor="middle"
                    fontSize="10"
                    fontFamily="ui-monospace,SFMono-Regular,Menlo,monospace"
                    fill="currentColor"
                  >
                    {bus.name}
                  </text>
                  <text
                    x={p[0]}
                    y={p[1] + radius + 26}
                    textAnchor="middle"
                    fontSize="9"
                    fontFamily="ui-monospace,SFMono-Regular,Menlo,monospace"
                    fill="currentColor"
                    fillOpacity={0.55}
                  >
                    LMP {bus.lmp.toFixed(1)}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        <aside className="space-y-3 text-sm">
          <div className="rounded-xl border border-seam bg-bg/40 p-3">
            <p className="mb-1 eyebrow text-[10px] text-ink/45">
              Hover detail
            </p>
            {hover === null && (
              <p className="text-xs text-ink/55">Hover a bus or line for details.</p>
            )}
            {hover?.kind === "bus" && (
              <div className="space-y-1">
                <p className="font-mono text-xs font-semibold text-ink">
                  {hover.bus.name}
                  {hover.bus.is_reference ? " (slack)" : ""}
                </p>
                {hover.bus.market_code && (
                  <p className="text-[11px] text-ink/55">market {hover.bus.market_code}</p>
                )}
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[11px] text-ink/75">
                  <dt>LMP</dt>
                  <dd className="text-right">{hover.bus.lmp.toFixed(2)}</dd>
                  <dt>Gen</dt>
                  <dd className="text-right">{hover.bus.gen_mw.toLocaleString()} MW</dd>
                  <dt>Gen max</dt>
                  <dd className="text-right">{hover.bus.gen_max_mw.toLocaleString()} MW</dd>
                  <dt>Load</dt>
                  <dd className="text-right">{hover.bus.load_mw.toLocaleString()} MW</dd>
                </dl>
              </div>
            )}
            {hover?.kind === "edge" && (
              <div className="space-y-1">
                <p className="font-mono text-xs font-semibold text-ink">
                  {hover.edge.from_bus} → {hover.edge.to_bus}
                </p>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[11px] text-ink/75">
                  <dt>Flow</dt>
                  <dd className="text-right">{hover.edge.flow_mw.toLocaleString()} MW</dd>
                  <dt>Limit</dt>
                  <dd className="text-right">{hover.edge.limit_mw.toLocaleString()} MW</dd>
                  <dt>Utilisation</dt>
                  <dd className="text-right">{(hover.edge.utilisation * 100).toFixed(1)}%</dd>
                  <dt>Binding</dt>
                  <dd className="text-right">{hover.edge.binding ? "yes" : "no"}</dd>
                </dl>
              </div>
            )}
          </div>

          <div className="rounded-xl border border-seam bg-bg/40 p-3 text-[11px] text-ink/65">
            <p className="mb-2 eyebrow text-ink/45 text-[10px]">
              Legend
            </p>
            <div className="space-y-1">
              <p>
                <span className="mr-2 inline-block h-1.5 w-6 align-middle"
                      style={{ background: "#475569" }} />
                util &lt; 30%
              </p>
              <p>
                <span className="mr-2 inline-block h-1.5 w-6 align-middle"
                      style={{ background: "#65a30d" }} />
                30–50%
              </p>
              <p>
                <span className="mr-2 inline-block h-1.5 w-6 align-middle"
                      style={{ background: "#d97706" }} />
                50–70%
              </p>
              <p>
                <span className="mr-2 inline-block h-1.5 w-6 align-middle"
                      style={{ background: "#ea580c" }} />
                70–100%
              </p>
              <p>
                <span className="mr-2 inline-block h-1.5 w-6 align-middle"
                      style={{ background: "#dc2626" }} />
                binding
              </p>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
