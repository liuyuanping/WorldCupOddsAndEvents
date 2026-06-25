/* ── Probability Trend Line Chart ──────────────────────── */
import { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { useAppStore } from "../store/useAppStore";
import { getTeamColor } from "../types";

/** Polymarket CLOB API supported intervals (30-day data retention) */
const TIME_INTERVALS = [
  { label: "1h", value: "1h" },
  { label: "6h", value: "6h" },
  { label: "1d", value: "1d" },
  { label: "1w", value: "1w" },
  { label: "1m", value: "1m" },
  { label: "Max", value: "all" },
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
  const dataProvider = useAppStore((s) => s.dataProvider);
  const selectedEventTypes = useAppStore((s) => s.selectedEventTypes);
  const setSelectedEvent = useAppStore((s) => s.setSelectedEvent);
  const setHoveredTeam = useAppStore((s) => s.setHoveredTeam);
  const setEventTimeRange = useAppStore((s) => s.setEventTimeRange);
  const eventTimeRange = useAppStore((s) => s.eventTimeRange);

  const [chartHeight, setChartHeight] = useState(720);
  const HEIGHT_PRESETS = [400, 600, 720, 900];

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

  // Filter events for selected teams + time range
  const filteredEvents = events.filter((e) => {
    if (!selectedTeamIds.has(e.team_id)) return false;
    if (selectedEventTypes.size > 0 && !selectedEventTypes.has(e.event_type)) return false;
    if (eventTimeRange) {
      const t = new Date(e.timestamp).getTime();
      const start = new Date(eventTimeRange.start).getTime();
      const end = new Date(eventTimeRange.end).getTime();
      if (t < start || t > end) return false;
    }
    return true;
  });

  const option = {
    tooltip: {
      trigger: "axis" as const,
      enterable: true,
      hideDelay: 300,
      transitionDuration: 0.2,
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
    series: [
      // Line series for each team
      ...teamIds.map((tid) => {
        const data = normalized.series.get(tid) || [];
        const color = getTeamColor(tid);
        return {
          type: "line" as const,
          name: `${oddsTrends[tid]?.flag_emoji || ""} ${oddsTrends[tid]?.team_name || tid}`,
          data,
          smooth: true,
          symbol: "none" as const,
          connectNulls: true,
          color,
          lineStyle: { width: 2 },
          z: 1,
        };
      }),
      // Event scatter series — one per team for proper coloring
      ...teamIds.map((tid) => {
        const teamColor = getTeamColor(tid);
        const teamEvents = filteredEvents.filter((e) => e.team_id === tid);
        if (teamEvents.length === 0) return null;
        // Find nearest y-values for each event
        const lineData = normalized.series.get(tid) || [];
        const scatterData = teamEvents.map((e) => {
          const evtTs = new Date(e.timestamp).getTime();
          let nearest = lineData.length > 0 ? lineData[0] : [evtTs, 0];
          for (const pt of lineData) {
            if (Math.abs(pt[0] - evtTs) < Math.abs(nearest[0] - evtTs)) nearest = pt;
          }
          return {
            value: [nearest[0], nearest[1]],
            eventTitle: e.title,
            eventDesc: e.description || "",
            eventType: e.event_type,
            eventSeverity: e.severity,
            eventTime: e.timestamp,
            teamId: tid,
            teamName: e.team_name,
          };
        });
        return {
          type: "scatter" as const,
          name: `${oddsTrends[tid]?.flag_emoji || ""} ${oddsTrends[tid]?.team_name || tid} · 事件`,
          data: scatterData,
          symbol: "triangle",
          symbolSize: 13,
          symbolRotate: 180,
          color: teamColor,
          itemStyle: { color: teamColor, borderColor: "#fff", borderWidth: 2 },
          emphasis: { itemStyle: { color: "#fff", borderColor: teamColor, borderWidth: 2 } },
          z: 10,
          tooltip: {
            trigger: "item" as const,
            enterable: true,
            hideDelay: 500,
            transitionDuration: 0.3,
            formatter: (p: any) => {
              const d = p.data;
              const sevLabels = ["", "低", "中", "高", "严重"];
              const sev = sevLabels[d.eventSeverity] || "?";
              const t = new Date(d.eventTime).toLocaleString("zh-CN");
              return `<div style="max-width:320px;word-wrap:break-word;overflow-wrap:break-word;white-space:normal;">
                <b>🔺 ${d.eventTitle}</b><br/>
                ${d.eventDesc}<br/>
                <span style="color:#94a3b8">${d.teamName} · ${d.eventType} · 严重度:${sev} · ${t}</span><br/>
                <span style="color:#f59e0b">点击查看详情</span></div>`;
            },
          },
        };
      }).filter(Boolean),
    ],
  };

  return (
    <div className="panel trend-panel">
      <div className="trend-header">
        <h3>📈 胜率趋势</h3>
        <div className="trend-controls">
          <div className="interval-btns">
            {HEIGHT_PRESETS.map((h) => (
              <button
                key={h}
                className={`chip ${chartHeight === h ? "active" : ""}`}
                onClick={() => setChartHeight(h)}
                style={{ fontSize: "0.6rem", padding: "0.1rem 0.35rem" }}
              >
                {h}
              </button>
            ))}
            <span style={{ color: "#475569", fontSize: "0.6rem", margin: "0 0.15rem" }}>|</span>
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
          {dataProvider !== "polymarket" && (
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
          )}
        </div>
      </div>
      <ReactECharts
        option={option}
        style={{ height: chartHeight, width: "100%" }}
        notMerge={true}
        onEvents={{
          dataZoom: (params: any) => {
            const batch = params.batch?.[0] || params;
            if (batch.startValue != null && batch.endValue != null) {
              setEventTimeRange({
                start: new Date(batch.startValue).toISOString(),
                end: new Date(batch.endValue).toISOString(),
              });
            }
          },
          click: (params: any) => {
            // Detect click on scatter (event) point
            if (params.componentType === "series" && params.seriesType === "scatter" && params.data) {
              const d = params.data;
              setSelectedEvent({
                team_id: d.teamId,
                team_name: d.teamName,
                event_type: d.eventType,
                title: d.eventTitle,
                description: d.eventDesc,
                timestamp: d.eventTime,
                severity: d.eventSeverity,
                confidence: 1,
              });
              setHoveredTeam(d.teamId);
            }
          },
        }}
      />
      <div className="trend-legend">
        {teamIds.map((tid) => (
          <span
            key={tid}
            className="legend-item"
            style={{
              color: getTeamColor(tid),
              opacity: 1,
            }}
          >
            {oddsTrends[tid]?.flag_emoji} {oddsTrends[tid]?.team_name}
          </span>
        ))}
      </div>
    </div>
  );
}
