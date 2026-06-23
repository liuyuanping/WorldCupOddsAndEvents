/* ── API Client ──────────────────────────────────────── */
import axios from "axios";
import type {
  OddsRecord,
  EventRecord,
  CorrelationCandidate,
  DataSourceInfo,
} from "../types";

const api = axios.create({
  baseURL: "",  // Relative URLs — goes through Vite proxy in dev
  timeout: 30000,
});

/* ── Odds ──────────────────────────────────────────── */

export async function fetchOdds(params: {
  match_id?: string;
  provider?: string;
  bookmaker?: string;
  market?: string;
}): Promise<OddsRecord[]> {
  const { data } = await api.get("/api/v1/odds", { params });
  return data;
}

export async function fetchBookmakers(provider: string): Promise<string[]> {
  const { data } = await api.get("/api/v1/odds/bookmakers", {
    params: { provider },
  });
  return data.bookmakers;
}

export async function fetchMarkets(provider: string): Promise<string[]> {
  const { data } = await api.get("/api/v1/odds/markets", {
    params: { provider },
  });
  return data.markets;
}

/* ── Events ─────────────────────────────────────────── */

export async function fetchEvents(params: {
  provider?: string;
  event_type?: string;
}): Promise<EventRecord[]> {
  const { data } = await api.get("/api/v1/events", { params });
  return data;
}

export async function fetchEventCategories(
  provider: string
): Promise<string[]> {
  const { data } = await api.get("/api/v1/events/categories", {
    params: { provider },
  });
  return data.categories;
}

/* ── Correlations ───────────────────────────────────── */

export async function fetchCorrelations(params: {
  match_id?: string;
  odds_provider?: string;
  event_provider?: string;
  min_score?: number;
}): Promise<CorrelationCandidate[]> {
  const { data } = await api.get("/api/v1/correlations", { params });
  return data;
}

/* ── Data Sources ───────────────────────────────────── */

export async function fetchDataSources(): Promise<DataSourceInfo[]> {
  const { data } = await api.get("/api/v1/datasources");
  return data.providers;
}

/* ── Health ─────────────────────────────────────────── */

export async function checkHealth(): Promise<Record<string, unknown>> {
  const { data } = await api.get("/health");
  return data;
}

/* ── Champion ───────────────────────────────────────── */

export async function fetchChampionTeams(provider?: string): Promise<{ teams: any[]; total: number }> {
  const { data } = await api.get("/api/v1/champion/teams", { params: provider ? { provider } : {} });
  return data;
}

export async function fetchChampionOdds(params: {
  team_ids?: string;
  bookmaker?: string;
  provider?: string;
}): Promise<{ odds: Record<string, any>; teams_count: number }> {
  const { data } = await api.get("/api/v1/champion/odds", { params });
  return data;
}

export async function fetchChampionTrend(params: {
  team_ids?: string;
  bookmaker?: string;
  provider?: string;
}): Promise<{ series: Record<string, any> }> {
  const { data } = await api.get("/api/v1/champion/trend", { params });
  return data;
}

export async function fetchChampionEvents(params: {
  team_id?: string;
  limit?: number;
  provider?: string;
}): Promise<{ events: any[]; total: number }> {
  const { data } = await api.get("/api/v1/champion/events", { params });
  return data;
}

export async function fetchChampionPrediction(params: {
  n_simulations?: number;
  provider?: string;
}): Promise<any> {
  const { data } = await api.get("/api/v1/champion/predict", { params });
  return data;
}
