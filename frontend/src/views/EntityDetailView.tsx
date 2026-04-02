import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchEntities, isAbortError } from "../api";
import { EntityItem, EntityType } from "../types";
import { EmptyState } from "../components/ui/EmptyState";
import { formatDate } from "../utils/format";
import { loadLaunchers, buildSearchUrl } from "../data/externalSearchLaunchers";
import styles from "./EntityDetailView.module.css";

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
    const [loading, setLoading] = useState(true);

    const load = useCallback(async (signal: AbortSignal) => {
        if (!entityType || !entityId) return;
        setLoading(true);
        try {
            // Fetch entities of this type and find the matching one
            const res = await fetchEntities({ type: entityType }, 200, 0, { signal });
            if (!signal.aborted) {
                const match = res.results.find((e) => e.id === entityId) ?? null;
                setEntity(match);
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
