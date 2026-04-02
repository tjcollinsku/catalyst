import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import type { GraphNode, GraphEdge, GraphStats, GraphNodeType } from "../../types";
import styles from "./EntityGraph.module.css";

/* ── Configuration ───────────────────────────────────────── */

const NODE_RADIUS: Record<GraphNodeType, number> = {
    person: 18,
    organization: 22,
    property: 16,
    financial_instrument: 14,
};

/** CSS variable names for node fill by type */
const NODE_COLOR_VAR: Record<GraphNodeType, string> = {
    person: "--graph-node-person",
    organization: "--graph-node-org",
    property: "--graph-node-property",
    financial_instrument: "--graph-node-financial",
};

/** D3 symbol generators by type */
const NODE_SHAPE: Record<GraphNodeType, d3.SymbolType> = {
    person: d3.symbolCircle,
    organization: d3.symbolSquare,
    property: d3.symbolTriangle,
    financial_instrument: d3.symbolDiamond,
};

/* ── D3 sim node / link extended types ───────────────────── */

interface SimNode extends d3.SimulationNodeDatum {
    id: string;
    type: GraphNodeType;
    label: string;
    metadata: GraphNode["metadata"];
    // d3 adds x, y, vx, vy
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
    relationship: string;
    label: string;
    weight: number;
    metadata: GraphEdge["metadata"];
}

/* ── Props ────────────────────────────────────────────────── */

interface EntityGraphProps {
    nodes: GraphNode[];
    edges: GraphEdge[];
    stats: GraphStats;
    /** Called when a node is clicked (to open slide panel) */
    onNodeClick?: (node: GraphNode) => void;
    /** ID of the currently-selected node (highlight ring) */
    selectedNodeId?: string | null;
    /** Width override (default: container width) */
    width?: number;
    /** Height override (default: container height) */
    height?: number;
}

/* ── Component ───────────────────────────────────────────── */

export function EntityGraph({
    nodes,
    edges,
    stats,
    onNodeClick,
    selectedNodeId,
}: EntityGraphProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const svgRef = useRef<SVGSVGElement>(null);
    const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null);
    const [showLegend, setShowLegend] = useState(true);
    const [tooltip, setTooltip] = useState<{
        x: number;
        y: number;
        node: SimNode;
    } | null>(null);

    /* ── Resolve CSS variable to actual color ──────────────── */
    const resolveColor = useCallback((varName: string): string => {
        if (!containerRef.current) return "#888";
        return getComputedStyle(containerRef.current)
            .getPropertyValue(varName)
            .trim() || "#888";
    }, []);

    /* ── Main D3 render effect ─────────────────────────────── */
    useEffect(() => {
        if (!svgRef.current || !containerRef.current) return;
        if (nodes.length === 0) return;

        const container = containerRef.current;
        const width = container.clientWidth;
        const height = container.clientHeight;

        // Clear previous render
        const svg = d3.select(svgRef.current);
        svg.selectAll("*").remove();

        // Build sim data (deep copy to avoid mutating props)
        const simNodes: SimNode[] = nodes.map((n) => ({
            ...n,
            x: undefined as unknown as number,
            y: undefined as unknown as number,
        }));
        const nodeMap = new Map(simNodes.map((n) => [n.id, n]));
        const simLinks: SimLink[] = edges
            .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
            .map((e) => ({
                source: e.source,
                target: e.target,
                relationship: e.relationship,
                label: e.label,
                weight: e.weight,
                metadata: e.metadata,
            }));

        // Zoom group
        const g = svg.append("g");

        const zoom = d3
            .zoom<SVGSVGElement, unknown>()
            .scaleExtent([0.15, 5])
            .on("zoom", (event) => {
                g.attr("transform", event.transform);
            });
        svg.call(zoom);

        // Center initial view
        svg.call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2));

        // Edge color from CSS
        const edgeColor = resolveColor("--graph-edge-default");
        const edgeHighlight = resolveColor("--graph-edge-highlight");
        const labelColor = resolveColor("--graph-label");

        // ── Render edges ───────────────────────────────────────
        const linkGroup = g
            .append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(simLinks)
            .join("line")
            .attr("stroke", edgeColor)
            .attr("stroke-width", (d) => Math.max(1, d.weight * 0.8))
            .attr("stroke-opacity", 0.6);

        // Edge labels (shown for small graphs or important edges)
        const edgeLabelGroup = g
            .append("g")
            .attr("class", "edge-labels")
            .selectAll("text")
            .data(simLinks.filter((d) => d.weight >= 2 || simLinks.length < 40))
            .join("text")
            .text((d) => d.label)
            .attr("font-size", 9)
            .attr("fill", labelColor)
            .attr("text-anchor", "middle")
            .attr("dy", -4)
            .attr("opacity", 0.7);

        // ── Render nodes ───────────────────────────────────────
        const nodeGroup = g
            .append("g")
            .attr("class", "nodes")
            .selectAll<SVGGElement, SimNode>("g")
            .data(simNodes)
            .join("g")
            .attr("cursor", "pointer")
            .call(
                d3
                    .drag<SVGGElement, SimNode>()
                    .on("start", (event, d) => {
                        if (!event.active) simRef.current?.alphaTarget(0.3).restart();
                        d.fx = d.x;
                        d.fy = d.y;
                    })
                    .on("drag", (event, d) => {
                        d.fx = event.x;
                        d.fy = event.y;
                    })
                    .on("end", (event, d) => {
                        if (!event.active) simRef.current?.alphaTarget(0);
                        d.fx = null;
                        d.fy = null;
                    })
            );

        // Node shapes
        nodeGroup
            .append("path")
            .attr("d", (d) => {
                const r = NODE_RADIUS[d.type] || 16;
                const area = Math.PI * r * r;
                // Scale up based on signal + detection count
                const boost = Math.min(
                    (d.metadata.signal_count + d.metadata.detection_count) * 15,
                    120
                );
                return d3.symbol().type(NODE_SHAPE[d.type]).size(area + boost)() || "";
            })
            .attr("fill", (d) => resolveColor(NODE_COLOR_VAR[d.type]))
            .attr("stroke", "transparent")
            .attr("stroke-width", 3)
            .attr("opacity", 0.9);

        // Selection ring (updated when selectedNodeId changes — see separate effect)
        nodeGroup
            .filter((d) => d.id === selectedNodeId)
            .select("path")
            .attr("stroke", edgeHighlight)
            .attr("stroke-width", 3);

        // Signal count indicator (red dot top-right)
        nodeGroup
            .filter((d) => d.metadata.signal_count > 0)
            .append("circle")
            .attr("r", 5)
            .attr("cx", (d) => (NODE_RADIUS[d.type] || 16) * 0.7)
            .attr("cy", (d) => -(NODE_RADIUS[d.type] || 16) * 0.7)
            .attr("fill", resolveColor("--graph-edge-signal"))
            .attr("stroke", resolveColor("--graph-bg"))
            .attr("stroke-width", 1.5);

        // Node labels
        nodeGroup
            .append("text")
            .text((d) => {
                const maxLen = 18;
                return d.label.length > maxLen
                    ? d.label.slice(0, maxLen - 1) + "…"
                    : d.label;
            })
            .attr("dy", (d) => (NODE_RADIUS[d.type] || 16) + 14)
            .attr("text-anchor", "middle")
            .attr("font-size", 11)
            .attr("fill", labelColor)
            .attr("pointer-events", "none");

        // ── Interactions ───────────────────────────────────────
        nodeGroup
            .on("click", (_event, d) => {
                if (onNodeClick) {
                    onNodeClick({
                        id: d.id,
                        type: d.type,
                        label: d.label,
                        metadata: d.metadata,
                    });
                }
            })
            .on("mouseenter", (event, d) => {
                // Highlight connected edges
                linkGroup.attr("stroke", (l) => {
                    const src =
                        typeof l.source === "object" ? (l.source as SimNode).id : l.source;
                    const tgt =
                        typeof l.target === "object" ? (l.target as SimNode).id : l.target;
                    return src === d.id || tgt === d.id ? edgeHighlight : edgeColor;
                });
                linkGroup.attr("stroke-opacity", (l) => {
                    const src =
                        typeof l.source === "object" ? (l.source as SimNode).id : l.source;
                    const tgt =
                        typeof l.target === "object" ? (l.target as SimNode).id : l.target;
                    return src === d.id || tgt === d.id ? 1 : 0.2;
                });

                // Tooltip
                const rect = container.getBoundingClientRect();
                setTooltip({
                    x: event.clientX - rect.left + 12,
                    y: event.clientY - rect.top - 10,
                    node: d,
                });
            })
            .on("mouseleave", () => {
                linkGroup.attr("stroke", edgeColor).attr("stroke-opacity", 0.6);
                setTooltip(null);
            });

        // ── Force simulation ───────────────────────────────────
        const simulation = d3
            .forceSimulation<SimNode>(simNodes)
            .force(
                "link",
                d3
                    .forceLink<SimNode, SimLink>(simLinks)
                    .id((d) => d.id)
                    .distance((d) => 100 / Math.max(1, d.weight * 0.5))
            )
            .force("charge", d3.forceManyBody().strength(-300))
            .force("center", d3.forceCenter(0, 0))
            .force(
                "collision",
                d3.forceCollide<SimNode>().radius((d) => (NODE_RADIUS[d.type] || 16) + 8)
            )
            .force("x", d3.forceX(0).strength(0.05))
            .force("y", d3.forceY(0).strength(0.05));

        simRef.current = simulation;

        simulation.on("tick", () => {
            linkGroup
                .attr("x1", (d) => (d.source as SimNode).x ?? 0)
                .attr("y1", (d) => (d.source as SimNode).y ?? 0)
                .attr("x2", (d) => (d.target as SimNode).x ?? 0)
                .attr("y2", (d) => (d.target as SimNode).y ?? 0);

            edgeLabelGroup
                .attr("x", (d) => {
                    const src = d.source as SimNode;
                    const tgt = d.target as SimNode;
                    return ((src.x ?? 0) + (tgt.x ?? 0)) / 2;
                })
                .attr("y", (d) => {
                    const src = d.source as SimNode;
                    const tgt = d.target as SimNode;
                    return ((src.y ?? 0) + (tgt.y ?? 0)) / 2;
                });

            nodeGroup.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
        });

        // Store zoom for toolbar controls
        (svg.node() as SVGSVGElement & { __zoom: typeof zoom }).__zoom = zoom as never;

        return () => {
            simulation.stop();
        };
    }, [nodes, edges, resolveColor, onNodeClick, selectedNodeId]);

    /* ── Zoom controls ─────────────────────────────────────── */
    const handleZoom = useCallback(
        (direction: "in" | "out" | "reset") => {
            if (!svgRef.current) return;
            const svg = d3.select(svgRef.current);
            const zoom = d3
                .zoom<SVGSVGElement, unknown>()
                .scaleExtent([0.15, 5]);

            if (direction === "reset") {
                const w = containerRef.current?.clientWidth ?? 800;
                const h = containerRef.current?.clientHeight ?? 600;
                svg.transition()
                    .duration(500)
                    .call(zoom.transform, d3.zoomIdentity.translate(w / 2, h / 2));
            } else {
                svg.transition()
                    .duration(300)
                    .call(zoom.scaleBy, direction === "in" ? 1.5 : 0.67);
            }
        },
        []
    );

    /* ── Render ─────────────────────────────────────────────── */

    if (nodes.length === 0) {
        return (
            <div className={styles.container} ref={containerRef}>
                <div className={styles.empty}>
                    No entities found. Upload documents to populate the graph.
                </div>
            </div>
        );
    }

    return (
        <div className={styles.container} ref={containerRef}>
            <svg
                ref={svgRef}
                className={styles.svg}
                role="img"
                aria-label={`Entity relationship graph with ${nodes.length} nodes and ${edges.length} connections`}
            />

            {/* Stats badge */}
            <div className={styles.stats}>
                {stats.total_nodes} entities · {stats.total_edges} connections
            </div>

            {/* Toolbar */}
            <div className={styles.toolbar}>
                <button
                    className={styles.toolbarBtn}
                    onClick={() => handleZoom("in")}
                    title="Zoom in"
                    aria-label="Zoom in"
                >
                    +
                </button>
                <button
                    className={styles.toolbarBtn}
                    onClick={() => handleZoom("out")}
                    title="Zoom out"
                    aria-label="Zoom out"
                >
                    −
                </button>
                <button
                    className={styles.toolbarBtn}
                    onClick={() => handleZoom("reset")}
                    title="Reset view"
                    aria-label="Reset view"
                >
                    ⌂
                </button>
                <button
                    className={styles.toolbarBtn}
                    onClick={() => setShowLegend((v) => !v)}
                    title="Toggle legend"
                    aria-label="Toggle legend"
                >
                    ◑
                </button>
            </div>

            {/* Legend */}
            {showLegend && (
                <div className={styles.legend}>
                    <div className={styles.legendItem}>
                        <span className={`${styles.legendDot} ${styles.legendDotPerson}`} />
                        Person
                    </div>
                    <div className={styles.legendItem}>
                        <span className={`${styles.legendDot} ${styles.legendDotOrg}`} />
                        Organization
                    </div>
                    <div className={styles.legendItem}>
                        <span className={`${styles.legendDot} ${styles.legendDotProperty}`} />
                        Property
                    </div>
                    <div className={styles.legendItem}>
                        <span
                            className={`${styles.legendDot} ${styles.legendDotFinancial}`}
                        />
                        Financial
                    </div>
                </div>
            )}

            {/* Tooltip */}
            {tooltip && (
                <div
                    className={styles.tooltip}
                    style={{ left: tooltip.x, top: tooltip.y }}
                >
                    <p className={styles.tooltipLabel}>{tooltip.node.label}</p>
                    <p className={styles.tooltipType}>{tooltip.node.type.replace("_", " ")}</p>
                    <p className={styles.tooltipMeta}>
                        {tooltip.node.metadata.signal_count > 0 &&
                            `${tooltip.node.metadata.signal_count} signal${tooltip.node.metadata.signal_count > 1 ? "s" : ""}`}
                        {tooltip.node.metadata.signal_count > 0 &&
                            tooltip.node.metadata.detection_count > 0 &&
                            " · "}
                        {tooltip.node.metadata.detection_count > 0 &&
                            `${tooltip.node.metadata.detection_count} detection${tooltip.node.metadata.detection_count > 1 ? "s" : ""}`}
                        {tooltip.node.metadata.doc_count > 0 &&
                            ` · ${tooltip.node.metadata.doc_count} doc${tooltip.node.metadata.doc_count > 1 ? "s" : ""}`}
                    </p>
                </div>
            )}
        </div>
    );
}
