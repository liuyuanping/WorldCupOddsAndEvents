/* ── Probability Trend Line Chart ──────────────────────── */
import ReactECharts from "echarts-for-react";
import { useAppStore } from "../store/useAppStore";
import { getTeamColor, SEVERITY_COLORS } from "../types";

export default function ChampionTrend() {
  const oddsTrends = useAppStore((s) => s.oddsTrends);
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const events = useAppStore((s) => s.events);
  const trendsLoading = useAppStore((s) => s.trendsLoading);
  const selectedBookmaker = useAppStore((s) => s.selectedBookmaker);
  const setSelectedBookmaker = useAppStore((s) => s.setSelectedBookmaker);
  const hoveredTeamId = useAppStore((s) => s.hoveredTeamId);
  const selectedEventTypes = useAppStore((s) => s.selectedEventTypes);

  if (trendsLoading && Object.keys(oddsTrends).length === 0) {
    return <div className="panel loading">加载数据中...</div>;
  }

  const teamIds = Object.keys(oddsTrends);
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
        const lines = params.map(
          (p: any) =>
            `<span style="color:${p.color}">●</span> ${p.seriesName}: <b>${p.value[1]?.toFixed(1)}%</b>`
        );
        const d = new Date(params[0]?.value[0]);
        return `<b>${d.toLocaleDateString("zh-CN")}</b><br/>${lines.join("<br/>")}`;
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
    grid: { top: 50, right: 30, bottom: 30, left: 60 },
    xAxis: {
      type: "time" as const,
      axisLabel: {
        formatter: (v: number) => {
          const d = new Date(v);
          return `${d.getMonth() + 1}/${d.getDate()}`;
        },
        fontSize: 11,
      },
    },
    yAxis: {
      type: "value" as const,
      name: "夺冠概率 (%)",
      axisLabel: { formatter: "{value}%", fontSize: 11 },
    },
    series: teamIds.map((tid) => {
      const series = oddsTrends[tid];
      // Use probability (0-1) → percentage
      const data = (series?.data || []).map((d) => [
        new Date(d.timestamp).getTime(),
        (d.prob ?? 0) * 100,
      ]);
      const isHovered = !hoveredTeamId || hoveredTeamId === tid;
      return {
        type: "line" as const,
        name: `${series?.flag_emoji || ""} ${series?.team_name || tid}`,
        data,
        smooth: true,
        symbol: "none" as const,
        lineStyle: {
          width: isHovered ? 2 : 1,
          color: getTeamColor(tid),
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
              const nearest = data.reduce((prev, curr) =>
                Math.abs(curr[0] - evtTs) < Math.abs(prev[0] - evtTs) ? curr : prev
              );
              return {
                name: e.title,
                coord: [nearest[0], nearest[1]],
                itemStyle: {
                  color: SEVERITY_COLORS[e.severity] || "#f59e0b",
                },
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
      <ReactECharts option={option} style={{ height: 360, width: "100%" }} />
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
