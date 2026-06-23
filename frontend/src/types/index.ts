/* ── Shared Types ─────────────────────────────────────── */

export interface OddsRecord {
  id: string;
  provider: string;
  source_id: string;
  match_id: string;
  bookmaker: string;
  market: string;
  selection: string;
  odds_value: number;
  odds_format: string;
  implied_probability: number | null;
  volume: number | null;
  timestamp: string;
  received_at: string | null;
  metadata: Record<string, unknown>;
}

export interface EventRecord {
  id: string;
  provider: string;
  source_id: string;
  event_type: string;
  title: string;
  description: string | null;
  timestamp: string;
  detected_at: string | null;
  severity: number; // 1=LOW, 2=MEDIUM, 3=HIGH, 4=CRITICAL
  confidence: number;
  source_url: string | null;
  entities: EntityRef[];
  metadata: Record<string, unknown>;
  related_odds_ids: string[];
  related_curves: string[];
}

export interface EntityRef {
  type: string;
  id: string;
  name: string;
}

export interface CorrelationCandidate {
  timestamp: string;
  score: number;
  magnitude: number;
  direction: string;
  detection_methods: string[];
  event_id: string;
  curve_id: string;
  lag_seconds: number | null;
}

export interface CurveDefinition {
  id: string;
  name: string;
  description?: string;
  type: string;
  source_config: CurveSourceConfig;
  calculation?: string;
  created_at: string;
  updated_at: string;
}

export interface CurveSourceConfig {
  provider: string;
  match_id: string;
  bookmaker?: string;
  market: string;
  selection: string;
}

export interface DataSourceInfo {
  id: string;
  type: "odds" | "event";
  state: string;
  name: string;
  info: Record<string, unknown>;
}

export type InteractionState =
  | { type: "IDLE" }
  | { type: "EVENT_HOVER"; eventId: string }
  | { type: "POINT_SELECT"; curveId: string; timestamp: string; value: number }
  | { type: "DETAIL_PANEL"; eventId: string; correlationIds: string[] };

export const SEVERITY_COLORS: Record<number, string> = {
  1: "#94a3b8", // LOW - slate
  2: "#facc15", // MEDIUM - yellow
  3: "#f97316", // HIGH - orange
  4: "#ef4444", // CRITICAL - red
};

export const SEVERITY_LABELS: Record<number, string> = {
  1: "低",
  2: "中",
  3: "高",
  4: "严重",
};

export const CURVE_COLORS = [
  "#3b82f6", "#ef4444", "#22c55e", "#f59e0b",
  "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16",
];
