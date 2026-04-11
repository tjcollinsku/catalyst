import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchEntityDetail, isAbortError } from "../api";
import { EntityItem, EntityType } from "../types";
import { EmptyState } from "../components/ui/EmptyState";
import { StickyNotes } from "../components/ui/StickyNotes";
import { formatDate } from "../utils/format";
import { loadLaunchers, buildSearchUrl } from "../data/externalSearchLaunchers";
import styles from "./EntityDetailView.module.css";

interface RelatedDocument {
    id: string;
    filename: string;
    doc_type: string;
    page_reference?: string;
    context_note?: string;
}

interface RelatedFinding {
    id: string;
    title: string;
    severity: string;
    status: string;
    context_note: string | undefined;
}

const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
    person: "Person",
    organization: "Organization",
    property: "Property",
    financial_instrument: "Financial Instrument",
};

const TYPE_ICONS: Record<EntityType, string> = {
    person: "\u{1F464}",
    organization: "\u{1F3E2}",
    property: "\u{1F3E0}",
    financial_instrument: "\u{1F4B3}",
};

export function EntityDetailView() {
    const { entityType, entityId } = useParams<{ entityType: string; entityId: string }>();
    const navigate = useNavigate();
    const [entity, setEntity] = useState<EntityItem | null>(null);
    const [relatedDocuments, setRelatedDocuments] = useState<RelatedDocument[]>([]);
    const [relatedFindings, setRelatedFindings] = useState<RelatedFinding[]>([]);
    const [loading, setLoading] = useState(true);

    const load = useCallback(async (signal: AbortSignal) => {
        if (!entityType || !entityId) return;
        setLoading(true);
        try {
            const data = await fetchEntityDetail(entityType, entityId, { signal });
            if (!signal.aborted) {
                // Map the response to EntityItem (ensure required fields exist)
                const entityData: EntityItem = {
                    id: String(data.id),
                    entity_type: (data.entity_type || entityType) as EntityType,
                    name: String(data.name || ""),
                    case_id: String(data.case_id || ""),
                    case_name: String(data.case_name || ""),
                    notes: String(data.notes || ""),
                    created_at: String(data.created_at || ""),
                    updated_at: String(data.updated_at || ""),
                    // Spread any other fields that exist
                    ...data,
                };
                setEntity(entityData);

                // Extract related documents if available
                const docs = (data.related_documents as RelatedDocument[] | undefined) || [];
                setRelatedDocuments(docs);

                // Extract related findings if available
                const findings = (data.related_findings as RelatedFinding[] | undefined) || [];
                setRelatedFindings(findings);
            }
        } catch (err) {
            if (!isAbortError(err)) console.error(err);
        } finally {
            if (!signal.aborted) setLoading(false);
        }
    }, [entityType, entityId]);

    useEffect(() => {
        const controller = new AbortController();
        void load(controller.signal);
        return () => controller.abort();
    }, [load]);

    if (loading) {
        return <p className={styles.loadingHint}>Loading entity...</p>;
    }

    if (!entity) {
        return (
            <EmptyState
                title="Entity not found."
                detail="The entity may have been deleted or the ID is invalid."
            />
        );
    }

    const validType = entity.entity_type as EntityType;
    const launchers = loadLaunchers();

    return (
        <>
            {/* Header */}
            <div className={styles.entityDetailHeader}>
                <button className={styles.backLink} onClick={() => navigate("/entities")}>
                    {"\u2190"} Entities
                </button>
                <div className={styles.entityDetailTitle}>
                    <span className={styles.entityIcon}>{TYPE_ICONS[validType]}</span>
                    <h2>{entity.name}</h2>
                    <span className={styles.entityTypeBadge}>{ENTITY_TYPE_LABELS[validType]}</span>
                </div>
                <div className={styles.entityDetailMeta}>
                    <span>
                        Case:{" "}
                        <button className={styles.triageCaseLink} onClick={() => navigate(`/cases/${entity.case_id}`)}>
                            {entity.case_name}
                        </button>
                    </span>
                    <span>Created: {formatDate(entity.created_at)}</span>
                    <span>Updated: {formatDate(entity.updated_at)}</span>
                </div>
            </div>

            {/* Entity-specific fields */}
            <div className={styles.entityDetailBody}>
                {validType === "person" && (
                    <section className={styles.infoCard}>
                        <h3>Person Details</h3>
                        <dl className={styles.entityFields}>
                            <dt>Full Name</dt>
                            <dd>{entity.name}</dd>
                            {entity.aliases && entity.aliases.length > 0 && (
                                <>
                                    <dt>Aliases</dt>
                                    <dd>{entity.aliases.join(", ")}</dd>
                                </>
                            )}
                            {entity.role_tags && entity.role_tags.length > 0 && (
                                <>
                                    <dt>Roles</dt>
                                    <dd>
                                        {entity.role_tags.map((tag) => (
                                            <span key={tag} className={styles.entityRoleTag}>{tag}</span>
                                        ))}
                                    </dd>
                                </>
                            )}
                            {entity.date_of_death && (
                                <>
                                    <dt>Date of Death</dt>
                                    <dd>{entity.date_of_death}</dd>
                                </>
                            )}
                        </dl>
                    </section>
                )}

                {validType === "organization" && (
                    <section className={styles.infoCard}>
                        <h3>Organization Details</h3>
                        <dl className={styles.entityFields}>
                            <dt>Name</dt>
                            <dd>{entity.name}</dd>
                            <dt>Type</dt>
                            <dd>{entity.org_type || "\u2014"}</dd>
                            <dt>EIN</dt>
                            <dd>{entity.ein || "\u2014"}</dd>
                            <dt>State</dt>
                            <dd>{entity.registration_state || "\u2014"}</dd>
                            <dt>Status</dt>
                            <dd>{entity.status || "\u2014"}</dd>
                            {entity.formation_date && (
                                <>
                                    <dt>Formed</dt>
                                    <dd>{entity.formation_date}</dd>
                                </>
                            )}
                        </dl>
                    </section>
                )}

                {validType === "property" && (
                    <section className={styles.infoCard}>
                        <h3>Property Details</h3>
                        <dl className={styles.entityFields}>
                            <dt>Address</dt>
                            <dd>{entity.address || "\u2014"}</dd>
                            <dt>Parcel #</dt>
                            <dd>{entity.parcel_number || "\u2014"}</dd>
                            <dt>County</dt>
                            <dd>{entity.county || "\u2014"}</dd>
                            <dt>Assessed Value</dt>
                            <dd>{entity.assessed_value ? `$${Number(entity.assessed_value).toLocaleString()}` : "\u2014"}</dd>
                            <dt>Purchase Price</dt>
                            <dd>{entity.purchase_price ? `$${Number(entity.purchase_price).toLocaleString()}` : "\u2014"}</dd>
                        </dl>
                    </section>
                )}

                {validType === "financial_instrument" && (
                    <section className={styles.infoCard}>
                        <h3>Financial Instrument Details</h3>
                        <dl className={styles.entityFields}>
                            <dt>Type</dt>
                            <dd>{entity.instrument_type || "\u2014"}</dd>
                            <dt>Filing #</dt>
                            <dd>{entity.filing_number || "\u2014"}</dd>
                            <dt>Filed</dt>
                            <dd>{entity.filing_date || "\u2014"}</dd>
                            <dt>Amount</dt>
                            <dd>{entity.amount ? `$${Number(entity.amount).toLocaleString()}` : "\u2014"}</dd>
                            {entity.anomaly_flags && entity.anomaly_flags.length > 0 && (
                                <>
                                    <dt>Anomaly Flags</dt>
                                    <dd>
                                        {entity.anomaly_flags.map((f) => (
                                            <span key={f} className={styles.entityRoleTag}>{f}</span>
                                        ))}
                                    </dd>
                                </>
                            )}
                        </dl>
                    </section>
                )}

                {/* Notes */}
                {entity.notes && (
                    <section className={styles.infoCard}>
                        <h3>Notes</h3>
                        <p>{entity.notes}</p>
                    </section>
                )}

                {/* Related Documents */}
                {relatedDocuments.length > 0 && (
                    <section className={styles.infoCard}>
                        <h3>{"\uD83D\uDCC4"} Related Documents ({relatedDocuments.length})</h3>
                        <div className={styles.documentList}>
                            {relatedDocuments.map((doc) => (
                                <div key={doc.id} className={styles.documentItem}>
                                    <button
                                        className={styles.documentLink}
                                        onClick={() => navigate(`/cases/${entity.case_id}`)}
                                        title="Navigate to case Documents tab"
                                    >
                                        <span className={styles.documentIcon}>{"\uD83D\uDCC4"}</span>
                                        <span className={styles.documentName}>{doc.filename}</span>
                                    </button>
                                    <span className={styles.documentType}>{doc.doc_type}</span>
                                    {doc.page_reference && (
                                        <span className={styles.pageRef}>{doc.page_reference}</span>
                                    )}
                                    {doc.context_note && (
                                        <p className={styles.contextNote}>{doc.context_note}</p>
                                    )}
                                </div>
                            ))}
                        </div>
                    </section>
                )}

                {/* Related Findings */}
                {relatedFindings.length > 0 && (
                    <section className={styles.infoCard}>
                        <h3>{"\u26A0\uFE0F"} Related Findings ({relatedFindings.length})</h3>
                        <div className={styles.findingsList}>
                            {relatedFindings.map((finding) => (
                                <button
                                    key={finding.id}
                                    className={styles.findingCard}
                                    onClick={() => navigate(`/cases/${entity.case_id}`)}
                                    title="Navigate to case Pipeline tab"
                                >
                                    <div className={styles.findingHeader}>
                                        <span className={styles.findingTitle}>{finding.title}</span>
                                        <span className={`${styles.severityBadge} ${styles[`severity${finding.severity}`]}`}>
                                            {finding.severity}
                                        </span>
                                    </div>
                                    <div className={styles.findingFooter}>
                                        <span className={styles.statusBadge}>{finding.status}</span>
                                        {finding.context_note && (
                                            <span className={styles.findingContext}>{finding.context_note}</span>
                                        )}
                                    </div>
                                </button>
                            ))}
                        </div>
                    </section>
                )}

                {/* Sticky Notes */}
                <section className={styles.infoCard}>
                    <h3>{"\uD83D\uDCDD"} Notes</h3>
                    {entityType && entityId && (
                        <StickyNotes
                            caseId={entity.case_id}
                            targetType={entityType}
                            targetId={entityId}
                        />
                    )}
                </section>

                {/* External search launchers */}
                <section className={styles.infoCard}>
                    <h3>{"\uD83D\uDD0E"} External Search</h3>
                    <p className={styles.externalSearchDesc}>
                        Open external databases in a new tab to search for &ldquo;{entity.name}&rdquo;.
                        Configure launchers in Settings.
                    </p>
                    <div className={styles.externalSearchGrid}>
                        {launchers.map((launcher) => (
                            <a
                                key={launcher.id}
                                href={buildSearchUrl(launcher.urlTemplate, entity.name)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className={styles.externalSearchBtn}
                            >
                                <span className={styles.externalSearchIcon}>{"\u2197"}</span>
                                {launcher.name}
                            </a>
                        ))}
                    </div>
                </section>
            </div>
        </>
    );
}
