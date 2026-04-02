import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCases, fetchSignalSummary, SignalSummaryItem, fetchActivityFeed, isAbortError } from "../api";
import { ActivityEntry, CaseSummary } from "../types";
import { formatDate } from "../utils/format";
import styles from "./DashboardView.module.css";

/* ── Severity color helpers ─────────────────────────────── */
const SEV_COLORS: Record<string, string> = {
    CRITICAL: "#ef4444",
    HIGH: "#f97316",
    MEDIUM: "#fbbf24",
    LOW: "#60a5fa",
};

const ACTION_LABELS: Record<string, string> = {
    INSERT: "Created",
    UPDATE: "Updated",
    DELETE: "Deleted",
};

const TABLE_LABELS: Record<string, string> = {
    cases: "Case",
    documents: "Document",
    signals: "Signal",
    detections: "Detection",
    government_referrals: "Referral",
    persons: "Person",
    organizations: "Organization",
    properties: "Property",
    financial_instruments: "Financial Instrument",
};

export function DashboardView() {
    const navigate = useNavigate();
    const [cases, setCases] = useState<CaseSummary[]>([]);
    const [signalSummary, setSignalSummary] = useState<SignalSummaryItem[]>([]);
    const [activity, setActivity] = useState<ActivityEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const mounted = useRef(true);

    const load = useCallback(async (signal: AbortSignal) => {
        setLoading(true);
        try {
            const [casesRes, summaryRes, activityRes] = await Promise.all([
                fetchCases(100, 0, { signal }),
                fetchSignalSummary({ signal }),
                fetchActivityFeed(15, { signal }),
            ]);
            if (!signal.aborted) {
                setCases(casesRes.results);
                setSignalSummary(summaryRes.results);
                setActivity(activityRes.results);
            }
        } catch (err) {
            if (!isAbortError(err)) console.error(err);
        } finally {
            if (!signal.aborted) setLoading(false);
        }
    }, []);

    useEffect(() => {
        mounted.current = true;
        const controller = new AbortController();
        void load(controller.signal);
        return () => {
            mounted.current = false;
            controller.abort();
        };
    }, [load]);

    /* ── Computed KPIs ──────────────────────────── */
    const totalCases = cases.length;
    const activeCases = cases.filter((c) => c.status === "ACTIVE").length;
    const totalOpenSignals = signalSummary.reduce((sum, s) => sum + s.open_count, 0);

    const sevCounts: Record<string, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    for (const s of signalSummary) {
        if (s.highest_severity in sevCounts) sevCounts[s.highest_severity]++;
    }

    const referredCases = cases.filter((c) => c.status === "REFERRED").length;
    const recentCases = [...cases].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 5);

    if (loading) {
        return (
            <div className={styles.dashboardLoading}>
                <p>Loading dashboard...</p>
            </div>
        );
    }

    return (
        <div className={styles.dashboard}>
            {/* ── KPI cards ── */}
            <div className={styles.kpiRow}>
                <button className={styles.kpiCard} onClick={() => navigate("/cases")}>
                    <span className={styles.kpiValue}>{totalCases}</span>
                    <span className={styles.kpiLabel}>Total Cases</span>
                    <span className={styles.kpiSub}>{activeCases} active</span>
                </button>
                <button className={`${styles.kpiCard} ${styles.kpiSignals}`} onClick={() => navigate("/triage")}>
                    <span className={styles.kpiValue}>{totalOpenSignals}</span>
                    <span className={styles.kpiLabel}>Open Signals</span>
                    <span className={styles.kpiSub}>across {signalSummary.filter((s) => s.open_count > 0).length} cases</span>
                </button>
                <button className={styles.kpiCard} onClick={() => navigate("/entities")}>
                    <span className={styles.kpiValue}>{"\u{1F464}"}</span>
                    <span className={styles.kpiLabel}>Entities</span>
                    <span className={styles.kpiSub}>Browse all entities</span>
                </button>
                <button className={styles.kpiCard} onClick={() => navigate("/referrals")}>
                    <span className={styles.kpiValue}>{referredCases}</span>
                    <span className={styles.kpiLabel}>Referred Cases</span>
                    <span className={styles.kpiSub}>View referrals</span>
                </button>
            </div>

            <div className={styles.dashboardGrid}>
                {/* ── Severity breakdown ── */}
                <section className={styles.dashCard}>
                    <h3>Signal Severity Breakdown</h3>
                    <div className={styles.severityBars}>
                        {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((sev) => {
                            const count = sevCounts[sev];
                            const maxCount = Math.max(...Object.values(sevCounts), 1);
                            return (
                                <div key={sev} className={styles.severityBarRow}>
                                    <span className={styles.severityBarLabel}>{sev}</span>
                                    <div className={styles.severityBarTrack}>
                                        <div
                                            className={styles.severityBarFill}
                                            style={{
                                                width: `${(count / maxCount) * 100}%`,
                                                backgroundColor: SEV_COLORS[sev],
                                            }}
                                        />
                                    </div>
                                    <span className={styles.severityBarCount}>{count}</span>
                                </div>
                            );
                        })}
                    </div>
                </section>

                {/* ── Recent cases ── */}
                <section className={styles.dashCard}>
                    <h3>Recently Updated Cases</h3>
                    {recentCases.length === 0 ? (
                        <p className={styles.dashEmpty}>No cases yet. Create one from the Cases view.</p>
                    ) : (
                        <ul className={styles.recentCasesList}>
                            {recentCases.map((c) => (
                                <li key={c.id}>
                                    <button className={styles.recentCaseRow} onClick={() => navigate(`/cases/${c.id}`)}>
                                        <span className={styles.recentCaseName}>{c.name}</span>
                                        <span className={`${styles.statusPill} ${styles[`statusPill${c.status.charAt(0).toUpperCase() + c.status.slice(1).toLowerCase()}`]}`}>{c.status}</span>
                                        <span className={styles.recentCaseTime}>{formatDate(c.updated_at)}</span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                {/* ── Activity feed ── */}
                <section className={`${styles.dashCard} ${styles.dashCardWide}`}>
                    <h3>Recent Activity</h3>
                    {activity.length === 0 ? (
                        <p className={styles.dashEmpty}>No activity recorded yet.</p>
                    ) : (
                        <ul className={styles.activityFeed}>
                            {activity.map((a) => (
                                <li key={a.id} className={styles.activityEntry}>
                                    <span className={styles.activityAction}>
                                        {ACTION_LABELS[a.action] ?? a.action}
                                    </span>
                                    <span className={styles.activityTable}>
                                        {TABLE_LABELS[a.table_name] ?? a.table_name}
                                    </span>
                                    {a.performed_by && (
                                        <span className={styles.activityUser}>by {a.performed_by}</span>
                                    )}
                                    <span className={styles.activityTime}>{formatDate(a.performed_at)}</span>
                                    {a.notes && <span className={styles.activityNote}>{a.notes}</span>}
                                </li>
                            ))}
                        </ul>
                    )}
                </section>
            </div>
        </div>
    );
}
