import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchEntities, isAbortError } from "../api";
import { EntityItem, EntityType } from "../types";
import { EmptyState } from "../components/ui/EmptyState";
import { formatDate } from "../utils/format";
import styles from "./EntityBrowserView.module.css";

const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
    person: "Person",
    organization: "Organization",
    property: "Property",
    financial_instrument: "Financial Instrument",
};

const ENTITY_TYPES: EntityType[] = ["person", "organization", "property", "financial_instrument"];

const TYPE_ICONS: Record<EntityType, string> = {
    person: "\u{1F464}",
    organization: "\u{1F3E2}",
    property: "\u{1F3E0}",
    financial_instrument: "\u{1F4B3}",
};

export function EntityBrowserView() {
    const navigate = useNavigate();
    const [entities, setEntities] = useState<EntityItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [typeFilter, setTypeFilter] = useState("all");
    const [searchQuery, setSearchQuery] = useState("");
    const debounceRef = useRef<ReturnType<typeof setTimeout>>();

    const load = useCallback(async (signal: AbortSignal, type: string, q: string) => {
        setLoading(true);
        try {
            const filters: { type?: string; q?: string } = {};
            if (type !== "all") filters.type = type;
            if (q.trim()) filters.q = q.trim();
            const res = await fetchEntities(filters, 200, 0, { signal });
            if (!signal.aborted) setEntities(res.results);
        } catch (err) {
            if (!isAbortError(err)) console.error(err);
        } finally {
            if (!signal.aborted) setLoading(false);
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        // Debounce search
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            void load(controller.signal, typeFilter, searchQuery);
        }, searchQuery ? 300 : 0);
        return () => {
            controller.abort();
            if (debounceRef.current) clearTimeout(debounceRef.current);
        };
    }, [load, typeFilter, searchQuery]);

    /* Type counts */
    const typeCounts: Record<string, number> = {};
    for (const e of entities) {
        typeCounts[e.entity_type] = (typeCounts[e.entity_type] || 0) + 1;
    }

    return (
        <>
            <div className={styles.entityBrowserHeader}>
                <h2>Entities</h2>
                <span className={styles.referralCount}>{entities.length} found</span>
            </div>

            {/* Type pills */}
            <div className={styles.entityTypePills}>
                <button
                    className={`${styles.typePill} ${typeFilter === "all" ? styles.typePillActive : ""}`}
                    onClick={() => setTypeFilter("all")}
                >
                    All ({entities.length})
                </button>
                {ENTITY_TYPES.map((t) => (
                    <button
                        key={t}
                        className={`${styles.typePill} ${typeFilter === t ? styles.typePillActive : ""}`}
                        onClick={() => setTypeFilter(typeFilter === t ? "all" : t)}
                    >
                        {TYPE_ICONS[t]} {ENTITY_TYPE_LABELS[t]} ({typeCounts[t] || 0})
                    </button>
                ))}
            </div>

            <div className={styles.entityBrowserFilters}>
                <input
                    type="search"
                    placeholder="Search entities by name..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className={`form-input ${styles.entityBrowserFiltersInput}`}
                />
            </div>

            {loading ? (
                <p className={styles.loadingHint}>Loading entities...</p>
            ) : entities.length === 0 ? (
                <EmptyState
                    title="No entities found."
                    detail="Entities are created when documents are processed and entity extraction runs."
                />
            ) : (
                <div className={styles.casesTableWrap}>
                    <table className={styles.casesTable}>
                        <thead>
                            <tr>
                                <th>Type</th>
                                <th>Name</th>
                                <th>Case</th>
                                <th>Details</th>
                                <th>Created</th>
                            </tr>
                        </thead>
                        <tbody>
                            {entities.map((e) => (
                                <tr
                                    key={`${e.entity_type}-${e.id}`}
                                    className={styles.casesTableRow}
                                    onClick={() => navigate(`/entities/${e.entity_type}/${e.id}`)}
                                    style={{ cursor: "pointer" }}
                                >
                                    <td>
                                        <span className={styles.entityTypeBadge}>
                                            {TYPE_ICONS[e.entity_type]} {ENTITY_TYPE_LABELS[e.entity_type]}
                                        </span>
                                    </td>
                                    <td><strong>{e.name}</strong></td>
                                    <td>
                                        <button
                                            className={styles.triageCaseLink}
                                            onClick={(ev) => {
                                                ev.stopPropagation();
                                                navigate(`/cases/${e.case_id}`);
                                            }}
                                        >
                                            {e.case_name}
                                        </button>
                                    </td>
                                    <td className={styles.entityDetailCell}>
                                        {e.entity_type === "person" && e.role_tags && e.role_tags.length > 0 && (
                                            <span className={styles.entityTags}>{e.role_tags.join(", ")}</span>
                                        )}
                                        {e.entity_type === "organization" && e.org_type && (
                                            <span className={styles.entityTags}>{e.org_type}{e.ein ? ` \u00B7 EIN: ${e.ein}` : ""}</span>
                                        )}
                                        {e.entity_type === "property" && (
                                            <span className={styles.entityTags}>{e.county || ""}{e.parcel_number ? ` \u00B7 ${e.parcel_number}` : ""}</span>
                                        )}
                                        {e.entity_type === "financial_instrument" && (
                                            <span className={styles.entityTags}>{e.instrument_type}{e.filing_number ? ` \u00B7 ${e.filing_number}` : ""}</span>
                                        )}
                                    </td>
                                    <td className={styles.timeCell}>{formatDate(e.created_at)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </>
    );
}
