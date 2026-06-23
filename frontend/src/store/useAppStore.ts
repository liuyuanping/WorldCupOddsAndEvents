/* ── Championship Store (Zustand) ────────────────────── */
import { create } from "zustand";
import type {
  TeamProfile,
  ChampionPrediction,
  TeamEventData,
  OddsTrendSeries,
} from "../types";
import {
  fetchChampionTeams,
  fetchChampionTrend,
  fetchChampionEvents,
  fetchChampionPrediction,
} from "../api/client";

interface AppState {
  /* Teams */
  teams: TeamProfile[];
  teamsLoading: boolean;
  selectedTeamIds: Set<string>;

  /* Odds trends */
  oddsTrends: Record<string, OddsTrendSeries>;
  trendsLoading: boolean;

  /* Events */
  events: TeamEventData[];
  eventsLoading: boolean;
  selectedEventTypes: Set<string>;
  hoveredTeamId: string | null;
  selectedEvent: TeamEventData | null;

  /* Prediction */
  prediction: ChampionPrediction | null;
  predictionLoading: boolean;

  /* Bookmaker / Provider */
  selectedBookmaker: string;
  dataProvider: string;

  /* Actions */
  loadTeams: () => Promise<void>;
  loadTrends: (teamIds: string[]) => Promise<void>;
  loadEvents: () => Promise<void>;
  loadPrediction: () => Promise<void>;
  toggleTeam: (tid: string) => void;
  selectTeams: (tids: string[]) => void;
  selectTopN: (n: number) => void;
  selectAll: () => void;
  deselectAll: () => void;
  setDataProvider: (p: string) => void;
  setSelectedBookmaker: (bm: string) => void;
  setHoveredTeam: (tid: string | null) => void;
  setSelectedEvent: (evt: TeamEventData | null) => void;
  toggleEventType: (t: string) => void;
}

const DEFAULT_TEAMS = [
  "france", "argentina", "spain", "england", "portugal", "germany",
  "netherlands", "brazil", "usa", "norway", "japan", "morocco",
];

export const useAppStore = create<AppState>((set, get) => ({
  teams: [],
  teamsLoading: false,
  selectedTeamIds: new Set(DEFAULT_TEAMS),

  oddsTrends: {},
  trendsLoading: false,

  events: [],
  eventsLoading: false,
  selectedEventTypes: new Set<string>(),
  hoveredTeamId: null,
  selectedEvent: null,

  prediction: null,
  predictionLoading: false,

  selectedBookmaker: "Pinnacle",
  dataProvider: "polymarket",

  loadTeams: async () => {
    set({ teamsLoading: true });
    try {
      const provider = get().dataProvider;
      const data = await fetchChampionTeams(provider);
      set({ teams: data.teams, teamsLoading: false });
    } catch (e) {
      console.error("loadTeams failed:", e);
      set({ teamsLoading: false });
    }
  },

  loadTrends: async (teamIds: string[]) => {
    set({ trendsLoading: true });
    try {
      const provider = get().dataProvider;
      const bm = get().selectedBookmaker;
      const data = await fetchChampionTrend({
        team_ids: teamIds.join(","),
        bookmaker: bm,
        provider: provider,
      });
      set({ oddsTrends: data.series as Record<string, OddsTrendSeries>, trendsLoading: false });
    } catch (e) {
      console.error("loadTrends failed:", e);
      set({ trendsLoading: false });
    }
  },

  loadEvents: async () => {
    set({ eventsLoading: true });
    try {
      const provider = get().dataProvider;
      const data = await fetchChampionEvents({ limit: 200, provider });
      set({ events: data.events, eventsLoading: false });
    } catch (e) {
      console.error("loadEvents failed:", e);
      set({ eventsLoading: false });
    }
  },

  loadPrediction: async () => {
    set({ predictionLoading: true });
    try {
      const provider = get().dataProvider;
      const data = await fetchChampionPrediction({ n_simulations: 10000, provider });
      set({ prediction: data, predictionLoading: false });
    } catch (e) {
      console.error("loadPrediction failed:", e);
      set({ predictionLoading: false });
    }
  },

  setDataProvider: (p: string) => {
    set({ dataProvider: p, selectedTeamIds: new Set(DEFAULT_TEAMS) });
    const state = get();
    state.loadTeams();
    state.loadEvents();
    state.loadPrediction();
  },

  toggleTeam: (tid: string) => {
    const next = new Set(get().selectedTeamIds);
    if (next.has(tid)) {
      if (next.size > 1) next.delete(tid);
    } else {
      next.add(tid);
    }
    set({ selectedTeamIds: next });
    get().loadTrends([...next]);
  },

  selectTeams: (tids: string[]) => {
    if (tids.length === 0) return;
    set({ selectedTeamIds: new Set(tids) });
    get().loadTrends(tids);
  },

  selectTopN: (n: number) => {
    const state = get();
    const sorted = [...state.teams]
      .sort((a, b) => b.implied_probability - a.implied_probability)
      .slice(0, n)
      .map((t) => t.team_id);
    set({ selectedTeamIds: new Set(sorted) });
    get().loadTrends(sorted);
  },

  selectAll: () => {
    const all = get().teams.map((t) => t.team_id);
    set({ selectedTeamIds: new Set(all) });
    get().loadTrends(all);
  },

  deselectAll: () => {
    const first = get().teams[0]?.team_id;
    if (first) {
      set({ selectedTeamIds: new Set([first]) });
      get().loadTrends([first]);
    }
  },

  setSelectedBookmaker: (bm: string) => {
    set({ selectedBookmaker: bm });
    get().loadTrends([...get().selectedTeamIds]);
  },

  setHoveredTeam: (tid: string | null) => set({ hoveredTeamId: tid }),
  setSelectedEvent: (evt: TeamEventData | null) => set({ selectedEvent: evt }),
  toggleEventType: (t: string) => {
    const next = new Set(get().selectedEventTypes);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    set({ selectedEventTypes: next });
  },
}));
