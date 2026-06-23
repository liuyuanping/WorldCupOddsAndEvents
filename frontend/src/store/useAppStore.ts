/* ── Chart State (Zustand) ──────────────────────────── */
import { create } from "zustand";
import type {
  OddsRecord,
  EventRecord,
  CorrelationCandidate,
  DataSourceInfo,
  InteractionState,
} from "../types";
import {
  fetchOdds,
  fetchEvents,
  fetchCorrelations,
  fetchDataSources,
} from "../api/client";

/* ── Types ──────────────────────────────────────────── */

interface AppState {
  /* Odds */
  oddsRecords: OddsRecord[];
  oddsLoading: boolean;
  selectedBookmakers: Set<string>;
  selectedMarket: string;
  oddsProvider: string;

  /* Events */
  events: EventRecord[];
  eventsLoading: boolean;
  selectedEventTypes: Set<string>;
  eventProvider: string;

  /* Correlations */
  correlations: CorrelationCandidate[];
  correlationsLoading: boolean;

  /* UI */
  interactionState: InteractionState;
  selectedCorrelation: CorrelationCandidate | null;
  timeRange: { start: string; end: string };
  dataSources: DataSourceInfo[];

  /* Actions */
  loadOdds: () => Promise<void>;
  loadEvents: () => Promise<void>;
  loadCorrelations: () => Promise<void>;
  loadDataSources: () => Promise<void>;
  setSelectedBookmakers: (bms: Set<string>) => void;
  toggleBookmaker: (bm: string) => void;
  setSelectedMarket: (m: string) => void;
  setOddsProvider: (p: string) => void;
  setEventProvider: (p: string) => void;
  toggleEventType: (t: string) => void;
  setInteractionState: (s: InteractionState) => void;
  setSelectedCorrelation: (c: CorrelationCandidate | null) => void;
  setTimeRange: (r: { start: string; end: string }) => void;
  hoverEvent: (eventId: string) => void;
  unhoverEvent: () => void;
  clickEvent: (eventId: string) => void;
  clearSelection: () => void;
}

/* ── Store ──────────────────────────────────────────── */

export const useAppStore = create<AppState>((set, get) => ({
  /* Default state */
  oddsRecords: [],
  oddsLoading: false,
  selectedBookmakers: new Set(["Pinnacle", "Bet365"]),
  selectedMarket: "h2h",
  oddsProvider: "mock_odds",

  events: [],
  eventsLoading: false,
  selectedEventTypes: new Set<string>(),
  eventProvider: "mock_events",

  correlations: [],
  correlationsLoading: false,

  interactionState: { type: "IDLE" },
  selectedCorrelation: null,
  timeRange: {
    start: "2026-06-23T06:00:00Z",
    end: "2026-06-23T18:00:00Z",
  },
  dataSources: [],

  /* Load odds data */
  loadOdds: async () => {
    set({ oddsLoading: true });
    try {
      const state = get();
      const records: OddsRecord[] = [];

      // Fetch per bookmaker for efficiency
      for (const bm of state.selectedBookmakers) {
        const batch = await fetchOdds({
          provider: state.oddsProvider,
          bookmaker: bm,
          market: state.selectedMarket,
          match_id: "wc2026_eng_fra",
        });
        records.push(...batch);
      }

      set({ oddsRecords: records, oddsLoading: false });
    } catch (err) {
      console.error("Failed to load odds:", err);
      set({ oddsLoading: false });
    }
  },

  /* Load events */
  loadEvents: async () => {
    set({ eventsLoading: true });
    try {
      const state = get();
      const records = await fetchEvents({
        provider: state.eventProvider,
      });
      set({ events: records, eventsLoading: false });
    } catch (err) {
      console.error("Failed to load events:", err);
      set({ eventsLoading: false });
    }
  },

  /* Load correlations */
  loadCorrelations: async () => {
    set({ correlationsLoading: true });
    try {
      const state = get();
      const candidates = await fetchCorrelations({
        odds_provider: state.oddsProvider,
        event_provider: state.eventProvider,
        min_score: 0.2,
      });
      set({ correlations: candidates, correlationsLoading: false });
    } catch (err) {
      console.error("Failed to load correlations:", err);
      set({ correlationsLoading: false });
    }
  },

  /* Load data sources */
  loadDataSources: async () => {
    try {
      const sources = await fetchDataSources();
      set({ dataSources: sources });
    } catch (err) {
      console.error("Failed to load data sources:", err);
    }
  },

  /* Selection actions */
  setSelectedBookmakers: (bms) => set({ selectedBookmakers: bms }),
  toggleBookmaker: (bm) => {
    const next = new Set(get().selectedBookmakers);
    if (next.has(bm)) {
      if (next.size > 1) next.delete(bm);
    } else {
      next.add(bm);
    }
    set({ selectedBookmakers: next });
  },
  setSelectedMarket: (m) => set({ selectedMarket: m }),
  setOddsProvider: (p) => set({ oddsProvider: p }),
  setEventProvider: (p) => set({ eventProvider: p }),
  toggleEventType: (t) => {
    const next = new Set(get().selectedEventTypes);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    set({ selectedEventTypes: next });
  },

  /* Interaction */
  setInteractionState: (s) => set({ interactionState: s }),
  setSelectedCorrelation: (c) => set({ selectedCorrelation: c }),
  setTimeRange: (r) => set({ timeRange: r }),

  hoverEvent: (eventId) =>
    set({ interactionState: { type: "EVENT_HOVER", eventId } }),
  unhoverEvent: () =>
    set((s) =>
      s.interactionState.type === "EVENT_HOVER"
        ? { interactionState: { type: "IDLE" } }
        : {}
    ),
  clickEvent: (eventId) => {
    const corrs = get().correlations.filter((c) => c.event_id === eventId);
    set({
      interactionState: {
        type: "DETAIL_PANEL",
        eventId,
        correlationIds: corrs.map((c) => c.curve_id),
      },
      selectedCorrelation: corrs[0] ?? null,
    });
  },
  clearSelection: () =>
    set({
      interactionState: { type: "IDLE" },
      selectedCorrelation: null,
    }),
}));
