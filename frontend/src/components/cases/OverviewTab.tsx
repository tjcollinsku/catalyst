import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
    CaseDashboardData,
    CaseCoverageData,
    fetchCaseDashboard,
    fetchCaseCoverage,
    fetchCaseGraph,
    isAbortError,
} from "../../api";
import type { CaseGraphResponse, GraphNode, TimelineEvent } from "../../types";
import { EntityGraph } from "../graph/EntityGraph";
import { EntityProfilePanel } from "../graph/EntityProfilePanel";
import { TimelineView } from "../graph/TimelineView";
import { ResizablePanelLayout } from "../ui/ResizablePanelLayout";
import { GraphSkeleton, TimelineSkeleton, Skeleton } from "../ui/Skeleton";
import { EmptyState } from "../ui/EmptyState";
import styles from "./OverviewTab.module.css";

/* ── Color helpers ─────────────────────────────────────────── */
const SEV_COLORS: Record<string, string> = {
    CRITICAL: "#ef4444",
    HIGH: "#f97316",
    MEDIUM: "#fbbf24",
    LOW: "#60a5fa",
};

const GAP_TYPE_LABELS: Record<string, string> = {
    RULE_BLIND: "Rule Blind",
    MISSING_DATA: "Missing Data",
    LOW_CONFIDENCE: "Low Confidence",
};

const GAP_TYPE_COLORS: Record<string, string> = {
    RULE_BLIND: "#ef4444",
    MISSING_DATA: "#f97316",
    LOW_CONFIDENCE: "#fbbf24",
};

function formatCurrency(val: string): string {
    const num = parseFloat(val);
    if (isNaN(num)) return "$0";
    return "$" + num.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function formatPercent(val: number): string {
    return (val * 100).toFixed(0) + "%";
}

/* ── Main component ───────────────────────────────────────── */

export function OverviewTab() {
    const { caseId } = useParams<{ caseId: string }>();
    const navigate = useNavigate();
    const [dashboard, setDashboard] = useState<CaseDashboardData | null>(null);
    const [coverage, setCoverage] = useState<CaseCoverageData | null>(null);
    const [graph, setGraph] = useState<CaseGraphResponse | null>(null);
    const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
    const [dateRange, setDateRange] = useState<[Date, Date] | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const mounted = useRef(true);

    const load = useCallback(
        async (signal: AbortSignal) => {
            if (!caseId) return;
            setLoading(true);
            setError(null);
            try {
                const [dashRes, covRes, graphRes] = await Promise.all([
                    fetchCaseDashboard(caseId, { signal }),
                    fetchCaseCoverage(caseId, { signal }),
                    fetchCaseGraph(caseId, { signal }),
                ]);
                if (!signal.aborted) {
                    setDashboard(dashRes);
                    setCoverage(covRes);
                    setGraph(graphRes);
                }
            } catch (err) {
                if (!isAbortError(err)) {
                    console.error(err);
                    if (!signal.aborted) setError("Failed to load dashboard data.");
                }
            } finally {
                if (!signal.aborted) setLoading(false);
            }
        },
        [caseId],
    );

    useEffect(() => {
        mounted.current = true;
        const controller = new AbortController();
        void load(controller.signal);
        return () => {
            mounted.current = false;
            controller.abort();
        };
    }, [load]);

    const handleNodeClick = useCallback((node: GraphNode) => {
        setSelectedNode((prev) => (prev?.id === node.id ? null : node));
    }, []);

    const handleBrushChange = useCallback((range: [Date, Date] | null) => {
        setDateRange(range);
    }, []);

    const handleTimelineEventClick = useCallback(
        (event: TimelineEvent) => {
            // If event references an entity, select it on the graph
            const entityId =
                event.metadata.entity_id ??
                event.metadata.property_id ??
                event.metadata.buyer_id;
            if (entityId && graph) {
                const node = graph.nodes.find((n) => n.id === entityId);
                if (node) {
                    setSelectedNode((prev) => (prev?.id === node.id ? null : node));
                }
            }
        },
        [graph]
    );

    // Filter graph nodes when a date range is brushed on the timeline.
    // We find which entity IDs appear in events within the range,
    // then show only those nodes (plus nodes connected to them).
    const filteredGraph = useMemo(() => {
        if (!graph) return null;
        if (!dateRange) return graph;

        const [start, end] = dateRange;
        const eventsInRange = graph.timeline_events.filter((e) => {
            const d = new Date(e.date);
            return d >= start && d <= end;
        });

        // Collect entity IDs referenced by events in range
        const activeEntityIds = new Set<string>();
        for (const e of eventsInRange) {
            if (e.metadata.entity_id) activeEntityIds.add(e.metadata.entity_id);
            if (e.metadata.property_id) activeEntityIds.add(e.metadata.property_id);
            if (e.metadata.buyer_id) activeEntityIds.add(e.metadata.buyer_id);
            if (e.metadata.seller_id) activeEntityIds.add(e.metadata.seller_id);
        }

        // If no entity IDs found in the range, show all nodes (don't blank the graph)
        if (activeEntityIds.size === 0) return graph;

        // Also include nodes connected via edges to active nodes
        const connectedIds = new Set(activeEntityIds);
        for (const edge of graph.edges) {
            if (activeEntityIds.has(edge.source)) connectedIds.add(edge.target);
            if (activeEntityIds.has(edge.target)) connectedIds.add(edge.source);
        }

        const filteredNodes = graph.nodes.filter((n) => connectedIds.has(n.id));
        const nodeIdSet = new Set(filteredNodes.map((n) => n.id));
        const filteredEdges = graph.edges.filter(
            (e) => nodeIdSet.has(e.source) && nodeIdSet.has(e.target)
        );

        return {
            ...graph,
            nodes: filteredNodes,
            edges: filteredEdges,
            stats: {
                ...graph.stats,
                total_nodes: filteredNodes.length,
                total_edges: filteredEdges.length,
            },
        };
    }, [graph, dateRange]);

    if (loading) {
        return (
            <div className={styles.overviewTab}>
                <div className={styles.overviewKpiRow}>
                    {[0, 1, 2, 3].map((i) => (
                        <div key={i} className={styles.overviewKpi}>
                            <Skeleton width="2rem" height="1.5rem" />
                            <Skeleton width="5rem" height="0.75rem" />
                            <Skeleton width="4rem" height="0.6rem" />
                        </div>
                    ))}
                </div>
                <div className={styles.graphContainer}>
                    <GraphSkeleton />
                </div>
                <TimelineSkeleton />
            </div>
        );
    }

    if (error || !dashboard) {
        return <div className="tab-error"><p>{error ?? "No data available."}</p></div>;
    }

    const d = dashboard;
    const c = coverage;

    return (
        <div className={styles.overviewTab}>
            {/* ── Row 1: KPI Cards (compact) ── */}
            <div className={styles.overviewKpiRow}>
                <button
                    className={styles.overviewKpi}
                    onClick={() => navigate(`/cases/${caseId}/documents`)}
                >
                    <span className={styles.overviewKpiValue}>{d.documents.total}</span>
                    <span className={styles.overviewKpiLabel}>Documents</span>
                    <span className={styles.overviewKpiSub}>
                        {d.documents.renamed_count} auto-renamed
                    </span>
                </button>
                <button
                    className={styles.overviewKpi}
                    onClick={() => navigate(`/cases/${caseId}/signals`)}
                >
                    <span className={styles.overviewKpiValue}>{d.signals.total}</span>
                    <span className={styles.overviewKpiLabel}>Signals</span>
                    <span className={styles.overviewKpiSub}>
                        {d.signals.by_status?.OPEN ?? 0} open
                    </span>
                </button>
                <div className={styles.overviewKpi}>
                    <span className={styles.overviewKpiValue}>{d.entities.total}</span>
                    <span className={styles.overviewKpiLabel}>Entities</span>
                    <span className={styles.overviewKpiSub}>
                        {d.entities.persons}P / {d.entities.organizations}O / {d.entities.properties}Pr
                    </span>
                </div>
                <button
                    className={styles.overviewKpi}
                    onClick={() => navigate(`/cases/${caseId}/findings`)}
                >
                    <span className={styles.overviewKpiValue}>{d.findings.total}</span>
                    <span className={styles.overviewKpiLabel}>Findings</span>
                    <span className={styles.overviewKpiSub}>
                        {d.detections.confirmed} confirmed detections
                    </span>
                </button>
            </div>

            {/* Screen reader announcement for graph selection */}
            <div className="sr-only" aria-live="polite" aria-atomic="true">
                {selectedNode
                    ? `Selected ${selectedNode.type.replace("_", " ")}: ${selectedNode.label}`
                    : "No entity selected"}
            </div>

            {/* ── Row 2: Entity Relationship Graph (centerpiece) ── */}
            {filteredGraph && filteredGraph.nodes.length === 0 && (
                <div className={styles.graphContainer}>
                    <EmptyState
                        icon="🔗"
                        title="No entities mapped yet"
                        detail="Upload documents to populate the investigation map. Entities are automatically extracted during processing."
                        action={{
                            label: "Upload Documents",
                            onClick: () => navigate(`/cases/${caseId}/documents`),
                        }}
                    />
                </div>
            )}
            {filteredGraph && filteredGraph.nodes.length > 0 && (
                <ResizablePanelLayout
                    panelContent={
                        selectedNode ? (
                            <EntityProfilePanel
                                caseId={caseId!}
                                node={selectedNode}
                                edges={graph?.edges ?? []}
                                allNodes={graph?.nodes ?? []}
                                onClose={() => setSelectedNode(null)}
                            />
                        ) : null
                    }
                    panelOpen={!!selectedNode}
                    panelWidth={360}
                    onPanelClose={() => setSelectedNode(null)}
                >
                    <div className={styles.graphContainer}>
                        <EntityGraph
                            nodes={filteredGraph.nodes}
                            edges={filteredGraph.edges}
                            stats={filteredGraph.stats}
                            onNodeClick={handleNodeClick}
                            selectedNodeId={selectedNode?.id}
                        />
                    </div>
                </ResizablePanelLayout>
            )}

            {/* ── Row 2.5: Timeline (below graph, synced) ── */}
            {graph && graph.timeline_events.length > 0 && (
                <TimelineView
                    events={graph.timeline_events}
                    onBrushChange={handleBrushChange}
                    onEventClick={handleTimelineEventClick}
                    highlightEntityId={selectedNode?.id}
                />
            )}
            {graph && graph.timeline_events.length === 0 && (
                <EmptyState
                    icon="📅"
                    title="No events to display"
                    detail="Upload documents to build a timeline. Events are created from document dates, signals, financial records, and property transactions."
                />
            )}

            {/* ── Row 3: Dashboard Cards Grid ── */}
            <div className={styles.overviewGrid}>
                {/* ── Signal Severity Breakdown ── */}
                <section className={styles.overviewCard}>
                    <h3>Signal Severity</h3>
                    <div className="severity-bars">
                        {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((sev) => {
                            const count = d.signals.by_severity[sev] ?? 0;
                            const maxCount = Math.max(
                                ...Object.values(d.signals.by_severity).map(Number),
                                1,
                            );
                            return (
                                <div key={sev} className="severity-bar-row">
                                    <span className="severity-bar-label">{sev}</span>
                                    <div className="severity-bar-track">
                                        <div
                                            className="severity-bar-fill"
                                            style={{
                                                width: `${(count / maxCount) * 100}%`,
                                                backgroundColor: SEV_COLORS[sev],
                                            }}
                                        />
                                    </div>
                                    <span className="severity-bar-count">{count}</span>
                                </div>
                            );
                        })}
                    </div>
                </section>

                {/* ── Top Triggered Rules ── */}
                <section className={styles.overviewCard}>
                    <h3>Top Signal Rules</h3>
                    {d.signals.top_rules.length === 0 ? (
                        <p className={styles.overviewEmpty}>No signals detected yet.</p>
                    ) : (
                        <ul className={styles.topRulesList}>
                            {d.signals.top_rules.slice(0, 7).map((r) => (
                                <li key={r.rule_id} className={styles.topRuleItem}>
                                    <span className={styles.topRuleId}>{r.rule_id}</span>
                                    <span className={styles.topRuleSummary}>{r.summary}</span>
                                    <span className={styles.topRuleCount}>{r.count}</span>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                {/* ── Pipeline Health ── */}
                <section className={styles.overviewCard}>
                    <h3>Pipeline Health</h3>
                    <div className={styles.pipelineStats}>
                        <div className={styles.pipelineStat}>
                            <span className={styles.pipelineStatValue}>
                                {formatPercent(d.pipeline.extraction_success_rate)}
                            </span>
                            <span className={styles.pipelineStatLabel}>Extraction Success</span>
                        </div>
                        <div className={styles.pipelineStat}>
                            <span className={styles.pipelineStatValue}>
                                {d.pipeline.ai_enhanced_count}
                            </span>
                            <span className={styles.pipelineStatLabel}>AI Enhanced</span>
                        </div>
                        <div className={styles.pipelineStat}>
                            <span className={styles.pipelineStatValue}>
                                {d.documents.renamed_count}/{d.documents.total}
                            </span>
                            <span className={styles.pipelineStatLabel}>Auto-Renamed</span>
                        </div>
                    </div>
                    {/* Document type breakdown */}
                    <div className={styles.docTypeBreakdown}>
                        {Object.entries(d.documents.by_type)
                            .sort(([, a], [, b]) => (b as number) - (a as number))
                            .map(([type, count]) => (
                                <span key={type} className={styles.docTypePill}>
                                    {type}: {count as number}
                                </span>
                            ))}
                    </div>
                </section>

                {/* ── Financial Overview ── */}
                {d.financials.years_covered > 0 && (
                    <section className={styles.overviewCard}>
                        <h3>Financial Overview ({d.financials.years_covered} years)</h3>
                        <div className={styles.financialSummary}>
                            <div className={styles.financialKpi}>
                                <span className={styles.financialValue}>
                                    {formatCurrency(d.financials.total_revenue)}
                                </span>
                                <span className={styles.financialLabel}>Total Revenue</span>
                            </div>
                            <div className={styles.financialKpi}>
                                <span className={styles.financialValue}>
                                    {formatCurrency(d.financials.total_expenses)}
                                </span>
                                <span className={styles.financialLabel}>Total Expenses</span>
                            </div>
                        </div>
                        {d.financials.timeline.length > 0 && (
                            <div className={styles.financialTimeline}>
                                {d.financials.timeline.map((y) => (
                                    <div key={y.year} className={styles.timelineYear}>
                                        <span className={styles.timelineYearLabel}>{y.year}</span>
                                        <span className={styles.timelineYearRev}>
                                            {formatCurrency(y.revenue)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>
                )}

                {/* ── Coverage Audit ── */}
                {c && (
                    <section className={`${styles.overviewCard} ${styles.overviewCardWide}`}>
                        <h3>
                            Signal Coverage
                            <span
                                className={styles.coverageScore}
                                style={{
                                    color:
                                        c.coverage_score >= 0.8
                                            ? "#22c55e"
                                            : c.coverage_score >= 0.5
                                              ? "#f97316"
                                              : "#ef4444",
                                }}
                            >
                                {formatPercent(c.coverage_score)}
                            </span>
                        </h3>
                        <p className={styles.coverageSummary}>
                            {c.active_rules} of {c.total_rules} signal rules active.{" "}
                            {c.blind_rules > 0 &&
                                `${c.blind_rules} rules cannot run due to missing data.`}
                        </p>
                        {c.gaps.length > 0 && (
                            <ul className={styles.coverageGaps}>
                                {c.gaps.map((gap, i) => (
                                    <li key={i} className={styles.coverageGapItem}>
                                        <span
                                            className={styles.gapTypeBadge}
                                            style={{
                                                backgroundColor:
                                                    GAP_TYPE_COLORS[gap.gap_type] ?? "#94a3b8",
                                            }}
                                        >
                                            {GAP_TYPE_LABELS[gap.gap_type] ?? gap.gap_type}
                                        </span>
                                        <span className={styles.gapRule}>{gap.rule_id}</span>
                                        <span className={styles.gapMessage}>{gap.message}</span>
                                        <span className={styles.gapRecommendation}>
                                            {gap.recommendation}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>
                )}
            </div>
        </div>
    );
}
