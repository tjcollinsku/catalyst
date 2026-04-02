import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import { FindingItem, FindingStatus } from "../../types";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { FormSelect } from "../ui/FormSelect";
import { formatDate } from "../../utils/format";
import styles from "./FindingsTab.module.css";

const STATUS_OPTIONS: FindingStatus[] = ["DRAFT", "REVIEWED", "INCLUDED_IN_MEMO", "EXCLUDED", "REFERRED"];

export function FindingsTab() {
    const {
        findings,
        loadingFindings,
        savingFindingId,
        onUpdateFinding,
        onDeleteFinding,
    } = useOutletContext<CaseDetailContext>();

    const [statusFilter, setStatusFilter] = useState("all");
    const [expandedId, setExpandedId] = useState<string | null>(null);

    const filtered = statusFilter === "all"
        ? findings
        : findings.filter((f) => f.status === statusFilter);

    if (loadingFindings) {
        return <p className={styles.loadingText}>Loading findings...</p>;
    }

    return (
        <>
            <article className="info-card">
                <div className="card-toolbar">
                    <h3>Findings ({filtered.length}/{findings.length})</h3>
                    <div className="compact-filters">
                        <FormSelect
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                            aria-label="Filter findings by status"
                        >
                            <option value="all">All statuses</option>
                            {STATUS_OPTIONS.map((s) => (
                                <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                            ))}
                        </FormSelect>
                    </div>
                </div>

                {filtered.length === 0 ? (
                    <EmptyState
                        title={
                            findings.length === 0
                                ? "No findings recorded for this case yet."
                                : "No findings match the current filter."
                        }
                        detail={
                            findings.length === 0
                                ? "Findings are created from confirmed detections. Review the Detections tab to escalate items."
                                : "Try changing the status filter to see other findings."
                        }
                    />
                ) : (
                    <div className={styles.findingsList}>
                        {filtered.map((finding) => (
                            <FindingCard
                                key={finding.id}
                                finding={finding}
                                expanded={expandedId === finding.id}
                                onToggle={() => setExpandedId(expandedId === finding.id ? null : finding.id)}
                                saving={savingFindingId === finding.id}
                                onUpdateStatus={(status) =>
                                    onUpdateFinding(finding.id, { status })
                                }
                                onDelete={() => onDeleteFinding(finding.id)}
                            />
                        ))}
                    </div>
                )}
            </article>
        </>
    );
}

/* ── Individual finding card ──────────────────────────────── */

interface FindingCardProps {
    finding: FindingItem;
    expanded: boolean;
    onToggle: () => void;
    saving: boolean;
    onUpdateStatus: (status: FindingStatus) => void;
    onDelete: () => void;
}

function FindingCard({ finding, expanded, onToggle, saving, onUpdateStatus, onDelete }: FindingCardProps) {
    const severityClass = styles[`findingCard${finding.severity.charAt(0) + finding.severity.slice(1).toLowerCase()}`];
    const badgeClass = styles[`severityBadge${finding.severity.charAt(0) + finding.severity.slice(1).toLowerCase()}`];
    const statusClass = styles[`statusPill${finding.status.toLowerCase().replace(/_/g, " ").split(" ").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join("")}`];

    return (
        <div className={`${styles.findingCard} ${severityClass}`}>
            <div className={styles.findingHeader} onClick={onToggle} role="button" tabIndex={0}
                 onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onToggle(); }}>
                <div className={styles.findingTitleRow}>
                    <span className={`${styles.severityBadge} ${badgeClass}`}>
                        {finding.severity}
                    </span>
                    <span className={styles.findingTitle}>{finding.title}</span>
                    <span className={`${styles.statusPill} ${statusClass}`}>
                        {finding.status.replace(/_/g, " ")}
                    </span>
                </div>
                <div className={styles.findingMeta}>
                    <span>Confidence: {finding.confidence}</span>
                    {finding.signal_rule_id && <span>Rule: {finding.signal_rule_id}</span>}
                    <span>Created: {formatDate(finding.created_at)}</span>
                </div>
            </div>

            {expanded && (
                <div className={styles.findingBody}>
                    <div className={styles.findingNarrative}>
                        <h4>Narrative</h4>
                        <p>{finding.narrative || "No narrative provided."}</p>
                    </div>

                    {finding.legal_refs.length > 0 && (
                        <div className={styles.findingLegalRefs}>
                            <h4>Legal References</h4>
                            <ul>
                                {finding.legal_refs.map((ref, i) => (
                                    <li key={i}>{ref}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {finding.entity_links.length > 0 && (
                        <div className={styles.findingLinks}>
                            <h4>Linked Entities ({finding.entity_links.length})</h4>
                            <ul>
                                {finding.entity_links.map((el) => (
                                    <li key={el.id}>
                                        {el.entity_type}: {el.entity_id}
                                        {el.context_note && ` — ${el.context_note}`}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className={styles.findingActions}>
                        <FormSelect
                            value={finding.status}
                            onChange={(e) => onUpdateStatus(e.target.value as FindingStatus)}
                            disabled={saving}
                            aria-label="Change finding status"
                        >
                            {STATUS_OPTIONS.map((s) => (
                                <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                            ))}
                        </FormSelect>
                        <Button
                            variant="secondary"
                            disabled={saving}
                            onClick={onDelete}
                        >
                            {saving ? "Saving..." : "Delete"}
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}
