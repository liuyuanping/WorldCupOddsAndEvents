import Toolbar from "./components/Toolbar";
import OddsChart from "./components/OddsChart";
import EventTimeline from "./components/EventTimeline";
import CorrelationPanel from "./components/CorrelationPanel";
import "./App.css";

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>赔率-事件关联分析系统</h1>
        <span className="subtitle">
          2026世界杯 — 英格兰 vs 法国 (模拟数据)
        </span>
      </header>

      <Toolbar />

      <main className="app-main">
        <div className="chart-area">
          <OddsChart />
        </div>

        <aside className="sidebar">
          <EventTimeline />
          <CorrelationPanel />
        </aside>
      </main>
    </div>
  );
}
