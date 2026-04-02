import { useCallback, useMemo, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import { SignalItem } from "../../types";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { FormSelect } from "../ui/FormSelect";
import { FormTextarea } from "../ui/FormTextarea";
import { formatDate } from "../../utils/format";
import { SIGNAL_CITATIONS } from "../../data/legalCitations";
import {
    SIGNAL_CHECKLISTS,
    getChecklistItemChecked,
    setChecklistItemChecked,
} from "../../data/investigationChecklists";
import styles from "./SignalsTab.module.css";

interface TriageDraft {
    status: string;
    note: string;
}

const QUICK_STATUSES = ["OPEN", "REVIEWED", "DISMISSED"];

export function SignalsTab() {
    const { caseId } = useParams<{ caseId: string }>();
    const {
        signals,
        onUpdateSignal,
        savingSignalId,
        onReevaluateSignals,
        reevaluatingSignals,
    } = useOutletContext<CaseDetailContext>();

    const [severityFilter, setSeverityFilter] = useState("all");
    const [statusFilter, setStatusFilter] = useState("all");
    const [activeSignalId, setActiveSignalId] = useState<string | null>(null);
    const [drafts, setDrafts] = useState<Record<string, TriageDraft>>({});
    // Incremented to force re-render after checklist localStorage writes
    const [, setChecklistTick] = useState(0);

    const severities = useMemo(
        () => Array.from(new Set(signals.map((s) => s.severity))).sort(),
        [signals],
    );
    const statuses = useMemo(
        () => Array.from(new Set(signals.map((s) => s.status))).sort(),
        [signals],
    );

    const filtered = useMemo(() => {
        return signals.filter((s) => {
            if (severityFilter !== "all" && s.severity !== severityFilter) return false;
            if (statusFilter !== "all" && s.status !== statusFilter) return false;
            return true;
        });
    }, [signals, severityFilter, statusFilter]);

    function getDraft(signal: SignalItem): TriageDraft {
        return drafts[signal.id] ?? { status: signal.status, note: signal.investigator_note };
    }

    function setDraft(signalId: string, draft: TriageDraft) {
        setDrafts((prev) => ({ ...prev, [signalId]: draft }));
    }

    function handleSave(signal: SignalItem) {
        const draft = getDraft(signal);
        onUpdateSignal(signal.id, {
            status: draft.status,
            investigator_note: draft.note,
        });
    }

    const handleChecklistToggle = useCallback(
        (ruleId: string, itemId: string, checked: boolean) => {
            if (!caseId) return;
            setChecklistItemChecked(caseId, ruleId, itemId, checked);
            setChecklistTick((v) => v + 1);
        },
        [caseId],
    );

    return (
        <>
            <article className="info-card">
                <div className="card-toolbar">
                    <h3>Signals ({filtered.length}/{signals.length})</h3>
                    <div className="compact-filters">
                        <FormSelect
                            value={severityFilter}
                            onChange={(e) => setSeverityFilter(e.target.value)}
                            aria-label="Filter signals by severity"
                        >
                            <option value="all">All severity</option>
                            {severities.map((s) => (
                                <option key={s} value={s}>{s}</option>
                            ))}
                        </FormSelect>
                        <FormSelect
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                            aria-label="Filter signals by status"
                        >
                            <option value="all">All status</option>
                            {statuses.map((s) => (
                                <option key={s} value={s}>{s}</option>
                            ))}
                        </FormSelect>
                    </div>
                </div>

                {filtered.length === 0 ? (
                    <EmptyState
                        title={
                            signals.length === 0
                                ? "No signals detected for this case yet."
                                : "No signals match the current filters."
                        }
                        detail={
                            signals.length === 0
                                ? "When detection rules flag activity, triage items will show up here for review."
                                : "Try broadening severity or status filters to show more triage items."
                        }
                    />
                ) : (
                    <ul className={styles.signalList}>
                        {filtered.map((signal) => {
                            const draft = getDraft(signal);
                            const isActive = signal.id === activeSignalId;
                            const citations = SIGNAL_CITATIONS[signal.rule_id] ?? [];
                            const checklist = SIGNAL_CHECKLISTS[signal.rule_id] ?? [];
                            return (
                                <li key={signal.id} className={styles.signalListItem}>
                                    <div
                                        className={isActive ? `${styles.signalCard} ${styles.activeSignal}` : styles.signalCard}
                                        role="button"
                                        tabIndex={0}
                                        onClick={() => setActiveSignalId(isActive ? null : signal.id)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter" || e.key === " ") {
                                                e.preventDefault();
                                                setActiveSignalId(isActive ? null : signal.id);
                                            }
                                        }}
                                        aria-label={`Focus signal ${signal.title}`}
                                    >
                                        <strong>{signal.title}</strong>
                                        <p className={styles.signalSubhead}>{signal.rule_id}</p>
                                        <p>{signal.description}</p>
                                        <p className={styles.signalSubhead}>Detected: {formatDate(signal.detected_at)}</p>

                                        {/* Legal citations — always visible */}
                                        {citations.length > 0 && (
                                            <div className={styles.legalCitations}>
                                                <span className={styles.citationsLabel}>{"\u2696\uFE0F"} Legal basis:</span>
                                                {citations.map((cite) => (
                                                    <a
                                                        key={cite.code}
                                                        href={cite.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className={styles.citationLink}
                                                        title={cite.title}
                                                        onClick={(e) => e.stopPropagation()}
                                                    >
                                                        {cite.code}
                                                    </a>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                    <div className={styles.signalBadges}>
                                        <span className={`${styles.tag} ${styles[signal.severity.toLowerCase()]}`}>
                                            {signal.severity}
                                        </span>
                                        <span className={`${styles.tag} ${styles.neutral}`}>{signal.status}</span>

                                        {isActive && (
                                            <>
                                                {/* Triage controls */}
                                                <div className={styles.triageQuickActions}>
                                                    {QUICK_STATUSES.map((qs) => (
                                                        <Button
                                                            key={`${signal.id}-${qs}`}
                                                            className={`${styles.triageChip} ${draft.status === qs ? styles.active : ""}`}
                                                            variant="secondary"
                                                            onClick={() => setDraft(signal.id, { ...draft, status: qs })}
                                                            aria-label={`Set signal status to ${qs}`}
                                                        >
                                                            {qs}
                                                        </Button>
                                                    ))}
                                                </div>
                                                <FormSelect
                                                    className={styles.triageSelect}
                                                    value={draft.status}
                                                    onChange={(e) => setDraft(signal.id, { ...draft, status: e.target.value })}
                                                >
                                                    {statuses.map((s) => (
                                                        <option key={s} value={s}>{s}</option>
                                                    ))}
                                                </FormSelect>
                                                <FormTextarea
                                                    className={styles.triageNote}
                                                    placeholder="Investigator note"
                                                    value={draft.note}
                                                    onChange={(e) => setDraft(signal.id, { ...draft, note: e.target.value })}
                                                    rows={2}
                                                />
                                                <Button
                                                    className={styles.triageSave}
                                                    onClick={() => handleSave(signal)}
                                                    disabled={savingSignalId === signal.id}
                                                >
                                                    {savingSignalId === signal.id ? "Saving..." : "Save"}
                                                </Button>

                                                {/* Investigation checklist */}
                                                {checklist.length > 0 && caseId && (
                                                    <div className={styles.investigationChecklist}>
                                                        <p className={styles.checklistHeader}>
                                                            {"\uD83D\uDCCB"} Investigators typically check:
                                                        </p>
                                                        <ul className={styles.checklistItems}>
                                                            {checklist.map((item) => {
                                                                const checked = getChecklistItemChecked(
                                                                    caseId,
                                                                    signal.rule_id,
                                                                    item.id,
                                                                );
                                                                return (
                                                                    <li key={item.id} className={styles.checklistItem}>
                                                                        <label>
                                                                            <input
                                                                                type="checkbox"
                                                                                checked={checked}
                                                                                onChange={(e) =>
                                                                                    handleChecklistToggle(
                                                                                        signal.rule_id,
                                                                                        item.id,
                                                                                        e.target.checked,
                                                                                    )
                                                                                }
                                                                            />
                                                                            <span className={checked ? styles.checklistDone : ""}>
                                                                                {item.label}
                                                                            </span>
                                                                        </label>
                                                                    </li>
                                                                );
                                                            })}
                                                        </ul>
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </article>

            {/* Re-evaluate bar */}
            <div className={styles.reevaluateBar}>
                <Button
                    variant="secondary"
                    disabled={reevaluatingSignals}
                    onClick={onReevaluateSignals}
                >
                    {reevaluatingSignals ? "Re-evaluating..." : "Re-evaluate Signals"}
                </Button>
                <span className={styles.reevaluateHint}>
                    Re-run all signal rules against this case&apos;s documents and entities.
                </span>
            </div>
        </>
    );
}
