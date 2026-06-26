/* ── Information Search Page (Full Screen) ───────────── */
import { useState, useCallback } from "react";
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

  return (
    <div className="search-page">
      <div className="search-page-header">
        <h2>🔍 信息检索</h2>
        <button className="action-btn search-btn-lg" onClick={doSearch} disabled={loading}>
          {loading ? "搜索中..." : `🌐 搜索 ${selectedTeamIds.size} 支球队`}
        </button>
      </div>

      {msg && <p className="search-msg">{msg}</p>}

      <div className="search-page-body">
        {/* Results */}
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

        {/* Edit form */}
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
              <div className="edit-row">
                <span className="edit-label">标题 *</span>
                <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
              </div>
              <div className="edit-row">
                <span className="edit-label">描述</span>
                <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)} rows={4} />
              </div>
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
              <div className="edit-row">
                <span className="edit-label">时间</span>
                <input type="datetime-local" value={editTs} onChange={(e) => setEditTs(e.target.value)}
                  style={{ padding: "0.25rem", background: "var(--bg)", color: "var(--text)",
                    border: "1px solid var(--border)", borderRadius: "3px", fontSize: "0.75rem" }} />
              </div>
              <div className="edit-row">
                <span className="edit-label">来源链接</span>
                <input value={editSourceUrl} onChange={(e) => setEditSourceUrl(e.target.value)} placeholder="https://..." />
              </div>
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
