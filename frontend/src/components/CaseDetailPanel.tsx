import { BulkUploadResult } from "../api";
import { CaseDetail, DetectionItem, DetectionUpdatePayload, DocumentItem, NewReferralPayload, ReferralItem, ReferralUpdatePayload, SignalItem } from "../types";
import { BulkUploadPanel } from "./BulkUploadPanel";
import { DetectionsPanel } from "./DetectionsPanel";
import { ReferralsPanel } from "./ReferralsPanel";
import { Button } from "./ui/Button";
import { EmptyState } from "./ui/EmptyState";
import { FormSelect } from "./ui/FormSelect";
import { FormTextarea } from "./ui/FormTextarea";
import { StateBlock } from "./ui/StateBlock";
import styles from "./CaseDetailPanel.module.css";

interface TriageDraft {
    status: string;
    note: string;
}

interface CaseDetailPanelProps {
    activeCaseName: string;
    selectedCase: CaseDetail | null;
    loadingCaseDetail: boolean;
    filteredDocuments: DocumentItem[];
    documentTypes: string[];
    ocrStatuses: string[];
    docTypeFilter: string;
    ocrFilter: string;
    filteredSignals: SignalItem[];
    signals: SignalItem[];
    signalSeverities: string[];
    signalStatuses: string[];
    signalSeverityFilter: string;
    signalStatusFilter: string;
    triageError: string | null;
    savingSignalId: string | null;
    activeSignalId: string | null;
    referrals: ReferralItem[];
    loadingReferrals: boolean;
    savingReferralId: number | null;
    detections: DetectionItem[];
    loadingDetections: boolean;
    savingDetectionId: string | null;
    deletingDocumentId: string | null;
    generatingMemo: boolean;
    processingPendingOcr: boolean;
    reevaluatingSignals: boolean;
    onDocTypeFilterChange: (value: string) => void;
    onOcrFilterChange: (value: string) => void;
    onSignalSeverityFilterChange: (value: string) => void;
    onSignalStatusFilterChange: (value: string) => void;
    getSignalDraft: (signal: SignalItem) => TriageDraft;
    onSignalDraftChange: (signalId: string, draft: TriageDraft) => void;
    onActiveSignalChange: (signalId: string) => void;
    onSignalSave: (signal: SignalItem) => void;
    onCreateReferral: (payload: NewReferralPayload) => void;
    onUpdateReferral: (referralId: number, payload: ReferralUpdatePayload) => void;
    onDeleteReferral: (referralId: number) => void;
    onUpdateDetection: (detectionId: string, payload: DetectionUpdatePayload) => void;
    onDeleteDetection: (detectionId: string) => void;
    onDeleteDocument: (documentId: string) => void;
    onGenerateMemo: () => void;
    onProcessPendingOcr: () => void;
    onReevaluateSignals: () => void;
    onBulkUpload: (files: File[]) => Promise<BulkUploadResult>;
    onBulkUploadComplete: (result: BulkUploadResult) => void;
    formatDate: (value: string) => string;
    formatSize: (value: number) => string;
}

export function CaseDetailPanel({
    activeCaseName,
    selectedCase,
    loadingCaseDetail,
    filteredDocuments,
    documentTypes,
    ocrStatuses,
    docTypeFilter,
    ocrFilter,
    filteredSignals,
    signals,
    signalSeverities,
    signalStatuses,
    signalSeverityFilter,
    signalStatusFilter,
    triageError,
    savingSignalId,
    activeSignalId,
    onDocTypeFilterChange,
    onOcrFilterChange,
    onSignalSeverityFilterChange,
    onSignalStatusFilterChange,
    getSignalDraft,
    onSignalDraftChange,
    onActiveSignalChange,
    onSignalSave,
    referrals,
    loadingReferrals,
    savingReferralId,
    detections,
    loadingDetections,
    savingDetectionId,
    deletingDocumentId,
    generatingMemo,
    processingPendingOcr,
    reevaluatingSignals,
    onCreateReferral,
    onUpdateReferral,
    onDeleteReferral,
    onUpdateDetection,
    onDeleteDetection,
    onDeleteDocument,
    onGenerateMemo,
    onProcessPendingOcr,
    onReevaluateSignals,
    onBulkUpload,
    onBulkUploadComplete,
    formatDate,
    formatSize
}: CaseDetailPanelProps) {
    const quickStatuses = ["OPEN", "REVIEWED", "DISMISSED"];
    const pendingOcrCount = (selectedCase?.documents ?? []).filter((document) => document.ocr_status === "PENDING").length;

    return (
        <section className="panel panel-detail">
            <div className="panel-heading">
                <h2>{activeCaseName}</h2>
                {selectedCase && <span>{selectedCase.status}</span>}
            </div>

            {selectedCase && (
                <div className={styles.detailMeta}>
                    <span>Last Updated: {formatDate(selectedCase.updated_at)}</span>
                    <span>Referral: {selectedCase.referral_ref || "Not assigned"}</span>
                </div>
            )}

            {loadingCaseDetail && (
                <StateBlock
                    title="Loading case details..."
                    detail="Pulling documents, signals, and metadata for the selected case."
                />
            )}

            {!loadingCaseDetail && !selectedCase && (
                <StateBlock
                    title="Choose a case to load investigation details."
                    detail="The detail panel will populate after a case is selected from the queue."
                />
            )}

            {!loadingCaseDetail && selectedCase && (
                <>
                    <article className={styles.infoCard}>
                        <h3>Case Notes</h3>
                        <p>{selectedCase.notes || "No notes yet."}</p>
                    </article>

                    <article className={styles.infoCard}>
                        <h3>Upload Documents</h3>
                        <BulkUploadPanel
                            onUpload={onBulkUpload}
                            onComplete={onBulkUploadComplete}
                        />
                    </article>

                    <article className={styles.infoCard}>
                        <div className={styles.cardToolbar}>
                            <h3>Documents ({filteredDocuments.length}/{selectedCase.documents.length})</h3>
                            <div className={styles.compactFilters}>
                                <Button
                                    variant="secondary"
                                    disabled={processingPendingOcr || pendingOcrCount === 0}
                                    onClick={onProcessPendingOcr}
                                >
                                    {processingPendingOcr
                                        ? "Processing OCR..."
                                        : `Process Pending OCR (${pendingOcrCount})`}
                                </Button>
                                <FormSelect
                                    value={docTypeFilter}
                                    onChange={(event) => onDocTypeFilterChange(event.target.value)}
                                    aria-label="Filter documents by type"
                                >
                                    <option value="all">All types</option>
                                    {documentTypes.map((docType) => (
                                        <option key={docType} value={docType}>
                                            {docType}
                                        </option>
                                    ))}
                                </FormSelect>
                                <FormSelect
                                    value={ocrFilter}
                                    onChange={(event) => onOcrFilterChange(event.target.value)}
                                    aria-label="Filter documents by OCR status"
                                >
                                    <option value="all">All OCR</option>
                                    {ocrStatuses.map((ocrStatus) => (
                                        <option key={ocrStatus} value={ocrStatus}>
                                            {ocrStatus}
                                        </option>
                                    ))}
                                </FormSelect>
                            </div>
                        </div>
                        <div className={styles.tableWrap}>
                            {filteredDocuments.length === 0 ? (
                                <EmptyState
                                    title={selectedCase.documents.length === 0
                                        ? "No documents have been attached to this case yet."
                                        : "No documents match the current filters."}
                                    detail={selectedCase.documents.length === 0
                                        ? "Once evidence is uploaded, it will appear here with type, OCR status, and upload timing."
                                        : "Try changing the document type or OCR filter to broaden the result set."}
                                />
                            ) : (
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Filename</th>
                                            <th>Type</th>
                                            <th>OCR</th>
                                            <th>Size</th>
                                            <th>Uploaded</th>
                                            <th>Action</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filteredDocuments.map((document) => (
                                            <tr key={document.id}>
                                                <td>{document.filename}</td>
                                                <td>{document.doc_type}</td>
                                                <td>{document.ocr_status}</td>
                                                <td>{formatSize(document.file_size)}</td>
                                                <td>{formatDate(document.uploaded_at)}</td>
                                                <td>
                                                    <Button
                                                        variant="secondary"
                                                        onClick={() => onDeleteDocument(document.id)}
                                                        disabled={deletingDocumentId === document.id}
                                                        aria-label={`Delete file ${document.filename}`}
                                                    >
                                                        {deletingDocumentId === document.id ? "Deleting..." : "Delete"}
                                                    </Button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </article>

                    <article className={styles.infoCard}>
                        <div className={styles.cardToolbar}>
                            <h3>Signals ({filteredSignals.length}/{signals.length})</h3>
                            <div className={styles.compactFilters}>
                                <FormSelect
                                    value={signalSeverityFilter}
                                    onChange={(event) => onSignalSeverityFilterChange(event.target.value)}
                                    aria-label="Filter signals by severity"
                                >
                                    <option value="all">All severity</option>
                                    {signalSeverities.map((severity) => (
                                        <option key={severity} value={severity}>
                                            {severity}
                                        </option>
                                    ))}
                                </FormSelect>
                                <FormSelect
                                    value={signalStatusFilter}
                                    onChange={(event) => onSignalStatusFilterChange(event.target.value)}
                                    aria-label="Filter signals by status"
                                >
                                    <option value="all">All status</option>
                                    {signalStatuses.map((status) => (
                                        <option key={status} value={status}>
                                            {status}
                                        </option>
                                    ))}
                                </FormSelect>
                            </div>
                        </div>
                        {triageError && <p className={styles.triageError}>{triageError}</p>}
                        {filteredSignals.length === 0 ? (
                            <EmptyState
                                title={signals.length === 0
                                    ? "No signals detected for this case yet."
                                    : "No signals match the current filters."}
                                detail={signals.length === 0
                                    ? "When detection rules flag activity, triage items will show up here for review."
                                    : "Try broadening severity or status filters to show more triage items."}
                            />
                        ) : (
                            <ul className={styles.signalList}>
                                {filteredSignals.map((signal) => {
                                    const draft = getSignalDraft(signal);
                                    return (
                                        <li key={signal.id}>
                                            <div
                                                className={signal.id === activeSignalId ? `${styles.signalCard} ${styles.activeSignal}` : styles.signalCard}
                                                role="button"
                                                tabIndex={0}
                                                onClick={() => onActiveSignalChange(signal.id)}
                                                onKeyDown={(event) => {
                                                    if (event.key === "Enter" || event.key === " ") {
                                                        event.preventDefault();
                                                        onActiveSignalChange(signal.id);
                                                    }
                                                }}
                                                aria-label={`Focus signal ${signal.title}`}
                                            >
                                                <strong>{signal.title}</strong>
                                                <p className={styles.signalSubhead}>{signal.rule_id}</p>
                                                <p>{signal.description}</p>
                                                <p className={styles.signalSubhead}>Detected: {formatDate(signal.detected_at)}</p>
                                            </div>
                                            <div className={styles.signalBadges}>
                                                <span className={`tag ${signal.severity.toLowerCase()}`}>
                                                    {signal.severity}
                                                </span>
                                                <span className="tag neutral">{signal.status}</span>
                                                <div className={styles.triageQuickActions}>
                                                    {quickStatuses.map((status) => (
                                                        <Button
                                                            key={`${signal.id}-${status}`}
                                                            className={draft.status === status ? `${styles.triageChip} ${styles.active}` : styles.triageChip}
                                                            variant="secondary"
                                                            onClick={() => onSignalDraftChange(signal.id, { ...draft, status })}
                                                            aria-label={`Set signal status to ${status}`}
                                                        >
                                                            {status}
                                                        </Button>
                                                    ))}
                                                </div>
                                                <FormSelect
                                                    className={styles.triageSelect}
                                                    value={draft.status}
                                                    onChange={(event) => onSignalDraftChange(signal.id, { ...draft, status: event.target.value })}
                                                >
                                                    {signalStatuses.map((status) => (
                                                        <option key={status} value={status}>
                                                            {status}
                                                        </option>
                                                    ))}
                                                </FormSelect>
                                                <FormTextarea
                                                    className={styles.triageNote}
                                                    placeholder="Investigator note"
                                                    value={draft.note}
                                                    onChange={(event) => onSignalDraftChange(signal.id, { ...draft, note: event.target.value })}
                                                    rows={2}
                                                />
                                                <Button
                                                    className={styles.triageSave}
                                                    onClick={() => void onSignalSave(signal)}
                                                    disabled={savingSignalId === signal.id}
                                                >
                                                    {savingSignalId === signal.id ? "Saving..." : "Save"}
                                                </Button>
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </article>
                    <article className={styles.infoCard}>
                        <div className={styles.cardToolbar}>
                            <h3>Referral Memo</h3>
                            <Button
                                variant="primary"
                                disabled={generatingMemo}
                                onClick={onGenerateMemo}
                            >
                                {generatingMemo ? "Generating…" : "Generate Memo"}
                            </Button>
                        </div>
                        <p className={styles.memoHint}>
                            Generates a summary memo from the current case state and referral records.
                            The memo is saved as a document and will appear in the Documents list above.
                        </p>
                    </article>

                    <div className={styles.reevaluateBar}>
                        <Button
                            variant="secondary"
                            disabled={reevaluatingSignals}
                            onClick={onReevaluateSignals}
                        >
                            {reevaluatingSignals ? "Re-evaluating..." : "Re-evaluate Signals"}
                        </Button>
                        <span className={styles.reevaluateHint}>
                            Re-run all signal rules against this case's documents and entities.
                        </span>
                    </div>

                    <DetectionsPanel
                        detections={detections}
                        loadingDetections={loadingDetections}
                        savingDetectionId={savingDetectionId}
                        onUpdateDetection={onUpdateDetection}
                        onDeleteDetection={onDeleteDetection}
                        formatDate={formatDate}
                    />

                    <article className={styles.infoCard}>
                        <ReferralsPanel
                            referrals={referrals}
                            loadingReferrals={loadingReferrals}
                            savingReferralId={savingReferralId}
                            onCreateReferral={onCreateReferral}
                            onUpdateReferral={onUpdateReferral}
                            onDeleteReferral={onDeleteReferral}
                            formatDate={formatDate}
                        />
                    </article>
                </>
            )}
        </section>
    );
}
