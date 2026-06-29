/* ── Event Feed ──────────────────────────────────────── */
import { useMemo, useState } from "react";
import { useAppStore } from "../store/useAppStore";
import { SEVERITY_COLORS, SEVERITY_LABELS, getTeamColor } from "../types";

export default function ChampionEvents() {
  const events = useAppStore((s) => s.events);
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const hoveredTeamId = useAppStore((s) => s.hoveredTeamId);
  const setHoveredTeam = useAppStore((s) => s.setHoveredTeam);
  const selectedEvent = useAppStore((s) => s.selectedEvent);
  const setSelectedEvent = useAppStore((s) => s.setSelectedEvent);
  const loadEvents = useAppStore((s) => s.loadEvents);
  const selectedEventTypes = useAppStore((s) => s.selectedEventTypes);
  const toggleEventType = useAppStore((s) => s.toggleEventType);
  const eventTimeRange = useAppStore((s) => s.eventTimeRange);
  const eventDataProvider = useAppStore((s) => s.eventDataProvider);
  const setEventDataProvider = useAppStore((s) => s.setEventDataProvider);

  // Filter events for selected teams only
  const filteredEvents = useMemo(() => {
    let result = events.filter((e) => selectedTeamIds.has(e.team_id));
    if (selectedEventTypes.size > 0) {
      result = result.filter((e) => selectedEventTypes.has(e.event_type));
    }
    // Filter by time range
    if (eventTimeRange) {
      const start = new Date(eventTimeRange.start).getTime();
      const end = new Date(eventTimeRange.end).getTime();
      result = result.filter((e) => {
        const t = new Date(e.timestamp).getTime();
        return t >= start && t <= end;
      });
    }
    return result.sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
  }, [events, selectedTeamIds, selectedEventTypes, eventTimeRange]);

  const eventTypes = useMemo(() => {
    const types = new Set(events.map((e) => e.event_type));
    return [...types].sort();
  }, [events]);

  // Default to first filtered event, or keep selected if still valid
  const displayEvent = selectedEvent || filteredEvents[0] || null;
  const [searchEngine, setSearchEngine] = useState("baidu");

  const searchEngines: Record<string, string> = {
    baidu: "https://www.baidu.com/s?wd=",
    google: "https://www.google.com/search?q=",
    sogou: "https://www.sogou.com/web?query=",
  };

  const handleTitleClick = () => {
    if (!displayEvent) return;
    if (displayEvent.source_url) {
      window.open(displayEvent.source_url, "_blank", "noopener");
    } else {
      const query = encodeURIComponent(displayEvent.title);
      window.open(searchEngines[searchEngine] + query, "_blank", "noopener");
    }
  };

  const handleDelete = async () => {
    if (!displayEvent?.source_id) return;
    try {
      const r = await fetch(`/api/v1/champion/events/db/${displayEvent.source_id}`, { method: "DELETE" });
      if (r.ok) {
        setSelectedEvent(null);
        loadEvents();
      }
    } catch {}
  };

  return (
    <div className="panel events-panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>📰 球队事件</h3>
        <select
          className="bm-select"
          value={eventDataProvider}
          onChange={(e) => {
            setEventDataProvider(e.target.value);
            useAppStore.getState().loadEvents();
          }}
        >
          <option value="database">🗄️ 数据库 (离线)</option>
          <option value="mock_team_events">🔬 Mock (模拟事件)</option>
          <option value="gdelt">🌐 GDELT (真实新闻)</option>
        </select>
      </div>

      {/* Fixed height detail area — always visible */}
      <div className="event-detail-popup">
        {displayEvent ? (
          <>
            <div className="popup-header">
              <span className="popup-team" style={{ color: getTeamColor(displayEvent.team_id) }}>
                {displayEvent.team_name}
              </span>
              <span
                className="popup-severity"
                style={{ background: SEVERITY_COLORS[displayEvent.severity] || "#94a3b8" }}
              >
                {SEVERITY_LABELS[displayEvent.severity]}
              </span>
              {displayEvent.source_id && (
                <button
                  className="popup-delete"
                  onClick={(e) => { e.stopPropagation(); handleDelete(); }}
                  title="删除此事件"
                >
                  🗑️
                </button>
              )}
            </div>
            <h4
              onClick={handleTitleClick}
              title={displayEvent.source_url ? "打开原始链接" : `用${searchEngine}搜索`}
              style={{ cursor: "pointer", textDecoration: "underline dotted" }}
            >
              {displayEvent.title}
            </h4>
            <p className="popup-desc">{displayEvent.description || "暂无详细描述"}</p>
            <div className="popup-meta">
              <span>类型: {displayEvent.event_type}</span>
              <span>来源: {displayEvent.provider || "未知"}</span>
              <span>{new Date(displayEvent.timestamp).toLocaleString("zh-CN")}</span>
              {!displayEvent.source_url && (
                <select
                  className="search-engine-select"
                  value={searchEngine}
                  onChange={(e) => setSearchEngine(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                >
                  <option value="baidu">百度</option>
                  <option value="google">Google</option>
                  <option value="sogou">搜狗</option>
                </select>
              )}
            </div>
          </>
        ) : (
          <p className="popup-empty">暂无事件</p>
        )}
      </div>

      {/* Type filter */}
      <div className="event-filters">
        {eventTypes.slice(0, 8).map((type) => (
          <button
            key={type}
            className={`chip ${selectedEventTypes.has(type) ? "active" : ""}`}
            onClick={() => toggleEventType(type)}
          >
            {type}
          </button>
        ))}
        {selectedEventTypes.size > 0 && (
          <button
            className="chip clear"
            onClick={() =>
              selectedEventTypes.forEach((t) => toggleEventType(t))
            }
          >
            清除
          </button>
        )}
      </div>

      {/* Event list */}
      <div className="event-list">
        {filteredEvents.slice(0, 40).map((evt, i) => {
          const isHovered = hoveredTeamId === evt.team_id;
          const isDimmed = hoveredTeamId && !isHovered;
          const isSelected = selectedEvent?.title === evt.title && selectedEvent?.team_id === evt.team_id;
          return (
            <div
              key={i}
              className={`event-item ${isHovered ? "highlighted" : ""} ${isSelected ? "selected" : ""}`}
              style={{
                borderLeft: `3px solid ${getTeamColor(evt.team_id)}`,
                opacity: isDimmed ? 0.35 : 1,
                outline: isSelected ? `1px solid ${getTeamColor(evt.team_id)}` : "none",
              }}
              onMouseEnter={() => setHoveredTeam(evt.team_id)}
              onMouseLeave={() => setHoveredTeam(null)}
              onClick={() => {
                setSelectedEvent(evt);
                setHoveredTeam(evt.team_id);
              }}
            >
              <div className="event-item-header">
                <span className="event-team">
                  {evt.team_name}
                </span>
                <span
                  className="event-severity"
                  style={{ background: SEVERITY_COLORS[evt.severity] || "#94a3b8" }}
                >
                  {SEVERITY_LABELS[evt.severity]}
                </span>
                <span className="event-date">
                  {new Date(evt.timestamp).toLocaleDateString("zh-CN", {
                    month: "short", day: "numeric",
                  })}
                </span>
              </div>
              <div className="event-item-title">{evt.title}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
