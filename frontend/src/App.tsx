import { useEffect } from "react";
import { useAppStore } from "./store/useAppStore";
import TopPicks from "./components/TopPicks";
import ChampionRanking from "./components/ChampionRanking";
import ChampionTrend from "./components/ChampionTrend";
import ChampionEvents from "./components/ChampionEvents";
import "./App.css";

export default function App() {
  const loadTeams = useAppStore((s) => s.loadTeams);
  const loadTrends = useAppStore((s) => s.loadTrends);
  const loadEvents = useAppStore((s) => s.loadEvents);
  const loadPrediction = useAppStore((s) => s.loadPrediction);
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const dataProvider = useAppStore((s) => s.dataProvider);
  const setDataProvider = useAppStore((s) => s.setDataProvider);

  useEffect(() => {
    loadTeams();
    loadEvents();
    loadPrediction();
  }, [dataProvider]);

  useEffect(() => {
    if (selectedTeamIds.size > 0) {
      loadTrends([...selectedTeamIds]);
    }
  }, [selectedTeamIds.size, dataProvider]);

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <h1>🏆 2026世界杯冠军预测</h1>
          <span className="subtitle">真实赔率 · 趋势追踪 · 蒙特卡洛模拟</span>
        </div>
        <div className="header-right">
          <select
            className="provider-select"
            value={dataProvider}
            onChange={(e) => setDataProvider(e.target.value)}
          >
            <option value="polymarket">📊 Polymarket (真实数据)</option>
            <option value="mock_champion_odds">🔬 Mock (模拟数据)</option>
          </select>
          <TopPicks />
        </div>
      </header>

      {/* Main Dashboard */}
      <main className="dashboard">
        {/* Left: Ranking */}
        <section className="panel-left">
          <ChampionRanking />
        </section>

        {/* Center: Trend Chart */}
        <section className="panel-center">
          <ChampionTrend />
        </section>

        {/* Right: Events */}
        <section className="panel-right">
          <ChampionEvents />
        </section>
      </main>
    </div>
  );
}
