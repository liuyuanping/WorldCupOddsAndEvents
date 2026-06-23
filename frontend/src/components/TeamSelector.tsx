/* ── Team Selector ───────────────────────────────────── */
import { useState, useMemo } from "react";
import { useAppStore } from "../store/useAppStore";
import { getTeamColor } from "../types";

export default function TeamSelector() {
  const teams = useAppStore((s) => s.teams);
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const toggleTeam = useAppStore((s) => s.toggleTeam);
  const selectTopN = useAppStore((s) => s.selectTopN);
  const selectAll = useAppStore((s) => s.selectAll);
  const deselectAll = useAppStore((s) => s.deselectAll);
  const [search, setSearch] = useState("");

  const sorted = useMemo(
    () => [...teams].sort((a, b) => b.implied_probability - a.implied_probability),
    [teams]
  );

  const filtered = useMemo(() => {
    if (!search.trim()) return sorted;
    const q = search.toLowerCase();
    return sorted.filter(
      (t) =>
        t.team_name.toLowerCase().includes(q) ||
        t.team_id.toLowerCase().includes(q)
    );
  }, [sorted, search]);

  const selectedCount = selectedTeamIds.size;

  return (
    <div className="panel team-selector">
      <div className="selector-header">
        <h3>🎯 球队选择 ({selectedCount}/{teams.length})</h3>
        <div className="selector-actions">
          <button className="action-btn" onClick={() => selectTopN(3)}>
            Top 3
          </button>
          <button className="action-btn" onClick={() => selectTopN(6)}>
            Top 6
          </button>
          <button className="action-btn" onClick={() => selectTopN(12)}>
            Top 12
          </button>
          <button className="action-btn" onClick={selectAll}>
            全选
          </button>
          <button className="action-btn" onClick={deselectAll}>
            清除
          </button>
        </div>
      </div>

      <input
        className="team-search"
        type="text"
        placeholder="搜索球队..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      <div className="team-grid">
        {filtered.map((t) => {
          const isSel = selectedTeamIds.has(t.team_id);
          const prob = (t.implied_probability * 100).toFixed(1);
          return (
            <div
              key={t.team_id}
              className={`team-chip ${isSel ? "active" : ""}`}
              style={isSel ? { background: getTeamColor(t.team_id), borderColor: getTeamColor(t.team_id) } : {}}
              onClick={() => toggleTeam(t.team_id)}
              title={`${t.team_name}: ${prob}%`}
            >
              <span className="team-chip-flag">{t.flag_emoji}</span>
              <span className="team-chip-name">{t.team_name}</span>
              <span className="team-chip-prob">{prob}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
