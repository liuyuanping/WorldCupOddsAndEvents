/* ── Toolbar Component ───────────────────────────────── */
import { useEffect } from "react";
import { useAppStore } from "../store/useAppStore";

export default function Toolbar() {
  const oddsProvider = useAppStore((s) => s.oddsProvider);
  const setOddsProvider = useAppStore((s) => s.setOddsProvider);
  const selectedBookmakers = useAppStore((s) => s.selectedBookmakers);
  const toggleBookmaker = useAppStore((s) => s.toggleBookmaker);
  const selectedMarket = useAppStore((s) => s.selectedMarket);
  const setSelectedMarket = useAppStore((s) => s.setSelectedMarket);
  const loadOdds = useAppStore((s) => s.loadOdds);
  const loadEvents = useAppStore((s) => s.loadEvents);
  const loadCorrelations = useAppStore((s) => s.loadCorrelations);
  const loadDataSources = useAppStore((s) => s.loadDataSources);
  const oddsLoading = useAppStore((s) => s.oddsLoading);
  const dataSources = useAppStore((s) => s.dataSources);

  useEffect(() => {
    loadDataSources();
    loadOdds();
    loadEvents();
    loadCorrelations();
  }, []);

  const handleProviderChange = (p: string) => {
    setOddsProvider(p);
    setTimeout(() => {
      loadOdds();
      loadCorrelations();
    }, 100);
  };

  const handleBookmakerToggle = (bm: string) => {
    toggleBookmaker(bm);
    setTimeout(loadOdds, 100);
  };

  const handleMarketChange = (m: string) => {
    setSelectedMarket(m);
    setTimeout(loadOdds, 100);
  };

  const handleRefresh = () => {
    loadOdds();
    loadEvents();
    loadCorrelations();
  };

  const allBookmakers = ["Pinnacle", "Bet365", "William Hill", "Betfair"];

  return (
    <div className="toolbar">
      <div className="toolbar-group">
        <label>数据源</label>
        <select
          value={oddsProvider}
          onChange={(e) => handleProviderChange(e.target.value)}
        >
          {dataSources
            .filter((ds) => ds.type === "odds" && ds.state === "active")
            .map((ds) => (
              <option key={ds.id} value={ds.id}>
                {ds.name || ds.id}
              </option>
            ))}
        </select>
      </div>

      <div className="toolbar-group">
        <label>博彩公司</label>
        <div className="chip-group">
          {allBookmakers.map((bm) => (
            <button
              key={bm}
              className={`chip ${selectedBookmakers.has(bm) ? "active" : ""}`}
              onClick={() => handleBookmakerToggle(bm)}
            >
              {bm}
            </button>
          ))}
        </div>
      </div>

      <div className="toolbar-group">
        <label>市场</label>
        <select
          value={selectedMarket}
          onChange={(e) => handleMarketChange(e.target.value)}
        >
          <option value="h2h">1X2 (胜平负)</option>
          <option value="over_under">大小球</option>
          <option value="asian_handicap">亚洲盘</option>
        </select>
      </div>

      <div className="toolbar-group">
        <button
          className="refresh-btn"
          onClick={handleRefresh}
          disabled={oddsLoading}
        >
          {oddsLoading ? "加载中..." : "刷新数据"}
        </button>
      </div>
    </div>
  );
}
