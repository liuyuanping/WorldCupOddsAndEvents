/* ── Information Search Panel ─────────────────────────── */
import { useState, useCallback } from "react";
import { useAppStore } from "../store/useAppStore";
import { getTeamColor } from "../types";

interface SearchResult {
  title: string;
  description: string;
  source_url: string;
  team_id: string;
  team_name: string;
  event_type: string;
  severity: number;
  timestamp: string;
  confidence: number;
}

const SEVERITY_LABELS: Record<number, string> = { 1: "低", 2: "中", 3: "高", 4: "严重" };

export default function SearchPanel() {
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const teams = useAppStore((s) => s.teams);
  const eventTimeRange = useAppStore((s) => s.eventTimeRange);

  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editType, setEditType] = useState("other");
  const [editSeverity, setEditSeverity] = useState(2);
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState("");

  const doSearch = useCallback(async () => {
    if (selectedTeamIds.size === 0) return;
    setLoading(true);
    setResults([]);
    setSelected(null);
    setMsg("");
    try {
      const teamIds = [...selectedTeamIds].join(",");
      const r = await fetch(`/api/v1/champion/search?team_ids=${teamIds}&limit=8`);
      const data = await r.json();
      setResults(data.results || []);
      if (data.results?.length === 0) setMsg("未找到相关信息");
    } catch {
      setMsg("搜索失败");
    }
    setLoading(false);
  }, [selectedTeamIds]);

  const selectResult = (r: SearchResult) => {
    setSelected(r);
    setEditTitle(r.title);
    setEditDesc(r.description);
    setEditType(r.event_type);
    setEditSeverity(r.severity);
  };

  const addToDatabase = async () => {
    if (!selected) return;
    setAdding(true);
    setMsg("");
    try {
      // Use current time if no timestamp available
      const ts = selected.timestamp || new Date().toISOString();
      const r = await fetch("/api/v1/champion/events/db", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          team_id: selected.team_id,
          team_name: selected.team_name,
          event_type: editType,
          title: editTitle,
          description: editDesc,
          timestamp: ts,
          severity: editSeverity,
          confidence: selected.confidence,
          source_url: selected.source_url,
        }),
      });
      if (r.ok) {
        setMsg("✅ 已添加到离线数据库");
        useAppStore.getState().loadEvents();
      } else {
        setMsg("❌ 添加失败");
      }
    } catch {
      setMsg("❌ 添加失败");
    }
    setAdding(false);
  };

  return (
    <div className="panel search-panel">
      <div className="search-header">
        <h3>🔍 信息检索</h3>
        <button className="action-btn" onClick={doSearch} disabled={loading}>
          {loading ? "搜索中..." : `搜索 ${selectedTeamIds.size} 队`}
        </button>
      </div>

      {msg && <p className="search-msg">{msg}</p>}

      {/* Results list */}
      <div className="search-results">
        {results.map((r, i) => (
          <div
            key={i}
            className={`search-item ${selected === r ? "selected" : ""}`}
            onClick={() => selectResult(r)}
          >
            <div className="search-item-header">
              <span className="search-team" style={{ color: getTeamColor(r.team_id) }}>
                {r.team_name}
              </span>
              <span className="search-type">{r.event_type}</span>
            </div>
            <div className="search-item-title">{r.title}</div>
          </div>
        ))}
      </div>

      {/* Edit form for selected result */}
      {selected && (
        <div className="search-edit">
          <h4>编辑后添加到数据库</h4>
          <div className="edit-row">
            <span className="edit-label">标题</span>
            <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
          </div>
          <div className="edit-row">
            <span className="edit-label">描述</span>
            <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)} rows={3} />
          </div>
          <div className="edit-row-inline">
            <div>
              <span className="edit-label">类型</span>
              <select value={editType} onChange={(e) => setEditType(e.target.value)}>
                <option value="injury">伤病</option>
                <option value="squad">名单</option>
                <option value="form">状态</option>
                <option value="transfer">转会</option>
                <option value="manager">教练</option>
                <option value="record">纪录</option>
                <option value="elimination">晋级/出局</option>
                <option value="other">其他</option>
              </select>
            </div>
            <div>
              <span className="edit-label">严重度</span>
              <select value={editSeverity} onChange={(e) => setEditSeverity(Number(e.target.value))}>
                {[1, 2, 3, 4].map((s) => (
                  <option key={s} value={s}>{SEVERITY_LABELS[s]}</option>
                ))}
              </select>
            </div>
          </div>
          <button className="action-btn add-btn" onClick={addToDatabase} disabled={adding}>
            {adding ? "添加中..." : "➕ 添加到离线数据库"}
          </button>
        </div>
      )}
    </div>
  );
}
