import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCrossCaseReferrals, isAbortError } from "../api";
import { CrossCaseReferral, ReferralStatus } from "../types";
import { FormSelect } from "../components/ui/FormSelect";
import { EmptyState } from "../components/ui/EmptyState";
import { formatDate } from "../utils/format";
import styles from "./ReferralsView.module.css";

const STATUS_LABELS: Record<ReferralStatus, string> = {
    DRAFT: "Draft",
    SUBMITTED: "Submitted",
    ACKNOWLEDGED: "Acknowledged",
    CLOSED: "Closed",
};

const STATUS_OPTIONS: ReferralStatus[] = ["DRAFT", "SUBMITTED", "ACKNOWLEDGED", "CLOSED"];

export function ReferralsView() {
    const navigate = useNavigate();
    const [referrals, setReferrals] = useState<CrossCaseReferral[]>([]);
    const [loading, setLoading] = useState(true);
    const [statusFilter, setStatusFilter] = useState("all");
    const [searchQuery, setSearchQuery] = useState("");
    const mounted = useRef(true);

    const load = useCallback(async (signal: AbortSignal) => {
        setLoading(true);
        try {
            const filters: { status?: string; agency?: string } = {};
            if (statusFilter !== "all") filters.status = statusFilter;
            if (searchQuery.trim()) filters.agency = searchQuery.trim();
            const res = await fetchCrossCaseReferrals(filters, 200, 0, { signal });
            if (!signal.aborted) setReferrals(res.results);
        } catch (err) {
            if (!isAbortError(err)) console.error(err);
        } finally {
            if (!signal.aborted) setLoading(false);
        }
    }, [statusFilter, searchQuery]);

    useEffect(() => {
        mounted.current = true;
        const controller = new AbortController();
        void load(controller.signal);
        return () => {
            mounted.current = false;
            controller.abort();
        };
    }, [load]);

    /* Pipeline summary */
    const counts: Record<string, number> = { DRAFT: 0, SUBMITTED: 0, ACKNOWLEDGED: 0, CLOSED: 0 };
    for (const r of referrals) {
        if (r.status in counts) counts[r.status]++;
    }

    return (
        <>
            <div className={styles.referralsViewHeader}>
                <h2>Government Referrals</h2>
                <span className={styles.referralCount}>{referrals.length} total</span>
            </div>

            {/* Pipeline overview */}
            <div className={styles.referralPipeline}>
                {STATUS_OPTIONS.map((s) => (
                    <button
                        key={s}
                        className={`${styles.pipelineStage} ${statusFilter === s ? styles.pipelineStageActive : ""}`}
                        onClick={() => setStatusFilter(statusFilter === s ? "all" : s)}
                    >
                        <span className={styles.pipelineCount}>{counts[s]}</span>
                        <span className={styles.pipelineLabel}>{STATUS_LABELS[s]}</span>
                    </button>
                ))}
            </div>

            <div className={styles.referralsViewFilters}>
                <input
                    type="search"
                    placeholder="Search by agency name..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className={`form-input ${styles.referralsViewFiltersInput}`}
                />
                <FormSelect
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    aria-label="Filter by status"
                >
                    <option value="all">All statuses</option>
                    {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                    ))}
                </FormSelect>
            </div>

            {loading ? (
                <p className={styles.loadingHint}>Loading referrals...</p>
            ) : referrals.length === 0 ? (
                <EmptyState
                    title="No referrals found."
                    detail="Create referrals from within individual case views."
                />
            ) : (
                <div className={styles.casesTableWrap}>
                    <table className={styles.casesTable}>
                        <thead>
                            <tr>
                                <th>Agency</th>
                                <th>Case</th>
                                <th>Status</th>
                                <th>Submission ID</th>
                                <th>Contact</th>
                                <th>Filed</th>
                            </tr>
                        </thead>
                        <tbody>
                            {referrals.map((r) => (
                                <tr
                                    key={r.referral_id}
                                    className={styles.casesTableRow}
                                    onClick={() => {
                                        if (r.case_id) navigate(`/cases/${r.case_id}/referrals`);
                                    }}
                                    style={{ cursor: r.case_id ? "pointer" : "default" }}
                                >
                                    <td><strong>{r.agency_name || "Unknown"}</strong></td>
                                    <td className={styles.triageCaseLink}>{r.case_name}</td>
                                    <td>
                                        <span className={`${styles.referralStatus} ${styles[`referralStatus${r.status.charAt(0).toUpperCase() + r.status.slice(1).toLowerCase()}`]}`}>
                                            {STATUS_LABELS[r.status]}
                                        </span>
                                    </td>
                                    <td className={styles.timeCell}>{r.submission_id || "\u2014"}</td>
                                    <td className={styles.timeCell}>{r.contact_alias || "\u2014"}</td>
                                    <td className={styles.timeCell}>{formatDate(r.filing_date)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </>
    );
}
