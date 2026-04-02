import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import styles from "./CasesListView.module.css";
import {
    createCase,
    fetchCases,
    fetchSignalSummary,
    isAbortError,
    SignalSummaryItem,
} from "../api";
import { CaseSummary, NewCasePayload } from "../types";
import { Button } from "../components/ui/Button";
import { FormInput } from "../components/ui/FormInput";
import { FormSelect } from "../components/ui/FormSelect";
import { FormTextarea } from "../components/ui/FormTextarea";
import { StateBlock } from "../components/ui/StateBlock";
import { ToastItem, ToastStack } from "../components/ui/ToastStack";
import { formatDate } from "../utils/format";

function severityDot(severity: string | undefined): string {
    if (!severity) return "\u26AA";
    switch (severity.toUpperCase()) {
        case "CRITICAL": return "\uD83D\uDD34";
        case "HIGH": return "\uD83D\uDFE0";
        case "MEDIUM": return "\uD83D\uDFE1";
        case "LOW": return "\uD83D\uDFE2";
        default: return "\u26AA";
    }
}

function relativeTime(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return formatDate(dateStr);
}

type ViewMode = "table" | "board";
const KANBAN_COLUMNS = ["ACTIVE", "PAUSED", "REFERRED", "CLOSED"] as const;

export function CasesListView() {
    const navigate = useNavigate();
    const [cases, setCases] = useState<CaseSummary[]>([]);
    const [severityMap, setSeverityMap] = useState<Record<string, string>>({});
    const [signalCounts, setSignalCounts] = useState<Record<string, number>>({});
    const [loading, setLoading] = useState(true);
    const [query, setQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [sort, setSort] = useState("updated_desc");
    const [viewMode, setViewMode] = useState<ViewMode>("table");

    // New case modal
    const [showModal, setShowModal] = useState(false);
    const [newName, setNewName] = useState("");
    const [newRef, setNewRef] = useState("");
    const [newNotes, setNewNotes] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [formError, setFormError] = useState("");

    // Toasts
    const [toasts, setToasts] = useState<ToastItem[]>([]);
    const toastId = useRef(0);
    const pushToast = useCallback((tone: "error" | "success", message: string) => {
        const id = ++toastId.current;
        setToasts((prev) => [...prev, { id, tone, message }]);
        setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3400);
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        async function load() {
            setLoading(true);
            try {
                const [casesRes, summaryRes] = await Promise.all([
                    fetchCases(100, 0, { signal: controller.signal }),
                    fetchSignalSummary({ signal: controller.signal }),
                ]);
                setCases(casesRes.results);
                const sevMap: Record<string, string> = {};
                const cntMap: Record<string, number> = {};
                for (const item of summaryRes.results as SignalSummaryItem[]) {
                    sevMap[item.case_id] = item.highest_severity;
                    cntMap[item.case_id] = item.open_count;
                }
                setSeverityMap(sevMap);
                setSignalCounts(cntMap);
            } catch (err) {
                if (!isAbortError(err)) pushToast("error", (err as Error).message);
            } finally {
                if (!controller.signal.aborted) setLoading(false);
            }
        }
        void load();
        return () => controller.abort();
    }, [pushToast]);

    const statuses = useMemo(
        () => Array.from(new Set(cases.map((c) => c.status))).sort(),
        [cases]
    );

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        const visible = cases.filter((c) => {
            const statusOk = statusFilter === "all" || c.status === statusFilter;
            const queryOk = !q || c.name.toLowerCase().includes(q) || c.referral_ref.toLowerCase().includes(q);
            return statusOk && queryOk;
        });
        const sorted = [...visible];
        sorted.sort((a, b) => {
            if (sort === "updated_asc") return new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
            if (sort === "name_asc") return a.name.localeCompare(b.name);
            if (sort === "name_desc") return b.name.localeCompare(a.name);
            if (sort === "status_asc") return a.status.localeCompare(b.status);
            return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        });
        return sorted;
    }, [cases, query, statusFilter, sort]);

    async function handleCreate(e: FormEvent) {
        e.preventDefault();
        const name = newName.trim();
        if (!name || name.length < 3) { setFormError("Case name must be at least 3 characters."); return; }
        setSubmitting(true);
        setFormError("");
        try {
            const payload: NewCasePayload = { name, referral_ref: newRef.trim() || undefined, notes: newNotes.trim() || undefined };
            const created = await createCase(payload);
            setCases((prev) => [created, ...prev]);
            setShowModal(false);
            setNewName(""); setNewRef(""); setNewNotes("");
            pushToast("success", `Case created: ${created.name}`);
            navigate(`/cases/${created.id}`);
        } catch (err) {
            pushToast("error", (err as Error).message);
        } finally {
            setSubmitting(false);
        }
    }

    // Keyboard: j/k to navigate, Enter to open
    const [focusIdx, setFocusIdx] = useState(-1);
    useEffect(() => {
        function onKey(e: KeyboardEvent) {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
            if (e.key === "n" && !showModal) { e.preventDefault(); setShowModal(true); return; }
            if (filtered.length === 0) return;
            if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); setFocusIdx((i) => Math.min(filtered.length - 1, i + 1)); }
            if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); setFocusIdx((i) => Math.max(0, i - 1)); }
            if (e.key === "Enter" && focusIdx >= 0 && focusIdx < filtered.length) { e.preventDefault(); navigate(`/cases/${filtered[focusIdx].id}`); }
        }
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [filtered, focusIdx, navigate, showModal]);

    return (
        <>
            <div className={styles.casesListHeader}>
                <h2>Cases</h2>
                <div className={styles.casesListActions}>
                    <div className={styles.viewToggle}>
                        <button className={`${styles.viewToggleBtn}${viewMode === "table" ? ` ${styles.active}` : ""}`} onClick={() => setViewMode("table")} title="Table view">{"\u2630"}</button>
                        <button className={`${styles.viewToggleBtn}${viewMode === "board" ? ` ${styles.active}` : ""}`} onClick={() => setViewMode("board")} title="Board view">{"\u25A6"}</button>
                    </div>
                    <Button variant="primary" onClick={() => setShowModal(true)}>+ New Case</Button>
                </div>
            </div>

            <div className={styles.casesListFilters}>
                <FormInput type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search cases..." aria-label="Search cases" />
                <FormSelect value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status">
                    <option value="all">All statuses</option>
                    {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
                </FormSelect>
                <FormSelect value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort cases">
                    <option value="updated_desc">Newest updated</option>
                    <option value="updated_asc">Oldest updated</option>
                    <option value="name_asc">Name A-Z</option>
                    <option value="name_desc">Name Z-A</option>
                    <option value="status_asc">Status A-Z</option>
                </FormSelect>
            </div>

            {loading ? (
                <StateBlock title="Loading cases..." detail="Fetching investigation queue from API." />
            ) : filtered.length === 0 ? (
                <StateBlock title="No cases match your filters." detail="Try clearing search or changing the status filter." />
            ) : viewMode === "board" ? (
                /* ── Kanban Board ── */
                <div className={styles.kanbanBoard}>
                    {KANBAN_COLUMNS.map((col) => {
                        const colCases = filtered.filter((c) => c.status === col);
                        return (
                            <div key={col} className={styles.kanbanColumn}>
                                <div className={styles.kanbanColumnHeader}>
                                    <span className={`${styles.statusPill} ${styles[`status${col.charAt(0).toUpperCase() + col.slice(1).toLowerCase()}`]}`}>{col}</span>
                                    <span className={styles.kanbanCount}>{colCases.length}</span>
                                </div>
                                <div className={styles.kanbanCards}>
                                    {colCases.map((c) => (
                                        <button
                                            key={c.id}
                                            className={styles.kanbanCard}
                                            onClick={() => navigate(`/cases/${c.id}`)}
                                        >
                                            <div className={styles.kanbanCardTop}>
                                                <span className={styles.kanbanSeverity}>{severityDot(severityMap[c.id])}</span>
                                                <span className={styles.kanbanCardName}>{c.name}</span>
                                            </div>
                                            {c.referral_ref && <span className={styles.kanbanCardRef}>Ref: {c.referral_ref}</span>}
                                            <div className={styles.kanbanCardMeta}>
                                                <span>{signalCounts[c.id] ?? 0} signals</span>
                                                <span>{relativeTime(c.updated_at)}</span>
                                            </div>
                                        </button>
                                    ))}
                                    {colCases.length === 0 && (
                                        <p className={styles.kanbanEmpty}>No cases</p>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            ) : (
                /* ── Table View ── */
                <div className={styles.casesTableWrap}>
                    <table className={styles.casesTable}>
                        <thead>
                            <tr>
                                <th style={{ width: 36 }}></th>
                                <th>Case Name</th>
                                <th>Status</th>
                                <th>Signals</th>
                                <th>Docs</th>
                                <th>Updated</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((c, idx) => (
                                <tr
                                    key={c.id}
                                    className={`${styles.casesTableRow}${idx === focusIdx ? ` ${styles.focused}` : ""}`}
                                    onClick={() => navigate(`/cases/${c.id}`)}
                                    tabIndex={0}
                                    onKeyDown={(e) => { if (e.key === "Enter") navigate(`/cases/${c.id}`); }}
                                >
                                    <td className={styles.severityCell}>{severityDot(severityMap[c.id])}</td>
                                    <td className={styles.nameCell}>
                                        <span className={styles.caseRowName}>{c.name}</span>
                                        {c.referral_ref && <span className={styles.caseRowRef}>Ref: {c.referral_ref}</span>}
                                    </td>
                                    <td><span className={`${styles.statusPill} ${styles[`status${c.status.charAt(0).toUpperCase() + c.status.slice(1).toLowerCase()}`]}`}>{c.status}</span></td>
                                    <td className={styles.numCell}>{signalCounts[c.id] ?? 0}</td>
                                    <td className={styles.numCell}>{"\u2014"}</td>
                                    <td className={styles.timeCell}>{relativeTime(c.updated_at)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <div className={styles.casesTableFooter}>
                        Showing {filtered.length} of {cases.length} cases
                    </div>
                </div>
            )}

            {/* New Case Modal */}
            {showModal && (
                <div className={styles.modalBackdrop} onClick={() => setShowModal(false)}>
                    <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <h3>Create New Case</h3>
                            <button className={styles.modalClose} onClick={() => setShowModal(false)}>{"\u2715"}</button>
                        </div>
                        <form onSubmit={handleCreate}>
                            <div className={styles.modalBody}>
                                <label className={styles.formLabel}>Case Name *</label>
                                <FormInput value={newName} onChange={(e) => { setNewName(e.target.value); setFormError(""); }} placeholder="Investigation name" autoFocus />
                                {formError && <p className={styles.fieldError}>{formError}</p>}
                                <label className={styles.formLabel}>Referral Reference</label>
                                <FormInput value={newRef} onChange={(e) => setNewRef(e.target.value)} placeholder="e.g. OAG-2026-0042" />
                                <label className={styles.formLabel}>Notes</label>
                                <FormTextarea value={newNotes} onChange={(e) => setNewNotes(e.target.value)} placeholder="Initial case notes" rows={3} />
                            </div>
                            <div className={styles.modalFooter}>
                                <Button variant="secondary" type="button" onClick={() => setShowModal(false)}>Cancel</Button>
                                <Button variant="primary" type="submit" disabled={submitting}>{submitting ? "Creating..." : "Create Case"}</Button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            <ToastStack toasts={toasts} onDismiss={(id) => setToasts((p) => p.filter((t) => t.id !== id))} />
        </>
    );
}
