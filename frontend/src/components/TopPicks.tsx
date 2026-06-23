/* ── Top Picks Banner ────────────────────────────────── */
import { useAppStore } from "../store/useAppStore";

export default function TopPicks() {
  const prediction = useAppStore((s) => s.prediction);
  const predictionLoading = useAppStore((s) => s.predictionLoading);

  if (!prediction && !predictionLoading) return null;

  if (predictionLoading) {
    return (
      <div className="top-picks loading">
        蒙特卡洛模拟中...
      </div>
    );
  }

  if (!prediction) return null;

  const { top_pick, value_pick, dark_horse, total_simulations } = prediction;

  const renderCard = (
    label: string,
    pick: typeof top_pick,
    color: string
  ) => (
    <div className="pick-card" style={{ borderTop: `3px solid ${color}` }}>
      <span className="pick-label">{label}</span>
      <span className="pick-flag">{pick.flag_emoji}</span>
      <span className="pick-name">{pick.team_name}</span>
      <span className="pick-prob">{pick.sim_probability.toFixed(1)}%</span>
      <span className="pick-edge" style={{ color: pick.value_edge_pct > 0 ? "#22c55e" : "#ef4444" }}>
        {pick.value_edge_pct > 0 ? "+" : ""}{pick.value_edge_pct.toFixed(1)}% vs市场
      </span>
    </div>
  );

  return (
    <div className="top-picks">
      <span className="top-picks-title">
        🎲 蒙特卡洛模拟 ({total_simulations.toLocaleString()} 次)
      </span>
      <div className="picks-row">
        {renderCard("🏆 最大热门", top_pick, "#fbbf24")}
        {renderCard("💰 最佳价值", value_pick, "#22c55e")}
        {renderCard("🐴 黑马候选", dark_horse, "#8b5cf6")}
      </div>
    </div>
  );
}
