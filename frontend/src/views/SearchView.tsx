import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import styles from "./SearchView.module.css";
import { fetchCases, fetchCrossCaseSignals, fetchEntities, isAbortError } from "../api";
import { CrossCaseSignal, SearchResultType } from "../types";
import { EmptyState } from "../components/ui/EmptyState";
import { formatDate } from "../utils/format";

/*
 * SearchView — Phase D
 *
 * Client-side search across cases, signals, and entities.
 * When the backend /api/search/ endpoint is ready, this can be
 * swapped to a single API call. For now, we fan out to existing
 * endpoints and merge results with a basic relevance score.
 */

interface MergedResult {
    type: SearchResultType;
    id: string;
    title: string;
    subtitle: string;
    snippet: string;
    relevance: number;
    case_id: string | null;
    case_name: string | null;
    route: string;
}

const TYPE_ICONS: Record<SearchResultType, string> = {
    case: "\uD83D\uDCC1",
    signal: "\u26A1",
    entity: "\uD83D\uDC64",
    document: "\uD83D\uDCC4",
    detection: "\uD83D\uDD0D",
};

const TYPE_LABELS: Record<SearchResultType, string> = {
    case: "Case",
    signal: "Signal",
    entity: "Entity",
    document: "Document",
    detection: "Detection",
};

function scoreTerm(text: string, terms: string[]): number {
    const lower = text.toLowerCase();
    let score = 0;
    for (const t of terms) {
        if (lower.includes(t)) score += 1;
    }
    return score;
}

function highlightSnippet(text: string, terms: string[]): string {
    if (!text || terms.length === 0) return text;
    // Find first matching position and extract surrounding text
    const lower = text.toLowerCase();
    for (const t of terms) {
        const idx = lower.indexOf(t);
        if (idx >= 0) {
            const start = Math.max(0, idx - 40);
            const end = Math.min(text.length, idx + t.length + 80);
            const prefix = start > 0 ? "..." : "";
            const suffix = end < text.length ? "..." : "";
            return prefix + text.slice(start, end) + suffix;
        }
    }
    return text.length > 120 ? text.slice(0, 120) + "..." : text;
}

export function SearchView() {
    const [searchParams, setSearchParams] = useSearchParams();
    const navigate = useNavigate();
    const query = searchParams.get("q") ?? "";
    const typeFilter = searchParams.get("type") ?? "all";

    const [inputValue, setInputValue] = useState(query);
    const [results, setResults] = useState<MergedResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [searchedQuery, setSearchedQuery] = useState("");

    const runSearch = useCallback(
        async (q: string, signal: AbortSignal) => {
            if (!q.trim()) {
                setResults([]);
                setSearchedQuery("");
                return;
            }

            setLoading(true);
            const terms = q.toLowerCase().split(/\s+/).filter(Boolean);

            try {
                // Fan out to existing endpoints
                const [casesRes, signalsRes, entitiesRes] = await Promise.all([
                    fetchCases(100, 0, { signal }),
                    fetchCrossCaseSignals({}, 200, 0, { signal }),
                    fetchEntities({}, 200, 0, { signal }),
                ]);

                if (signal.aborted) return;

                const merged: MergedResult[] = [];

                // Score cases
                for (const c of casesRes.results) {
                    const score =
                        scoreTerm(c.name, terms) * 3 +
                        scoreTerm(c.notes ?? "", terms) +
                        scoreTerm(c.referral_ref ?? "", terms);
                    if (score > 0) {
                        merged.push({
                            type: "case",
                            id: c.id,
                            title: c.name,
                            subtitle: `${c.status} \u00B7 ${formatDate(c.created_at)}`,
                            snippet: highlightSnippet(c.notes || "No description", terms),
                            relevance: score,
                            case_id: c.id,
                            case_name: c.name,
                            route: `/cases/${c.id}`,
                        });
                    }
                }

                // Score signals
                for (const s of signalsRes.results) {
                    const score =
                        scoreTerm(s.title, terms) * 3 +
                        scoreTerm(s.description, terms) * 2 +
                        scoreTerm(s.rule_id, terms) +
                        scoreTerm(s.detected_summary ?? "", terms) +
                        scoreTerm(s.investigator_note ?? "", terms);
                    if (score > 0) {
                        merged.push({
                            type: "signal",
                            id: s.id,
                            title: s.title,
                            subtitle: `${s.rule_id} \u00B7 ${s.severity} \u00B7 ${s.status}`,
                            snippet: highlightSnippet(
                                s.description || s.detected_summary || "",
                                terms,
                            ),
                            relevance: score,
                            case_id: (s as CrossCaseSignal).case_id ?? null,
                            case_name: (s as CrossCaseSignal).case_name ?? null,
                            route: (s as CrossCaseSignal).case_id
                                ? `/cases/${(s as CrossCaseSignal).case_id}/signals`
                                : "/triage",
                        });
                    }
                }

                // Score entities
                for (const e of entitiesRes.results) {
                    const score =
                        scoreTerm(e.name, terms) * 4 +
                        scoreTerm(e.notes ?? "", terms) +
                        scoreTerm(e.entity_type, terms);
                    if (score > 0) {
                        merged.push({
                            type: "entity",
                            id: e.id,
                            title: e.name,
                            subtitle: `${e.entity_type} \u00B7 ${e.case_name}`,
                            snippet: highlightSnippet(e.notes || `${e.entity_type} entity`, terms),
                            relevance: score,
                            case_id: e.case_id,
                            case_name: e.case_name,
                            route: `/entities/${e.entity_type}/${e.id}`,
                        });
                    }
                }

                // Sort by relevance descending
                merged.sort((a, b) => b.relevance - a.relevance);

                setResults(merged);
                setSearchedQuery(q);
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

    // Build AI overview (client-side summary of top results)
    const aiOverview = useMemo(() => {
        if (!searchedQuery || results.length === 0) return null;

        const topResults = results.slice(0, 5);
        const caseNames = [...new Set(results.map((r) => r.case_name).filter(Boolean))];
        const typeBreakdown = Object.entries(typeCounts)
            .filter(([k]) => k !== "all")
            .map(([k, v]) => `${v} ${TYPE_LABELS[k as SearchResultType] || k}${v > 1 ? "s" : ""}`)
            .join(", ");

        const overview = `Found ${results.length} results (${typeBreakdown}) across ${caseNames.length} case${caseNames.length !== 1 ? "s" : ""}. ` +
            `Top match: "${topResults[0].title}" (${TYPE_LABELS[topResults[0].type]})` +
            (topResults[0].case_name ? ` in ${topResults[0].case_name}.` : ".");

        return overview;
    }, [searchedQuery, results, typeCounts]);

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
                    {(["all", "case", "signal", "entity"] as const).map((t) => (
                        <button
                            key={t}
                            className={`${styles.typePill} ${typeFilter === t ? styles.active : ""}`}
                            onClick={() => handleTypeChange(t)}
                        >
                            {t === "all" ? "All" : `${TYPE_ICONS[t]} ${TYPE_LABELS[t]}`} (
                            {typeCounts[t] || 0})
                        </button>
                    ))}
                </div>
            )}

            {/* AI Overview */}
            {aiOverview && (
                <div className={styles.aiOverviewCard}>
                    <div className={styles.aiOverviewHeader}>
                        <span className={styles.aiOverviewIcon}>{"\uD83E\uDD16"}</span>
                        <strong>AI Overview</strong>
                    </div>
                    <p className={styles.aiOverviewBody}>{aiOverview}</p>
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
                                    {TYPE_ICONS[result.type]}
                                </span>
                            </div>
                            <div className={styles.searchResultContent}>
                                <div className={styles.searchResultTitle}>
                                    <strong>{result.title}</strong>
                                    <span className={styles.searchResultTypeBadge}>
                                        {TYPE_LABELS[result.type]}
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
                                {(result.relevance * 0.15).toFixed(2)}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </>
    );
}
