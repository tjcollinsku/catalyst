import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import { DocumentItem } from "../../types";
import { BulkUploadPanel } from "../BulkUploadPanel";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { FormSelect } from "../ui/FormSelect";
import { PdfViewer } from "../ui/PdfViewer";
import { formatDate, formatSize } from "../../utils/format";
import styles from "./DocumentsTab.module.css";

export function DocumentsTab() {
    const {
        caseDetail,
        documents,
        onBulkUpload,
        onBulkUploadComplete,
        onDeleteDocument,
        deletingDocumentId,
        onProcessPendingOcr,
        processingPendingOcr,
        onGenerateMemo,
        generatingMemo,
    } = useOutletContext<CaseDetailContext>();

    const [docTypeFilter, setDocTypeFilter] = useState("all");
    const [ocrFilter, setOcrFilter] = useState("all");
    const [viewingDoc, setViewingDoc] = useState<DocumentItem | null>(null);

    const documentTypes = useMemo(
        () => Array.from(new Set(documents.map((d) => d.doc_type))).sort(),
        [documents],
    );

    const ocrStatuses = useMemo(
        () => Array.from(new Set(documents.map((d) => d.ocr_status))).sort(),
        [documents],
    );

    const filtered = useMemo(() => {
        return documents.filter((d) => {
            if (docTypeFilter !== "all" && d.doc_type !== docTypeFilter) return false;
            if (ocrFilter !== "all" && d.ocr_status !== ocrFilter) return false;
            return true;
        });
    }, [documents, docTypeFilter, ocrFilter]);

    const pendingOcrCount = documents.filter((d) => d.ocr_status === "PENDING").length;

    return (
        <>
            {/* Upload section */}
            <article className="info-card">
                <h3>Upload Documents</h3>
                <BulkUploadPanel onUpload={onBulkUpload} onComplete={onBulkUploadComplete} />
            </article>

            {/* Documents table */}
            <article className="info-card">
                <div className="card-toolbar">
                    <h3>Documents ({filtered.length}/{documents.length})</h3>
                    <div className="compact-filters">
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
                            onChange={(e) => setDocTypeFilter(e.target.value)}
                            aria-label="Filter documents by type"
                        >
                            <option value="all">All types</option>
                            {documentTypes.map((t) => (
                                <option key={t} value={t}>{t}</option>
                            ))}
                        </FormSelect>
                        <FormSelect
                            value={ocrFilter}
                            onChange={(e) => setOcrFilter(e.target.value)}
                            aria-label="Filter documents by OCR status"
                        >
                            <option value="all">All OCR</option>
                            {ocrStatuses.map((s) => (
                                <option key={s} value={s}>{s}</option>
                            ))}
                        </FormSelect>
                    </div>
                </div>
                <div className="table-wrap">
                    {filtered.length === 0 ? (
                        <EmptyState
                            title={
                                documents.length === 0
                                    ? "No documents have been attached to this case yet."
                                    : "No documents match the current filters."
                            }
                            detail={
                                documents.length === 0
                                    ? "Once evidence is uploaded, it will appear here with type, OCR status, and upload timing."
                                    : "Try changing the document type or OCR filter to broaden the result set."
                            }
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
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((doc) => (
                                    <tr key={doc.id}>
                                        <td title={doc.filename}>
                                            {doc.display_name || doc.filename}
                                        </td>
                                        <td>{doc.doc_type}</td>
                                        <td>{doc.ocr_status}</td>
                                        <td>{formatSize(doc.file_size)}</td>
                                        <td>{formatDate(doc.uploaded_at)}</td>
                                        <td className={styles.docActionsCell}>
                                            <Button
                                                variant="secondary"
                                                onClick={() => setViewingDoc(doc)}
                                                aria-label={`View file ${doc.filename}`}
                                            >
                                                {"\uD83D\uDC41"} View
                                            </Button>
                                            <Button
                                                variant="secondary"
                                                onClick={() => onDeleteDocument(doc.id)}
                                                disabled={deletingDocumentId === doc.id}
                                                aria-label={`Delete file ${doc.filename}`}
                                            >
                                                {deletingDocumentId === doc.id ? "Deleting..." : "Delete"}
                                            </Button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </article>

            {/* Referral memo generator */}
            <article className="info-card">
                <div className="card-toolbar">
                    <h3>Referral Memo</h3>
                    <Button variant="primary" disabled={generatingMemo} onClick={onGenerateMemo}>
                        {generatingMemo ? "Generating\u2026" : "Generate Memo"}
                    </Button>
                </div>
                <p className={styles.memoHint}>
                    Generates a summary memo from the current case state and referral records.
                    The memo is saved as a document and will appear in the Documents list above.
                </p>
            </article>

            {/* Case notes (read-only for now) */}
            {caseDetail?.notes && (
                <article className="info-card">
                    <h3>Case Notes</h3>
                    <p>{caseDetail.notes}</p>
                </article>
            )}

            {/* PDF Viewer slide-over */}
            {viewingDoc && caseDetail && (
                <PdfViewer document={viewingDoc} caseId={caseDetail.id} onClose={() => setViewingDoc(null)} />
            )}
        </>
    );
}