import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCrossCaseSignals, isAbortError, updateSignal, CrossCaseSignalFilters } from "../api";
import { CrossCaseSignal } from "../types";
import { Button } from "../components/ui/Button";
import { FormSelect } from "../components/ui/FormSelect";
import { FormTextarea } from "../components/ui/FormTextarea";
import { EmptyState } from "../components/ui/EmptyState";
import { ToastItem, ToastStack } from "../components/ui/ToastStack";
import { formatDate } from "../utils/format";
import styles from "./TriageView.module.css";

const QUICK_STATUSES = ["OPEN", "CONFIRMED", "DISMISSED", "ESCALATED"];
const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

interface TriageDraft {
    status: string;
    note: string;
}

export function TriageView() {
    const navigate = useNavigate();
    const [signals, setSignals] = useState<CrossCaseSignal[]>([]);
    const [loading, setLoading] = useState(true);
    const [statusFilter, setStatusFilter] = useState("OPEN");
    const [severityFilter, setSeverityFilter] = useState("all");
    const [activeId, setActiveId] = useState<string | null>(null);
    const [drafts, setDrafts] = useState<Record<string, TriageDraft>>({});
    const [savingId, setSavingId] = useState<string | null>(null);

    /* Toast */
    const [toasts, setToasts] = useState<ToastItem[]>([]);
    const toastId = useRef(0);
    const pushToast = useCallback((tone: "error" | "success", message: string) => {
        const id = ++toastId.current;
        setToasts((prev) => [...prev, { id, tone, message }]);
        setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3400);
    }, []);

    /* Load signals */
    const load = useCallback(async (signal: AbortSignal, filters: CrossCaseSignalFilters) => {
        setLoading(true);
        try {
            const res = await fetchCrossCaseSignals(filters, 200, 0, { signal });
            if (!signal.aborted) setSignals(res.results);
        } catch (err) {
            if (!isAbortError(err)) pushToast("error", (err as Error).message);
        } finally {
            if (!signal.aborted) setLoading(false);
        }
    }, [pushToast]);

    useEffect(() => {
        const controller = new AbortController();
        const filters: CrossCaseSignalFilters = {};
        if (statusFilter !== "all") filters.status = statusFilter;
        if (severityFilter !== "all") filters.severity = severityFilter;
        void load(controller.signal, filters);
        return () => controller.abort();
    }, [load, statusFilter, severityFilter]);

    /* Derived */
    const openCount = useMemo(() => signals.filter((s) => s.status === "OPEN").length, [signals]);

    function getDraft(signal: CrossCaseSignal): TriageDraft {
        return drafts[signal.id] ?? { status: signal.status, note: signal.investigator_note };
    }

    function setDraft(signalId: string, draft: TriageDraft) {
        setDrafts((prev) => ({ ...prev, [signalId]: draft }));
    }

    async function handleSave(signal: CrossCaseSignal) {
        const caseId = signal.case_id;
        if (!caseId) return;
        const draft = getDraft(signal);
        setSavingId(signal.id);
        try {
            const updated = await updateSignal(caseId, signal.id, {
                status: draft.status,
                investigator_note: draft.note,
            });
            setSignals((prev) =>
                prev.map((s) => (s.id === signal.id ? { ...s, ...updated } : s)),
            );
            pushToast("success", "Signal updated");
        } catch (err) {
            pushToast("error", (err as Error).message);
        } finally {
            setSavingId(null);
        }
    }

    return (
        <>
            <div className={styles.triageHeader}>
                <h2>Signal Triage Queue</h2>
                <span className={styles.triageOpenBadge}>{openCount} open</span>
            </div>

            <div className={styles.triageFilters}>
                <FormSelect
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    aria-label="Filter by status"
                >
                    <option value="all">All status</option>
                    {QUICK_STATUSES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                    ))}
                </FormSelect>
                <FormSelect
                    value={severityFilter}
                    onChange={(e) => setSeverityFilter(e.target.value)}
                    aria-label="Filter by severity"
                >
                    <option value="all">All severity</option>
                    {SEVERITIES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                    ))}
                </FormSelect>
            </div>

            {loading ? (
                <p className={styles.loadingHint}>Loading signals...</p>
            ) : signals.length === 0 ? (
                <EmptyState
                    title="No signals match the current filters."
                    detail="Try broadening filters or wait for new signals to be detected."
                />
            ) : (
                <ul className={`${styles.triageList}`}>
                    {signals.map((signal) => {
                        const draft = getDraft(signal);
                        const isActive = signal.id === activeId;
                        return (
                            <li key={signal.id} className={styles.triageItem}>
                                <div
                                    className={isActive ? `${styles.signalCard} ${styles.activeSignal}` : styles.signalCard}
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => setActiveId(isActive ? null : signal.id)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" || e.key === " ") {
                                            e.preventDefault();
                                            setActiveId(isActive ? null : signal.id);
                                        }
                                    }}
                                >
                                    <div className={styles.triageCardHeader}>
                                        <strong>{signal.title}</strong>
                                        <button
                                            className={styles.triageCaseLink}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                if (signal.case_id) navigate(`/cases/${signal.case_id}/signals`);
                                            }}
                                        >
                                            {signal.case_name}
                                        </button>
                                    </div>
                                    <p className={styles.signalSubhead}>{signal.rule_id}</p>
                                    <p>{signal.description}</p>
                                    <p className={styles.signalSubhead}>Detected: {formatDate(signal.detected_at)}</p>
                                </div>
                                <div className={styles.signalBadges}>
                                    <span className={`${styles.tag} ${styles[`tag${signal.severity.charAt(0).toUpperCase() + signal.severity.slice(1).toLowerCase()}`]}`}>{signal.severity}</span>
                                    <span className={`${styles.tag} ${styles.tagNeutral}`}>{signal.status}</span>

                                    {isActive && (
                                        <>
                                            <div className={styles.triageQuickActions}>
                                                {QUICK_STATUSES.map((qs) => (
                                                    <Button
                                                        key={qs}
                                                        className={`${styles.triageChip} ${draft.status === qs ? styles.triageChipActive : ""}`}
                                                        variant="secondary"
                                                        onClick={() => setDraft(signal.id, { ...draft, status: qs })}
                                                    >
                                                        {qs}
                                                    </Button>
                                                ))}
                                            </div>
                                            <FormTextarea
                                                className={styles.triageNote}
                                                placeholder="Investigator note"
                                                value={draft.note}
                                                onChange={(e) => setDraft(signal.id, { ...draft, note: e.target.value })}
                                                rows={2}
                                            />
                                            <Button
                                                className={styles.triageSave}
                                                onClick={() => void handleSave(signal)}
                                                disabled={savingId === signal.id}
                                            >
                                                {savingId === signal.id ? "Saving..." : "Save"}
                                            </Button>
                                        </>
                                    )}
                                </div>
                            </li>
                        );
                    })}
                </ul>
            )}

            <ToastStack toasts={toasts} onDismiss={(id) => setToasts((p) => p.filter((t) => t.id !== id))} />
        </>
    );
}
