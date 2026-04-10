import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import styles from "./CaseDetailView.module.css";
import { useShellContext } from "../contexts/ShellContext";
import {
    bulkUploadDocuments,
    BulkUploadResult,
    createFinding,
    deleteDocument,
    deleteFinding,
    fetchCaseDetail,
    fetchCaseFindings,
    generateReferralMemo,
    isAbortError,
    processPendingOcr,
    reevaluateFindings,
    updateFinding,
} from "../api";
import {
    CaseDetail,
    DocumentItem,
    FindingItem,
    FindingUpdatePayload,
    NewFindingPayload,
} from "../types";
import { ToastItem, ToastStack } from "../components/ui/ToastStack";
import { StateBlock } from "../components/ui/StateBlock";

/* ── Tab configuration ─────────────────────────────────────── */
const TABS = [
    { label: "Overview", path: "overview" },
    { label: "Documents", path: "documents" },
    { label: "Research", path: "research" },
    { label: "Financials", path: "financials" },
    { label: "Pipeline", path: "pipeline" },
    { label: "Referrals", path: "referrals" },
] as const;

/* ── Context type shared with child tabs via Outlet ───────── */
export interface CaseDetailContext {
    caseId: string;
    caseDetail: CaseDetail | null;
    /* Documents */
    documents: DocumentItem[];
    onBulkUpload: (files: File[]) => Promise<BulkUploadResult>;
    onBulkUploadComplete: (result: BulkUploadResult) => void;
    onDeleteDocument: (documentId: string) => void;
    deletingDocumentId: string | null;
    onProcessPendingOcr: () => void;
    processingPendingOcr: boolean;
    onGenerateMemo: () => void;
    generatingMemo: boolean;
    /* Findings (consolidated — replaces signals + detections + old findings) */
    findings: FindingItem[];
    loadingFindings: boolean;
    savingFindingId: string | null;
    onCreateFinding: (payload: NewFindingPayload) => void;
    onUpdateFinding: (findingId: string, payload: FindingUpdatePayload) => void;
    onDeleteFinding: (findingId: string) => void;
    onReevaluateFindings: () => void;
    reevaluatingFindings: boolean;
    /* Utility */
    pushToast: (tone: "error" | "success", message: string) => void;
}

export function CaseDetailView() {
    const { caseId } = useParams<{ caseId: string }>();
    const navigate = useNavigate();
    const { setCaseName, refreshBadges } = useShellContext();

    /* ── Toast system ─────────────────────────────────────── */
    const [toasts, setToasts] = useState<ToastItem[]>([]);
    const toastId = useRef(0);
    const pushToast = useCallback((tone: "error" | "success", message: string) => {
        const id = ++toastId.current;
        setToasts((prev) => [...prev, { id, tone, message }]);
        setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3400);
    }, []);

    /* ── Core case state ──────────────────────────────────── */
    const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
    const [loading, setLoading] = useState(true);

    /* ── Findings ─────────────────────────────────────────── */
    const [findings, setFindings] = useState<FindingItem[]>([]);
    const [loadingFindings, setLoadingFindings] = useState(true);
    const [savingFindingId, setSavingFindingId] = useState<string | null>(null);
    const [reevaluatingFindings_, setReevaluatingFindings] = useState(false);

    /* ── Documents ────────────────────────────────────────── */
    const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(null);
    const [generatingMemo, setGeneratingMemo] = useState(false);
    const [processingPendingOcr_, setProcessingPendingOcr] = useState(false);

    /* ── Load everything on mount / caseId change ─────────── */
    useEffect(() => {
        if (!caseId) return;
        const controller = new AbortController();
        async function load() {
            setLoading(true);
            setLoadingFindings(true);
            try {
                const [detail, findingsRes] = await Promise.all([
                    fetchCaseDetail(caseId!, { signal: controller.signal }),
                    fetchCaseFindings(caseId!, { signal: controller.signal }),
                ]);
                if (!controller.signal.aborted) {
                    setCaseDetail(detail);
                    setCaseName(detail.name);
                    setFindings(findingsRes.results);
                }
            } catch (err) {
                if (!isAbortError(err)) pushToast("error", (err as Error).message);
            } finally {
                if (!controller.signal.aborted) {
                    setLoading(false);
                    setLoadingFindings(false);
                }
            }
        }
        void load();
        return () => {
            controller.abort();
            setCaseName(null);
        };
    }, [caseId, pushToast, setCaseName]);

    /* ── Document handlers ────────────────────────────────── */
    const handleBulkUpload = useCallback(
        async (files: File[]) => {
            if (!caseId) throw new Error("No case selected");
            return bulkUploadDocuments(caseId, files);
        },
        [caseId],
    );

    const handleBulkUploadComplete = useCallback(
        (result: BulkUploadResult) => {
            if (result.created.length > 0) {
                setCaseDetail((prev) =>
                    prev ? { ...prev, documents: [...prev.documents, ...result.created] } : prev,
                );
                pushToast("success", `${result.created.length} document(s) uploaded`);
            }
            if (result.errors.length > 0) {
                pushToast("error", `${result.errors.length} file(s) failed to upload`);
            }
        },
        [pushToast],
    );

    const handleDeleteDocument = useCallback(
        async (documentId: string) => {
            if (!caseId) return;
            setDeletingDocumentId(documentId);
            try {
                await deleteDocument(caseId, documentId);
                setCaseDetail((prev) =>
                    prev ? { ...prev, documents: prev.documents.filter((d) => d.id !== documentId) } : prev,
                );
                pushToast("success", "Document deleted");
            } catch (err) {
                pushToast("error", (err as Error).message);
            } finally {
                setDeletingDocumentId(null);
            }
        },
        [caseId, pushToast],
    );

    const handleProcessPendingOcr = useCallback(async () => {
        if (!caseId) return;
        setProcessingPendingOcr(true);
        try {
            const result = await processPendingOcr(caseId);
            if (result.processed.length > 0) {
                setCaseDetail((prev) => {
                    if (!prev) return prev;
                    const updated = new Map(result.processed.map((d) => [d.id, d]));
                    return {
                        ...prev,
                        documents: prev.documents.map((d) => updated.get(d.id) ?? d),
                    };
                });
                pushToast("success", `OCR completed for ${result.processed.length} document(s)`);
            }
            if (result.errors.length > 0) {
                pushToast("error", `OCR failed for ${result.errors.length} document(s)`);
            }
        } catch (err) {
            pushToast("error", (err as Error).message);
        } finally {
            setProcessingPendingOcr(false);
        }
    }, [caseId, pushToast]);

    const handleGenerateMemo = useCallback(async () => {
        if (!caseId) return;
        setGeneratingMemo(true);
        try {
            const doc = await generateReferralMemo(caseId);
            setCaseDetail((prev) =>
                prev ? { ...prev, documents: [...prev.documents, doc] } : prev,
            );
            pushToast("success", `Memo generated: ${doc.filename}`);
        } catch (err) {
            pushToast("error", (err as Error).message);
        } finally {
            setGeneratingMemo(false);
        }
    }, [caseId, pushToast]);

    /* ── Finding handlers ─────────────────────────────────── */
    const handleCreateFinding = useCallback(
        async (payload: NewFindingPayload) => {
            if (!caseId) return;
            try {
                const created = await createFinding(caseId, payload);
                setFindings((prev) => [created, ...prev]);
                pushToast("success", `Finding created: ${created.title}`);
            } catch (err) {
                pushToast("error", (err as Error).message);
            }
        },
        [caseId, pushToast],
    );

    const handleUpdateFinding = useCallback(
        async (findingId: string, payload: FindingUpdatePayload) => {
            if (!caseId) return;
            setSavingFindingId(findingId);
            try {
                const updated = await updateFinding(caseId, findingId, payload);
                setFindings((prev) => prev.map((f) => (f.id === findingId ? updated : f)));
                pushToast("success", "Finding updated");
                refreshBadges();
            } catch (err) {
                pushToast("error", (err as Error).message);
            } finally {
                setSavingFindingId(null);
            }
        },
        [caseId, pushToast, refreshBadges],
    );

    const handleDeleteFinding = useCallback(
        async (findingId: string) => {
            if (!caseId) return;
            setSavingFindingId(findingId);
            try {
                await deleteFinding(caseId, findingId);
                setFindings((prev) => prev.filter((f) => f.id !== findingId));
                pushToast("success", "Finding deleted");
            } catch (err) {
                pushToast("error", (err as Error).message);
            } finally {
                setSavingFindingId(null);
            }
        },
        [caseId, pushToast],
    );

    const handleReevaluateFindings = useCallback(async () => {
        if (!caseId) return;
        setReevaluatingFindings(true);
        try {
            const result = await reevaluateFindings(caseId);
            if (result.new_findings.length > 0) {
                setFindings((prev) => [...result.new_findings, ...prev]);
                pushToast("success", `${result.new_findings.length} new finding(s) detected`);
            } else {
                pushToast("success", "Re-evaluation complete — no new findings");
            }
            refreshBadges();
        } catch (err) {
            pushToast("error", (err as Error).message);
        } finally {
            setReevaluatingFindings(false);
        }
    }, [caseId, pushToast, refreshBadges]);


    /* ── Outlet context ───────────────────────────────────── */
    const context: CaseDetailContext = {
        caseId: caseId ?? "",
        caseDetail,
        documents: caseDetail?.documents ?? [],
        onBulkUpload: handleBulkUpload,
        onBulkUploadComplete: handleBulkUploadComplete,
        onDeleteDocument: (id) => void handleDeleteDocument(id),
        deletingDocumentId,
        onProcessPendingOcr: () => void handleProcessPendingOcr(),
        processingPendingOcr: processingPendingOcr_,
        onGenerateMemo: () => void handleGenerateMemo(),
        generatingMemo,
        findings,
        loadingFindings,
        savingFindingId,
        onCreateFinding: (payload) => void handleCreateFinding(payload),
        onUpdateFinding: (id, payload) => void handleUpdateFinding(id, payload),
        onDeleteFinding: (id) => void handleDeleteFinding(id),
        onReevaluateFindings: () => void handleReevaluateFindings(),
        reevaluatingFindings: reevaluatingFindings_,
        pushToast,
    };

    /* ── Render ────────────────────────────────────────────── */
    if (!caseId) {
        return <StateBlock title="No case selected." detail="Navigate to a case from the cases list." />;
    }

    return (
        <>
            {/* Case header */}
            <div className={styles.caseDetailHeader}>
                <button className={styles.backLink} onClick={() => navigate("/cases")} aria-label="Back to cases">
                    {"\u2190"} Cases
                </button>
                <div className={styles.caseDetailTitleRow}>
                    <h2>{caseDetail?.name ?? "Loading..."}</h2>
                    {caseDetail && (
                        <span className={`${styles.statusPill} ${styles[`status${caseDetail.status.charAt(0).toUpperCase() + caseDetail.status.slice(1).toLowerCase()}`]}`}>
                            {caseDetail.status}
                        </span>
                    )}
                </div>
                {caseDetail && (
                    <div className={styles.caseDetailMeta}>
                        <span>Ref: {caseDetail.referral_ref || "—"}</span>
                        <span>{caseDetail.notes || "No case notes"}</span>
                    </div>
                )}
            </div>

            {/* Tab bar */}
            <nav className={styles.caseTabBar} aria-label="Case detail tabs">
                {TABS.map((tab) => (
                    <NavLink
                        key={tab.path}
                        to={tab.path}
                        end
                        className={({ isActive }) => isActive ? styles.tabActive : styles.caseTab}
                    >
                        {tab.label}
                        {tab.path === "documents" && (caseDetail?.documents.length ?? 0) > 0 && (
                            <span className={styles.tabCount}>{caseDetail?.documents.length}</span>
                        )}
                        {tab.path === "pipeline" && findings.length > 0 && (
                            <span className={styles.tabCount}>{findings.length}</span>
                        )}
                    </NavLink>
                ))}
            </nav>

            {/* Tab content */}
            {loading ? (
                <StateBlock title="Loading case details..." detail="Pulling documents, findings, and metadata." />
            ) : (
                <div className={styles.caseTabContent}>
                    <Outlet context={context} />
                </div>
            )}

            <ToastStack toasts={toasts} onDismiss={(id) => setToasts((p) => p.filter((t) => t.id !== id))} />
        </>
    );
}
