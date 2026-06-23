/* ── Event Feed ──────────────────────────────────────── */
import { useMemo } from "react";
import { useAppStore } from "../store/useAppStore";
import { SEVERITY_COLORS, SEVERITY_LABELS } from "../types";

export default function ChampionEvents() {
  const events = useAppStore((s) => s.events);
  const selectedTeamIds = useAppStore((s) => s.selectedTeamIds);
  const hoveredTeamId = useAppStore((s) => s.hoveredTeamId);
  const setHoveredTeam = useAppStore((s) => s.setHoveredTeam);
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

  return (
    <div className="panel events-panel">
      <h3>📰 球队事件</h3>

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
          return (
            <div
              key={i}
              className={`event-item ${isHovered ? "highlighted" : ""}`}
              style={{
                borderLeft: `3px solid ${SEVERITY_COLORS[evt.severity] || "#94a3b8"}`,
                opacity: isDimmed ? 0.35 : 1,
              }}
              onMouseEnter={() => setHoveredTeam(evt.team_id)}
              onMouseLeave={() => setHoveredTeam(null)}
            >
              <div className="event-item-header">
                <span className="event-team">
                  {evt.team_name}
                </span>
                <span
                  className="event-severity"
                  style={{
                    background: SEVERITY_COLORS[evt.severity] || "#94a3b8",
                  }}
                >
                  {SEVERITY_LABELS[evt.severity]}
                </span>
                <span className="event-date">
                  {new Date(evt.timestamp).toLocaleDateString("zh-CN", {
                    month: "short",
                    day: "numeric",
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
