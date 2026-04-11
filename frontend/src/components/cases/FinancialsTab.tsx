import { Fragment, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { FinancialSnapshotItem } from "../../types";
import { fetchCaseFinancials } from "../../api";
import styles from "./FinancialsTab.module.css";

interface CaseDetailContext {
    caseDetail: { id: string; name: string };
}

interface Anomaly {
    year: number;
    type: string;
    severity: "error" | "warning";
    message: string;
}

interface CellAnomalyState {
    severity: "error" | "warning";
    message: string;
}

function fmt(val: number | null | undefined): string {
    if (val == null) return "\u2014";
    return "$" + val.toLocaleString("en-US");
}

function yoyBadge(pct: number | undefined): JSX.Element | null {
    if (pct == null) return null;
    const cls = Math.abs(pct) > 50 ? styles.yoyFlag : pct > 0 ? styles.yoyUp : styles.yoyDown;
    return <span className={`${styles.yoyBadge} ${cls}`}>{pct > 0 ? "+" : ""}{pct.toFixed(1)}%</span>;
}

// Compute program ratio: (total_expenses - officer_compensation - professional_fundraising) / total_expenses
function computeProgramRatio(snap: FinancialSnapshotItem): number | null {
    const { total_expenses, officer_compensation_total, professional_fundraising } = snap;
    if (total_expenses == null || total_expenses === 0) return null;
    const deductible = (officer_compensation_total ?? 0) + (professional_fundraising ?? 0);
    return ((total_expenses - deductible) / total_expenses) * 100;
}

// Detect anomalies for a single year's snapshot
function detectAnomalies(snap: FinancialSnapshotItem, previousSnap: FinancialSnapshotItem | null): Anomaly[] {
    const anomalies: Anomaly[] = [];

    // SR-021: Revenue spike (YoY > 100%)
    if (previousSnap && previousSnap.total_revenue && previousSnap.total_revenue > 0 && snap.total_revenue) {
        const revenueYoy = ((snap.total_revenue - previousSnap.total_revenue) / Math.abs(previousSnap.total_revenue)) * 100;
        if (revenueYoy > 100) {
            anomalies.push({
                year: snap.tax_year,
                type: "revenue_spike",
                severity: "error",
                message: `Revenue spike (+${revenueYoy.toFixed(0)}%)`,
            });
        }
    }

    // SR-013: Zero officer compensation at high-revenue org
    if (
        snap.officer_compensation_total != null &&
        snap.officer_compensation_total === 0 &&
        snap.total_revenue != null &&
        snap.total_revenue > 100000
    ) {
        anomalies.push({
            year: snap.tax_year,
            type: "zero_officer_pay",
            severity: "error",
            message: "Zero officer compensation (high revenue)",
        });
    }

    // SR-029: Low program ratio < 50%
    const programRatio = computeProgramRatio(snap);
    if (programRatio != null && programRatio < 50) {
        anomalies.push({
            year: snap.tax_year,
            type: "low_program_ratio",
            severity: "error",
            message: `Low program ratio (${programRatio.toFixed(1)}%)`,
        });
    }

    // Net assets growing while revenue declining
    if (
        previousSnap &&
        snap.total_revenue != null &&
        previousSnap.total_revenue != null &&
        snap.net_assets_eoy != null &&
        previousSnap.net_assets_eoy != null
    ) {
        const revenueDeclining = snap.total_revenue < previousSnap.total_revenue;
        const assetsGrowing = snap.net_assets_eoy > previousSnap.net_assets_eoy;
        if (revenueDeclining && assetsGrowing) {
            anomalies.push({
                year: snap.tax_year,
                type: "assets_revenue_mismatch",
                severity: "warning",
                message: "Assets growing despite declining revenue",
            });
        }
    }

    return anomalies;
}

const LINE_ITEMS: { key: keyof FinancialSnapshotItem; label: string; group: string }[] = [
    { key: "total_contributions", label: "Contributions & Grants", group: "Revenue" },
    { key: "program_service_revenue", label: "Program Service Revenue", group: "Revenue" },
    { key: "investment_income", label: "Investment Income", group: "Revenue" },
    { key: "other_revenue", label: "Other Revenue", group: "Revenue" },
    { key: "total_revenue", label: "Total Revenue", group: "Revenue" },
    { key: "grants_paid", label: "Grants Paid", group: "Expenses" },
    { key: "salaries_and_compensation", label: "Salaries & Compensation", group: "Expenses" },
    { key: "professional_fundraising", label: "Professional Fundraising", group: "Expenses" },
    { key: "other_expenses", label: "Other Expenses", group: "Expenses" },
    { key: "total_expenses", label: "Total Expenses", group: "Expenses" },
    { key: "revenue_less_expenses", label: "Revenue Less Expenses", group: "Bottom Line" },
    { key: "total_assets_eoy", label: "Total Assets (EOY)", group: "Balance Sheet" },
    { key: "total_liabilities_eoy", label: "Total Liabilities (EOY)", group: "Balance Sheet" },
    { key: "net_assets_eoy", label: "Net Assets (EOY)", group: "Balance Sheet" },
    { key: "officer_compensation_total", label: "Officer Compensation", group: "Compensation" },
    { key: "num_employees", label: "Employees", group: "Compensation" },
];

export function FinancialsTab() {
    const { caseDetail } = useOutletContext<CaseDetailContext>();
    const [data, setData] = useState<FinancialSnapshotItem[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchCaseFinancials(caseDetail.id)
            .then((r: { results: FinancialSnapshotItem[] }) => setData(r.results))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [caseDetail.id]);

    if (loading) return <div className="tab-loading">Loading financial data...</div>;
    if (data.length === 0) {
        return (
            <div className="empty-state">
                <p>No IRS Form 990 financial data has been extracted for this case.</p>
                <p className="text-muted">Upload 990 filings on the Documents tab to auto-populate.</p>
            </div>
        );
    }

    const years = data.map(d => d.tax_year);
    const sortedData = [...data].sort((a, b) => a.tax_year - b.tax_year);

    // Detect all anomalies
    const allAnomalies: Anomaly[] = [];
    sortedData.forEach((snap, idx) => {
        const prev = idx > 0 ? sortedData[idx - 1] : null;
        allAnomalies.push(...detectAnomalies(snap, prev));
    });

    // Build a map of anomalies by (year, key) for cell highlighting
    const anomalyMap = new Map<string, CellAnomalyState>();
    allAnomalies.forEach(anom => {
        const key = `${anom.year}-${anom.type}`;
        // If not yet mapped, add it. If already mapped, keep most severe
        if (!anomalyMap.has(key)) {
            anomalyMap.set(key, { severity: anom.severity, message: anom.message });
        }
    });

    // Determine which cells to highlight based on anomaly type
    function getCellAnomalyClass(snap: FinancialSnapshotItem, itemKey: keyof FinancialSnapshotItem): string {
        const revenueAnomaly = anomalyMap.get(`${snap.tax_year}-revenue_spike`);
        const zeroPayAnomaly = anomalyMap.get(`${snap.tax_year}-zero_officer_pay`);
        const lowRatioAnomaly = anomalyMap.get(`${snap.tax_year}-low_program_ratio`);
        const mismatchAnomaly = anomalyMap.get(`${snap.tax_year}-assets_revenue_mismatch`);

        // Highlight total_revenue cells for revenue spike
        if (revenueAnomaly && itemKey === "total_revenue") {
            return styles.cellError;
        }
        // Highlight officer compensation for zero pay
        if (zeroPayAnomaly && itemKey === "officer_compensation_total") {
            return styles.cellError;
        }
        // Highlight total_expenses for low program ratio
        if (lowRatioAnomaly && itemKey === "total_expenses") {
            return styles.cellError;
        }
        // Highlight net_assets_eoy for mismatch
        if (mismatchAnomaly && itemKey === "net_assets_eoy") {
            return styles.cellWarning;
        }

        return "";
    }

    // Group line items
    let lastGroup = "";

    return (
        <div className={styles.financialsTab}>
            <h3>Year-over-Year Financial Summary</h3>
            <p className="text-muted">
                EIN: {data[0]?.ein || "\u2014"} &middot; {data.length} tax year{data.length !== 1 ? "s" : ""}
                {data[0]?.organization_name && ` \u00b7 ${data[0].organization_name}`}
            </p>

            {/* Anomaly Summary Strip */}
            {allAnomalies.length > 0 && (
                <div className={styles.anomalySummary}>
                    {allAnomalies.map((anom, idx) => (
                        <div
                            key={`${anom.year}-${anom.type}-${idx}`}
                            className={`${styles.anomalyChip} ${styles[`severity${anom.severity === "error" ? "Error" : "Warning"}`]}`}
                            title={anom.message}
                        >
                            ⚠ {anom.message}
                        </div>
                    ))}
                </div>
            )}

            <div className={styles.financialsTableWrap}>
                <table className={styles.financialsTable}>
                    <thead>
                        <tr>
                            <th className={styles.lineItemCol}>Line Item</th>
                            {years.map(y => (
                                <th key={y} className={styles.yearCol}>{y}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {LINE_ITEMS.map(item => {
                            const showGroupHeader = item.group !== lastGroup;
                            lastGroup = item.group;
                            const isTotal = item.key.startsWith("total_") || item.key === "revenue_less_expenses" || item.key === "net_assets_eoy";

                            return (
                                <Fragment key={item.key}>
                                    {showGroupHeader && (
                                        <tr className={styles.groupHeaderRow}>
                                            <td colSpan={years.length + 1}>{item.group}</td>
                                        </tr>
                                    )}
                                    <tr className={isTotal ? styles.totalRow : ""}>
                                        <td className={styles.lineItemLabel}>{item.label}</td>
                                        {data.map(snap => {
                                            const val = snap[item.key] as number | null;
                                            const yoyKey = `${item.key}_yoy_pct` as keyof FinancialSnapshotItem;
                                            const yoy = snap[yoyKey] as number | undefined;
                                            const cellAnomalyClass = getCellAnomalyClass(snap, item.key);

                                            return (
                                                <td
                                                    key={snap.tax_year}
                                                    className={`${styles.amountCell} ${cellAnomalyClass}`}
                                                >
                                                    {item.key === "num_employees"
                                                        ? (val != null ? val.toLocaleString() : "\u2014")
                                                        : fmt(val)}
                                                    {yoyBadge(yoy)}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                </Fragment>
                            );
                        })}

                        {/* Analysis Group */}
                        <tr className={styles.groupHeaderRow}>
                            <td colSpan={years.length + 1}>Analysis</td>
                        </tr>

                        {/* Program Ratio Row */}
                        <tr>
                            <td className={styles.lineItemLabel}>Program Service Ratio</td>
                            {data.map(snap => {
                                const ratio = computeProgramRatio(snap);
                                const lowRatioAnomaly = anomalyMap.get(`${snap.tax_year}-low_program_ratio`);
                                const cellClass = lowRatioAnomaly ? styles.cellError : "";

                                return (
                                    <td key={snap.tax_year} className={`${styles.amountCell} ${cellClass}`}>
                                        {ratio != null ? `${ratio.toFixed(1)}%` : "\u2014"}
                                    </td>
                                );
                            })}
                        </tr>
                    </tbody>
                </table>
            </div>

            <div className={styles.financialsConfidence}>
                {data.map(d => (
                    <span key={d.tax_year} className={styles.confBadge}>
                        {d.tax_year}: {Math.round(d.confidence * 100)}% confidence
                        {d.source !== "EXTRACTED" && ` (${d.source})`}
                    </span>
                ))}
            </div>
        </div>
    );
}
