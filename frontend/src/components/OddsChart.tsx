/* ── Odds Chart Component (ECharts) ─────────────────── */
import { useMemo, useCallback } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { useAppStore } from "../store/useAppStore";
import { CURVE_COLORS, SEVERITY_COLORS } from "../types";

/* LTTB downsampling for performance */
function lttb(
  data: Array<[number, number]>,
  targetPoints: number
): Array<[number, number]> {
  if (data.length <= targetPoints) return data;

  const result: Array<[number, number]> = [data[0]];
  const bucketSize = (data.length - 2) / (targetPoints - 2);
  let a = 0;

  for (let i = 0; i < targetPoints - 2; i++) {
    const bucketStart = Math.floor((i + 1) * bucketSize) + 1;
    const bucketEnd = Math.floor((i + 2) * bucketSize) + 1;
    const avgBucketEnd = Math.min(bucketEnd, data.length - 1);

    const nextBucketEnd2 = Math.floor((i + 3) * bucketSize) + 1;
    const nextStart = Math.floor((i + 2) * bucketSize) + 1;
    const nextEnd = Math.min(nextBucketEnd2, data.length);
    let sumX = 0,
      sumY = 0;
    const count = nextEnd - nextStart;
    if (count > 0) {
      for (let j = nextStart; j < nextEnd; j++) {
        sumX += data[j][0];
        sumY += data[j][1];
      }
    }
    const nextAvg: [number, number] = [sumX / count, sumY / count];

    let maxArea = -1;
    let maxPoint = bucketStart;

    for (let j = bucketStart; j < avgBucketEnd; j++) {
      const area =
        Math.abs(
          (data[a][0] - nextAvg[0]) * (data[j][1] - data[a][1]) -
            (data[a][0] - data[j][0]) * (nextAvg[1] - data[a][1])
        ) * 0.5;
      if (area > maxArea) {
        maxArea = area;
        maxPoint = j;
      }
    }
    result.push(data[maxPoint]);
    a = maxPoint;
  }
  result.push(data[data.length - 1]);
  return result;
}

export default function OddsChart() {
  const oddsRecords = useAppStore((s) => s.oddsRecords);
  const events = useAppStore((s) => s.events);
  const correlations = useAppStore((s) => s.correlations);
  const selectedBookmakers = useAppStore((s) => s.selectedBookmakers);
  const selectedMarket = useAppStore((s) => s.selectedMarket);
  const selectedEventTypes = useAppStore((s) => s.selectedEventTypes);
  const interactionState = useAppStore((s) => s.interactionState);
  const hoverEvent = useAppStore((s) => s.hoverEvent);
  const unhoverEvent = useAppStore((s) => s.unhoverEvent);
  const clickEvent = useAppStore((s) => s.clickEvent);
  const clearSelection = useAppStore((s) => s.clearSelection);

  const onChartClick = useCallback(
    (params: any) => {
      // Click on blank area → clear
      if (!params.seriesIndex && !params.data) {
        clearSelection();
      }
    },
    [clearSelection]
  );

  const option: EChartsOption = useMemo(() => {
    // Group odds by bookmaker + selection
    const groups = new Map<string, Array<[number, number]>>();

    for (const r of oddsRecords) {
      if (!selectedBookmakers.has(r.bookmaker)) continue;
      if (r.market !== selectedMarket) continue;

      const key = `${r.bookmaker} / ${r.selection}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push([
        new Date(r.timestamp).getTime(),
        r.odds_value,
      ]);
    }

    // Filtered events
    const filteredEvents =
      selectedEventTypes.size === 0
        ? events
        : events.filter((e) => selectedEventTypes.has(e.event_type));

    // Highlighted event from interaction state
    const highlightedEventId =
      interactionState.type === "EVENT_HOVER"
        ? interactionState.eventId
        : interactionState.type === "DETAIL_PANEL"
        ? interactionState.eventId
        : null;

    return {
      tooltip: {
        trigger: "axis",
        formatter: (params: any) => {
          if (!Array.isArray(params)) return "";
          const lines = params.map(
            (p: any) =>
              `<span style="color:${p.color}">●</span> ${p.seriesName}: <b>${p.value[1]?.toFixed(3)}</b>`
          );
          const time = new Date(params[0]?.value[0]).toLocaleTimeString(
            "zh-CN"
          );
          return `<b>${time}</b><br/>${lines.join("<br/>")}`;
        },
      },
      legend: {
        top: 10,
        data: [...groups.keys()],
        textStyle: { fontSize: 12 },
      },
      grid: {
        top: 60,
        right: 40,
        bottom: 80,
        left: 60,
      },
      xAxis: {
        type: "time",
        name: "时间",
        axisLabel: {
          formatter: (v: number) =>
            new Date(v).toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
            }),
        },
      },
      yAxis: {
        type: "value",
        name: "赔率 (Decimal)",
        axisLabel: { formatter: "{value}" },
      },
      dataZoom: [
        { type: "inside", start: 0, end: 100 },
        {
          type: "slider",
          start: 0,
          end: 100,
          height: 25,
          bottom: 10,
        },
      ],
      series: [
        ...[...groups.entries()].map(([name, data], i) => ({
          type: "line" as const,
          name,
          data: lttb(data.sort((a, b) => a[0] - b[0]), 2000),
          smooth: true,
          symbol: "none",
          lineStyle: { width: 2, color: CURVE_COLORS[i % CURVE_COLORS.length] },
          markPoint: {
            silent: false,
            symbol: "pin",
            symbolSize: 28,
            label: { show: false },
            data: filteredEvents
              .filter((e) => {
                // Only show events whose correlations match this curve
                const curveCorrs = correlations.filter(
                  (c) =>
                    c.event_id === e.source_id &&
                    c.curve_id.startsWith(
                      name.split(" / ")[0]
                    )
                );
                return curveCorrs.length > 0;
              })
              .map((e) => ({
                name: e.title,
                coord: [new Date(e.timestamp).getTime(), 0],
                symbol: "pin",
                symbolSize: highlightedEventId === e.source_id ? 36 : 24,
                itemStyle: {
                  color:
                    highlightedEventId === e.source_id
                      ? "#fff"
                      : SEVERITY_COLORS[e.severity],
                  borderColor: SEVERITY_COLORS[e.severity],
                  borderWidth: highlightedEventId === e.source_id ? 3 : 1,
                },
                label: {
                  show: highlightedEventId === e.source_id,
                  formatter: e.title,
                  position: "top",
                  fontSize: 12,
                },
                eventId: e.source_id,
              })),
            // @ts-expect-error: custom event handling
            _eventData: filteredEvents.map((e) => e.source_id),
          },
        })),
      ],
      // Event vertical lines (markLine)
      ...(filteredEvents.length > 0
        ? [
            {
              type: "line" as const,
              name: "事件",
              data: [],
              markLine: {
                silent: false,
                symbol: "none",
                lineStyle: {
                  type: "dashed" as const,
                  color: "#999",
                  width: 1,
                  opacity: 0.6,
                },
                label: { show: false },
                data: filteredEvents.map((e) => ({
                  xAxis: new Date(e.timestamp).getTime(),
                  label: {
                    show: highlightedEventId === e.source_id,
                    formatter: e.title,
                    position: "start",
                    fontSize: 11,
                    color: SEVERITY_COLORS[e.severity],
                  },
                  lineStyle: {
                    color:
                      highlightedEventId === e.source_id
                        ? SEVERITY_COLORS[e.severity]
                        : "#ccc",
                    width:
                      highlightedEventId === e.source_id ? 2 : 1,
                    type:
                      highlightedEventId === e.source_id
                        ? ("solid" as const)
                        : ("dashed" as const),
                  },
                })),
              },
            } as any,
          ]
        : []),
    };
  }, [
    oddsRecords,
    events,
    correlations,
    selectedBookmakers,
    selectedMarket,
    selectedEventTypes,
    interactionState,
  ]);

  return (
    <ReactECharts
      option={option}
      style={{ height: "100%", width: "100%" }}
      onEvents={{
        click: onChartClick,
      }}
      notMerge
      lazyUpdate
    />
  );
}
