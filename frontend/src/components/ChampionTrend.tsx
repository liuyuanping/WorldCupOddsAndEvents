/* ── Probability Trend Line Chart ──────────────────────── */
import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useAppStore } from "../store/useAppStore";
import { getTeamColor, SEVERITY_COLORS } from "../types";

const TIME_INTERVALS = [
  { label: "1h", value: "1h" },
  { label: "6h", value: "6h" },
  { label: "1d", value: "1d" },
  { label: "1w", value: "1w" },
  { label: "1m", value: "1m" },
  { label: "3m", value: "3m" },
  { label: "6m", value: "6m" },
  { label: "1y", value: "1y" },
  { label: "All", value: "all" },
];

/** Format timestamp to full datetime */
function fmtTime(ts: number): string {
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** Build a common time grid from all series and interpolate each team's values */
function normalizeSeries(
  oddsTrends: Record<string, { team_name: string; flag_emoji: string; data: Array<{ timestamp: string; prob: number }> }>,
  teamIds: string[]
): { grid: number[]; series: Map<string, Array<[number, number]>> } {
  // Collect all unique timestamps
  const tsSet = new Set<number>();
  for (const tid of teamIds) {
    const s = oddsTrends[tid];
    if (!s) continue;
    for (const d of s.data) {
      tsSet.add(new Date(d.timestamp).getTime());
    }
  }
  let grid = [...tsSet].sort((a, b) => a - b);
  if (grid.length < 2) return { grid, series: new Map() };

  // Cap grid to 500 points to prevent performance issues
  const MAX_GRID = 500;
  if (grid.length > MAX_GRID) {
    const step = (grid.length - 1) / (MAX_GRID - 1);
    const sampled = [grid[0]];
    for (let i = 1; i < MAX_GRID - 1; i++) {
      sampled.push(grid[Math.round(i * step)]);
    }
    sampled.push(grid[grid.length - 1]);
    grid = sampled;
  }

  // Interpolate each team to the common grid
  const result = new Map<string, Array<[number, number]>>();
  for (const tid of teamIds) {
    const s = oddsTrends[tid];
    if (!s || s.data.length < 2) {
      // Not enough data → use raw points
      const raw = (s?.data || []).map((d) => [new Date(d.timestamp).getTime(), (d.prob ?? 0) * 100] as [number, number]);
      result.set(tid, raw);
      continue;
    }

    // Build lookup from raw data
    const rawMap = new Map<number, number>();
    for (const d of s.data) {
      rawMap.set(new Date(d.timestamp).getTime(), (d.prob ?? 0) * 100);
    }

    // Interpolate missing points
    const rawTs = [...rawMap.keys()].sort((a, b) => a - b);
    const interpolated: Array<[number, number]> = [];

    for (const t of grid) {
      if (rawMap.has(t)) {
        interpolated.push([t, rawMap.get(t)!]);
      } else {
        // Find nearest neighbors
        let lo = -1, hi = -1;
        for (let j = rawTs.length - 1; j >= 0; j--) {
          if (rawTs[j] <= t) { lo = j; break; }
        }
        for (let j = 0; j < rawTs.length; j++) {
          if (rawTs[j] >= t) { hi = j; break; }
        }

        if (lo >= 0 && hi >= 0 && lo !== hi) {
          // Linear interpolation
          const tLo = rawTs[lo], tHi = rawTs[hi];
          const vLo = rawMap.get(tLo)!, vHi = rawMap.get(tHi)!;
          const frac = (t - tLo) / (tHi - tLo);
          interpolated.push([t, vLo + (vHi - vLo) * frac]);
        } else if (lo >= 0) {
          interpolated.push([t, rawMap.get(rawTs[lo])!]);
        } else if (hi >= 0) {
          interpolated.push([t, rawMap.get(rawTs[hi])!]);
        }
      }
    }

    result.set(tid, interpolated);
  }

  return { grid, series: result };
}

export default function ChampionTrend() {
  const oddsTrends = useAppStore((s) => s.oddsTrends);
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const events = useAppStore((s) => s.events);
  const trendsLoading = useAppStore((s) => s.trendsLoading);
  const selectedBookmaker = useAppStore((s) => s.selectedBookmaker);
  const setSelectedBookmaker = useAppStore((s) => s.setSelectedBookmaker);
  const trendInterval = useAppStore((s) => s.trendInterval);
  const setTrendInterval = useAppStore((s) => s.setTrendInterval);
  const hoveredTeamId = useAppStore((s) => s.hoveredTeamId);
  const selectedEventTypes = useAppStore((s) => s.selectedEventTypes);

  const teamIds = Object.keys(oddsTrends);

  // Normalize all series to a common time grid
  const normalized = useMemo(
    () => (teamIds.length > 0 ? normalizeSeries(oddsTrends, teamIds) : { grid: [], series: new Map<string, Array<[number, number]>>() }),
    [oddsTrends, teamIds]
  );

  if (trendsLoading && teamIds.length === 0) {
    return <div className="panel loading">加载数据中...</div>;
  }

  if (teamIds.length === 0) {
    return <div className="panel loading">选择球队查看胜率趋势</div>;
  }

  // Filter events for selected teams
  const filteredEvents = events.filter((e) => {
    if (!selectedTeamIds.has(e.team_id)) return false;
    if (selectedEventTypes.size > 0 && !selectedEventTypes.has(e.event_type)) return false;
    return true;
  });

  const option = {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return "";
        const ts = params[0]?.value[0];
        const lines = params.map(
          (p: any) =>
            `<span style="color:${p.color}">●</span> ${p.seriesName}: <b>${p.value[1]?.toFixed(1)}%</b>`
        );
        return `<b>${fmtTime(ts)}</b><br/>${lines.join("<br/>")}`;
      },
    },
    legend: {
      top: 5,
      data: teamIds.map((tid) => {
        const s = oddsTrends[tid];
        return s ? `${s.flag_emoji || ""} ${s.team_name || tid}` : tid;
      }),
      textStyle: { color: "#e2e8f0", fontSize: 11 },
    },
    grid: { top: 50, right: 30, bottom: 60, left: 60 },
    dataZoom: [
      { type: "inside", start: 0, end: 100 },
      { type: "slider", start: 0, end: 100, height: 25, bottom: 10 },
    ],
    xAxis: {
      type: "time" as const,
      axisLabel: {
        formatter: (v: number) => fmtTime(v).slice(0, 10),
        fontSize: 11,
      },
    },
    yAxis: {
      type: "value" as const,
      name: "夺冠概率 (%)",
      axisLabel: { formatter: "{value}%", fontSize: 11 },
    },
    series: teamIds.map((tid) => {
      const data = normalized.series.get(tid) || [];
      const isHovered = !hoveredTeamId || hoveredTeamId === tid;
      const color = getTeamColor(tid);
      return {
        type: "line" as const,
        name: `${oddsTrends[tid]?.flag_emoji || ""} ${oddsTrends[tid]?.team_name || tid}`,
        data,
        smooth: true,
        symbol: "none" as const,
        connectNulls: true,
        color,
        lineStyle: {
          width: isHovered ? 2 : 1,
          opacity: isHovered ? 1 : 0.2,
        },
        markPoint: {
          silent: true,
          symbol: "triangle",
          symbolSize: 10,
          data: filteredEvents
            .filter((e) => e.team_id === tid)
            .map((e) => {
              const evtTs = new Date(e.timestamp).getTime();
              const nearest = data.reduce((prev: [number, number], curr: [number, number]) =>
                Math.abs(curr[0] - evtTs) < Math.abs(prev[0] - evtTs) ? curr : prev, data[0] || [0, 0]
              );
              return {
                name: e.title,
                coord: [nearest[0], nearest[1]],
                itemStyle: { color: SEVERITY_COLORS[e.severity] || "#f59e0b" },
              };
            }),
        },
      };
    }),
  };

  return (
    <div className="panel trend-panel">
      <div className="trend-header">
        <h3>📈 胜率趋势</h3>
        <div className="trend-controls">
          <div className="interval-btns">
            {TIME_INTERVALS.map((ti) => (
              <button
                key={ti.value}
                className={`chip ${trendInterval === ti.value ? "active" : ""}`}
                onClick={() => setTrendInterval(ti.value)}
              >
                {ti.label}
              </button>
            ))}
          </div>
          <select
            value={selectedBookmaker}
            onChange={(e) => setSelectedBookmaker(e.target.value)}
            className="bm-select"
          >
            <option value="Pinnacle">Pinnacle</option>
            <option value="Bet365">Bet365</option>
            <option value="William Hill">William Hill</option>
            <option value="Betfair">Betfair</option>
          </select>
        </div>
      </div>
      <ReactECharts option={option} style={{ height: 360, width: "100%" }} notMerge={true} />
      <div className="trend-legend">
        {teamIds.map((tid) => (
          <span
            key={tid}
            className="legend-item"
            style={{
              color: getTeamColor(tid),
              opacity: hoveredTeamId && hoveredTeamId !== tid ? 0.3 : 1,
            }}
          >
            {oddsTrends[tid]?.flag_emoji} {oddsTrends[tid]?.team_name}
          </span>
        ))}
      </div>
    </div>
  );
}
