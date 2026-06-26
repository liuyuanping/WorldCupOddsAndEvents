/* ── Information Search Page (Full Screen) ───────────── */
import { useState, useCallback, useEffect, useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useAppStore } from "../store/useAppStore";
import { getTeamColor } from "../types";

interface SearchResult {
  title: string; description: string; source_url: string;
  team_id: string; team_name: string; event_type: string;
  severity: number; timestamp: string; confidence: number;
}

const SEVERITY_LABELS: Record<number, string> = { 1: "低", 2: "中", 3: "高", 4: "严重" };
const EVENT_TYPES = ["injury","squad","form","transfer","manager","record","elimination","upset","comeback","suspension","other"];
const TIME_INTERVALS = [
  { label: "1h", value: "1h" }, { label: "6h", value: "6h" },
  { label: "1d", value: "1d" }, { label: "1w", value: "1w" },
  { label: "1m", value: "1m" }, { label: "Max", value: "all" },
];

export default function SearchPage() {
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const teams = useAppStore((s) => s.teams);

  // Team & interval for the left panel
  const [searchTeam, setSearchTeam] = useState("");
  const [searchInterval, setSearchInterval] = useState("1m");
  const [trendData, setTrendData] = useState<Array<{ timestamp: string; prob: number }>>([]);
  const [trendLoading, setTrendLoading] = useState(false);

  // Default team = first selected on dashboard
  useEffect(() => {
    if (!searchTeam && selectedTeamIds.size > 0) {
      setSearchTeam([...selectedTeamIds][0]);
    }
  }, [selectedTeamIds]);

  // Fetch trend data for selected team
  useEffect(() => {
    if (!searchTeam) return;
    setTrendLoading(true);
    fetch(`/api/v1/champion/trend?team_ids=${searchTeam}&interval=${searchInterval}&provider=polymarket`)
      .then((r) => r.json())
      .then((d) => setTrendData(d.series?.[searchTeam]?.data || []))
      .catch(() => setTrendData([]))
      .finally(() => setTrendLoading(false));
  }, [searchTeam, searchInterval]);

  // Search results
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [editTeamId, setEditTeamId] = useState("");
  const [editTeamName, setEditTeamName] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editType, setEditType] = useState("other");
  const [editSeverity, setEditSeverity] = useState(2);
  const [editTs, setEditTs] = useState("");
  const [editConfidence, setEditConfidence] = useState(0.85);
  const [editSourceUrl, setEditSourceUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState("");

  const teamNames = teams.map((t) => ({ id: t.team_id, name: t.team_name }));

  const doSearch = useCallback(async () => {
    if (selectedTeamIds.size === 0) return;
    setLoading(true); setResults([]); setSelected(null); setMsg("");
    try {
      const r = await fetch(`/api/v1/champion/search?team_ids=${[...selectedTeamIds].join(",")}&limit=15`);
      const data = await r.json();
      setResults(data.results || []);
      if (data.results?.length === 0) setMsg("未找到相关信息");
    } catch { setMsg("搜索失败"); }
    setLoading(false);
  }, [selectedTeamIds]);

  const selectResult = (r: SearchResult) => {
    setSelected(r);
    setEditTeamId(r.team_id); setEditTeamName(r.team_name);
    setEditTitle(r.title); setEditDesc(r.description);
    setEditType(r.event_type); setEditSeverity(r.severity);
    setEditTs(r.timestamp ? r.timestamp.slice(0, 19) : new Date().toISOString().slice(0, 19));
    setEditConfidence(r.confidence); setEditSourceUrl(r.source_url || "");
  };

  const addToDatabase = async () => {
    if (!selected) return;
    setAdding(true); setMsg("");
    try {
      const r = await fetch("/api/v1/champion/events/db", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          team_id: editTeamId, team_name: editTeamName,
          event_type: editType, title: editTitle, description: editDesc,
          timestamp: editTs + ":00Z", severity: editSeverity,
          confidence: editConfidence, source_url: editSourceUrl,
        }),
      });
      if (r.ok) { setMsg("✅ 已添加到离线数据库"); useAppStore.getState().loadEvents(); }
      else { setMsg("❌ 添加失败"); }
    } catch { setMsg("❌ 添加失败"); }
    setAdding(false);
  };

  // Trend chart option
  const teamColor = getTeamColor(searchTeam);
  const trendOption = useMemo(() => ({
    tooltip: { trigger: "axis" as const, formatter: (params: any) => {
      if (!Array.isArray(params)) return "";
      const d = params[0]?.value;
      return `<b>${new Date(d[0]).toLocaleString("zh-CN")}</b><br/>胜率: <b>${d[1].toFixed(1)}%</b>`;
    }},
    grid: { top: 30, right: 10, bottom: 25, left: 45 },
    xAxis: { type: "time" as const, axisLabel: { fontSize: 10, formatter: (v: number) => {
      const d = new Date(v); return `${d.getMonth() + 1}/${d.getDate()}`;
    }}},
    yAxis: { type: "value" as const, name: "%", axisLabel: { fontSize: 10, formatter: "{value}" } },
    series: [{
      type: "line" as const, name: "胜率", smooth: true, symbol: "none" as const, color: teamColor,
      data: (trendData || []).map((d) => [new Date(d.timestamp).getTime(), (d.prob ?? 0) * 100]),
    }],
  }), [trendData, teamColor]);

  return (
    <div className="search-page">
      <div className="search-page-header">
        <h2>🔍 信息检索</h2>
      </div>

      {msg && <p className="search-msg">{msg}</p>}

      <div className="search-page-body">
        {/* Left: Team selector + Trend chart + execute button */}
        <div className="search-page-left">
          <div className="search-left-section">
            <span className="edit-label">选择球队</span>
            <select value={searchTeam} onChange={(e) => setSearchTeam(e.target.value)}
              style={{ width: "100%", padding: "0.3rem", background: "var(--bg)", color: "var(--text)",
                border: "1px solid var(--border)", borderRadius: "4px", fontSize: "0.8rem" }}>
              {teams.sort((a, b) => b.implied_probability - a.implied_probability).map((t) => (
                <option key={t.team_id} value={t.team_id}>{t.flag_emoji} {t.team_name}</option>
              ))}
            </select>
          </div>

          <div className="search-left-section">
            <span className="edit-label">时间段</span>
            <div className="interval-btns" style={{ flexWrap: "wrap" }}>
              {TIME_INTERVALS.map((ti) => (
                <button key={ti.value}
                  className={`chip ${searchInterval === ti.value ? "active" : ""}`}
                  onClick={() => setSearchInterval(ti.value)}
                  style={{ fontSize: "0.65rem", padding: "0.1rem 0.4rem" }}>
                  {ti.label}
                </button>
              ))}
            </div>
          </div>

          <button className="action-btn search-btn-lg" onClick={doSearch} disabled={loading}
            style={{ width: "100%", margin: "0.5rem 0" }}>
            {loading ? "搜索中..." : "▶ 执行搜索"}
          </button>

          <div className="search-left-section" style={{ flex: 1, minHeight: 0 }}>
            <span className="edit-label">胜率趋势</span>
            <div style={{ height: "100%", minHeight: 200 }}>
              {trendLoading ? (
                <p className="search-msg">加载中...</p>
              ) : trendData.length > 0 ? (
                <ReactECharts option={trendOption} style={{ height: "100%", width: "100%" }} notMerge={true} />
              ) : (
                <p className="search-msg" style={{ paddingTop: "3rem" }}>暂无数据</p>
              )}
            </div>
          </div>
        </div>

        {/* Center: Results */}
        <div className="search-page-results">
          {results.map((r, i) => (
            <div key={i} className={`search-item ${selected === r ? "selected" : ""}`} onClick={() => selectResult(r)}>
              <div className="search-item-header">
                <span className="search-team" style={{ color: getTeamColor(r.team_id) }}>{r.team_name}</span>
                <span className="search-type">{r.event_type}</span>
              </div>
              <div className="search-item-title">{r.title}</div>
              <div className="search-item-url">{r.source_url}</div>
            </div>
          ))}
        </div>

        {/* Right: Edit form */}
        <div className="search-page-edit">
          {selected ? (
            <>
              <h4>编辑后添加到数据库</h4>
              <div className="edit-row">
                <span className="edit-label">球队</span>
                <select value={editTeamId} onChange={(e) => {
                  const t = teamNames.find((x) => x.id === e.target.value);
                  setEditTeamId(e.target.value); setEditTeamName(t?.name || "");
                }}>
                  {teamNames.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <div className="edit-row"><span className="edit-label">标题 *</span>
                <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} /></div>
              <div className="edit-row"><span className="edit-label">描述</span>
                <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)} rows={4} /></div>
              <div className="edit-row-inline">
                <div><span className="edit-label">类型</span>
                  <select value={editType} onChange={(e) => setEditType(e.target.value)}>
                    {EVENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select></div>
                <div><span className="edit-label">严重度</span>
                  <select value={editSeverity} onChange={(e) => setEditSeverity(Number(e.target.value))}>
                    {[1, 2, 3, 4].map((s) => <option key={s} value={s}>{SEVERITY_LABELS[s]}</option>)}
                  </select></div>
                <div><span className="edit-label">置信度</span>
                  <input type="number" min="0" max="1" step="0.05" value={editConfidence}
                    onChange={(e) => setEditConfidence(Number(e.target.value))}
                    style={{ width: "70px", padding: "0.2rem", background: "var(--bg)", color: "var(--text)",
                      border: "1px solid var(--border)", borderRadius: "3px", fontSize: "0.7rem" }} /></div>
              </div>
              <div className="edit-row"><span className="edit-label">时间</span>
                <input type="datetime-local" value={editTs} onChange={(e) => setEditTs(e.target.value)}
                  style={{ padding: "0.25rem", background: "var(--bg)", color: "var(--text)",
                    border: "1px solid var(--border)", borderRadius: "3px", fontSize: "0.75rem" }} /></div>
              <div className="edit-row"><span className="edit-label">来源链接</span>
                <input value={editSourceUrl} onChange={(e) => setEditSourceUrl(e.target.value)} placeholder="https://..." /></div>
              <button className="action-btn add-btn" onClick={addToDatabase} disabled={adding}>
                {adding ? "添加中..." : "➕ 添加到离线数据库"}
              </button>
            </>
          ) : (
            <p className="search-edit-hint">选择一条搜索结果开始编辑</p>
          )}
        </div>
      </div>
    </div>
  );
}
