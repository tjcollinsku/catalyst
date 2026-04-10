import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import styles from "./SearchView.module.css";
import { searchAll, isAbortError } from "../api";
import { SearchResult } from "../types";
import { EmptyState } from "../components/ui/EmptyState";

/*
 * SearchView — Phase D (updated to use backend /api/search/ endpoint)
 *
 * Full-text search across cases, signals, entities, and documents
 * using PostgreSQL full-text search with SearchVector / SearchQuery.
 */

const TYPE_ICONS: Record<string, string> = {
    case: "\uD83D\uDCC1",
    finding: "\u26A1",
    entity: "\uD83D\uDC64",
    document: "\uD83D\uDCC4",
};

const TYPE_LABELS: Record<string, string> = {
    case: "Case",
    finding: "Finding",
    entity: "Entity",
    document: "Document",
};

export function SearchView() {
    const [searchParams, setSearchParams] = useSearchParams();
    const navigate = useNavigate();
    const query = searchParams.get("q") ?? "";
    const typeFilter = searchParams.get("type") ?? "all";

    const [inputValue, setInputValue] = useState(query);
    const [results, setResults] = useState<SearchResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [searchedQuery, setSearchedQuery] = useState("");
    const [aiOverview, setAiOverview] = useState<string | null>(null);

    const runSearch = useCallback(
        async (q: string, signal: AbortSignal) => {
            if (!q.trim()) {
                setResults([]);
                setSearchedQuery("");
                setAiOverview(null);
                return;
            }

            setLoading(true);

            try {
                const response = await searchAll(q, {}, { signal });

                if (signal.aborted) return;

                setResults(response.results);
                setSearchedQuery(q);
                setAiOverview(response.ai_overview || null);
            } catch (err) {
                if (!isAbortError(err)) console.error("Search failed:", err);
            } finally {
                if (!signal.aborted) setLoading(false);
            }
        },
        [],
    );

    // Run search whenever the URL query param changes
    useEffect(() => {
        const controller = new AbortController();
        if (query) {
            void runSearch(query, controller.signal);
        } else {
            setResults([]);
            setSearchedQuery("");
            setAiOverview(null);
            setLoading(false);
        }
        return () => controller.abort();
    }, [query, runSearch]);

    // Keep local input in sync with URL
    useEffect(() => {
        setInputValue(query);
    }, [query]);

    function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        const trimmed = inputValue.trim();
        if (trimmed) {
            setSearchParams({ q: trimmed, ...(typeFilter !== "all" ? { type: typeFilter } : {}) });
        }
    }

    function handleTypeChange(newType: string) {
        const params: Record<string, string> = {};
        if (query) params.q = query;
        if (newType !== "all") params.type = newType;
        setSearchParams(params);
    }

    // Filter results by type if filter active
    const filteredResults = useMemo(() => {
        if (typeFilter === "all") return results;
        return results.filter((r) => r.type === typeFilter);
    }, [results, typeFilter]);

    // Count per type
    const typeCounts = useMemo(() => {
        const counts: Record<string, number> = { all: results.length };
        for (const r of results) {
            counts[r.type] = (counts[r.type] || 0) + 1;
        }
        return counts;
    }, [results]);

    // Build summary if backend didn't provide one
    const overviewText = useMemo(() => {
        if (aiOverview) return aiOverview;
        if (!searchedQuery || results.length === 0) return null;

        const caseNames = [...new Set(results.map((r) => r.case_name).filter(Boolean))];
        const typeBreakdown = Object.entries(typeCounts)
            .filter(([k]) => k !== "all")
            .map(([k, v]) => `${v} ${TYPE_LABELS[k] || k}${v > 1 ? "s" : ""}`)
            .join(", ");

        return `Found ${results.length} results (${typeBreakdown}) across ${caseNames.length} case${caseNames.length !== 1 ? "s" : ""}. ` +
            `Top match: "${results[0].title}" (${TYPE_LABELS[results[0].type] || results[0].type})` +
            (results[0].case_name ? ` in ${results[0].case_name}.` : ".");
    }, [aiOverview, searchedQuery, results, typeCounts]);

    return (
        <>
            {/* Search input */}
            <div className={styles.searchViewHeader}>
                <form onSubmit={handleSubmit} className={styles.searchViewForm}>
                    <span className={styles.searchIcon}>{"\uD83D\uDD0D"}</span>
                    <input
                        type="text"
                        className={styles.searchViewInput}
                        placeholder="Search cases, signals, entities..."
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        autoFocus
                    />
                    <button type="submit" className={styles.searchViewSubmit}>
                        Search
                    </button>
                </form>
            </div>

            {/* Results header */}
            {searchedQuery && (
                <div className={styles.searchResultsHeader}>
                    <h2>
                        Results for &ldquo;{searchedQuery}&rdquo;
                    </h2>
                    <span className={styles.referralCount}>
                        {filteredResults.length} of {results.length} results
                    </span>
                </div>
            )}

            {/* Type filter pills */}
            {searchedQuery && results.length > 0 && (
                <div className={styles.entityTypePills}>
                    {(["all", "case", "finding", "entity", "document"] as const).map((t) => (
                        <button
                            key={t}
                            className={`${styles.typePill} ${typeFilter === t ? styles.active : ""}`}
                            onClick={() => handleTypeChange(t)}
                        >
                            {t === "all" ? "All" : `${TYPE_ICONS[t] || ""} ${TYPE_LABELS[t] || t}`} (
                            {typeCounts[t] || 0})
                        </button>
                    ))}
                </div>
            )}

            {/* AI Overview */}
            {overviewText && (
                <div className={styles.aiOverviewCard}>
                    <div className={styles.aiOverviewHeader}>
                        <span className={styles.aiOverviewIcon}>{"\uD83E\uDD16"}</span>
                        <strong>AI Overview</strong>
                    </div>
                    <p className={styles.aiOverviewBody}>{overviewText}</p>
                </div>
            )}

            {/* Loading state */}
            {loading && <p className={styles.loadingHint}>Searching across all cases...</p>}

            {/* No query state */}
            {!searchedQuery && !loading && (
                <EmptyState
                    title="Search across your investigation data"
                    detail="Enter a query to search cases, signals, entities, and documents. Use the top bar search (Cmd+K) for quick access from any view."
                />
            )}

            {/* No results */}
            {searchedQuery && !loading && filteredResults.length === 0 && (
                <EmptyState
                    title="No results found"
                    detail={`No matches for "${searchedQuery}". Try different keywords or broaden your type filter.`}
                />
            )}

            {/* Results list */}
            {filteredResults.length > 0 && (
                <div className={styles.searchResultsList}>
                    {filteredResults.map((result) => (
                        <div
                            key={`${result.type}-${result.id}`}
                            className={styles.searchResultCard}
                            role="button"
                            tabIndex={0}
                            onClick={() => navigate(result.route)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") navigate(result.route);
                            }}
                        >
                            <div className={styles.searchResultLeft}>
                                <span className={styles.searchResultTypeIcon}>
                                    {TYPE_ICONS[result.type] || "\uD83D\uDD0D"}
                                </span>
                            </div>
                            <div className={styles.searchResultContent}>
                                <div className={styles.searchResultTitle}>
                                    <strong>{result.title}</strong>
                                    <span className={styles.searchResultTypeBadge}>
                                        {TYPE_LABELS[result.type] || result.type}
                                    </span>
                                </div>
                                <div className={styles.searchResultSubtitle}>{result.subtitle}</div>
                                <div className={styles.searchResultSnippet}>{result.snippet}</div>
                                {result.case_name && (
                                    <div className={styles.searchResultCase}>
                                        {"\uD83D\uDCC1"} {result.case_name}
                                    </div>
                                )}
                            </div>
                            <div className={styles.searchResultRelevance}>
                                {result.relevance.toFixed(2)}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </>
    );
}
