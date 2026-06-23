/* ── Event Timeline Component ────────────────────────── */
import { useMemo } from "react";
import { useAppStore } from "../store/useAppStore";
import { SEVERITY_COLORS, SEVERITY_LABELS, type EventRecord } from "../types";

function EventCard({
  event,
  isHighlighted,
  isDimmed,
}: {
  event: EventRecord;
  isHighlighted: boolean;
  isDimmed: boolean;
}) {
  const hoverEvent = useAppStore((s) => s.hoverEvent);
  const unhoverEvent = useAppStore((s) => s.unhoverEvent);
  const clickEvent = useAppStore((s) => s.clickEvent);

  const time = new Date(event.timestamp).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });

  const severityColor = SEVERITY_COLORS[event.severity] || "#94a3b8";

  return (
    <div
      className={`event-card ${isHighlighted ? "highlighted" : ""} ${isDimmed ? "dimmed" : ""}`}
      style={{
        borderLeft: `4px solid ${severityColor}`,
        opacity: isDimmed ? 0.4 : 1,
        transform: isHighlighted ? "scale(1.02)" : "scale(1)",
      }}
      onMouseEnter={() => hoverEvent(event.source_id)}
      onMouseLeave={() => unhoverEvent()}
      onClick={() => clickEvent(event.source_id)}
    >
      <div className="event-time">{time}</div>
      <div className="event-badge" style={{ background: severityColor }}>
        {SEVERITY_LABELS[event.severity]}
      </div>
      <div className="event-title">{event.title}</div>
      <div className="event-type">{event.event_type}</div>
    </div>
  );
}

export default function EventTimeline() {
  const events = useAppStore((s) => s.events);
  const selectedEventTypes = useAppStore((s) => s.selectedEventTypes);
  const toggleEventType = useAppStore((s) => s.toggleEventType);
  const interactionState = useAppStore((s) => s.interactionState);

  const highlightedEventId =
    interactionState.type === "EVENT_HOVER"
      ? interactionState.eventId
      : interactionState.type === "DETAIL_PANEL"
        ? interactionState.eventId
        : null;

  // Show only filtered events
  const filteredEvents = useMemo(() => {
    if (selectedEventTypes.size === 0) return events;
    return events.filter((e) => selectedEventTypes.has(e.event_type));
  }, [events, selectedEventTypes]);

  // Get unique event types
  const eventTypes = useMemo(() => {
    const types = new Set(events.map((e) => e.event_type));
    return [...types].sort();
  }, [events]);

  return (
    <div className="event-timeline">
      <h3>事件时间轴</h3>

      {/* Event type filter chips */}
      <div className="event-filters">
        {eventTypes.map((type) => (
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
        {filteredEvents.length === 0 ? (
          <p className="empty">暂无事件</p>
        ) : (
          filteredEvents.map((event) => (
            <EventCard
              key={event.source_id}
              event={event}
              isHighlighted={highlightedEventId === event.source_id}
              isDimmed={
                highlightedEventId !== null &&
                highlightedEventId !== event.source_id
              }
            />
          ))
        )}
      </div>
    </div>
  );
}
