/* ── Correlation Detail Panel ────────────────────────── */
import { useAppStore } from "../store/useAppStore";
import type { CorrelationCandidate, EventRecord } from "../types";
import { SEVERITY_COLORS, SEVERITY_LABELS } from "../types";

export default function CorrelationPanel() {
  const interactionState = useAppStore((s) => s.interactionState);
  const correlations = useAppStore((s) => s.correlations);
  const events = useAppStore((s) => s.events);
  const clearSelection = useAppStore((s) => s.clearSelection);

  if (interactionState.type !== "DETAIL_PANEL") {
    return (
      <div className="correlation-panel">
        <h3>关联详情</h3>
        <p className="hint">点击事件查看关联分析</p>
      </div>
    );
  }

  const event: EventRecord | undefined = events.find(
    (e) => e.source_id === interactionState.eventId
  );

  const eventCorrelations: CorrelationCandidate[] = correlations.filter(
    (c) => c.event_id === interactionState.eventId
  );

  if (!event) {
    return (
      <div className="correlation-panel">
        <h3>关联详情</h3>
        <p className="hint">事件数据加载中...</p>
      </div>
    );
  }

  return (
    <div className="correlation-panel">
      <div className="panel-header">
        <h3>关联详情</h3>
        <button className="close-btn" onClick={clearSelection}>
          ✕
        </button>
      </div>

      {/* Event info */}
      <div className="event-detail">
        <div className="detail-row">
          <span
            className="severity-dot"
            style={{
              background: SEVERITY_COLORS[event.severity],
            }}
          />
          <span className="label">严重程度:</span>
          <span>{SEVERITY_LABELS[event.severity]}</span>
        </div>
        <h4>{event.title}</h4>
        <p className="event-desc">{event.description || "无描述"}</p>
        <div className="detail-row">
          <span className="label">时间:</span>
          <span>
            {new Date(event.timestamp).toLocaleString("zh-CN")}
          </span>
        </div>
        <div className="detail-row">
          <span className="label">类型:</span>
          <span>{event.event_type}</span>
        </div>
        <div className="detail-row">
          <span className="label">置信度:</span>
          <span>{(event.confidence * 100).toFixed(0)}%</span>
        </div>
      </div>

      {/* Correlations */}
      <div className="correlations-list">
        <h4>关联曲线 ({eventCorrelations.length})</h4>
        {eventCorrelations.length === 0 ? (
          <p className="hint">未检测到显著关联</p>
        ) : (
          eventCorrelations.map((c, i) => (
            <div key={i} className="correlation-item">
              <div className="corr-header">
                <span className="curve-name">{c.curve_id}</span>
                <span
                  className="corr-score"
                  style={{
                    color:
                      c.score > 0.6 ? "#ef4444" : c.score > 0.4 ? "#f59e0b" : "#22c55e",
                  }}
                >
                  {(c.score * 100).toFixed(0)}%
                </span>
              </div>
              <div className="corr-details">
                <span>
                  方向:{" "}
                  <b
                    style={{
                      color:
                        c.direction === "up" ? "#22c55e" : c.direction === "down" ? "#ef4444" : "#94a3b8",
                    }}
                  >
                    {c.direction === "up" ? "↑上升" : c.direction === "down" ? "↓下降" : "→持平"}
                  </b>
                </span>
                <span>幅度: <b>{(c.magnitude * 100).toFixed(2)}%</b></span>
                {c.lag_seconds !== null && (
                  <span>延迟: <b>{c.lag_seconds}s</b></span>
                )}
              </div>
              <div className="corr-methods">
                {c.detection_methods.map((m) => (
                  <span key={m} className="method-tag">
                    {m}
                  </span>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
