import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCrossCaseFindings, isAbortError, updateFinding, CrossCaseFindingFilters } from "../api";
import { CrossCaseFinding, FindingUpdatePayload } from "../types";
import { Button } from "../components/ui/Button";
import { FormSelect } from "../components/ui/FormSelect";
import { FormTextarea } from "../components/ui/FormTextarea";
import { EmptyState } from "../components/ui/EmptyState";
import { ToastItem, ToastStack } from "../components/ui/ToastStack";
import { formatDate } from "../utils/format";
import styles from "./TriageView.module.css";

const QUICK_STATUSES = ["NEW", "NEEDS_EVIDENCE", "CONFIRMED", "DISMISSED"];
const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

interface TriageDraft {
    status: string;
    note: string;
}

export function TriageView() {
    const navigate = useNavigate();
    const [findings, setFindings] = useState<CrossCaseFinding[]>([]);
    const [loading, setLoading] = useState(true);
    const [statusFilter, setStatusFilter] = useState("NEW");
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

    /* Load findings */
    const load = useCallback(async (signal: AbortSignal, filters: CrossCaseFindingFilters) => {
        setLoading(true);
        try {
            const res = await fetchCrossCaseFindings(filters, 200, 0, { signal });
            if (!signal.aborted) setFindings(res.results);
        } catch (err) {
            if (!isAbortError(err)) pushToast("error", (err as Error).message);
        } finally {
            if (!signal.aborted) setLoading(false);
        }
    }, [pushToast]);

    useEffect(() => {
        const controller = new AbortController();
        const filters: CrossCaseFindingFilters = {};
        if (statusFilter !== "all") filters.status = statusFilter;
        if (severityFilter !== "all") filters.severity = severityFilter;
        void load(controller.signal, filters);
        return () => controller.abort();
    }, [load, statusFilter, severityFilter]);

    /* Derived */
    const newCount = useMemo(() => findings.filter((f) => f.status === "NEW").length, [findings]);

    function getDraft(finding: CrossCaseFinding): TriageDraft {
        return drafts[finding.id] ?? { status: finding.status, note: finding.investigator_note };
    }

    function setDraft(findingId: string, draft: TriageDraft) {
        setDrafts((prev) => ({ ...prev, [findingId]: draft }));
    }

    async function handleSave(finding: CrossCaseFinding) {
        const caseId = finding.case_id;
        if (!caseId) return;
        const draft = getDraft(finding);
        setSavingId(finding.id);
        try {
            const payload: FindingUpdatePayload = {
                status: draft.status as FindingUpdatePayload["status"],
                investigator_note: draft.note,
            };
            const updated = await updateFinding(caseId, finding.id, payload);
            setFindings((prev) =>
                prev.map((f) => (f.id === finding.id ? { ...f, ...updated } : f)),
            );
            pushToast("success", "Finding updated");
        } catch (err) {
            pushToast("error", (err as Error).message);
        } finally {
            setSavingId(null);
        }
    }

    return (
        <>
            <div className={styles.triageHeader}>
                <h2>Finding Triage Queue</h2>
                <span className={styles.triageOpenBadge}>{newCount} new</span>
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
                <p className={styles.loadingHint}>Loading findings...</p>
            ) : findings.length === 0 ? (
                <EmptyState
                    title="No findings match the current filters."
                    detail="Try broadening filters or wait for new findings to be detected."
                />
            ) : (
                <ul className={`${styles.triageList}`}>
                    {findings.map((finding) => {
                        const draft = getDraft(finding);
                        const isActive = finding.id === activeId;
                        return (
                            <li key={finding.id} className={styles.triageItem}>
                                <div
                                    className={isActive ? `${styles.signalCard} ${styles.activeSignal}` : styles.signalCard}
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => setActiveId(isActive ? null : finding.id)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" || e.key === " ") {
                                            e.preventDefault();
                                            setActiveId(isActive ? null : finding.id);
                                        }
                                    }}
                                >
                                    <div className={styles.triageCardHeader}>
                                        <strong>{finding.title}</strong>
                                        <button
                                            className={styles.triageCaseLink}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                if (finding.case_id) navigate(`/cases/${finding.case_id}/pipeline`);
                                            }}
                                        >
                                            {finding.case_name}
                                        </button>
                                    </div>
                                    <p className={styles.signalSubhead}>{finding.rule_id || "MANUAL"}</p>
                                    <p>{finding.description}</p>
                                    <p className={styles.signalSubhead}>Created: {formatDate(finding.created_at)}</p>
                                </div>
                                <div className={styles.signalBadges}>
                                    <span className={`${styles.tag} ${styles[`tag${finding.severity.charAt(0).toUpperCase() + finding.severity.slice(1).toLowerCase()}`]}`}>{finding.severity}</span>
                                    <span className={`${styles.tag} ${styles.tagNeutral}`}>{finding.status}</span>

                                    {isActive && (
                                        <>
                                            <div className={styles.triageQuickActions}>
                                                {QUICK_STATUSES.map((qs) => (
                                                    <Button
                                                        key={qs}
                                                        className={`${styles.triageChip} ${draft.status === qs ? styles.triageChipActive : ""}`}
                                                        variant="secondary"
                                                        onClick={() => setDraft(finding.id, { ...draft, status: qs })}
                                                    >
                                                        {qs}
                                                    </Button>
                                                ))}
                                            </div>
                                            <FormTextarea
                                                className={styles.triageNote}
                                                placeholder="Investigator note"
                                                value={draft.note}
                                                onChange={(e) => setDraft(finding.id, { ...draft, note: e.target.value })}
                                                rows={2}
                                            />
                                            <Button
                                                className={styles.triageSave}
                                                onClick={() => void handleSave(finding)}
                                                disabled={savingId === finding.id}
                                            >
                                                {savingId === finding.id ? "Saving..." : "Save"}
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
