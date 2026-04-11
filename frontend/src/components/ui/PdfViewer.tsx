import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DocumentItem, DocumentDetail, FindingItem } from "../../types";
import { fetchDocumentDetail, fetchCaseFindings } from "../../api";
import { StateBlock } from "./StateBlock";
import { EmptyState } from "./EmptyState";
import { StickyNotes } from "./StickyNotes";
import styles from "./PdfViewer.module.css";

interface PdfViewerProps {
    document: DocumentItem;
    caseId: string;
    onClose: () => void;
}

function formatMoney(val: number | null | undefined): string {
    if (val == null) return "\u2014";
    return "$" + val.toLocaleString("en-US");
}

/**
 * Slide-over document viewer with PDF preview + data tabs.
 * Shows entities, financials, and metadata extracted from the document.
 */
type TabKey = "pdf" | "entities" | "financials" | "notes" | "findings" | "info";

export function PdfViewer({ document: doc, caseId, onClose }: PdfViewerProps) {
    const panelRef = useRef<HTMLDivElement>(null);
    const navigate = useNavigate();
    const [isOpen, setIsOpen] = useState(false);
    const [activeTab, setActiveTab] = useState<TabKey>("pdf");
    const [detail, setDetail] = useState<DocumentDetail | null>(null);
    const [loading, setLoading] = useState(false);
    const [docFindings, setDocFindings] = useState<FindingItem[]>([]);

    // Animate in on mount
    useEffect(() => {
        requestAnimationFrame(() => setIsOpen(true));
    }, []);

    // Fetch document detail (entities + financials)
    useEffect(() => {
        if (!caseId || !doc.id) return;
        setLoading(true);
        fetchDocumentDetail(caseId, doc.id)
            .then(setDetail)
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [caseId, doc.id]);

    // Fetch findings linked to this document
    useEffect(() => {
        if (!caseId) return;
        fetchCaseFindings(caseId)
            .then((r) => {
                const linked = (r.results || []).filter(
                    (f: FindingItem) =>
                        f.trigger_doc_id === doc.id ||
                        f.document_links.some((dl) => dl.document_id === doc.id)
                );
                setDocFindings(linked);
            })
            .catch(() => {});
    }, [caseId, doc.id]);

    // Close on Escape
    useEffect(() => {
        function handleKey(e: KeyboardEvent) {
            if (e.key === "Escape") onClose();
        }
        window.addEventListener("keydown", handleKey);
        return () => window.removeEventListener("keydown", handleKey);
    }, [onClose]);

    const is990 = doc.doc_type === "IRS_990" || doc.doc_type === "IRS_990T";
    const entityCount = detail
        ? (detail.persons?.length || 0) + (detail.organizations?.length || 0)
        : 0;

    function handleClose() {
        setIsOpen(false);
        setTimeout(onClose, 200);
    }

    const SEV_COLORS: Record<string, string> = {
        CRITICAL: "#dc2626",
        HIGH: "#ea580c",
        MEDIUM: "#ca8a04",
        LOW: "#16a34a",
        INFORMATIONAL: "#6b7280",
    };

    const tabs: { key: TabKey; label: string; show: boolean }[] = [
        { key: "pdf", label: "Document", show: true },
        { key: "entities", label: `Entities${entityCount ? ` (${entityCount})` : ""}`, show: true },
        { key: "notes", label: "Notes", show: true },
        { key: "findings", label: `Findings${docFindings.length ? ` (${docFindings.length})` : ""}`, show: true },
        { key: "financials", label: "Financials", show: is990 },
        { key: "info", label: "Info", show: true },
    ];

    return (
        <div className={`${styles.overlay} ${isOpen ? styles.open : ""}`}>
            <div className={styles.backdrop} onClick={handleClose} />
            <div ref={panelRef} className={`${styles.panel} ${isOpen ? styles.open : ""}`}>
                <div className={styles.header}>
                    <div className={styles.title}>
                        <span>{"\uD83D\uDCC4"}</span>
                        <strong>{doc.filename}</strong>
                    </div>
                    <button type="button" className={styles.close} onClick={handleClose} aria-label="Close viewer">
                        {"\u2715"}
                    </button>
                </div>

                {/* Tab bar */}
                <div className={styles.tabs}>
                    {tabs.filter(t => t.show).map(t => (
                        <button
                            key={t.key}
                            type="button"
                            className={activeTab === t.key ? styles.tabActive : styles.tab}
                            onClick={() => setActiveTab(t.key as typeof activeTab)}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>

                {/* Tab content */}
                <div className={styles.body}>
                    {loading && <StateBlock title="Loading document details..." />}

                    {activeTab === "pdf" && (
                        <div className={styles.embed}>
                            {detail?.extracted_text ? (
                                <pre className={styles.extractedText}>{detail.extracted_text}</pre>
                            ) : loading ? (
                                <p className={styles.placeholder}>Loading document text...</p>
                            ) : (
                                <p className={styles.placeholder}>
                                    No extracted text available for <strong>{doc.filename}</strong>.
                                    {doc.ocr_status === "PENDING" && " Run OCR processing to extract text from this document."}
                                </p>
                            )}
                        </div>
                    )}

                    {activeTab === "entities" && detail && (
                        <div className={styles.entities}>
                            {(detail.persons?.length ?? 0) > 0 && (
                                <section>
                                    <h4>{"\uD83D\uDC64"} Persons ({detail.persons!.length})</h4>
                                    <ul className={styles.entityList}>
                                        {detail.persons!.map(p => (
                                            <li
                                                key={p.id}
                                                className={styles.entityItem}
                                                onClick={() => navigate(`/entities/person/${p.id}`)}
                                                style={{ cursor: "pointer" }}
                                            >
                                                <strong>{p.full_name}</strong>
                                                {p.role_tags.length > 0 && (
                                                    <span className={styles.roleTags}> — {p.role_tags.join(", ")}</span>
                                                )}
                                                {p.context_note && <p className={styles.contextNote}>{p.context_note}</p>}
                                            </li>
                                        ))}
                                    </ul>
                                </section>
                            )}
                            {(detail.organizations?.length ?? 0) > 0 && (
                                <section>
                                    <h4>{"\uD83C\uDFE2"} Organizations ({detail.organizations!.length})</h4>
                                    <ul className={styles.entityList}>
                                        {detail.organizations!.map(o => (
                                            <li
                                                key={o.id}
                                                className={styles.entityItem}
                                                onClick={() => navigate(`/entities/organization/${o.id}`)}
                                                style={{ cursor: "pointer" }}
                                            >
                                                <strong>{o.name}</strong>
                                                {o.ein && <span className={styles.ein}> (EIN: {o.ein})</span>}
                                                {o.context_note && <p className={styles.contextNote}>{o.context_note}</p>}
                                            </li>
                                        ))}
                                    </ul>
                                </section>
                            )}
                            {entityCount === 0 && (
                                <EmptyState title="No entities" detail="No entities linked to this document." />
                            )}
                        </div>
                    )}

                    {activeTab === "notes" && (
                        <div className={styles.notesTab}>
                            <StickyNotes caseId={caseId} targetType="document" targetId={doc.id} />
                        </div>
                    )}

                    {activeTab === "findings" && (
                        <div className={styles.findingsTab}>
                            {docFindings.length > 0 ? (
                                <ul className={styles.findingsList}>
                                    {docFindings.map(f => (
                                        <li key={f.id} className={styles.findingCard}>
                                            <div className={styles.findingHeader}>
                                                <span
                                                    className={styles.findingSev}
                                                    style={{ color: SEV_COLORS[f.severity] ?? "#6b7280" }}
                                                >
                                                    {f.severity}
                                                </span>
                                                <span className={styles.findingRule}>{f.rule_id || "MANUAL"}</span>
                                                <span className={styles.findingStatus}>{f.status}</span>
                                            </div>
                                            <strong>{f.title}</strong>
                                            {f.description && (
                                                <p className={styles.findingDesc}>
                                                    {f.description.length > 200
                                                        ? f.description.slice(0, 200) + "..."
                                                        : f.description}
                                                </p>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <EmptyState
                                    title="No findings from this document"
                                    detail="Run signal analysis to detect findings, or findings may be linked to other documents."
                                />
                            )}
                        </div>
                    )}

                    {activeTab === "financials" && detail && (
                        <div className={styles.financials}>
                            {(detail.financial_snapshots?.length ?? 0) > 0 ? (
                                <table className="financials-table">
                                    <thead>
                                        <tr>
                                            <th>Year</th>
                                            <th>Revenue</th>
                                            <th>Expenses</th>
                                            <th>Net</th>
                                            <th>Assets (EOY)</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {detail.financial_snapshots!.map(s => (
                                            <tr key={s.id}>
                                                <td>{s.tax_year}</td>
                                                <td>{formatMoney(s.total_revenue)}</td>
                                                <td>{formatMoney(s.total_expenses)}</td>
                                                <td>{formatMoney(s.revenue_less_expenses)}</td>
                                                <td>{formatMoney(s.total_assets_eoy)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            ) : (
                                <EmptyState title="No financials" detail="No financial data for this document." />
                            )}
                        </div>
                    )}

                    {activeTab === "info" && (
                        <div className={styles.info}>
                            <dl className="info-list">
                                <dt>Filename</dt><dd>{doc.filename}</dd>
                                <dt>Type</dt><dd>{doc.doc_type}</dd>
                                <dt>SHA-256</dt><dd className="hash-value">{doc.sha256_hash}</dd>
                                <dt>Size</dt><dd>{doc.file_size.toLocaleString()} bytes</dd>
                                <dt>OCR Status</dt><dd>{doc.ocr_status}</dd>
                                <dt>Uploaded</dt><dd>{doc.uploaded_at}</dd>
                                {doc.source_url && <><dt>Source</dt><dd><a href={doc.source_url} target="_blank" rel="noopener noreferrer">{doc.source_url}</a></dd></>}
                            </dl>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}