import { useState } from "react";
import { DetectionItem, DetectionStatus, DetectionUpdatePayload } from "../types";
import { Button } from "./ui/Button";
import { EmptyState } from "./ui/EmptyState";
import { FormSelect } from "./ui/FormSelect";
import { FormTextarea } from "./ui/FormTextarea";
import styles from "./DetectionsPanel.module.css";

const SEVERITY_CLASS: Record<string, string> = {
    CRITICAL: "critical",
    HIGH: "high",
    MEDIUM: "medium",
    LOW: "low",
    INFORMATIONAL: "neutral",
};

const STATUS_LABELS: Record<DetectionStatus, string> = {
    OPEN: "Open",
    REVIEWED: "Reviewed",
    CONFIRMED: "Confirmed",
    DISMISSED: "Dismissed",
    ESCALATED: "Escalated",
};

const SIGNAL_TYPE_LABELS: Record<string, string> = {
    DECEASED_SIGNER: "Deceased signer",
    DATE_IMPOSSIBILITY: "Date impossibility",
    MISSING_REQUIRED_FIELDS: "Missing required fields",
    METADATA_MISMATCH: "Metadata mismatch",
    HASH_CHANGE: "Hash change on re-intake",
    VALUATION_DELTA: "Property valuation delta",
    SELF_DEALING: "Self-dealing indicator",
    UCC_LOOP: "UCC lien loop",
    PROCUREMENT_BYPASS: "Procurement bypass",
    REVENUE_ANOMALY: "990 revenue anomaly",
    PHANTOM_OFFICER: "Phantom officer",
    NAME_RECONCILIATION: "Name reconciliation",
    TIMELINE_COMPRESSION: "Timeline compression",
    CHARTER_CONFLICT: "Charter status conflict",
    ADDRESS_NEXUS: "Address nexus",
    ASSET_DISCREPANCY: "990 vs deed asset discrepancy",
    BLANKET_LIEN: "Blanket lien indicator",
    RAPID_FLIP: "Rapid property flip",
    GOVERNANCE_GAP: "Governance gap",
    FAMILY_NETWORK: "Family network density",
    SOCIAL_CLUSTER: "Social cluster overlap",
    ENTITY_FORMATION_TIMING: "Entity formation timing",
    CONDUIT_PATTERN: "Conduit entity pattern",
    RELATED_PARTY_TX: "Related party transaction",
    EXPENSE_RATIO: "Low program expense ratio",
};

const STATUS_OPTIONS: DetectionStatus[] = ["OPEN", "REVIEWED", "CONFIRMED", "DISMISSED", "ESCALATED"];

interface DetectionsPanelProps {
    detections: DetectionItem[];
    loadingDetections: boolean;
    savingDetectionId: string | null;
    onUpdateDetection: (detectionId: string, payload: DetectionUpdatePayload) => void;
    onDeleteDetection: (detectionId: string) => void;
    onEscalateToFinding?: (detection: DetectionItem) => void;
    formatDate: (value: string) => string;
}

interface ReviewDraft {
    status: DetectionStatus;
    note: string;
}

export function DetectionsPanel({
    detections,
    loadingDetections,
    savingDetectionId,
    onUpdateDetection,
    onDeleteDetection,
    onEscalateToFinding,
    formatDate,
}: DetectionsPanelProps) {
    const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
    const [activeId, setActiveId] = useState<string | null>(null);
    const [severityFilter, setSeverityFilter] = useState("all");
    const [statusFilter, setStatusFilter] = useState("all");

    function getDraft(detection: DetectionItem): ReviewDraft {
        return drafts[detection.id] ?? { status: detection.status, note: detection.investigator_note };
    }

    function setDraft(detectionId: string, draft: ReviewDraft) {
        setDrafts((prev) => ({ ...prev, [detectionId]: draft }));
    }

    const severities = [...new Set(detections.map((d) => d.severity))].sort();
    const statuses = [...new Set(detections.map((d) => d.status))].sort();

    const filtered = detections.filter((d) => {
        if (severityFilter !== "all" && d.severity !== severityFilter) return false;
        if (statusFilter !== "all" && d.status !== statusFilter) return false;
        return true;
    });

    if (loadingDetections) {
        return (
            <article className={styles.infoCard}>
                <h3>Detections</h3>
                <p className={styles.signalSubhead}>Loading detections…</p>
            </article>
        );
    }

    return (
        <article className={styles.infoCard}>
            <div className={styles.cardToolbar}>
                <h3>Detections ({filtered.length}/{detections.length})</h3>
                <div className={styles.compactFilters}>
                    <FormSelect
                        value={severityFilter}
                        onChange={(e) => setSeverityFilter(e.target.value)}
                        aria-label="Filter detections by severity"
                    >
                        <option value="all">All severity</option>
                        {severities.map((s) => (
                            <option key={s} value={s}>{s}</option>
                        ))}
                    </FormSelect>
                    <FormSelect
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        aria-label="Filter detections by status"
                    >
                        <option value="all">All status</option>
                        {statuses.map((s) => (
                            <option key={s} value={s}>{STATUS_LABELS[s as DetectionStatus] ?? s}</option>
                        ))}
                    </FormSelect>
                </div>
            </div>

            {filtered.length === 0 ? (
                <EmptyState
                    title={detections.length === 0
                        ? "No detections for this case yet."
                        : "No detections match the current filters."}
                    detail={detections.length === 0
                        ? "Detections are written when the system flags a suspicious pattern across documents and entities."
                        : "Try broadening severity or status filters."}
                />
            ) : (
                <ul className={styles.signalList}>
                    {filtered.map((detection) => {
                        const draft = getDraft(detection);
                        const isSaving = savingDetectionId === detection.id;
                        const isActive = activeId === detection.id;
                        const evidenceKeys = Object.keys(detection.evidence_snapshot);

                        return (
                            <li key={detection.id}>
                                <div
                                    className={isActive ? `${styles.signalCard} ${styles.activeSignal}` : styles.signalCard}
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => setActiveId(isActive ? null : detection.id)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" || e.key === " ") {
                                            e.preventDefault();
                                            setActiveId(isActive ? null : detection.id);
                                        }
                                    }}
                                    aria-label={`Review detection: ${SIGNAL_TYPE_LABELS[detection.signal_type] ?? detection.signal_type}`}
                                >
                                    <strong>{SIGNAL_TYPE_LABELS[detection.signal_type] ?? detection.signal_type}</strong>
                                    <p className={styles.signalSubhead}>{detection.detection_method === "INVESTIGATOR_MANUAL" ? "Manual flag" : "Auto-detected"} · {formatDate(detection.detected_at)}</p>
                                    {evidenceKeys.length > 0 && (
                                        <ul className={styles.signalSubhead} style={{ margin: "4px 0 0", paddingLeft: "1rem" }}>
                                            {evidenceKeys.map((k) => (
                                                <li key={k}><strong>{k}:</strong> {String(detection.evidence_snapshot[k])}</li>
                                            ))}
                                        </ul>
                                    )}
                                    {detection.investigator_note && (
                                        <p className={styles.signalSubhead} style={{ marginTop: 4 }}>
                                            Note: {detection.investigator_note}
                                        </p>
                                    )}
                                </div>

                                <div className={styles.signalBadges}>
                                    <span className={`tag ${SEVERITY_CLASS[detection.severity] ?? "neutral"}`}>
                                        {detection.severity}
                                    </span>
                                    <span className="tag neutral">{STATUS_LABELS[detection.status] ?? detection.status}</span>

                                    {isActive && (
                                        <>
                                            <FormSelect
                                                className={styles.triageSelect}
                                                value={draft.status}
                                                onChange={(e) => setDraft(detection.id, { ...draft, status: e.target.value as DetectionStatus })}
                                            >
                                                {STATUS_OPTIONS.map((s) => (
                                                    <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                                                ))}
                                            </FormSelect>
                                            <FormTextarea
                                                className={styles.triageNote}
                                                placeholder="Investigator note (required to dismiss)"
                                                value={draft.note}
                                                onChange={(e) => setDraft(detection.id, { ...draft, note: e.target.value })}
                                                rows={2}
                                            />
                                            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                                                <Button
                                                    className={styles.triageSave}
                                                    disabled={isSaving}
                                                    onClick={() => onUpdateDetection(detection.id, {
                                                        status: draft.status,
                                                        investigator_note: draft.note,
                                                    })}
                                                >
                                                    {isSaving ? "Saving…" : "Save"}
                                                </Button>
                                                {onEscalateToFinding && (
                                                    <Button
                                                        disabled={isSaving}
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            onEscalateToFinding(detection);
                                                        }}
                                                    >
                                                        Escalate to Finding
                                                    </Button>
                                                )}
                                                <Button
                                                    variant="secondary"
                                                    disabled={isSaving}
                                                    onClick={() => {
                                                        if (confirm("Delete this detection?")) {
                                                            onDeleteDetection(detection.id);
                                                        }
                                                    }}
                                                >
                                                    Delete
                                                </Button>
                                            </div>
                                        </>
                                    )}
                                </div>
                            </li>
                        );
                    })}
                </ul>
            )}
        </article>
    );
}
