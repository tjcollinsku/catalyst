import { useState, useCallback } from "react";
import { useOutletContext } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import { ResearchResult, searchParcels, searchOhioSOS, searchOhioAOS, searchIRS, searchRecorder, addResearchToCase } from "../../api";
import styles from "./ResearchTab.module.css";

type SourceType = "parcels" | "ohio-sos" | "ohio-aos" | "irs" | "recorder";

interface SourceConfig {
    id: SourceType;
    label: string;
    description: string;
    placeholder: string;
    columns: string[];
}

const SOURCES: Record<SourceType, SourceConfig> = {
    parcels: {
        id: "parcels",
        label: "County Parcel Search",
        description: "Search property ownership records across Ohio counties",
        placeholder: "Owner name or parcel number",
        columns: ["PIN", "Owner", "County", "Acres", "Link", "Add"],
    },
    "ohio-sos": {
        id: "ohio-sos",
        label: "Ohio Secretary of State",
        description: "Search business entity registrations and filings",
        placeholder: "Entity name or number",
        columns: ["Charter #", "Business Name", "Status", "Filing Date", "County", "Add"],
    },
    "ohio-aos": {
        id: "ohio-aos",
        label: "Ohio Auditor of State",
        description: "Search audit reports and findings for recovery",
        placeholder: "Entity name",
        columns: ["Entity Name", "County", "Report Type", "Period", "Findings?", "Add"],
    },
    irs: {
        id: "irs",
        label: "IRS Tax-Exempt Search",
        description: "Search nonprofit organizations by EIN, name, or location",
        placeholder: "Organization name or EIN",
        columns: ["EIN", "Name", "City", "Status", "Ruling Date", "Assets", "Income", "Revoked?", "Add"],
    },
    recorder: {
        id: "recorder",
        label: "County Recorder (by county)",
        description: "Generate search URL for county recorder portals",
        placeholder: "Name (press Enter after selecting county)",
        columns: ["County", "Search URL", "Action"],
    },
};

export function ResearchTab() {
    const { caseId, pushToast } = useOutletContext<CaseDetailContext>();
    const [activeSource, setActiveSource] = useState<SourceType>("parcels");
    const [query, setQuery] = useState("");
    const [county, setCounty] = useState(""); // For recorder searches
    const [results, setResults] = useState<ResearchResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [addedRows, setAddedRows] = useState<Set<number>>(new Set());
    const [addingRow, setAddingRow] = useState<number | null>(null);

    const handleSearch = useCallback(async () => {
        if (!query.trim()) {
            pushToast("error", "Please enter a search query");
            return;
        }

        setLoading(true);
        setError(null);
        setResults(null);

        try {
            let result: ResearchResult;

            switch (activeSource) {
                case "parcels": {
                    const searchType = query.match(/^\d{4}-\d{4}-\d{4}$/) ? "parcel" : "owner";
                    result = await searchParcels(caseId, query, searchType, county);
                    break;
                }
                case "ohio-sos": {
                    result = await searchOhioSOS(caseId, query);
                    break;
                }
                case "ohio-aos": {
                    result = await searchOhioAOS(caseId, query);
                    break;
                }
                case "irs": {
                    result = await searchIRS(caseId, query);
                    break;
                }
                case "recorder": {
                    if (!county.trim()) {
                        pushToast("error", "Please select a county for recorder search");
                        setLoading(false);
                        return;
                    }
                    result = await searchRecorder(caseId, county, query);
                    break;
                }
                default:
                    throw new Error("Unknown source");
            }

            if (result.error) {
                setError(result.error);
            } else {
                setResults(result);
                setAddedRows(new Set());
            }
        } catch (err) {
            const message = err instanceof Error ? err.message : "Search failed";
            setError(message);
            pushToast("error", message);
        } finally {
            setLoading(false);
        }
    }, [caseId, query, county, activeSource, pushToast]);

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter" && !loading) {
            handleSearch();
        }
    };

    const handleAddToCase = useCallback(async (rowIndex: number, rowData: Record<string, unknown>) => {
        setAddingRow(rowIndex);
        try {
            const result = await addResearchToCase(caseId, activeSource, rowData);
            setAddedRows(prev => new Set(prev).add(rowIndex));
            if (result.duplicate) {
                pushToast("success", `Already in case: ${result.created}`);
            } else {
                pushToast("success", `Added ${result.created} to case`);
            }
        } catch (err) {
            pushToast("error", `Failed to add: ${(err as Error).message}`);
        } finally {
            setAddingRow(null);
        }
    }, [caseId, activeSource, pushToast]);

    const renderResults = () => {
        if (!results) return null;

        const config = SOURCES[activeSource];

        if (results.count === 0) {
            return (
                <div className={styles.resultsEmpty}>
                    <p>No results found.</p>
                    <p style={{ fontSize: "0.8rem", marginTop: "0.5rem" }}>Try adjusting your search query.</p>
                </div>
            );
        }

        return (
            <>
                <div className={styles.resultsMeta}>
                    Found <strong>{results.count}</strong> result{results.count !== 1 ? "s" : ""} from{" "}
                    <strong>{config.label}</strong>
                </div>
                <div className={styles.resultsTableWrap}>
                    <table className={styles.resultsTable}>
                        <thead>
                            <tr>
                                {config.columns.map((col) => (
                                    <th key={col}>{col}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {results.results.map((row, idx) => (
                                <tr key={idx}>
                                    {activeSource === "parcels" && renderParcelRow(row as Record<string, unknown>, idx)}
                                    {activeSource === "ohio-sos" && renderSosRow(row as Record<string, unknown>, idx)}
                                    {activeSource === "ohio-aos" && renderAosRow(row as Record<string, unknown>, idx)}
                                    {activeSource === "irs" && renderIrsRow(row as Record<string, unknown>, idx)}
                                    {activeSource === "recorder" && renderRecorderRow(row as Record<string, unknown>)}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </>
        );
    };

    const renderParcelRow = (row: Record<string, unknown>, rowIndex: number) => {
        const parcelNumber = String(row.parcel_number ?? "—");
        const ownerName = String(row.owner_name ?? "—");
        const rowCounty = String(row.county ?? "—");
        const acres = row.acres ? parseFloat(String(row.acres)).toFixed(2) : "—";
        const auditorUrl = String(row.auditor_url ?? "");
        return (
            <>
                <td className={styles.parcelPin}>{parcelNumber}</td>
                <td className={styles.parcelOwner}>{ownerName}</td>
                <td className={styles.parcelCounty}>{rowCounty}</td>
                <td className={styles.parcelAcres}>{acres}</td>
                <td>
                    {auditorUrl && (
                        <a href={auditorUrl} target="_blank" rel="noopener noreferrer">
                            View →
                        </a>
                    )}
                </td>
                <td>
                    {addedRows.has(rowIndex) ? (
                        <span className={styles.addedButton}>✓ Added</span>
                    ) : (
                        <button
                            className={styles.addButton}
                            onClick={() => handleAddToCase(rowIndex, row)}
                            disabled={addingRow === rowIndex || addedRows.has(rowIndex)}
                        >
                            {addingRow === rowIndex ? "Adding..." : "Add to Case"}
                        </button>
                    )}
                </td>
            </>
        );
    };

    const renderSosRow = (row: Record<string, unknown>, rowIndex: number) => {
        const entityNumber = String(row.entity_number ?? "—");
        const businessName = String(row.business_name ?? "—");
        const status = String(row.status ?? "—");
        const filingDate = row.filing_date ? formatDate(String(row.filing_date)) : "—";
        const rowCounty = String(row.county ?? "—");
        return (
            <>
                <td className={styles.sosCharter}>{entityNumber}</td>
                <td className={styles.sosName}>{businessName}</td>
                <td className={styles.sosStatus}>
                    <span style={{
                        padding: "2px 6px",
                        borderRadius: "3px",
                        fontSize: "0.75rem",
                        background: status === "ACTIVE" ? "rgba(34, 197, 94, 0.1)" : "rgba(107, 114, 128, 0.1)",
                        color: status === "ACTIVE" ? "#22c55e" : "#6b7280"
                    }}>
                        {status}
                    </span>
                </td>
                <td className={styles.sosDate}>{filingDate}</td>
                <td>{rowCounty}</td>
                <td>
                    {addedRows.has(rowIndex) ? (
                        <span className={styles.addedButton}>✓ Added</span>
                    ) : (
                        <button
                            className={styles.addButton}
                            onClick={() => handleAddToCase(rowIndex, row)}
                            disabled={addingRow === rowIndex || addedRows.has(rowIndex)}
                        >
                            {addingRow === rowIndex ? "Adding..." : "Add to Case"}
                        </button>
                    )}
                </td>
            </>
        );
    };

    const renderAosRow = (row: Record<string, unknown>, rowIndex: number) => {
        const entityName = String(row.entity_name ?? "—");
        const rowCounty = String(row.county ?? "—");
        const reportType = String(row.report_type ?? "—");
        const period = String(row.period ?? "—");
        const hasFindings = Boolean(row.has_findings_for_recovery);
        return (
            <>
                <td className={styles.aosEntity}>{entityName}</td>
                <td className={styles.aosCounty}>{rowCounty}</td>
                <td className={styles.aosType}>{reportType}</td>
                <td>{period}</td>
                <td className={styles.aosFindings}>
                    {hasFindings ? (
                        <span className={styles.findingsFlag}>YES</span>
                    ) : (
                        "—"
                    )}
                </td>
                <td>
                    {addedRows.has(rowIndex) ? (
                        <span className={styles.addedButton}>✓ Added</span>
                    ) : (
                        <button
                            className={styles.addButton}
                            onClick={() => handleAddToCase(rowIndex, row)}
                            disabled={addingRow === rowIndex || addedRows.has(rowIndex)}
                        >
                            {addingRow === rowIndex ? "Adding..." : "Add Note"}
                        </button>
                    )}
                </td>
            </>
        );
    };

    const renderIrsRow = (row: Record<string, unknown>, rowIndex: number) => {
        const ein = String(row.ein ?? "—");
        const orgName = String(row.organization_name ?? "—");
        const city = String(row.city ?? "");
        const state = String(row.state ?? "");
        const location = city ? `${city}, ${state}` : "—";
        const status = String(row.status ?? "—");
        const rulingDate = row.ruling_date ? formatDate(String(row.ruling_date)) : "—";
        const totalAssets = row.total_assets ? formatCurrency(Number(row.total_assets)) : "—";
        const totalRevenue = row.total_revenue ? formatCurrency(Number(row.total_revenue)) : "—";
        const hasRevocation = Boolean(row.revocation_date);
        return (
            <>
                <td className={styles.irsEin}>{ein}</td>
                <td className={styles.irsName}>{orgName}</td>
                <td>{location}</td>
                <td className={styles.irsStatus}>
                    <span style={{
                        padding: "2px 6px",
                        borderRadius: "3px",
                        fontSize: "0.75rem",
                        background: status === "ACTIVE" ? "rgba(34, 197, 94, 0.1)" : "rgba(107, 114, 128, 0.1)",
                        color: status === "ACTIVE" ? "#22c55e" : "#6b7280"
                    }}>
                        {status}
                    </span>
                </td>
                <td>{rulingDate}</td>
                <td style={{ textAlign: "right" }}>{totalAssets}</td>
                <td style={{ textAlign: "right" }}>{totalRevenue}</td>
                <td className={styles.irsRevoked}>
                    {hasRevocation ? (
                        <span className={styles.revokedFlag}>YES</span>
                    ) : (
                        "—"
                    )}
                </td>
                <td>
                    {addedRows.has(rowIndex) ? (
                        <span className={styles.addedButton}>✓ Added</span>
                    ) : (
                        <button
                            className={styles.addButton}
                            onClick={() => handleAddToCase(rowIndex, row)}
                            disabled={addingRow === rowIndex || addedRows.has(rowIndex)}
                        >
                            {addingRow === rowIndex ? "Adding..." : "Add to Case"}
                        </button>
                    )}
                </td>
            </>
        );
    };

    const renderRecorderRow = (row: Record<string, unknown>) => {
        const rowCounty = String(row.county ?? "—");
        const searchUrl = String(row.search_url ?? "");
        return (
            <>
                <td className={styles.recorderCounty}>{rowCounty}</td>
                <td style={{ flex: 1, minWidth: "300px" }}>
                    {searchUrl && (
                        <a href={searchUrl} target="_blank" rel="noopener noreferrer">
                            {searchUrl}
                        </a>
                    )}
                </td>
                <td className={styles.recorderAction}>
                    {searchUrl && (
                        <button
                            onClick={() => window.open(searchUrl, "_blank")}
                            title="Open county recorder portal"
                        >
                            Open Portal
                        </button>
                    )}
                </td>
            </>
        );
    };

    const formatDate = (dateString: string) => {
        try {
            return new Date(dateString).toLocaleDateString("en-US");
        } catch {
            return dateString;
        }
    };

    const formatCurrency = (value: number) => {
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(value);
    };

    const sourceConfig = SOURCES[activeSource];

    return (
        <div className={styles.researchTab}>
            {/* Header */}
            <div className={styles.researchHeader}>
                <h3 className={styles.researchTitle}>Research External Data Sources</h3>
                <p className={styles.researchDescription}>
                    Search government and public records to find entities, properties, and financial information.
                </p>
            </div>

            {/* Search controls */}
            <div className={styles.searchControls}>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    <div>
                        <h4 style={{ margin: "0 0 0.75rem 0", fontSize: "0.85rem", fontWeight: 600, color: "var(--text-main)" }}>
                            Select Data Source
                        </h4>
                        <div className={styles.sourceTabs}>
                            {(Object.keys(SOURCES) as SourceType[]).map((source) => (
                                <button
                                    key={source}
                                    className={`${styles.sourceTab} ${activeSource === source ? styles.active : ""}`}
                                    onClick={() => {
                                        setActiveSource(source);
                                        setQuery("");
                                        setResults(null);
                                        setError(null);
                                    }}
                                    title={SOURCES[source].description}
                                >
                                    {SOURCES[source].label}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                <div className={styles.searchRow}>
                    {activeSource === "recorder" && (
                        <div className={styles.searchInputGroup}>
                            <label className={styles.searchLabel}>County</label>
                            <select
                                className={styles.searchInput}
                                value={county}
                                onChange={(e) => setCounty(e.target.value)}
                                style={{ cursor: "pointer" }}
                            >
                                <option value="">Select county...</option>
                                {OHIO_COUNTIES.map((c) => (
                                    <option key={c} value={c}>
                                        {c}
                                    </option>
                                ))}
                            </select>
                        </div>
                    )}
                    <div className={styles.searchInputGroup} style={{ flex: 1 }}>
                        <label className={styles.searchLabel}>Search</label>
                        <input
                            type="text"
                            className={styles.searchInput}
                            placeholder={sourceConfig.placeholder}
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={handleKeyDown}
                        />
                    </div>
                    <button
                        className={styles.searchButton}
                        onClick={handleSearch}
                        disabled={loading || !query.trim()}
                    >
                        {loading ? "Searching..." : "Search"}
                    </button>
                </div>
            </div>

            {/* Results */}
            <div className={styles.resultsArea}>
                {error && (
                    <div className={styles.errorBox}>
                        <div className={styles.errorTitle}>Search Error</div>
                        <p className={styles.errorMessage}>{error}</p>
                    </div>
                )}

                {loading && (
                    <div className={styles.resultsLoading}>
                        <p>Searching {sourceConfig.label}...</p>
                        <p style={{ fontSize: "0.75rem", marginTop: "0.5rem" }}>This may take a moment.</p>
                    </div>
                )}

                {!loading && !error && !results && (
                    <div className={styles.resultsEmpty}>
                        <p>Enter a search query and click "Search" to begin.</p>
                        <p style={{ fontSize: "0.8rem", marginTop: "0.5rem" }}>{sourceConfig.description}</p>
                    </div>
                )}

                {!loading && results && renderResults()}
            </div>

            {/* Notes and warnings */}
            {results && (results.notes.length > 0 || results.staleness_warning) && (
                <div className={styles.notesSection}>
                    {results.staleness_warning && (
                        <div className={`${styles.warningBox} ${results.staleness_warning.level === "CRITICAL" ? styles.critical : ""}`}>
                            <h4 className={styles.warningTitle}>{results.staleness_warning.level} Warning</h4>
                            <p className={styles.warningMessage}>{results.staleness_warning.message}</p>
                        </div>
                    )}
                    {results.notes.length > 0 && (
                        <>
                            <h4 className={styles.notesTitle}>Notes</h4>
                            <ul className={styles.notesList}>
                                {results.notes.map((note, idx) => (
                                    <li key={idx}>{note}</li>
                                ))}
                            </ul>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

// Ohio counties for the recorder dropdown
const OHIO_COUNTIES = [
    "Adams",
    "Allen",
    "Ashland",
    "Ashtabula",
    "Athens",
    "Auglaize",
    "Belmont",
    "Brown",
    "Butler",
    "Carroll",
    "Champaign",
    "Clark",
    "Clermont",
    "Clinton",
    "Columbiana",
    "Coshocton",
    "Crawford",
    "Cuyahoga",
    "Darke",
    "Defiance",
    "Delaware",
    "Erie",
    "Fairfield",
    "Fayette",
    "Franklin",
    "Fulton",
    "Gallia",
    "Geauga",
    "Greene",
    "Guernsey",
    "Hamilton",
    "Hancock",
    "Hardin",
    "Harrison",
    "Henry",
    "Highland",
    "Hocking",
    "Holmes",
    "Huron",
    "Jackson",
    "Jefferson",
    "Knox",
    "Lake",
    "Lawrence",
    "Licking",
    "Logan",
    "Lorain",
    "Lucas",
    "Madison",
    "Mahoning",
    "Marion",
    "Medina",
    "Meigs",
    "Mercer",
    "Miami",
    "Monroe",
    "Montgomery",
    "Morgan",
    "Morrow",
    "Muskingum",
    "Noble",
    "Ottawa",
    "Paulding",
    "Perry",
    "Pickaway",
    "Pike",
    "Portage",
    "Preble",
    "Putnam",
    "Richland",
    "Ross",
    "Sandusky",
    "Scioto",
    "Seneca",
    "Shelby",
    "Stark",
    "Summit",
    "Trumbull",
    "Tuscarawas",
    "Union",
    "Van Wert",
    "Vinton",
    "Warren",
    "Washington",
    "Wayne",
    "Williams",
    "Wood",
    "Wyandot",
].sort();
