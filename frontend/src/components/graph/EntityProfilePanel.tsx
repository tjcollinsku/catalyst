import type { GraphNode, GraphEdge, GraphNodeType } from "../../types";
import { SlidePanel, SlidePanelSection } from "../ui/SlidePanel";
import { AISummaryBadge } from "../ai/AISummaryBadge";
import styles from "./EntityProfilePanel.module.css";

/* ── Type icon map ───────────────────────────────────────── */

const TYPE_ICON: Record<GraphNodeType, string> = {
    person: "\uD83D\uDC64",       // 👤
    organization: "\uD83C\uDFE2", // 🏢
    property: "\uD83C\uDFE0",     // 🏠
    financial_instrument: "\uD83D\uDCB3", // 💳
};

const TYPE_CLASS: Record<GraphNodeType, string> = {
    person: styles.typePerson,
    organization: styles.typeOrg,
    property: styles.typeProperty,
    financial_instrument: styles.typeFinancial,
};

const NODE_COLOR_VAR: Record<GraphNodeType, string> = {
    person: "var(--graph-node-person)",
    organization: "var(--graph-node-org)",
    property: "var(--graph-node-property)",
    financial_instrument: "var(--graph-node-financial)",
};

/* ── Props ────────────────────────────────────────────────── */

interface EntityProfilePanelProps {
    caseId: string;
    node: GraphNode;
    edges: GraphEdge[];
    allNodes: GraphNode[];
    onClose: () => void;
}

/* ── Component ───────────────────────────────────────────── */

export function EntityProfilePanel({
    caseId,
    node,
    edges,
    allNodes,
    onClose,
}: EntityProfilePanelProps) {
    const { type, label, metadata } = node;

    // Find edges connected to this node
    const connectedEdges = edges.filter(
        (e) => e.source === node.id || e.target === node.id
    );

    // Build connected entities list
    const nodeMap = new Map(allNodes.map((n) => [n.id, n]));
    const connections = connectedEdges.map((e) => {
        const otherId = e.source === node.id ? e.target : e.source;
        const otherNode = nodeMap.get(otherId);
        return {
            id: otherId,
            label: otherNode?.label ?? otherId.slice(0, 8),
            type: otherNode?.type ?? ("unknown" as GraphNodeType),
            relationship: e.label,
        };
    });

    // De-duplicate connections (same entity may have multiple edges)
    const uniqueConnections = Array.from(
        new Map(connections.map((c) => [c.id, c])).values()
    );

    return (
        <SlidePanel
            title={label}
            subtitle={type.replace("_", " ")}
            onClose={onClose}
        >
            {/* ── Header with icon ──────────────────────────────── */}
            <div className={styles.header}>
                <div className={`${styles.typeIcon} ${TYPE_CLASS[type]}`}>
                    {TYPE_ICON[type]}
                </div>
                <div className={styles.headerInfo}>
                    <h3 className={styles.entityName}>{label}</h3>
                    <span className={styles.entityType}>{type.replace("_", " ")}</span>
                </div>
            </div>

            {/* ── Stat pills ────────────────────────────────────── */}
            <div className={styles.statRow}>
                {metadata.finding_count > 0 && (
                    <span className={`${styles.statPill} ${styles.statPillDanger}`}>
                        {metadata.finding_count} finding{metadata.finding_count > 1 ? "s" : ""}
                    </span>
                )}
                {metadata.doc_count > 0 && (
                    <span className={styles.statPill}>
                        {metadata.doc_count} document{metadata.doc_count > 1 ? "s" : ""}
                    </span>
                )}
            </div>

            {/* ── AI summary ────────────────────────────────────── */}
            <div className={styles.aiRow}>
                <AISummaryBadge
                    caseId={caseId}
                    targetType="entity"
                    targetId={node.id}
                />
            </div>

            {/* ── Type-specific metadata ────────────────────────── */}
            <SlidePanelSection title="Details" defaultOpen>
                <div className={styles.fieldGrid}>
                    {type === "person" && (
                        <>
                            {metadata.aliases && metadata.aliases.length > 0 && (
                                <>
                                    <span className={styles.fieldLabel}>Aliases</span>
                                    <span className={styles.fieldValue}>
                                        {metadata.aliases.join(", ")}
                                    </span>
                                </>
                            )}
                            {metadata.date_of_death && (
                                <>
                                    <span className={styles.fieldLabel}>Deceased</span>
                                    <span className={styles.fieldValue}>
                                        {metadata.date_of_death}
                                    </span>
                                </>
                            )}
                        </>
                    )}
                    {type === "organization" && (
                        <>
                            {metadata.org_type && (
                                <>
                                    <span className={styles.fieldLabel}>Type</span>
                                    <span className={styles.fieldValue}>{metadata.org_type}</span>
                                </>
                            )}
                            {metadata.ein && (
                                <>
                                    <span className={styles.fieldLabel}>EIN</span>
                                    <span className={styles.fieldValue}>{metadata.ein}</span>
                                </>
                            )}
                            {metadata.status && (
                                <>
                                    <span className={styles.fieldLabel}>Status</span>
                                    <span className={styles.fieldValue}>{metadata.status}</span>
                                </>
                            )}
                        </>
                    )}
                    {type === "property" && (
                        <>
                            {metadata.parcel_number && (
                                <>
                                    <span className={styles.fieldLabel}>Parcel</span>
                                    <span className={styles.fieldValue}>
                                        {metadata.parcel_number}
                                    </span>
                                </>
                            )}
                            {metadata.county && (
                                <>
                                    <span className={styles.fieldLabel}>County</span>
                                    <span className={styles.fieldValue}>{metadata.county}</span>
                                </>
                            )}
                            {metadata.assessed_value && (
                                <>
                                    <span className={styles.fieldLabel}>Assessed</span>
                                    <span className={styles.fieldValue}>
                                        ${Number(metadata.assessed_value).toLocaleString()}
                                    </span>
                                </>
                            )}
                            {metadata.purchase_price && (
                                <>
                                    <span className={styles.fieldLabel}>Purchase</span>
                                    <span className={styles.fieldValue}>
                                        ${Number(metadata.purchase_price).toLocaleString()}
                                    </span>
                                </>
                            )}
                        </>
                    )}
                    {type === "financial_instrument" && (
                        <>
                            {metadata.instrument_type && (
                                <>
                                    <span className={styles.fieldLabel}>Type</span>
                                    <span className={styles.fieldValue}>
                                        {metadata.instrument_type}
                                    </span>
                                </>
                            )}
                            {metadata.filing_number && (
                                <>
                                    <span className={styles.fieldLabel}>Filing #</span>
                                    <span className={styles.fieldValue}>
                                        {metadata.filing_number}
                                    </span>
                                </>
                            )}
                            {metadata.filing_date && (
                                <>
                                    <span className={styles.fieldLabel}>Filed</span>
                                    <span className={styles.fieldValue}>
                                        {metadata.filing_date}
                                    </span>
                                </>
                            )}
                            {metadata.amount && (
                                <>
                                    <span className={styles.fieldLabel}>Amount</span>
                                    <span className={styles.fieldValue}>
                                        ${Number(metadata.amount).toLocaleString()}
                                    </span>
                                </>
                            )}
                        </>
                    )}
                </div>
            </SlidePanelSection>

            {/* ── Role tags (persons) ───────────────────────────── */}
            {type === "person" && metadata.role_tags && metadata.role_tags.length > 0 && (
                <SlidePanelSection title="Roles" defaultOpen count={metadata.role_tags.length}>
                    <div className={styles.tags}>
                        {metadata.role_tags.map((tag) => (
                            <span key={tag} className={styles.tag}>
                                {tag.replace(/_/g, " ")}
                            </span>
                        ))}
                    </div>
                </SlidePanelSection>
            )}

            {/* ── Connected entities ────────────────────────────── */}
            {uniqueConnections.length > 0 && (
                <SlidePanelSection
                    title="Connections"
                    defaultOpen
                    count={uniqueConnections.length}
                >
                    <ul className={styles.connectionList}>
                        {uniqueConnections.map((conn) => (
                            <li key={conn.id} className={styles.connectionItem}>
                                <span
                                    className={styles.connectionDot}
                                    style={{
                                        background:
                                            NODE_COLOR_VAR[conn.type] ?? "var(--text-soft)",
                                    }}
                                />
                                <span className={styles.connectionLabel}>{conn.label}</span>
                                <span className={styles.connectionRelation}>
                                    {conn.relationship}
                                </span>
                            </li>
                        ))}
                    </ul>
                </SlidePanelSection>
            )}
        </SlidePanel>
    );
}
