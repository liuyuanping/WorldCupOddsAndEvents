/* ── Team Ranking Bar Chart (All Teams) ───────────────── */
import ReactECharts from "echarts-for-react";
import { useAppStore } from "../store/useAppStore";
import { getTeamColor } from "../types";

export default function ChampionRanking() {
  const teams = useAppStore((s) => s.teams);
  const prediction = useAppStore((s) => s.prediction);
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const hoveredTeamId = useAppStore((s) => s.hoveredTeamId);
  const setHoveredTeam = useAppStore((s) => s.setHoveredTeam);
  const toggleTeam = useAppStore((s) => s.toggleTeam);

  if (teams.length === 0) {
    return <div className="panel loading">加载球队数据中...</div>;
  }

  // Build data: use sim_probability if prediction loaded, else market
  const rankData = [...teams]
    .map((t) => {
      const pred = prediction?.rankings.find((r) => r.team_id === t.team_id);
      return {
        ...t,
        simProb: pred?.sim_probability ?? t.implied_probability * 100,
        marketProb: pred?.market_probability ?? t.implied_probability * 100,
        edge: pred?.value_edge_pct ?? 0,
      };
    })
    .sort((a, b) => b.simProb - a.simProb);

  const allTeams = rankData;  // Show every team
  const isSelected = (tid: string) => selectedTeamIds.has(tid);
  const isHovered = (tid: string) => hoveredTeamId === tid;

  // Dynamic height: 28px per team
  const chartHeight = Math.max(allTeams.length * 28, 400);

  // Top team's simProb as x-axis max (cap at 20%)
  const xMax = Math.ceil(Math.max(...allTeams.map((t) => t.simProb), 1) + 2);

  const option = {
    tooltip: {
      trigger: "axis" as const,
      axisPointer: { type: "shadow" as const },
      formatter: (params: any) => {
        const p = params[0];
        if (!p) return "";
        const t = allTeams[p.dataIndex];
        return `<b>${t.flag_emoji} ${t.team_name}</b><br/>
          模拟概率: <b>${t.simProb.toFixed(2)}%</b><br/>
          市场概率: ${t.marketProb.toFixed(2)}%<br/>
          价值优势: ${t.edge > 0 ? "+" : ""}${t.edge.toFixed(2)}%<br/>
          最佳赔率: ${t.best_odds}<br/>
          <span style="color:#94a3b8">点击切换曲线显示</span>`;
      },
    },
    grid: { top: 5, right: 30, bottom: 5, left: 130 },
    xAxis: {
      type: "value" as const,
      max: Math.min(xMax, 25),
      axisLabel: { formatter: "{value}%", fontSize: 10 },
      splitLine: { lineStyle: { color: "#1e293b" } },
    },
    yAxis: {
      type: "category" as const,
      data: allTeams.map((t) => t.team_name).reverse(),
      axisLabel: {
        fontSize: 12,
        fontWeight: "bold" as const,
        formatter: (v: string, i: number) => {
          const t = [...allTeams].reverse()[i];
          return `${t.flag_emoji}  ${v}`;
        },
      },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: "bar" as const,
        name: "模拟概率",
        data: allTeams
          .map((t) => ({
            value: t.simProb,
            itemStyle: {
              color: isHovered(t.team_id)
                ? "#fff"
                : isSelected(t.team_id)
                  ? getTeamColor(t.team_id)
                  : "#475569",
              borderRadius: [0, 3, 3, 0],
              opacity: hoveredTeamId && !isHovered(t.team_id) ? 0.3 : 1,
            },
          }))
          .reverse(),
        barMaxWidth: 20,
        label: {
          show: true,
          position: "right" as const,
          formatter: (p: any) => `${p.value.toFixed(1)}%`,
          fontSize: 10,
          color: "#94a3b8",
        },
        emphasis: {
          itemStyle: { color: "#fbbf24" },
        },
      },
    ],
  };

  return (
    <div className="panel ranking-panel">
      <h3>🏆 夺冠概率排名 ({allTeams.length} 队)</h3>
      <ReactECharts
        option={option}
        style={{ height: chartHeight, width: "100%" }}
        notMerge={true}
        onEvents={{
          click: (params: any) => {
            const idx = params.dataIndex;
            const t = [...allTeams].reverse()[idx];
            if (t) toggleTeam(t.team_id);
          },
          mouseover: (params: any) => {
            const idx = params.dataIndex;
            const t = [...allTeams].reverse()[idx];
            if (t) setHoveredTeam(t.team_id);
          },
          mouseout: () => setHoveredTeam(null),
        }}
      />
      <div className="ranking-hint">
        点击柱状条切换趋势图 | 悬停高亮
      </div>
    </div>
  );
}
