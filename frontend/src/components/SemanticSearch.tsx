import { useState } from "react";
import { Button } from "./ui/Button";
import { FormInput } from "./ui/FormInput";
import styles from "./SemanticSearch.module.css";

interface SemanticSearchProps {
    selectedCaseId: string | null;
}

export function SemanticSearch({ selectedCaseId }: SemanticSearchProps) {
    const [query, setQuery] = useState("");
    const [scopeToCase, setScopeToCase] = useState(true);
    const [results, setResults] = useState<unknown[]>([]);
    const [searching, setSearching] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleSearch() {
        if (!query.trim()) return;
        setSearching(true);
        setError(null);
        try {
            const params = new URLSearchParams({ q: query.trim() });
            if (scopeToCase && selectedCaseId) {
                params.set("case_id", selectedCaseId);
            }
            const response = await fetch(`/api/semantic/search/?${params.toString()}`, {
                headers: { Accept: "application/json" },
            });
            if (!response.ok) {
                throw new Error(`Search failed (${response.status})`);
            }
            const data = await response.json();
            setResults(data.results ?? []);
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setSearching(false);
        }
    }

    return (
        <div className={styles.semanticSearchBar}>
            <div className={styles.semanticSearchRow}>
                <FormInput
                    className={styles.semanticSearchInput}
                    placeholder="Semantic search across documents..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter") {
                            void handleSearch();
                        }
                    }}
                />
                <Button
                    variant="primary"
                    disabled={searching || !query.trim()}
                    onClick={() => { void handleSearch(); }}
                >
                    {searching ? "Searching..." : "Search"}
                </Button>
                <label className={styles.semanticScopeToggle}>
                    <input
                        type="checkbox"
                        checked={scopeToCase}
                        onChange={(e) => setScopeToCase(e.target.checked)}
                    />
                    Scope to case
                </label>
            </div>
            {error && <div className={styles.semanticError}>{error}</div>}
            {!error && results.length === 0 && query.trim() && !searching && (
                <p className={styles.semanticEmpty}>No results found.</p>
            )}
            {results.length > 0 && (
                <div className={styles.semanticResults}>
                    {results.map((result, index) => {
                        const r = result as Record<string, unknown>;
                        return (
                            <div key={index} className="info-card" style={{ marginBottom: "0.5rem" }}>
                                <strong>{String(r.filename ?? r.document_id ?? `Result ${index + 1}`)}</strong>
                                <p style={{ fontSize: "0.85rem", color: "var(--text-soft)" }}>
                                    {String(r.snippet ?? r.text ?? "")}
                                </p>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
