import { useEffect, useState } from "react";
import { useAppStore } from "./store/useAppStore";
import ChampionRanking from "./components/ChampionRanking";
import ChampionTrend from "./components/ChampionTrend";
import ChampionEvents from "./components/ChampionEvents";
import TeamSelector from "./components/TeamSelector";
import SearchPage from "./components/SearchPage";
import LLMSettings from "./components/LLMSettings";
import Toast from "./components/Toast";
import "./App.css";

export default function App() {
  const [page, setPage] = useState<"dashboard" | "search">("dashboard");
  const loadTeams = useAppStore((s) => s.loadTeams);
  const loadTrends = useAppStore((s) => s.loadTrends);
  const loadEvents = useAppStore((s) => s.loadEvents);
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const dataProvider = useAppStore((s) => s.dataProvider);
  const setDataProvider = useAppStore((s) => s.setDataProvider);
  const onlineMode = useAppStore((s) => s.onlineMode);
  const toggleOnlineMode = useAppStore((s) => s.toggleOnlineMode);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => { loadTeams(); loadEvents(); }, [dataProvider]);
  useEffect(() => {
    if (selectedTeamIds.size > 0) loadTrends([...selectedTeamIds]);
  }, [selectedTeamIds.size, dataProvider]);

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1>{page === "dashboard" ? "🏆 2026世界杯冠军预测" : "🔍 信息检索"}</h1>
          <span className="subtitle">
            {page === "dashboard" ? "真实赔率 · 趋势追踪" : "互联网搜索 · 添加到离线数据库"}
          </span>
        </div>
        <div className="header-right">
          {page === "dashboard" && (
            <>
              <select className="provider-select" value={dataProvider} onChange={(e) => setDataProvider(e.target.value)}>
                <option value="polymarket">📊 Polymarket (真实数据)</option>
                <option value="mock_champion_odds">🔬 Mock (模拟数据)</option>
              </select>
              <button className={`refresh-toggle ${onlineMode ? "active" : ""}`} onClick={toggleOnlineMode}>
                {onlineMode ? "🔄 刷新中" : "💾 缓存"}
              </button>
              <button className="action-btn" onClick={() => setShowSettings(true)}
                style={{ fontSize: "0.75rem" }} title="AI 设置">⚙️</button>
            </>
          )}
          <button className="nav-btn" onClick={() => setPage(page === "dashboard" ? "search" : "dashboard")}>
            {page === "dashboard" ? "🔍 信息检索" : "🏠 返回首页"}
          </button>
        </div>
      </header>

      {page === "dashboard" ? (
        <main className="dashboard">
          <section className="panel-left"><ChampionRanking /></section>
          <section className="panel-center"><TeamSelector /><ChampionTrend /></section>
          <section className="panel-right"><ChampionEvents /></section>
        </main>
      ) : (
        <SearchPage />
      )}
      <Toast />
      {showSettings && <LLMSettings onClose={() => setShowSettings(false)} />}
    </div>
  );
}
