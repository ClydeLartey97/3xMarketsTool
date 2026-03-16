"use client";

import { Area, AreaChart, CartesianGrid, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type ChartPoint = {
  timestamp: string;
  actual?: number;
  forecast?: number;
  lower?: number;
  upper?: number;
};

export function PriceForecastChart({ data }: { data: ChartPoint[] }) {
  return (
    <div className="h-[360px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <defs>
            <linearGradient id="band" x1="0" x2="0" y1="0" y2="1">
              <stop offset="5%" stopColor="#0f9f7c" stopOpacity={0.24} />
              <stop offset="95%" stopColor="#0f9f7c" stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#d7e2ec" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" minTickGap={24} tick={{ fill: "#415466", fontSize: 11 }} />
          <YAxis tick={{ fill: "#415466", fontSize: 11 }} width={64} />
          <Tooltip />
          <Legend />
          <Area type="monotone" dataKey="upper" stroke="transparent" fill="transparent" />
          <Area type="monotone" dataKey="lower" stroke="transparent" fill="url(#band)" />
          <Line type="monotone" dataKey="actual" stroke="#08111a" strokeWidth={2.2} dot={false} name="Actual" />
          <Line type="monotone" dataKey="forecast" stroke="#f97316" strokeWidth={2.4} dot={false} name="Forecast" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
