import { Fragment, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { FinancialSnapshotItem } from "../../types";
import { fetchCaseFinancials } from "../../api";
import styles from "./FinancialsTab.module.css";

interface CaseDetailContext {
    caseDetail: { id: string; name: string };
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

    // Group line items
    let lastGroup = "";

    return (
        <div className={styles.financialsTab}>
            <h3>Year-over-Year Financial Summary</h3>
            <p className="text-muted">
                EIN: {data[0]?.ein || "\u2014"} &middot; {data.length} tax year{data.length !== 1 ? "s" : ""}
                {data[0]?.organization_name && ` \u00b7 ${data[0].organization_name}`}
            </p>

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
                                            return (
                                                <td key={snap.tax_year} className={styles.amountCell}>
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
