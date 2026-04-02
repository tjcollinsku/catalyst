import { useEffect, useRef, useState } from "react";
import { DocumentItem, DocumentDetail } from "../../types";
import { fetchDocumentDetail } from "../../api";
import { StateBlock } from "./StateBlock";
import { EmptyState } from "./EmptyState";
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
export function PdfViewer({ document: doc, caseId, onClose }: PdfViewerProps) {
    const panelRef = useRef<HTMLDivElement>(null);
    const [isOpen, setIsOpen] = useState(false);
    const [activeTab, setActiveTab] = useState<"pdf" | "entities" | "financials" | "info">("pdf");
    const [detail, setDetail] = useState<DocumentDetail | null>(null);
    const [loading, setLoading] = useState(false);

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

    // Close on Escape
    useEffect(() => {
        function handleKey(e: KeyboardEvent) {
            if (e.key === "Escape") onClose();
        }
        window.addEventListener("keydown", handleKey);
        return () => window.removeEventListener("keydown", handleKey);
    }, [onClose]);

    // TODO: Use for embedded PDF preview when implemented
    // const fileUrl = doc.file_path ? `/media/${doc.file_path}` : `/media/${doc.id}/`;
    const is990 = doc.doc_type === "IRS_990" || doc.doc_type === "IRS_990T";

    function handleClose() {
        setIsOpen(false);
        setTimeout(onClose, 200);
    }

    const tabs: { key: typeof activeTab; label: string; show: boolean }[] = [
        { key: "pdf", label: "Document", show: true },
        { key: "entities", label: `Entities${detail ? ` (${(detail.persons?.length || 0) + (detail.organizations?.length || 0)})` : ""}`, show: true },
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
                            <p className={styles.placeholder}>
                                PDF preview not yet implemented. Document: <strong>{doc.filename}</strong>
                            </p>
                        </div>
                    )}

                    {activeTab === "entities" && detail && (
                        <div className={styles.entities}>
                            {(detail.persons?.length ?? 0) > 0 && (
                                <section>
                                    <h4>Persons ({detail.persons!.length})</h4>
                                    <ul className="entity-list">
                                        {detail.persons!.map(p => (
                                            <li key={p.id}>
                                                <strong>{p.full_name}</strong>
                                                {p.role_tags.length > 0 && (
                                                    <span className="role-tags"> — {p.role_tags.join(", ")}</span>
                                                )}
                                                {p.context_note && <p className="context-note">{p.context_note}</p>}
                                            </li>
                                        ))}
                                    </ul>
                                </section>
                            )}
                            {(detail.organizations?.length ?? 0) > 0 && (
                                <section>
                                    <h4>Organizations ({detail.organizations!.length})</h4>
                                    <ul className="entity-list">
                                        {detail.organizations!.map(o => (
                                            <li key={o.id}>
                                                <strong>{o.name}</strong>
                                                {o.ein && <span className="ein"> (EIN: {o.ein})</span>}
                                                {o.context_note && <p className="context-note">{o.context_note}</p>}
                                            </li>
                                        ))}
                                    </ul>
                                </section>
                            )}
                            {(detail.persons?.length ?? 0) === 0 && (detail.organizations?.length ?? 0) === 0 && (
                                <EmptyState title="No entities" detail="No entities linked to this document." />
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