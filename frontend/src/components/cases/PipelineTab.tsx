import { useCallback, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import type {
    FindingItem,
    FindingUpdatePayload,
    FindingStatus,
    EvidenceWeight,
} from "../../types";
import { PipelineStatusBar, PipelineStage } from "../ui/PipelineStatusBar";
import { SeverityBadge } from "../ui/SeverityBadge";
import { SlidePanel, SlidePanelSection } from "../ui/SlidePanel";
import { ResizablePanelLayout } from "../ui/ResizablePanelLayout";
import { FormSelect } from "../ui/FormSelect";
import { FormTextarea } from "../ui/FormTextarea";
import { Button } from "../ui/Button";
import { formatDate } from "../../utils/format";
import { AISummaryBadge } from "../ai/AISummaryBadge";
import { EmptyState } from "../ui/EmptyState";
import styles from "./PipelineTab.module.css";

/* ── Pipeline stages (derived from FindingStatus) ──────── */

const FINDING_STAGES: PipelineStage[] = [
    { key: "new", label: "New", icon: "⚡", count: 0, colorClass: "countNew" },
    { key: "needs_evidence", label: "Needs Evidence", icon: "🔍", count: 0, colorClass: "countReviewing" },
    { key: "confirmed", label: "Confirmed", icon: "✓", count: 0, colorClass: "countConfirmed" },
    { key: "dismissed", label: "Dismissed", icon: "✕", count: 0, colorClass: "countDraft" },
];

function statusToStage(status: FindingStatus): string {
    switch (status) {
        case "NEW": return "new";
        case "NEEDS_EVIDENCE": return "needs_evidence";
        case "CONFIRMED": return "confirmed";
        case "DISMISSED": return "dismissed";
        default: return "new";
    }
}

/* ── Evidence weight badge styling ──────────────────────── */

const WEIGHT_LABEL: Record<EvidenceWeight, string> = {
    SPECULATIVE: "Speculative",
    DIRECTIONAL: "Directional",
    DOCUMENTED: "Documented",
    TRACED: "Traced",
};

const WEIGHT_CLASS: Record<string, string> = {
    SPECULATIVE: styles.weightSpeculative ?? "",
    DIRECTIONAL: styles.weightDirectional ?? "",
    DOCUMENTED: styles.weightDocumented ?? "",
    TRACED: styles.weightTraced ?? "",
};

/* ── Severity badge class ────────────────────────────────── */

const SEV_CLASS: Record<string, string> = {
    CRITICAL: styles.sevCritical,
    HIGH: styles.sevHigh,
    MEDIUM: styles.sevMedium,
    LOW: styles.sevLow,
    INFORMATIONAL: styles.sevInfo,
};

const CARD_SEV_CLASS: Record<string, string> = {
    CRITICAL: styles.cardSevCritical,
    HIGH: styles.cardSevHigh,
    MEDIUM: styles.cardSevMedium,
    LOW: styles.cardSevLow,
    INFORMATIONAL: styles.cardSevInfo,
};

/* ── Main component ──────────────────────────────────────── */

export function PipelineTab() {
    const ctx = useOutletContext<CaseDetailContext>();
    const {
        findings,
        savingFindingId,
        onUpdateFinding,
        onDeleteFinding,
        onReevaluateFindings,
        reevaluatingFindings,
        pushToast,
    } = ctx;

    const [activeStage, setActiveStage] = useState<string | null>(null);
    const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
    const [severityFilter, setSeverityFilter] = useState("all");
    const [weightFilter, setWeightFilter] = useState("all");

    /* ── Stage counts for status bar ─────────────────────── */

    const stages: PipelineStage[] = useMemo(() => {
        const counts: Record<string, number> = { new: 0, needs_evidence: 0, confirmed: 0, dismissed: 0 };
        for (const f of findings) {
            const stage = statusToStage(f.status);
            if (counts[stage] !== undefined) counts[stage]++;
        }
        return FINDING_STAGES.map((s) => ({ ...s, count: counts[s.key] ?? 0 }));
    }, [findings]);

    /* ── Filtered items ──────────────────────────────────── */

    const filteredFindings = useMemo(() => {
        return findings
            .filter((f) => {
                if (activeStage && statusToStage(f.status) !== activeStage) return false;
                if (severityFilter !== "all" && f.severity !== severityFilter) return false;
                if (weightFilter !== "all" && f.evidence_weight !== weightFilter) return false;
                return true;
            })
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    }, [findings, activeStage, severityFilter, weightFilter]);

    /* ── Selected finding for detail panel ────────────────── */

    const selectedFinding = useMemo(
        () => filteredFindings.find((f) => f.id === selectedFindingId) ?? null,
        [filteredFindings, selectedFindingId]
    );

    /* ── Quick actions ───────────────────────────────────── */

    const handleNeedsEvidence = useCallback(
        (id: string) => {
            onUpdateFinding(id, { status: "NEEDS_EVIDENCE" });
            pushToast("success", "Marked as needs evidence.");
        },
        [onUpdateFinding, pushToast]
    );

    const handleConfirm = useCallback(
        (id: string) => {
            onUpdateFinding(id, { status: "CONFIRMED" });
            pushToast("success", "Finding confirmed for referral.");
        },
        [onUpdateFinding, pushToast]
    );

    const handleDismiss = useCallback(
        (id: string) => {
            onUpdateFinding(id, { status: "DISMISSED", investigator_note: "Dismissed from pipeline" });
            pushToast("success", "Finding dismissed.");
        },
        [onUpdateFinding, pushToast]
    );

    /* ── Render card ─────────────────────────────────────── */

    function renderCard(finding: FindingItem, cardIndex = 0) {
        const isSelected = selectedFindingId === finding.id;
        const isSaving = savingFindingId === finding.id;
        const stage = statusToStage(finding.status);

        return (
            <div
                key={finding.id}
                className={`${styles.card} ${CARD_SEV_CLASS[finding.severity] ?? ""} ${isSelected ? styles.cardSelected : ""}`}
                onClick={() => setSelectedFindingId(isSelected ? null : finding.id)}
                style={{
                    ...(isSaving ? { opacity: 0.6, pointerEvents: "none" as const } : {}),
                    ...({ "--card-i": cardIndex } as React.CSSProperties),
                }}
            >
                {/* Header */}
                <div className={styles.cardHeader}>
                    <span className={styles.cardRuleId}>{finding.rule_id || "MANUAL"}</span>
                    <span className={`${styles.sevBadge} ${SEV_CLASS[finding.severity] ?? styles.sevInfo}`}>
                        {finding.severity}
                    </span>
                    <span
                        className={`${styles.weightBadge ?? ""} ${WEIGHT_CLASS[finding.evidence_weight] ?? ""}`}
                        title={`Evidence: ${WEIGHT_LABEL[finding.evidence_weight] ?? finding.evidence_weight}`}
                    >
                        {WEIGHT_LABEL[finding.evidence_weight] ?? finding.evidence_weight}
                    </span>
                    <span className={styles.cardTime}>{formatDate(finding.created_at)}</span>
                </div>

                {/* Body */}
                <div className={styles.cardBody}>
                    <strong>{finding.title}</strong>
                    {finding.description && (
                        <span style={{ marginLeft: "0.5em", color: "var(--text-soft)" }}>
                            {finding.description.length > 120
                                ? finding.description.slice(0, 120) + "..."
                                : finding.description}
                        </span>
                    )}
                </div>

                {/* Narrative preview */}
                {finding.narrative && (
                    <div className={styles.narrativePreview}>
                        {finding.narrative.length > 200
                            ? finding.narrative.slice(0, 200) + "..."
                            : finding.narrative}
                    </div>
                )}

                {/* Legal references */}
                {finding.legal_refs.length > 0 && (
                    <div className={styles.legalRefs}>
                        {finding.legal_refs.map((ref) => (
                            <span key={ref} className={styles.legalRef}>{ref}</span>
                        ))}
                    </div>
                )}

                {/* Trigger document link */}
                {(finding.trigger_doc_filename || finding.document_links.length > 0) && (
                    <div style={{
                        fontSize: "var(--text-xs)",
                        color: "var(--accent)",
                        marginTop: "0.25rem",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.25rem",
                    }}>
                        📄 {finding.trigger_doc_filename
                            ?? finding.document_links[0]?.document_filename
                            ?? "Linked document"}
                        {finding.document_links.length > 1 && (
                            <span style={{ color: "var(--text-soft)" }}>
                                {` +${finding.document_links.length - 1} more`}
                            </span>
                        )}
                    </div>
                )}

                {/* Source badge */}
                {finding.source === "MANUAL" && (
                    <span style={{
                        fontSize: "0.65rem",
                        padding: "0.1rem 0.3rem",
                        borderRadius: "var(--radius-sm)",
                        background: "rgba(139, 92, 246, 0.1)",
                        color: "var(--text-soft)",
                    }}>
                        Manual
                    </span>
                )}

                {/* AI summary badge */}
                <div className={styles.cardAiBadge} onClick={(e) => e.stopPropagation()}>
                    <AISummaryBadge
                        caseId={ctx.caseId}
                        targetType="finding"
                        targetId={finding.id}
                        compact
                    />
                </div>

                {/* Quick actions */}
                <div className={styles.cardFooter}>
                    {stage === "new" && (
                        <>
                            <button
                                className={styles.quickAction}
                                onClick={(e) => { e.stopPropagation(); handleNeedsEvidence(finding.id); }}
                            >
                                Needs Evidence
                            </button>
                            <button
                                className={styles.quickAction}
                                onClick={(e) => { e.stopPropagation(); handleConfirm(finding.id); }}
                            >
                                Confirm
                            </button>
                            <button
                                className={styles.quickActionDanger}
                                onClick={(e) => { e.stopPropagation(); handleDismiss(finding.id); }}
                            >
                                Dismiss
                            </button>
                        </>
                    )}
                    {stage === "needs_evidence" && (
                        <>
                            <button
                                className={styles.quickAction}
                                onClick={(e) => { e.stopPropagation(); handleConfirm(finding.id); }}
                            >
                                Confirm
                            </button>
                            <button
                                className={styles.quickActionDanger}
                                onClick={(e) => { e.stopPropagation(); handleDismiss(finding.id); }}
                            >
                                Dismiss
                            </button>
                        </>
                    )}
                </div>
            </div>
        );
    }

    /* ── Detail panel content ────────────────────────────── */

    function renderDetailPanel() {
        if (!selectedFinding) return null;
        return (
            <FindingDetailPanel
                finding={selectedFinding}
                onUpdate={onUpdateFinding}
                onDelete={onDeleteFinding}
                saving={savingFindingId === selectedFinding.id}
                pushToast={pushToast}
            />
        );
    }

    /* ── Render ──────────────────────────────────────────── */

    return (
        <div className={styles.pipeline}>
            {/* Status bar */}
            <PipelineStatusBar
                stages={stages}
                activeStage={activeStage}
                onStageClick={(key) => setActiveStage((prev) => (prev === key ? null : key))}
            />

            {/* Toolbar */}
            <div className={styles.toolbar}>
                <span className={styles.toolbarLabel}>Severity:</span>
                <FormSelect
                    value={severityFilter}
                    onChange={(e) => setSeverityFilter(e.target.value)}
                    aria-label="Filter by severity"
                >
                    <option value="all">All</option>
                    <option value="CRITICAL">Critical</option>
                    <option value="HIGH">High</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="LOW">Low</option>
                    <option value="INFORMATIONAL">Info</option>
                </FormSelect>
                <span className={styles.toolbarLabel} style={{ marginLeft: "0.5rem" }}>Evidence:</span>
                <FormSelect
                    value={weightFilter}
                    onChange={(e) => setWeightFilter(e.target.value)}
                    aria-label="Filter by evidence weight"
                >
                    <option value="all">All</option>
                    <option value="SPECULATIVE">Speculative</option>
                    <option value="DIRECTIONAL">Directional</option>
                    <option value="DOCUMENTED">Documented</option>
                    <option value="TRACED">Traced</option>
                </FormSelect>
                <span className={styles.toolbarSpacer} />
                <Button
                    variant="secondary"
                    size="sm"
                    onClick={onReevaluateFindings}
                    disabled={reevaluatingFindings}
                >
                    {reevaluatingFindings ? "Re-evaluating..." : "Re-evaluate Findings"}
                </Button>
                <span className={styles.toolbarCount}>
                    {filteredFindings.length} finding{filteredFindings.length !== 1 ? "s" : ""}
                </span>
            </div>

            {/* Card list + detail panel */}
            <ResizablePanelLayout
                panelContent={renderDetailPanel()}
                panelOpen={!!selectedFinding}
                panelWidth={400}
                onPanelClose={() => setSelectedFindingId(null)}
            >
                <div className={styles.cardList}>
                    {filteredFindings.length === 0 ? (
                        <EmptyState
                            icon="🔍"
                            title={activeStage
                                ? `No findings at the "${stages.find((s) => s.key === activeStage)?.label ?? activeStage}" stage`
                                : "No findings yet"}
                            detail="Upload documents and run signal analysis to detect findings, or create a finding manually."
                        />
                    ) : (
                        filteredFindings.map((f, idx) => renderCard(f, idx))
                    )}
                </div>
            </ResizablePanelLayout>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   Finding Detail Panel (slide-in)
   ═══════════════════════════════════════════════════════════ */

function FindingDetailPanel({
    finding,
    onUpdate,
    onDelete,
    saving,
    pushToast,
}: {
    finding: FindingItem;
    onUpdate: (id: string, payload: FindingUpdatePayload) => void;
    onDelete: (id: string) => void;
    saving: boolean;
    pushToast: (tone: "error" | "success", msg: string) => void;
}) {
    const [title, setTitle] = useState(finding.title);
    const [narrative, setNarrative] = useState(finding.narrative);
    const [status, setStatus] = useState<FindingStatus>(finding.status);
    const [weight, setWeight] = useState<EvidenceWeight>(finding.evidence_weight);
    const [note, setNote] = useState(finding.investigator_note);

    const hasChanges =
        title !== finding.title ||
        narrative !== finding.narrative ||
        status !== finding.status ||
        weight !== finding.evidence_weight ||
        note !== finding.investigator_note;

    return (
        <SlidePanel
            title={finding.title}
            subtitle={`Finding · ${finding.status} · ${finding.evidence_weight}`}
            onClose={() => {}}
        >
            <SlidePanelSection title="Overview" defaultOpen>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.5rem", flexWrap: "wrap" }}>
                    <SeverityBadge severity={finding.severity as "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL"} />
                    <span style={{
                        fontSize: "0.65rem",
                        padding: "0.1rem 0.4rem",
                        borderRadius: "var(--radius-sm)",
                        background: "rgba(69, 137, 255, 0.1)",
                        color: "var(--accent)",
                        fontWeight: 500,
                    }}>
                        {WEIGHT_LABEL[finding.evidence_weight] ?? finding.evidence_weight}
                    </span>
                    {finding.source === "MANUAL" && (
                        <span style={{
                            fontSize: "0.65rem",
                            padding: "0.1rem 0.3rem",
                            borderRadius: "var(--radius-sm)",
                            background: "rgba(139, 92, 246, 0.1)",
                            color: "var(--text-soft)",
                        }}>
                            Manual
                        </span>
                    )}
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)" }}>
                        {formatDate(finding.created_at)}
                    </span>
                </div>
                <p style={{ fontSize: "var(--text-sm)", color: "var(--text-main)", margin: "0.5rem 0" }}>
                    {finding.description}
                </p>
                {finding.legal_refs.length > 0 && (
                    <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
                        {finding.legal_refs.map((ref) => (
                            <span
                                key={ref}
                                style={{
                                    fontSize: "0.65rem",
                                    padding: "0.1rem 0.4rem",
                                    borderRadius: "var(--radius-sm)",
                                    background: "rgba(69, 137, 255, 0.1)",
                                    color: "var(--accent)",
                                    fontWeight: 500,
                                }}
                            >
                                {ref}
                            </span>
                        ))}
                    </div>
                )}
                {finding.evidence_snapshot && Object.keys(finding.evidence_snapshot).length > 0 && (
                    <details style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)" }}>
                        <summary style={{ cursor: "pointer", marginBottom: "0.25rem" }}>Evidence Snapshot</summary>
                        <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.7rem" }}>
                            {JSON.stringify(finding.evidence_snapshot, null, 2)}
                        </pre>
                    </details>
                )}
            </SlidePanelSection>

            <SlidePanelSection title="Edit" defaultOpen>
                <label style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", display: "block", marginBottom: "0.25rem" }}>
                    Title
                </label>
                <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    style={{
                        width: "100%",
                        padding: "0.4rem 0.6rem",
                        fontSize: "var(--text-sm)",
                        background: "var(--surface-2)",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "var(--radius-sm)",
                        color: "var(--text-main)",
                        marginBottom: "0.5rem",
                    }}
                />
                <label style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", display: "block", marginBottom: "0.25rem" }}>
                    Narrative
                </label>
                <FormTextarea
                    value={narrative}
                    onChange={(e) => setNarrative(e.target.value)}
                    rows={6}
                    placeholder="Investigation narrative..."
                />
                <label style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", display: "block", margin: "0.5rem 0 0.25rem" }}>
                    Status
                </label>
                <FormSelect value={status} onChange={(e) => setStatus(e.target.value as FindingStatus)}>
                    <option value="NEW">New</option>
                    <option value="NEEDS_EVIDENCE">Needs Evidence</option>
                    <option value="CONFIRMED">Confirmed</option>
                    <option value="DISMISSED">Dismissed</option>
                </FormSelect>
                <label style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", display: "block", margin: "0.5rem 0 0.25rem" }}>
                    Evidence Weight
                </label>
                <FormSelect value={weight} onChange={(e) => setWeight(e.target.value as EvidenceWeight)}>
                    <option value="SPECULATIVE">Speculative</option>
                    <option value="DIRECTIONAL">Directional</option>
                    <option value="DOCUMENTED">Documented</option>
                    <option value="TRACED">Traced</option>
                </FormSelect>
                <label style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", display: "block", margin: "0.5rem 0 0.25rem" }}>
                    Investigator Note
                </label>
                <FormTextarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={3}
                    placeholder="Your analysis notes..."
                />
                <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.4rem" }}>
                    <Button
                        variant="primary"
                        size="sm"
                        disabled={saving || !hasChanges}
                        onClick={() => {
                            onUpdate(finding.id, { title, narrative, status, evidence_weight: weight, investigator_note: note });
                            pushToast("success", "Finding updated.");
                        }}
                    >
                        {saving ? "Saving..." : "Save Changes"}
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => onDelete(finding.id)}>
                        Delete
                    </Button>
                </div>
            </SlidePanelSection>

            {/* Linked documents */}
            <SlidePanelSection
                title="Source Documents"
                defaultOpen
                count={finding.document_links.length + (finding.trigger_doc_id && !finding.document_links.some(dl => dl.document_id === finding.trigger_doc_id) ? 1 : 0)}
            >
                {/* Show trigger doc if not already in document_links */}
                {finding.trigger_doc_id && finding.trigger_doc_filename && !finding.document_links.some(dl => dl.document_id === finding.trigger_doc_id) && (
                    <div style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        padding: "0.35rem 0.5rem",
                        margin: "0.2rem 0",
                        borderRadius: "var(--radius-sm)",
                        background: "rgba(69, 137, 255, 0.08)",
                        fontSize: "var(--text-xs)",
                    }}>
                        <span>📄</span>
                        <span style={{ color: "var(--accent)", fontWeight: 500 }}>
                            {finding.trigger_doc_filename}
                        </span>
                        <span style={{ color: "var(--text-soft)", marginLeft: "auto" }}>
                            Trigger
                        </span>
                    </div>
                )}
                {finding.document_links.map((dl, i) => (
                    <div
                        key={i}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem",
                            padding: "0.35rem 0.5rem",
                            margin: "0.2rem 0",
                            borderRadius: "var(--radius-sm)",
                            background: "rgba(69, 137, 255, 0.08)",
                            fontSize: "var(--text-xs)",
                        }}
                    >
                        <span>📄</span>
                        <span style={{ color: "var(--accent)", fontWeight: 500 }}>
                            {dl.document_filename || `Doc ${dl.document_id.slice(0, 8)}`}
                        </span>
                        {dl.page_reference && (
                            <span style={{ color: "var(--text-soft)" }}>
                                p. {dl.page_reference}
                            </span>
                        )}
                        {dl.context_note && (
                            <span style={{ color: "var(--text-soft)", marginLeft: "auto" }}>
                                {dl.context_note}
                            </span>
                        )}
                    </div>
                ))}
                {finding.document_links.length === 0 && !finding.trigger_doc_id && (
                    <p style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", margin: "0.2rem 0", fontStyle: "italic" }}>
                        No documents linked yet. Upload documents and re-evaluate findings.
                    </p>
                )}
            </SlidePanelSection>

            {/* Linked entities */}
            {finding.entity_links.length > 0 && (
                <SlidePanelSection
                    title="Linked Entities"
                    defaultOpen
                    count={finding.entity_links.length}
                >
                    {finding.entity_links.map((el, i) => (
                        <div
                            key={i}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "0.4rem",
                                padding: "0.35rem 0.5rem",
                                margin: "0.2rem 0",
                                borderRadius: "var(--radius-sm)",
                                background: "rgba(69, 137, 255, 0.08)",
                                fontSize: "var(--text-xs)",
                            }}
                        >
                            <span>{el.entity_type === "person" ? "👤" : el.entity_type === "organization" ? "🏢" : "📍"}</span>
                            <span style={{ color: "var(--text-main)" }}>
                                {el.entity_type}: {el.entity_id.slice(0, 8)}
                            </span>
                            {el.context_note && (
                                <span style={{ color: "var(--text-soft)", marginLeft: "auto" }}>
                                    {el.context_note}
                                </span>
                            )}
                        </div>
                    ))}
                </SlidePanelSection>
            )}
        </SlidePanel>
    );
}
