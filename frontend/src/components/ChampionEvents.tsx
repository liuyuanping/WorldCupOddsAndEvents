/* ── Event Feed ──────────────────────────────────────── */
import { useMemo } from "react";
import { useAppStore } from "../store/useAppStore";
import { SEVERITY_COLORS, SEVERITY_LABELS, getTeamColor } from "../types";

export default function ChampionEvents() {
  const events = useAppStore((s) => s.events);
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const hoveredTeamId = useAppStore((s) => s.hoveredTeamId);
  const setHoveredTeam = useAppStore((s) => s.setHoveredTeam);
  const selectedEvent = useAppStore((s) => s.selectedEvent);
  const setSelectedEvent = useAppStore((s) => s.setSelectedEvent);
  const selectedEventTypes = useAppStore((s) => s.selectedEventTypes);
  const toggleEventType = useAppStore((s) => s.toggleEventType);

  // Filter events for selected teams only
  const filteredEvents = useMemo(() => {
    let result = events.filter((e) => selectedTeamIds.has(e.team_id));
    if (selectedEventTypes.size > 0) {
      result = result.filter((e) => selectedEventTypes.has(e.event_type));
    }
    return result.sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
  }, [events, selectedTeamIds, selectedEventTypes]);

  const eventTypes = useMemo(() => {
    const types = new Set(events.map((e) => e.event_type));
    return [...types].sort();
  }, [events]);

  // Default to first filtered event, or keep selected if still valid
  const displayEvent = selectedEvent || filteredEvents[0] || null;

  return (
    <div className="panel events-panel">
      <h3>📰 球队事件</h3>

      {/* Fixed height detail area — always visible */}
      <div className="event-detail-popup">
        {displayEvent ? (
          <>
            <div className="popup-header">
              <span
                className="popup-severity"
                style={{ background: SEVERITY_COLORS[displayEvent.severity] || "#94a3b8" }}
              >
                {SEVERITY_LABELS[displayEvent.severity]}
              </span>
              <span className="popup-team" style={{ color: getTeamColor(displayEvent.team_id) }}>
                {displayEvent.team_name}
              </span>
              {selectedEvent && (
                <button className="popup-close" onClick={() => setSelectedEvent(null)}>✕</button>
              )}
            </div>
            <h4>{displayEvent.title}</h4>
            <p className="popup-desc">{displayEvent.description || "暂无详细描述"}</p>
            <div className="popup-meta">
              <span>类型: {displayEvent.event_type}</span>
              <span>置信度: {(displayEvent.confidence * 100).toFixed(0)}%</span>
              <span>{new Date(displayEvent.timestamp).toLocaleString("zh-CN")}</span>
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
