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

export default function SearchPage() {
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const teams = useAppStore((s) => s.teams);

  // Time range state
  const DURATIONS = [
    { label: "1h", sec: 3600 }, { label: "6h", sec: 21600 },
    { label: "1d", sec: 86400 }, { label: "1w", sec: 604800 },
    { label: "1m", sec: 2592000 }, { label: "全部", sec: -1 },
  ];
  const now = new Date();
  const defStart = new Date(now.getTime() - 2592000000).toISOString().slice(0, 16);
  const defEnd = now.toISOString().slice(0, 16);
  const [searchTeam, setSearchTeam] = useState("");
  const [timeBase, setTimeBase] = useState<"now" | "start">("now");
  const [startTime, setStartTime] = useState(defStart);
  const [endTime, setEndTime] = useState(defEnd);
  const [trendData, setTrendData] = useState<Array<{ timestamp: string; prob: number }>>([]);
  const [trendLoading, setTrendLoading] = useState(false);

  // Default team = first selected on dashboard
  useEffect(() => {
    if (!searchTeam && selectedTeamIds.size > 0) {
      setSearchTeam([...selectedTeamIds][0]);
    }
  }, [selectedTeamIds]);

  // Compute interval string from time range
  const computedInterval = useMemo(() => {
    const s = new Date(startTime).getTime();
    const e = new Date(endTime).getTime();
    const diffSec = (e - s) / 1000;
    if (diffSec <= 0) return "1h";
    if (diffSec <= 7200) return "1h";
    if (diffSec <= 43200) return "6h";
    if (diffSec <= 172800) return "1d";
    if (diffSec <= 1209600) return "1w";
    if (diffSec > 2592000) return "all";
    return "1m";
  }, [startTime, endTime]);

  // Handle duration quick buttons
  const applyDuration = (sec: number) => {
    if (sec === -1) {
      setStartTime("2025-07-01T00:00");
      setEndTime(new Date().toISOString().slice(0, 16));
      return;
    }
    const nowDt = new Date();
    if (timeBase === "now") {
      const s = new Date(nowDt.getTime() - sec * 1000);
      setStartTime(s.toISOString().slice(0, 16));
      setEndTime(nowDt.toISOString().slice(0, 16));
    } else {
      const s = new Date(startTime);
      const e = new Date(s.getTime() + sec * 1000);
      setEndTime(e.toISOString().slice(0, 16));
    }
  };

  // Fetch trend data for selected team
  useEffect(() => {
    if (!searchTeam) return;
    setTrendLoading(true);
    fetch(`/api/v1/champion/trend?team_ids=${searchTeam}&interval=${computedInterval}&provider=polymarket`)
      .then((r) => r.json())
      .then((d) => setTrendData(d.series?.[searchTeam]?.data || []))
      .catch(() => setTrendData([]))
      .finally(() => setTrendLoading(false));
  }, [searchTeam, computedInterval]);

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

  const showToast = useAppStore((s) => s.showToast);

  const teamNames = teams.map((t) => ({ id: t.team_id, name: t.team_name }));

  const doSearch = useCallback(async () => {
    if (selectedTeamIds.size === 0) return;
    setLoading(true); setResults([]); setSelected(null);
    try {
      const r = await fetch(`/api/v1/champion/search?team_ids=${[...selectedTeamIds].join(",")}&limit=15`);
      const data = await r.json();
      setResults(data.results || []);
      if (data.results?.length === 0) showToast("未找到相关信息");
    } catch { showToast("搜索失败"); }
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
    setAdding(true);
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
      if (r.ok) { showToast("✅ 已添加到离线数据库"); useAppStore.getState().loadEvents(); }
      else { showToast("❌ 添加失败"); }
    } catch { showToast("❌ 添加失败"); }
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
    dataZoom: [
      { type: "inside", start: 0, end: 100 },
    ],
    series: [{
      type: "line" as const, name: "胜率", smooth: true, symbol: "none" as const, color: teamColor,
      data: (trendData || []).map((d) => [new Date(d.timestamp).getTime(), (d.prob ?? 0) * 100]),
    }],
  }), [trendData, teamColor]);

  return (
    <div className="search-page">
      <div className="search-page-body">
        {/* Left: Team selector + Trend chart + execute button */}
        <div className="search-page-left">
          <div className="search-section-title">球队与趋势</div>
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
            <div className="time-base-btns">
              <button className={`chip ${timeBase === "now" ? "active" : ""}`}
                onClick={() => setTimeBase("now")} style={{ fontSize: "0.6rem" }}>从现在</button>
              <button className={`chip ${timeBase === "start" ? "active" : ""}`}
                onClick={() => setTimeBase("start")} style={{ fontSize: "0.6rem" }}>从开始时间</button>
            </div>
            <div className="time-inputs">
              <input id="sp-start" type="datetime-local" value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="time-input" />
              <span style={{ color: "var(--text-muted)", fontSize: "0.6rem" }}>~</span>
              <input id="sp-end" type="datetime-local" value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="time-input" />
            </div>
            <div className="interval-btns" style={{ flexWrap: "wrap" }}>
              {DURATIONS.map((d) => (
                <button key={d.label} className="chip"
                  onClick={() => applyDuration(d.sec)}
                  style={{ fontSize: "0.6rem", padding: "0.1rem 0.35rem" }}>
                  {d.sec === -1 ? "全部" : timeBase === "now" ? `过去${d.label}` : `${d.label}后`}
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
                <ReactECharts
                  option={trendOption}
                  style={{ height: "100%", width: "100%" }}
                  notMerge={true}
                  onEvents={{
                    dataZoom: (params: any) => {
                      const batch = params.batch?.[0] || params;
                      if (batch.startValue != null && batch.endValue != null) {
                        setStartTime(new Date(batch.startValue).toISOString().slice(0, 16));
                        setEndTime(new Date(batch.endValue).toISOString().slice(0, 16));
                      }
                    },
                  }}
                />
              ) : (
                <p className="search-msg" style={{ paddingTop: "3rem" }}>暂无数据</p>
              )}
            </div>
          </div>
        </div>

        {/* Center: Results */}
        <div className="search-page-results">
          <div className="search-section-title">搜索结果</div>
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
          <div className="search-section-title">编辑入库</div>
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
