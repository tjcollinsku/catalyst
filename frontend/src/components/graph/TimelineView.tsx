import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import * as d3 from "d3";
import type { TimelineEvent, TimelineLayer } from "../../types";
import styles from "./TimelineView.module.css";

/* ── Layer configuration ─────────────────────────────────── */

interface LayerConfig {
    key: TimelineLayer;
    label: string;
    icon: string;
    color: string;       // CSS variable name
    shape: "circle" | "triangle" | "diamond" | "square";
}

const LAYERS: LayerConfig[] = [
    { key: "document",    label: "Documents",    icon: "\uD83D\uDCC4", color: "--graph-node-person",    shape: "circle"   },
    { key: "signal",      label: "Signals",      icon: "\u26A1",       color: "--graph-edge-signal",    shape: "triangle" },
    { key: "financial",   label: "Financial",     icon: "\uD83D\uDCB0", color: "--graph-node-org",       shape: "diamond"  },
    { key: "transaction", label: "Transactions",  icon: "\uD83C\uDFE0", color: "--graph-node-property",  shape: "square"   },
];

/* Severity → opacity for signal markers */
const SEVERITY_OPACITY: Record<string, number> = {
    CRITICAL: 1.0,
    HIGH: 0.9,
    MEDIUM: 0.7,
    LOW: 0.5,
    INFORMATIONAL: 0.35,
};

/* ── D3 symbol helpers ───────────────────────────────────── */

function markerPath(shape: LayerConfig["shape"], size: number): string {
    const gen = d3.symbol().size(size);
    switch (shape) {
        case "circle":   return gen.type(d3.symbolCircle)() || "";
        case "triangle": return gen.type(d3.symbolTriangle)() || "";
        case "diamond":  return gen.type(d3.symbolDiamond)() || "";
        case "square":   return gen.type(d3.symbolSquare)() || "";
    }
}

/* ── Props ────────────────────────────────────────────────── */

interface TimelineViewProps {
    events: TimelineEvent[];
    /** Called when user brushes a date range on the timeline */
    onBrushChange?: (range: [Date, Date] | null) => void;
    /** Called when user clicks an event marker */
    onEventClick?: (event: TimelineEvent) => void;
    /** Entity ID highlighted from the graph (highlights related events) */
    highlightEntityId?: string | null;
}

/* ── Component ───────────────────────────────────────────── */

export function TimelineView({
    events,
    onBrushChange,
    onEventClick,
    highlightEntityId,
}: TimelineViewProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const svgRef = useRef<SVGSVGElement>(null);
    const brushRef = useRef<d3.BrushBehavior<unknown> | null>(null);
    const [activeLayers, setActiveLayers] = useState<Set<TimelineLayer>>(
        new Set(LAYERS.map((l) => l.key))
    );
    const [brushRange, setBrushRange] = useState<[Date, Date] | null>(null);
    const [tooltip, setTooltip] = useState<{
        x: number;
        y: number;
        event: TimelineEvent;
    } | null>(null);

    /* ── Resolve CSS color ─────────────────────────────────── */
    const resolveColor = useCallback((varName: string): string => {
        if (!containerRef.current) return "#888";
        return getComputedStyle(containerRef.current)
            .getPropertyValue(varName)
            .trim() || "#888";
    }, []);

    /* ── Filtered + parsed events ──────────────────────────── */
    const filteredEvents = useMemo(() => {
        return events
            .filter((e) => activeLayers.has(e.layer))
            .map((e) => ({ ...e, _date: new Date(e.date) }))
            .filter((e) => !isNaN(e._date.getTime()))
            .sort((a, b) => a._date.getTime() - b._date.getTime());
    }, [events, activeLayers]);

    /* ── Layer counts ──────────────────────────────────────── */
    const layerCounts = useMemo(() => {
        const counts: Record<string, number> = {};
        for (const e of events) {
            counts[e.layer] = (counts[e.layer] || 0) + 1;
        }
        return counts;
    }, [events]);

    /* ── Toggle layer ──────────────────────────────────────── */
    const toggleLayer = useCallback((layer: TimelineLayer) => {
        setActiveLayers((prev) => {
            const next = new Set(prev);
            if (next.has(layer)) {
                next.delete(layer);
            } else {
                next.add(layer);
            }
            return next;
        });
    }, []);

    /* ── Clear brush ───────────────────────────────────────── */
    const clearBrush = useCallback(() => {
        setBrushRange(null);
        onBrushChange?.(null);
        // Also clear the D3 brush visual
        if (svgRef.current && brushRef.current) {
            d3.select(svgRef.current).select<SVGGElement>(".brush-group").call(
                brushRef.current.move as never,
                null
            );
        }
    }, [onBrushChange]);

    /* ── Main D3 render ────────────────────────────────────── */
    useEffect(() => {
        if (!svgRef.current || !containerRef.current) return;
        if (filteredEvents.length === 0) return;

        const svgEl = svgRef.current;
        const svg = d3.select(svgEl);
        svg.selectAll("*").remove();

        const wrapper = svgEl.parentElement!;
        const width = wrapper.clientWidth;
        const height = wrapper.clientHeight;
        const margin = { top: 10, right: 20, bottom: 30, left: 20 };
        const innerW = width - margin.left - margin.right;
        const innerH = height - margin.top - margin.bottom;

        // Date extent (pad by 5% on each side)
        const dates = filteredEvents.map((e) => e._date);
        const [minDate, maxDate] = d3.extent(dates) as [Date, Date];
        const pad = (maxDate.getTime() - minDate.getTime()) * 0.05 || 86400000;
        const xDomain: [Date, Date] = [
            new Date(minDate.getTime() - pad),
            new Date(maxDate.getTime() + pad),
        ];

        const xScale = d3.scaleTime().domain(xDomain).range([0, innerW]);

        // Y positions: one "lane" per layer
        const layerKeys = LAYERS.filter((l) => activeLayers.has(l.key)).map((l) => l.key);
        const laneHeight = innerH / Math.max(layerKeys.length, 1);
        const yPos = (layer: TimelineLayer) => {
            const idx = layerKeys.indexOf(layer);
            return idx >= 0 ? idx * laneHeight + laneHeight / 2 : innerH / 2;
        };

        const g = svg
            .append("g")
            .attr("transform", `translate(${margin.left},${margin.top})`);

        // ── X axis ─────────────────────────────────────────────
        const axisColor = resolveColor("--graph-label");

        g.append("g")
            .attr("transform", `translate(0,${innerH})`)
            .call(
                d3
                    .axisBottom(xScale)
                    .ticks(d3.timeYear.every(1) ?? 6)
                    .tickFormat((d) => d3.timeFormat("%Y")(d as Date))
            )
            .selectAll("text")
            .attr("fill", axisColor)
            .attr("font-size", 10);

        g.selectAll(".domain, .tick line").attr("stroke", axisColor).attr("opacity", 0.3);

        // ── Lane background lines ──────────────────────────────
        layerKeys.forEach((layer) => {
            const y = yPos(layer);
            g.append("line")
                .attr("x1", 0)
                .attr("x2", innerW)
                .attr("y1", y)
                .attr("y2", y)
                .attr("stroke", axisColor)
                .attr("stroke-opacity", 0.1)
                .attr("stroke-dasharray", "3,3");
        });

        // ── Layer config lookup ────────────────────────────────
        const layerMap = new Map(LAYERS.map((l) => [l.key, l]));

        // ── Render event markers ───────────────────────────────
        const markers = g
            .selectAll<SVGPathElement, (typeof filteredEvents)[number]>("path.marker")
            .data(filteredEvents)
            .join("path")
            .attr("class", "marker")
            .attr("d", (d) => {
                const cfg = layerMap.get(d.layer);
                return cfg ? markerPath(cfg.shape, 80) : markerPath("circle", 80);
            })
            .attr("transform", (d) => {
                const x = xScale(d._date);
                const y = yPos(d.layer);
                return `translate(${x},${y})`;
            })
            .attr("fill", (d) => {
                const cfg = layerMap.get(d.layer);
                return cfg ? resolveColor(cfg.color) : "#888";
            })
            .attr("opacity", (d) => {
                if (d.layer === "signal") {
                    return SEVERITY_OPACITY[d.metadata.severity ?? "MEDIUM"] ?? 0.7;
                }
                return 0.8;
            })
            .attr("cursor", "pointer")
            .attr("stroke", "transparent")
            .attr("stroke-width", 2);

        // Highlight events related to selected entity
        if (highlightEntityId) {
            markers.attr("opacity", (d) => {
                const eid = d.metadata.entity_id ?? d.metadata.property_id ?? d.metadata.buyer_id;
                return eid === highlightEntityId ? 1 : 0.15;
            });
        }

        // ── Interactions ───────────────────────────────────────
        markers
            .on("mouseenter", (event, d) => {
                const rect = containerRef.current!.getBoundingClientRect();
                setTooltip({
                    x: event.clientX - rect.left + 10,
                    y: event.clientY - rect.top - 10,
                    event: d,
                });
                d3.select(event.currentTarget as SVGPathElement)
                    .attr("stroke", resolveColor("--graph-edge-highlight"))
                    .attr("stroke-width", 2);
            })
            .on("mouseleave", (event) => {
                setTooltip(null);
                d3.select(event.currentTarget as SVGPathElement)
                    .attr("stroke", "transparent");
            })
            .on("click", (_event, d) => {
                onEventClick?.(d);
            });

        // ── Brush for date range selection ─────────────────────
        const brush = d3
            .brushX()
            .extent([
                [0, 0],
                [innerW, innerH],
            ])
            .on("end", (event) => {
                if (!event.selection) {
                    setBrushRange(null);
                    onBrushChange?.(null);
                    return;
                }
                const [x0, x1] = event.selection as [number, number];
                const dateRange: [Date, Date] = [xScale.invert(x0), xScale.invert(x1)];
                setBrushRange(dateRange);
                onBrushChange?.(dateRange);
            });

        brushRef.current = brush;

        const brushGroup = g
            .append("g")
            .attr("class", "brush-group")
            .call(brush);

        // Style the brush selection area
        brushGroup
            .selectAll(".selection")
            .attr("fill", resolveColor("--accent"))
            .attr("fill-opacity", 0.12)
            .attr("stroke", resolveColor("--accent"))
            .attr("stroke-opacity", 0.4);

        return () => {
            brushRef.current = null;
        };
    }, [filteredEvents, activeLayers, resolveColor, onBrushChange, onEventClick, highlightEntityId]);

    /* ── Format date for display ───────────────────────────── */
    const formatDate = (d: Date) =>
        d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });

    /* ── Render ─────────────────────────────────────────────── */

    if (events.length === 0) {
        return (
            <div className={styles.container} ref={containerRef}>
                <div className={styles.empty}>
                    No timeline events. Upload documents to build a timeline.
                </div>
            </div>
        );
    }

    return (
        <div className={styles.container} ref={containerRef} style={{ position: "relative" }}>
            {/* ── Layer toggle bar ─────────────────────────────── */}
            <div className={styles.toggleBar}>
                {LAYERS.map((layer) => (
                    <button
                        key={layer.key}
                        className={`${styles.toggleBtn} ${
                            activeLayers.has(layer.key) ? styles.toggleBtnActive : ""
                        }`}
                        onClick={() => toggleLayer(layer.key)}
                        title={`Toggle ${layer.label}`}
                    >
                        <span
                            className={styles.toggleDot}
                            style={{
                                background: activeLayers.has(layer.key)
                                    ? `var(${LAYERS.find((l) => l.key === layer.key)?.color})`
                                    : "var(--text-soft)",
                                opacity: activeLayers.has(layer.key) ? 1 : 0.3,
                            }}
                        />
                        {layer.icon} {layer.label}
                        <span className={styles.toggleCount}>
                            {layerCounts[layer.key] ?? 0}
                        </span>
                    </button>
                ))}
                <span className={styles.toggleSpacer} />
                {brushRange && (
                    <button className={styles.clearBrush} onClick={clearBrush}>
                        Clear selection
                    </button>
                )}
            </div>

            {/* ── Brush range display ──────────────────────────── */}
            {brushRange && (
                <div className={styles.brushRange}>
                    Selected:
                    <span className={styles.brushRangeHighlight}>
                        {formatDate(brushRange[0])}
                    </span>
                    &mdash;
                    <span className={styles.brushRangeHighlight}>
                        {formatDate(brushRange[1])}
                    </span>
                </div>
            )}

            {/* ── SVG timeline ─────────────────────────────────── */}
            <div className={styles.svgWrap}>
                <svg ref={svgRef} className={styles.svg} />
            </div>

            {/* ── Tooltip ──────────────────────────────────────── */}
            {tooltip && (
                <div
                    className={styles.tooltip}
                    style={{ left: tooltip.x, top: tooltip.y, position: "absolute" }}
                >
                    <p className={styles.tooltipLabel}>{tooltip.event.label}</p>
                    <p className={styles.tooltipDate}>
                        {formatDate(new Date(tooltip.event.date))}
                    </p>
                    {tooltip.event.layer === "signal" && tooltip.event.metadata.severity && (
                        <p className={styles.tooltipMeta}>
                            Severity: {tooltip.event.metadata.severity}
                        </p>
                    )}
                    {tooltip.event.layer === "financial" && tooltip.event.metadata.total_revenue && (
                        <p className={styles.tooltipMeta}>
                            Revenue: ${Number(tooltip.event.metadata.total_revenue).toLocaleString()}
                        </p>
                    )}
                    {tooltip.event.layer === "transaction" && tooltip.event.metadata.price && (
                        <p className={styles.tooltipMeta}>
                            Price: ${Number(tooltip.event.metadata.price).toLocaleString()}
                        </p>
                    )}
                </div>
            )}
        </div>
    );
}
