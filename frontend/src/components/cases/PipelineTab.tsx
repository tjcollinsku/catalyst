import { useCallback, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import type {
    SignalItem,
    DetectionItem,
    FindingItem,
    DetectionUpdatePayload,
    FindingUpdatePayload,
    SignalUpdatePayload,
} from "../../types";
import { PipelineStatusBar, DEFAULT_STAGES, PipelineStage } from "../ui/PipelineStatusBar";
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

/* ── Pipeline stage mapping ──────────────────────────────── */

type PipelineItemType = "signal" | "detection" | "finding";

interface PipelineItem {
    id: string;
    type: PipelineItemType;
    stage: string;       // pipeline stage key
    severity: string;
    title: string;
    subtitle: string;
    date: string;
    raw: SignalItem | DetectionItem | FindingItem;
}

function mapSignalToStage(s: SignalItem): string {
    if (s.status === "OPEN") return "new";
    if (s.status === "UNDER_REVIEW") return "reviewing";
    if (s.status === "CONFIRMED" || s.status === "ESCALATED") return "confirmed";
    if (s.status === "DISMISSED") return "dismissed"; // won't show in pipeline
    return "new";
}

function mapDetectionToStage(d: DetectionItem): string {
    if (d.status === "CONFIRMED" || d.status === "REVIEWED") return "confirmed";
    if (d.status === "ESCALATED") return "draft";
    if (d.status === "OPEN") return "reviewing";
    return "confirmed";
}

function mapFindingToStage(f: FindingItem): string {
    if (f.status === "DRAFT") return "draft";
    if (f.status === "REVIEWED" || f.status === "INCLUDED_IN_MEMO" || f.status === "REFERRED") return "published";
    if (f.status === "EXCLUDED") return "dismissed";
    return "draft";
}

/* ── Confidence bar color ────────────────────────────────── */

function confColor(v: number): string {
    if (v >= 0.7) return "#22c55e";
    if (v >= 0.4) return "#fbbf24";
    return "#ef4444";
}

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
        signals,
        onUpdateSignal,
        savingSignalId,
        onReevaluateSignals,
        reevaluatingSignals,
        detections,
        savingDetectionId,
        onUpdateDetection,
        onDeleteDetection,
        findings,
        savingFindingId,
        onCreateFinding,
        onUpdateFinding,
        onDeleteFinding,
        pushToast,
    } = ctx;

    const [activeStage, setActiveStage] = useState<string | null>(null);
    const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
    const [severityFilter, setSeverityFilter] = useState("all");

    /* ── Build unified pipeline items ────────────────────── */

    const allItems: PipelineItem[] = useMemo(() => {
        const items: PipelineItem[] = [];

        for (const s of signals) {
            const stage = mapSignalToStage(s);
            if (stage === "dismissed") continue;
            items.push({
                id: `signal-${s.id}`,
                type: "signal",
                stage,
                severity: s.severity,
                title: s.rule_id,
                subtitle: s.detected_summary || s.description || s.title,
                date: s.detected_at,
                raw: s,
            });
        }

        for (const d of detections) {
            const stage = mapDetectionToStage(d);
            if (stage === "dismissed") continue;
            items.push({
                id: `detection-${d.id}`,
                type: "detection",
                stage,
                severity: d.severity,
                title: d.signal_type,
                subtitle: String(d.evidence_snapshot?.summary ?? d.signal_type),
                date: d.detected_at,
                raw: d,
            });
        }

        for (const f of findings) {
            const stage = mapFindingToStage(f);
            if (stage === "dismissed") continue;
            items.push({
                id: `finding-${f.id}`,
                type: "finding",
                stage,
                severity: f.severity,
                title: f.title,
                subtitle: f.narrative,
                date: f.created_at,
                raw: f,
            });
        }

        // Sort by date descending
        items.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
        return items;
    }, [signals, detections, findings]);

    /* ── Stage counts for status bar ─────────────────────── */

    const stages: PipelineStage[] = useMemo(() => {
        const counts: Record<string, number> = { new: 0, reviewing: 0, confirmed: 0, draft: 0, published: 0 };
        for (const item of allItems) {
            if (counts[item.stage] !== undefined) counts[item.stage]++;
        }
        return DEFAULT_STAGES.map((s) => ({ ...s, count: counts[s.key] ?? 0 }));
    }, [allItems]);

    /* ── Filtered items ──────────────────────────────────── */

    const filteredItems = useMemo(() => {
        return allItems.filter((item) => {
            if (activeStage && item.stage !== activeStage) return false;
            if (severityFilter !== "all" && item.severity !== severityFilter) return false;
            return true;
        });
    }, [allItems, activeStage, severityFilter]);

    /* ── Selected item for detail panel ──────────────────── */

    const selectedItem = useMemo(
        () => filteredItems.find((i) => i.id === selectedItemId) ?? null,
        [filteredItems, selectedItemId]
    );

    /* ── Quick actions ───────────────────────────────────── */

    const handleStartReview = useCallback(
        (signalId: string) => {
            onUpdateSignal(signalId, { status: "UNDER_REVIEW" });
        },
        [onUpdateSignal]
    );

    const handleConfirmSignal = useCallback(
        (signalId: string) => {
            onUpdateSignal(signalId, { status: "CONFIRMED" });
            pushToast("success", "Signal confirmed.");
        },
        [onUpdateSignal, pushToast]
    );

    const handleDismissSignal = useCallback(
        (signalId: string) => {
            onUpdateSignal(signalId, { status: "DISMISSED" });
            pushToast("success", "Signal dismissed.");
        },
        [onUpdateSignal, pushToast]
    );

    const handleEscalateDetection = useCallback(
        (detection: DetectionItem) => {
            const ruleId = String(detection.evidence_snapshot?.rule_id ?? "");
            const summary = String(detection.evidence_snapshot?.summary ?? "");
            onCreateFinding({
                title: `${detection.signal_type}: ${ruleId}`,
                narrative: summary || `Escalated from detection. Review evidence and add analysis.`,
                severity: detection.severity as "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL",
                confidence: "PROBABLE",
                signal_type: detection.signal_type,
                signal_rule_id: ruleId,
                detection_id: detection.id,
            });
            pushToast("success", "Finding drafted from detection.");
        },
        [onCreateFinding, pushToast]
    );

    /* ── Render card ─────────────────────────────────────── */

    function renderCard(item: PipelineItem, cardIndex = 0) {
        const isSelected = selectedItemId === item.id;
        const isSaving =
            (item.type === "signal" && savingSignalId === (item.raw as SignalItem).id) ||
            (item.type === "detection" && savingDetectionId === (item.raw as DetectionItem).id) ||
            (item.type === "finding" && savingFindingId === (item.raw as FindingItem).id);

        return (
            <div
                key={item.id}
                className={`${styles.card} ${CARD_SEV_CLASS[item.severity] ?? ""} ${isSelected ? styles.cardSelected : ""}`}
                onClick={() => setSelectedItemId(isSelected ? null : item.id)}
                style={{
                    ...(isSaving ? { opacity: 0.6, pointerEvents: "none" as const } : {}),
                    ...({ "--card-i": cardIndex } as React.CSSProperties),
                }}
            >
                {/* Header */}
                <div className={styles.cardHeader}>
                    <span className={styles.cardRuleId}>{item.title}</span>
                    <span className={`${styles.sevBadge} ${SEV_CLASS[item.severity] ?? styles.sevInfo}`}>
                        {item.severity}
                    </span>
                    {item.type === "detection" && (
                        <span className={styles.confBar}>
                            <span className={styles.confBarTrack}>
                                <span
                                    className={styles.confBarFill}
                                    style={{
                                        width: `${((item.raw as DetectionItem).confidence_score ?? 0) * 100}%`,
                                        background: confColor((item.raw as DetectionItem).confidence_score ?? 0),
                                    }}
                                />
                            </span>
                            {Math.round(((item.raw as DetectionItem).confidence_score ?? 0) * 100)}%
                        </span>
                    )}
                    <span className={styles.cardTime}>{formatDate(item.date)}</span>
                </div>

                {/* Body */}
                <div className={styles.cardBody}>{item.subtitle}</div>

                {/* Finding narrative + legal refs */}
                {item.type === "finding" && (
                    <>
                        <div className={styles.narrativePreview}>
                            {(item.raw as FindingItem).narrative}
                        </div>
                        {(item.raw as FindingItem).legal_refs.length > 0 && (
                            <div className={styles.legalRefs}>
                                {(item.raw as FindingItem).legal_refs.map((ref) => (
                                    <span key={ref} className={styles.legalRef}>{ref}</span>
                                ))}
                            </div>
                        )}
                    </>
                )}

                {/* AI summary badge */}
                <div className={styles.cardAiBadge} onClick={(e) => e.stopPropagation()}>
                    <AISummaryBadge
                        caseId={ctx.caseId}
                        targetType={item.type}
                        targetId={item.id}
                        compact
                    />
                </div>

                {/* Quick actions */}
                <div className={styles.cardFooter}>
                    {item.type === "signal" && item.stage === "new" && (
                        <>
                            <button
                                className={styles.quickAction}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleStartReview((item.raw as SignalItem).id);
                                }}
                            >
                                Start Review
                            </button>
                            <button
                                className={styles.quickAction}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleConfirmSignal((item.raw as SignalItem).id);
                                }}
                            >
                                Confirm
                            </button>
                            <button
                                className={styles.quickActionDanger}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleDismissSignal((item.raw as SignalItem).id);
                                }}
                            >
                                Dismiss
                            </button>
                        </>
                    )}
                    {item.type === "signal" && item.stage === "reviewing" && (
                        <>
                            <button
                                className={styles.quickAction}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleConfirmSignal((item.raw as SignalItem).id);
                                }}
                            >
                                Confirm
                            </button>
                            <button
                                className={styles.quickActionDanger}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleDismissSignal((item.raw as SignalItem).id);
                                }}
                            >
                                Dismiss
                            </button>
                        </>
                    )}
                    {item.type === "detection" && (
                        <button
                            className={styles.quickAction}
                            onClick={(e) => {
                                e.stopPropagation();
                                handleEscalateDetection(item.raw as DetectionItem);
                            }}
                        >
                            Draft Finding
                        </button>
                    )}
                    {item.type === "finding" && (item.raw as FindingItem).status === "DRAFT" && (
                        <button
                            className={styles.quickAction}
                            onClick={(e) => {
                                e.stopPropagation();
                                onUpdateFinding((item.raw as FindingItem).id, { status: "REVIEWED" });
                                pushToast("success", "Finding published.");
                            }}
                        >
                            Publish
                        </button>
                    )}
                </div>
            </div>
        );
    }

    /* ── Detail panel content ────────────────────────────── */

    function renderDetailPanel() {
        if (!selectedItem) return null;

        if (selectedItem.type === "signal") {
            const sig = selectedItem.raw as SignalItem;
            return (
                <SignalDetailPanel
                    signal={sig}
                    onUpdate={onUpdateSignal}
                    onStartReview={() => handleStartReview(sig.id)}
                    onConfirm={() => handleConfirmSignal(sig.id)}
                    onDismiss={() => handleDismissSignal(sig.id)}
                    saving={savingSignalId === sig.id}
                />
            );
        }

        if (selectedItem.type === "detection") {
            const det = selectedItem.raw as DetectionItem;
            return (
                <DetectionDetailPanel
                    detection={det}
                    onUpdate={onUpdateDetection}
                    onDelete={onDeleteDetection}
                    onEscalate={() => handleEscalateDetection(det)}
                    saving={savingDetectionId === det.id}
                />
            );
        }

        if (selectedItem.type === "finding") {
            const fin = selectedItem.raw as FindingItem;
            return (
                <FindingDetailPanel
                    finding={fin}
                    onUpdate={onUpdateFinding}
                    onDelete={onDeleteFinding}
                    saving={savingFindingId === fin.id}
                    pushToast={pushToast}
                />
            );
        }

        return null;
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
                <span className={styles.toolbarSpacer} />
                <Button
                    variant="secondary"
                    size="sm"
                    onClick={onReevaluateSignals}
                    disabled={reevaluatingSignals}
                >
                    {reevaluatingSignals ? "Re-evaluating..." : "Re-evaluate Signals"}
                </Button>
                <span className={styles.toolbarCount}>
                    {filteredItems.length} item{filteredItems.length !== 1 ? "s" : ""}
                </span>
            </div>

            {/* Card list + detail panel */}
            <ResizablePanelLayout
                panelContent={renderDetailPanel()}
                panelOpen={!!selectedItem}
                panelWidth={400}
                onPanelClose={() => setSelectedItemId(null)}
            >
                <div className={styles.cardList}>
                    {filteredItems.length === 0 ? (
                        <EmptyState
                            icon="🔍"
                            title={activeStage
                                ? `No items at the "${stages.find((s) => s.key === activeStage)?.label ?? activeStage}" stage`
                                : "No pipeline items found"}
                            detail="Upload documents and run signal analysis to populate the pipeline."
                        />
                    ) : (
                        filteredItems.map((item, idx) => renderCard(item, idx))
                    )}
                </div>
            </ResizablePanelLayout>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════
   Detail Panels (slide-in content for each item type)
   ═══════════════════════════════════════════════════════════ */

/* ── Signal Detail Panel ─────────────────────────────────── */

function SignalDetailPanel({
    signal,
    onUpdate,
    onStartReview,
    onConfirm,
    onDismiss,
    saving,
}: {
    signal: SignalItem;
    onUpdate: (id: string, payload: SignalUpdatePayload) => void;
    onStartReview: () => void;
    onConfirm: () => void;
    onDismiss: () => void;
    saving: boolean;
}) {
    const [note, setNote] = useState(signal.investigator_note);

    return (
        <SlidePanel
            title={signal.rule_id}
            subtitle={`Signal · ${signal.status}`}
            onClose={() => {}}
        >
            <SlidePanelSection title="Overview" defaultOpen>
                <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <SeverityBadge severity={signal.severity as "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL"} />
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)" }}>
                        Detected: {formatDate(signal.detected_at)}
                    </span>
                </div>
                <p style={{ fontSize: "var(--text-sm)", color: "var(--text-main)", margin: "0.5rem 0" }}>
                    {signal.title}
                </p>
                <p style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", lineHeight: 1.5 }}>
                    {signal.detected_summary || signal.description}
                </p>
            </SlidePanelSection>

            <SlidePanelSection title="Investigator Notes" defaultOpen>
                <FormTextarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={4}
                    placeholder="Add your analysis notes..."
                />
                <div style={{ marginTop: "0.5rem" }}>
                    <Button
                        variant="primary"
                        size="sm"
                        disabled={saving || note === signal.investigator_note}
                        onClick={() => onUpdate(signal.id, { investigator_note: note })}
                    >
                        {saving ? "Saving..." : "Save Note"}
                    </Button>
                </div>
            </SlidePanelSection>

            <SlidePanelSection title="Actions" defaultOpen>
                <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                    {signal.status === "OPEN" && (
                        <Button variant="secondary" size="sm" onClick={onStartReview}>
                            Start Review
                        </Button>
                    )}
                    {(signal.status === "OPEN" || signal.status === "UNDER_REVIEW") && (
                        <>
                            <Button variant="primary" size="sm" onClick={onConfirm}>
                                Confirm
                            </Button>
                            <Button variant="danger" size="sm" onClick={onDismiss}>
                                Dismiss
                            </Button>
                        </>
                    )}
                </div>
            </SlidePanelSection>
        </SlidePanel>
    );
}

/* ── Detection Detail Panel ──────────────────────────────── */

function DetectionDetailPanel({
    detection,
    onUpdate,
    onDelete,
    onEscalate,
    saving,
}: {
    detection: DetectionItem;
    onUpdate: (id: string, payload: DetectionUpdatePayload) => void;
    onDelete: (id: string) => void;
    onEscalate: () => void;
    saving: boolean;
}) {
    const [note, setNote] = useState(detection.investigator_note);

    return (
        <SlidePanel
            title={detection.signal_type}
            subtitle={`Detection · ${detection.status}`}
            onClose={() => {}}
        >
            <SlidePanelSection title="Overview" defaultOpen>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.5rem" }}>
                    <SeverityBadge severity={detection.severity} />
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)" }}>
                        Confidence: {Math.round(detection.confidence_score * 100)}%
                    </span>
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)" }}>
                        {formatDate(detection.detected_at)}
                    </span>
                </div>
                {detection.evidence_snapshot && (
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", lineHeight: 1.5 }}>
                        {typeof detection.evidence_snapshot === "object" &&
                            Object.entries(detection.evidence_snapshot).map(([k, v]) => (
                                <p key={k} style={{ margin: "0.2rem 0" }}>
                                    <strong>{k}:</strong> {String(v)}
                                </p>
                            ))}
                    </div>
                )}
            </SlidePanelSection>

            <SlidePanelSection title="Investigator Notes" defaultOpen>
                <FormTextarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={4}
                    placeholder="Add your analysis notes..."
                />
                <div style={{ marginTop: "0.5rem" }}>
                    <Button
                        variant="primary"
                        size="sm"
                        disabled={saving || note === detection.investigator_note}
                        onClick={() => onUpdate(detection.id, { investigator_note: note })}
                    >
                        {saving ? "Saving..." : "Save Note"}
                    </Button>
                </div>
            </SlidePanelSection>

            <SlidePanelSection title="Actions" defaultOpen>
                <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                    <Button variant="primary" size="sm" onClick={onEscalate}>
                        Draft Finding
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => onDelete(detection.id)}>
                        Delete Detection
                    </Button>
                </div>
            </SlidePanelSection>
        </SlidePanel>
    );
}

/* ── Finding Detail Panel ────────────────────────────────── */

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
    const [status, setStatus] = useState(finding.status);

    const hasChanges = title !== finding.title || narrative !== finding.narrative || status !== finding.status;

    return (
        <SlidePanel
            title={finding.title}
            subtitle={`Finding · ${finding.status}`}
            onClose={() => {}}
        >
            <SlidePanelSection title="Overview" defaultOpen>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.5rem" }}>
                    <SeverityBadge severity={finding.severity} />
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)" }}>
                        Confidence: {finding.confidence}
                    </span>
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)" }}>
                        {formatDate(finding.created_at)}
                    </span>
                </div>
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
                <FormSelect value={status} onChange={(e) => setStatus(e.target.value as FindingItem["status"])}>
                    <option value="DRAFT">Draft</option>
                    <option value="REVIEWED">Reviewed</option>
                    <option value="INCLUDED_IN_MEMO">Included in Memo</option>
                    <option value="EXCLUDED">Excluded</option>
                    <option value="REFERRED">Referred</option>
                </FormSelect>
                <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.4rem" }}>
                    <Button
                        variant="primary"
                        size="sm"
                        disabled={saving || !hasChanges}
                        onClick={() => {
                            onUpdate(finding.id, { title, narrative, status: status as FindingItem["status"] });
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

            {/* Linked entities + documents */}
            {(finding.entity_links.length > 0 || finding.document_links.length > 0) && (
                <SlidePanelSection
                    title="Linked Evidence"
                    defaultOpen
                    count={finding.entity_links.length + finding.document_links.length}
                >
                    {finding.entity_links.map((el) => (
                        <p key={el.id} style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", margin: "0.2rem 0" }}>
                            {el.entity_type}: {el.entity_id.slice(0, 8)}
                            {el.context_note && ` — ${el.context_note}`}
                        </p>
                    ))}
                    {finding.document_links.map((dl) => (
                        <p key={dl.id} style={{ fontSize: "var(--text-xs)", color: "var(--text-soft)", margin: "0.2rem 0" }}>
                            Doc: {dl.document_id.slice(0, 8)}
                            {dl.page_reference && ` (p. ${dl.page_reference})`}
                            {dl.context_note && ` — ${dl.context_note}`}
                        </p>
                    ))}
                </SlidePanelSection>
            )}
        </SlidePanel>
    );
}
