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

// Fixed per-team color map — same color across all modules
export const TEAM_COLORS: Record<string, string> = {
  // Tier 1: favorites
  "france":       "#3b82f6",  // blue
  "argentina":    "#56b8e5",  // light blue (argentina flag)
  "spain":        "#ef4444",  // red
  "england":      "#f59e0b",  // amber
  // Tier 2: contenders
  "portugal":     "#22c55e",  // green
  "germany":      "#8b5cf6",  // violet
  "netherlands":  "#f97316",  // orange
  "brazil":       "#06b6d4",  // cyan
  // Tier 3
  "usa":          "#ec4899",  // pink
  "norway":       "#84cc16",  // lime
  "japan":        "#e11d48",  // rose
  "morocco":      "#14b8a6",  // teal
  "colombia":     "#d946ef",  // fuchsia
  "mexico":       "#0ea5e9",  // sky
  "belgium":      "#a855f7",  // purple
  "switzerland":  "#64748b",  // slate
  // Tier 4
  "croatia":      "#f43f5e",
  "canada":       "#10b981",
  "ivory_coast":  "#6366f1",
  "south_korea":  "#f97316",
  "senegal":      "#2dd4bf",
  "australia":    "#fbbf24",
  "austria":      "#ef4444",
  "egypt":        "#3b82f6",
  "sweden":       "#06b6d4",
  // Long shots
  "ghana":        "#84cc16",
  "uruguay":      "#8b5cf6",
  "paraguay":     "#ec4899",
  "scotland":     "#22c55e",
  "ecuador":      "#f59e0b",
  "congo_dr":     "#a855f7",
  "new_zealand":  "#64748b",
  "curacao":      "#0ea5e9",
  "iran":         "#d946ef",
  "algeria":      "#14b8a6",
  "bosnia":       "#e11d48",
  "uzbekistan":   "#6366f1",
  "panama":       "#10b981",
  "iraq":         "#f43f5e",
  "south_africa": "#fbbf24",
  "cape_verde":   "#2dd4bf",
  "czechia":      "#f97316",
  "qatar":        "#a855f7",
  "saudi_arabia": "#06b6d4",
};

export function getTeamColor(teamId: string): string {
  return TEAM_COLORS[teamId] || "#475569";  // fallback gray
}

/* ── Champion Types ──────────────────────────────────── */

export interface TeamProfile {
  team_id: string;
  team_name: string;
  flag_emoji: string;
  group: string;
  elo_rating: number;
  best_odds: number;
  avg_odds: number;
  implied_probability: number;
  odds_trend_30d: number;
  recent_form: string;
  key_events_count?: number;
  events_summary?: string[];
}

export interface ChampionOddsData {
  team_name: string;
  timeline: Array<{ timestamp: string; odds_value: number; implied_probability: number; bookmaker: string }>;
  latest: Record<string, number>;
  latest_avg: number;
}

export interface TeamEventData {
  source_id?: string;
  team_id: string;
  team_name: string;
  event_type: string;
  title: string;
  description: string;
  timestamp: string;
  severity: number;
  confidence: number;
  source_url?: string;
}

export interface ChampionPredictionResult {
  team_id: string;
  team_name: string;
  flag_emoji: string;
  market_probability: number;
  sim_probability: number;
  value_edge_pct: number;
  elo_rating: number;
  group: string;
}

export interface ChampionPrediction {
  rankings: ChampionPredictionResult[];
  total_simulations: number;
  top_pick: ChampionPredictionResult;
  value_pick: ChampionPredictionResult;
  dark_horse: ChampionPredictionResult;
}

export interface OddsTrendSeries {
  team_name: string;
  flag_emoji: string;
  data: Array<{ timestamp: string; odds: number; prob: number }>;
}
