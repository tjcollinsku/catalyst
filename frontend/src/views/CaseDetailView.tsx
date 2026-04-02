import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import styles from "./CaseDetailView.module.css";
import { useShellContext } from "../contexts/ShellContext";
import {
    bulkUploadDocuments,
    BulkUploadResult,
    createFinding,
    deleteDocument,
    deleteDetection,
    deleteFinding,
    deleteReferral,
    fetchCaseDetail,
    fetchCaseSignals,
    fetchDetections,
    fetchFindings,
    fetchReferrals,
    generateReferralMemo,
    createReferral,
    isAbortError,
    processPendingOcr,
    reevaluateSignals,
    updateDetection,
    updateFinding,
    updateReferral,
    updateSignal,
} from "../api";
import {
    CaseDetail,
    DetectionItem,
    DetectionUpdatePayload,
    DocumentItem,
    FindingItem,
    FindingUpdatePayload,
    NewFindingPayload,
    NewReferralPayload,
    ReferralItem,
    ReferralUpdatePayload,
    SignalItem,
    SignalUpdatePayload,
} from "../types";
import { ToastItem, ToastStack } from "../components/ui/ToastStack";
import { StateBlock } from "../components/ui/StateBlock";

/* ── Tab configuration ─────────────────────────────────────── */
const TABS = [
    { label: "Overview", path: "overview" },
    { label: "Documents", path: "documents" },
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
    /* Signals */
    signals: SignalItem[];
    onUpdateSignal: (signalId: string, payload: SignalUpdatePayload) => void;
    savingSignalId: string | null;
    onReevaluateSignals: () => void;
    reevaluatingSignals: boolean;
    /* Detections */
    detections: DetectionItem[];
    loadingDetections: boolean;
    savingDetectionId: string | null;
    onUpdateDetection: (detectionId: string, payload: DetectionUpdatePayload) => void;
    onDeleteDetection: (detectionId: string) => void;
    /* Findings */
    findings: FindingItem[];
    loadingFindings: boolean;
    savingFindingId: string | null;
    onCreateFinding: (payload: NewFindingPayload) => void;
    onUpdateFinding: (findingId: string, payload: FindingUpdatePayload) => void;
    onDeleteFinding: (findingId: string) => void;
    /* Referrals */
    referrals: ReferralItem[];
    loadingReferrals: boolean;
    savingReferralId: number | null;
    onCreateReferral: (payload: NewReferralPayload) => void;
    onUpdateReferral: (referralId: number, payload: ReferralUpdatePayload) => void;
    onDeleteReferral: (referralId: number) => void;
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

    /* ── Signals ──────────────────────────────────────────── */
    const [signals, setSignals] = useState<SignalItem[]>([]);
    const [savingSignalId, setSavingSignalId] = useState<string | null>(null);
    const [reevaluatingSignals_, setReevaluatingSignals] = useState(false);

    /* ── Detections ───────────────────────────────────────── */
    const [detections, setDetections] = useState<DetectionItem[]>([]);
    const [loadingDetections, setLoadingDetections] = useState(true);
    const [savingDetectionId, setSavingDetectionId] = useState<string | null>(null);

    /* ── Findings ─────────────────────────────────────────── */
    const [findings, setFindings] = useState<FindingItem[]>([]);
    const [loadingFindings, setLoadingFindings] = useState(true);
    const [savingFindingId, setSavingFindingId] = useState<string | null>(null);

    /* ── Referrals ────────────────────────────────────────── */
    const [referrals, setReferrals] = useState<ReferralItem[]>([]);
    const [loadingReferrals, setLoadingReferrals] = useState(true);
    const [savingReferralId, setSavingReferralId] = useState<number | null>(null);

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
            setLoadingDetections(true);
            setLoadingFindings(true);
            setLoadingReferrals(true);
            try {
                const [detail, signalsRes, detectionsRes, findingsRes, referralsRes] = await Promise.all([
                    fetchCaseDetail(caseId!, { signal: controller.signal }),
                    fetchCaseSignals(caseId!, { signal: controller.signal }),
                    fetchDetections(caseId!, { signal: controller.signal }),
                    fetchFindings(caseId!, { signal: controller.signal }),
                    fetchReferrals(caseId!, { signal: controller.signal }),
                ]);
                if (!controller.signal.aborted) {
                    setCaseDetail(detail);
                    setCaseName(detail.name);
                    setSignals(signalsRes.results);
                    setDetections(detectionsRes.results);
                    setFindings(findingsRes.results);
                    setReferrals(referralsRes.results);
                }
            } catch (err) {
                if (!isAbortError(err)) pushToast("error", (err as Error).message);
            } finally {
                if (!controller.signal.aborted) {
                    setLoading(false);
                    setLoadingDetections(false);
                    setLoadingFindings(false);
                    setLoadingReferrals(false);
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

    /* ── Signal handlers ──────────────────────────────────── */
    const handleUpdateSignal = useCallback(
        async (signalId: string, payload: SignalUpdatePayload) => {
            if (!caseId) return;
            setSavingSignalId(signalId);
            try {
                const updated = await updateSignal(caseId, signalId, payload);
                setSignals((prev) => prev.map((s) => (s.id === signalId ? updated : s)));
                pushToast("success", "Signal updated");
                refreshBadges();
            } catch (err) {
                pushToast("error", (err as Error).message);
            } finally {
                setSavingSignalId(null);
            }
        },
        [caseId, pushToast],
    );

    const handleReevaluateSignals = useCallback(async () => {
        if (!caseId) return;
        setReevaluatingSignals(true);
        try {
            const result = await reevaluateSignals(caseId);
            if (result.new_detections.length > 0) {
                setDetections((prev) => [...result.new_detections, ...prev]);
                pushToast("success", `${result.new_detections.length} new detection(s) found`);
            } else {
                pushToast("success", "Re-evaluation complete — no new detections");
            }
        } catch (err) {
            pushToast("error", (err as Error).message);
        } finally {
            setReevaluatingSignals(false);
        }
    }, [caseId, pushToast]);

    /* ── Detection handlers ───────────────────────────────── */
    const handleUpdateDetection = useCallback(
        async (detectionId: string, payload: DetectionUpdatePayload) => {
            if (!caseId) return;
            setSavingDetectionId(detectionId);
            try {
                const updated = await updateDetection(caseId, detectionId, payload);
                setDetections((prev) => prev.map((d) => (d.id === detectionId ? updated : d)));
                pushToast("success", "Detection updated");
            } catch (err) {
                pushToast("error", (err as Error).message);
            } finally {
                setSavingDetectionId(null);
            }
        },
        [caseId, pushToast],
    );

    const handleDeleteDetection = useCallback(
        async (detectionId: string) => {
            if (!caseId) return;
            setSavingDetectionId(detectionId);
            try {
                await deleteDetection(caseId, detectionId);
                setDetections((prev) => prev.filter((d) => d.id !== detectionId));
                pushToast("success", "Detection deleted");
            } catch (err) {
                pushToast("error", (err as Error).message);
            } finally {
                setSavingDetectionId(null);
            }
        },
        [caseId, pushToast],
    );

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
            } catch (err) {
                pushToast("error", (err as Error).message);
            } finally {
                setSavingFindingId(null);
            }
        },
        [caseId, pushToast],
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

    /* ── Referral handlers ────────────────────────────────── */
    const handleCreateReferral = useCallback(
        async (payload: NewReferralPayload) => {
            if (!caseId) return;
            try {
                const created = await createReferral(caseId, payload);
                setReferrals((prev) => [created, ...prev]);
                pushToast("success", `Referral created: ${created.agency_name}`);
            } catch (err) {
                pushToast("error", (err as Error).message);
            }
        },
        [caseId, pushToast],
    );

    const handleUpdateReferral = useCallback(
        async (referralId: number, payload: ReferralUpdatePayload) => {
            if (!caseId) return;
            setSavingReferralId(referralId);
            try {
                const updated = await updateReferral(caseId, referralId, payload);
                setReferrals((prev) => prev.map((r) => (r.referral_id === referralId ? updated : r)));
                pushToast("success", "Referral updated");
            } catch (err) {
                pushToast("error", (err as Error).message);
            } finally {
                setSavingReferralId(null);
            }
        },
        [caseId, pushToast],
    );

    const handleDeleteReferral = useCallback(
        async (referralId: number) => {
            if (!caseId) return;
            setSavingReferralId(referralId);
            try {
                await deleteReferral(caseId, referralId);
                setReferrals((prev) => prev.filter((r) => r.referral_id !== referralId));
                pushToast("success", "Referral deleted");
            } catch (err) {
                pushToast("error", (err as Error).message);
            } finally {
                setSavingReferralId(null);
            }
        },
        [caseId, pushToast],
    );

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
        signals,
        onUpdateSignal: (id, payload) => void handleUpdateSignal(id, payload),
        savingSignalId,
        onReevaluateSignals: () => void handleReevaluateSignals(),
        reevaluatingSignals: reevaluatingSignals_,
        detections,
        loadingDetections,
        savingDetectionId,
        onUpdateDetection: (id, payload) => void handleUpdateDetection(id, payload),
        onDeleteDetection: (id) => void handleDeleteDetection(id),
        findings,
        loadingFindings,
        savingFindingId,
        onCreateFinding: (payload) => void handleCreateFinding(payload),
        onUpdateFinding: (id, payload) => void handleUpdateFinding(id, payload),
        onDeleteFinding: (id) => void handleDeleteFinding(id),
        referrals,
        loadingReferrals,
        savingReferralId,
        onCreateReferral: (payload) => void handleCreateReferral(payload),
        onUpdateReferral: (id, payload) => void handleUpdateReferral(id, payload),
        onDeleteReferral: (id) => void handleDeleteReferral(id),
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
                        {tab.path === "pipeline" && (signals.length + detections.length + findings.length) > 0 && (
                            <span className={styles.tabCount}>
                                {signals.length + detections.length + findings.length}
                            </span>
                        )}
                        {tab.path === "referrals" && referrals.length > 0 && (
                            <span className={styles.tabCount}>{referrals.length}</span>
                        )}
                    </NavLink>
                ))}
            </nav>

            {/* Tab content */}
            {loading ? (
                <StateBlock title="Loading case details..." detail="Pulling documents, signals, and metadata." />
            ) : (
                <div className={styles.caseTabContent}>
                    <Outlet context={context} />
                </div>
            )}

            <ToastStack toasts={toasts} onDismiss={(id) => setToasts((p) => p.filter((t) => t.id !== id))} />
        </>
    );
}