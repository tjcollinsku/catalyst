/**
 * LegacyCasesView — wraps the existing App.tsx case management logic
 * inside the new shell layout. This is a bridge component that will be
 * broken apart into CasesListView + CaseDetailView in Phase B.
 *
 * All existing functionality (case CRUD, document upload, signal triage,
 * referrals, detections) works exactly as before.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./LegacyCasesView.module.css";
import {
    BulkUploadResult,
    bulkUploadDocuments,
    createCase,
    createReferral,
    deleteDetection,
    deleteDocument,
    deleteReferral,
    fetchCaseDetail,
    fetchCases,
    fetchCaseSignals,
    fetchDetections,
    fetchReferrals,
    fetchSignalSummary,
    generateReferralMemo,
    isAbortError,
    processPendingOcr,
    reevaluateSignals,
    updateDetection,
    updateReferral,
    updateSignal,
} from "../api";
import { CaseDetailPanel } from "../components/CaseDetailPanel";
import { CasesPanel } from "../components/CasesPanel";
import { DashboardMetrics } from "../components/DashboardMetrics";
import { ToastItem, ToastStack } from "../components/ui/ToastStack";
import {
    CaseDetail,
    CaseSummary,
    DetectionItem,
    DetectionUpdatePayload,
    NewReferralPayload,
    ReferralItem,
    ReferralUpdatePayload,
    SignalItem,
} from "../types";
import { formatDate, formatSize } from "../utils/format";

export function LegacyCasesView() {
    const [cases, setCases] = useState<CaseSummary[]>([]);
    const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
    const [selectedCase, setSelectedCase] = useState<CaseDetail | null>(null);
    const [signals, setSignals] = useState<SignalItem[]>([]);
    const [activeSignalId, setActiveSignalId] = useState<string | null>(null);
    const [caseQuery, setCaseQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [caseSort, setCaseSort] = useState("updated_desc");
    const [docTypeFilter, setDocTypeFilter] = useState("all");
    const [ocrFilter, setOcrFilter] = useState("all");
    const [signalSeverityFilter, setSignalSeverityFilter] = useState("all");
    const [signalStatusFilter, setSignalStatusFilter] = useState("all");
    const [newCaseName, setNewCaseName] = useState("");
    const [newCaseReferral, setNewCaseReferral] = useState("");
    const [newCaseNotes, setNewCaseNotes] = useState("");
    const [isSubmittingCase, setIsSubmittingCase] = useState(false);
    const [savingSignalId, setSavingSignalId] = useState<string | null>(null);
    const [triageDrafts, setTriageDrafts] = useState<Record<string, { status: string; note: string }>>({});
    const [triageError, setTriageError] = useState<string | null>(null);
    const [toasts, setToasts] = useState<ToastItem[]>([]);
    const [formErrors, setFormErrors] = useState<{ name?: string; referral?: string }>({});
    const [caseSeverityMap, setCaseSeverityMap] = useState<Record<string, string>>({});
    const [referrals, setReferrals] = useState<ReferralItem[]>([]);
    const [loadingReferrals, setLoadingReferrals] = useState(false);
    const [savingReferralId, setSavingReferralId] = useState<number | null>(null);
    const [detections, setDetections] = useState<DetectionItem[]>([]);
    const [loadingDetections, setLoadingDetections] = useState(false);
    const [savingDetectionId, setSavingDetectionId] = useState<string | null>(null);
    const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(null);
    const [generatingMemo, setGeneratingMemo] = useState(false);
    const [processingPendingOcr, setProcessingPendingOcr] = useState(false);
    const [reevaluatingSignals, setReevaluatingSignals] = useState(false);
    const [loadingCases, setLoadingCases] = useState(true);
    const [loadingCaseDetail, setLoadingCaseDetail] = useState(false);
    const toastIdRef = useRef(0);

    function removeToast(id: number) {
        setToasts((previous) => previous.filter((toast) => toast.id !== id));
    }

    function pushToast(tone: "error" | "success", message: string) {
        const id = ++toastIdRef.current;
        setToasts((previous) => [...previous, { id, tone, message }]);
        window.setTimeout(() => removeToast(id), 3400);
    }

    // ── Load cases on mount ──
    useEffect(() => {
        const controller = new AbortController();
        async function loadCases() {
            setLoadingCases(true);
            try {
                const [response, summaryResponse] = await Promise.all([
                    fetchCases(25, 0, { signal: controller.signal }),
                    fetchSignalSummary({ signal: controller.signal }),
                ]);
                setCases(response.results);
                setSelectedCaseId((current) => {
                    if (current && response.results.some((c) => c.id === current)) return current;
                    return response.results[0]?.id ?? null;
                });
                const map: Record<string, string> = {};
                for (const item of summaryResponse.results) {
                    map[item.case_id] = item.highest_severity;
                }
                setCaseSeverityMap(map);
            } catch (error) {
                if (!isAbortError(error)) pushToast("error", (error as Error).message);
            } finally {
                if (!controller.signal.aborted) setLoadingCases(false);
            }
        }
        void loadCases();
        return () => controller.abort();
    }, []);

    // ── Load case detail when selection changes ──
    useEffect(() => {
        if (!selectedCaseId) {
            setSelectedCase(null);
            setSignals([]);
            setReferrals([]);
            setDetections([]);
            setActiveSignalId(null);
            return;
        }
        const controller = new AbortController();
        async function loadCaseDetail(caseId: string) {
            setLoadingCaseDetail(true);
            setLoadingReferrals(true);
            setLoadingDetections(true);
            try {
                const [detail, signalResponse, referralResponse, detectionResponse] = await Promise.all([
                    fetchCaseDetail(caseId, { signal: controller.signal }),
                    fetchCaseSignals(caseId, { signal: controller.signal }),
                    fetchReferrals(caseId, { signal: controller.signal }),
                    fetchDetections(caseId, { signal: controller.signal }),
                ]);
                setSelectedCase(detail);
                setSignals(signalResponse.results);
                setReferrals(referralResponse.results);
                setDetections(detectionResponse.results);
                setActiveSignalId((current) => {
                    if (current && signalResponse.results.some((s) => s.id === current)) return current;
                    return signalResponse.results[0]?.id ?? null;
                });
            } catch (error) {
                if (!isAbortError(error)) pushToast("error", (error as Error).message);
            } finally {
                if (!controller.signal.aborted) {
                    setLoadingCaseDetail(false);
                    setLoadingReferrals(false);
                    setLoadingDetections(false);
                }
            }
        }
        void loadCaseDetail(selectedCaseId);
        return () => controller.abort();
    }, [selectedCaseId]);

    // ── Handlers (same as original App.tsx) ──

    async function handleCreateReferral(payload: NewReferralPayload) {
        if (!selectedCaseId) return;
        try {
            const created = await createReferral(selectedCaseId, payload);
            setReferrals((prev) => [created, ...prev]);
            pushToast("success", `Referral to ${created.agency_name} created.`);
        } catch (error) { pushToast("error", (error as Error).message); }
    }

    async function handleUpdateReferral(referralId: number, payload: ReferralUpdatePayload) {
        if (!selectedCaseId) return;
        setSavingReferralId(referralId);
        try {
            const updated = await updateReferral(selectedCaseId, referralId, payload);
            setReferrals((prev) => prev.map((r) => (r.referral_id === updated.referral_id ? updated : r)));
            pushToast("success", "Referral updated.");
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setSavingReferralId(null); }
    }

    async function handleDeleteReferral(referralId: number) {
        if (!selectedCaseId) return;
        setSavingReferralId(referralId);
        try {
            await deleteReferral(selectedCaseId, referralId);
            setReferrals((prev) => prev.filter((r) => r.referral_id !== referralId));
            pushToast("success", "Referral deleted.");
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setSavingReferralId(null); }
    }

    async function handleUpdateDetection(detectionId: string, payload: DetectionUpdatePayload) {
        if (!selectedCaseId) return;
        setSavingDetectionId(detectionId);
        try {
            const updated = await updateDetection(selectedCaseId, detectionId, payload);
            setDetections((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
            pushToast("success", "Detection updated.");
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setSavingDetectionId(null); }
    }

    async function handleDeleteDetection(detectionId: string) {
        if (!selectedCaseId) return;
        setSavingDetectionId(detectionId);
        try {
            await deleteDetection(selectedCaseId, detectionId);
            setDetections((prev) => prev.filter((d) => d.id !== detectionId));
            pushToast("success", "Detection removed.");
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setSavingDetectionId(null); }
    }

    async function handleBulkUpload(files: File[]): Promise<BulkUploadResult> {
        if (!selectedCaseId) return { created: [], errors: [] };
        try {
            return await bulkUploadDocuments(selectedCaseId, files);
        } catch (error) {
            const message = (error as Error).message || "Upload failed.";
            pushToast("error", message);
            return { created: [], errors: files.map((f) => ({ filename: f.name, error: message })) };
        }
    }

    function handleBulkUploadComplete(result: BulkUploadResult) {
        if (result.created.length > 0) {
            setSelectedCase((prev) => prev ? { ...prev, documents: [...result.created, ...prev.documents] } : prev);
            pushToast("success", `${result.created.length} document${result.created.length > 1 ? "s" : ""} uploaded.`);
        }
        if (result.errors.length > 0) {
            pushToast("error", `${result.errors.length} file${result.errors.length > 1 ? "s" : ""} failed to upload.`);
        }
    }

    async function handleDeleteDocument(documentId: string) {
        if (!selectedCaseId || !selectedCase) return;
        const target = selectedCase.documents.find((d) => d.id === documentId);
        if (!target || !window.confirm(`Delete "${target.filename}" from this case?`)) return;
        setDeletingDocumentId(documentId);
        try {
            await deleteDocument(selectedCaseId, documentId);
            setSelectedCase((prev) => prev ? { ...prev, documents: prev.documents.filter((d) => d.id !== documentId) } : prev);
            pushToast("success", `Deleted document: ${target.filename}`);
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setDeletingDocumentId(null); }
    }

    async function handleGenerateMemo() {
        if (!selectedCaseId) return;
        setGeneratingMemo(true);
        try {
            const doc = await generateReferralMemo(selectedCaseId);
            setSelectedCase((prev) => prev ? { ...prev, documents: [doc, ...prev.documents] } : prev);
            pushToast("success", "Referral memo generated and added to documents.");
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setGeneratingMemo(false); }
    }

    async function handleProcessPendingOcr() {
        if (!selectedCaseId) return;
        setProcessingPendingOcr(true);
        try {
            const result = await processPendingOcr(selectedCaseId);
            if (result.processed.length > 0) {
                const processedById = new Map(result.processed.map((d) => [d.id, d]));
                setSelectedCase((prev) => prev ? { ...prev, documents: prev.documents.map((d) => processedById.get(d.id) ?? d) } : prev);
            }
            pushToast("success", `OCR: ${result.processed.length} processed, ${result.errors.length} failed, ${result.skipped} skipped.`);
            if (result.errors.length > 0) pushToast("error", `OCR errors: ${result.errors.map((e) => e.filename).join(", ")}`);
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setProcessingPendingOcr(false); }
    }

    async function handleReevaluateSignals() {
        if (!selectedCaseId) return;
        setReevaluatingSignals(true);
        try {
            const result = await reevaluateSignals(selectedCaseId);
            if (result.new_detections.length > 0) setDetections((prev) => [...result.new_detections, ...prev]);
            pushToast("success", `Re-evaluation: ${result.documents_evaluated} docs, ${result.new_detections.length} new detection(s).`);
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setReevaluatingSignals(false); }
    }

    const activeCaseName = useMemo(() => selectedCase?.name ?? "No case selected", [selectedCase]);
    const availableStatuses = useMemo(() => Array.from(new Set(cases.map((c) => c.status))).sort(), [cases]);

    const filteredCases = useMemo(() => {
        const q = caseQuery.trim().toLowerCase();
        const visible = cases.filter((c) => {
            const statusMatch = statusFilter === "all" || c.status === statusFilter;
            const queryMatch = q.length === 0 || c.name.toLowerCase().includes(q) || c.referral_ref.toLowerCase().includes(q);
            return statusMatch && queryMatch;
        });
        const sorted = [...visible];
        sorted.sort((a, b) => {
            if (caseSort === "updated_asc") return new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
            if (caseSort === "name_asc") return a.name.localeCompare(b.name);
            if (caseSort === "name_desc") return b.name.localeCompare(a.name);
            if (caseSort === "status_asc") return a.status.localeCompare(b.status);
            return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        });
        return sorted;
    }, [cases, caseQuery, statusFilter, caseSort]);

    useEffect(() => {
        if (filteredCases.length === 0) { setSelectedCaseId(null); return; }
        if (!filteredCases.some((c) => c.id === selectedCaseId)) setSelectedCaseId(filteredCases[0].id);
    }, [filteredCases, selectedCaseId]);

    const openCaseCount = useMemo(() => cases.filter((c) => c.status.toUpperCase() === "ACTIVE").length, [cases]);
    const highSeveritySignals = useMemo(() => signals.filter((s) => { const sev = s.severity.toLowerCase(); return sev === "high" || sev === "critical"; }).length, [signals]);
    const openSignals = useMemo(() => signals.filter((s) => s.status.toLowerCase() === "open").length, [signals]);
    const documentTypes = useMemo(() => Array.from(new Set((selectedCase?.documents ?? []).map((d) => d.doc_type))).sort(), [selectedCase]);
    const ocrStatuses = useMemo(() => Array.from(new Set((selectedCase?.documents ?? []).map((d) => d.ocr_status))).sort(), [selectedCase]);
    const filteredDocuments = useMemo(() => (selectedCase?.documents ?? []).filter((d) => {
        return (docTypeFilter === "all" || d.doc_type === docTypeFilter) && (ocrFilter === "all" || d.ocr_status === ocrFilter);
    }), [selectedCase, docTypeFilter, ocrFilter]);
    const signalSeverities = useMemo(() => Array.from(new Set(signals.map((s) => s.severity))).sort(), [signals]);
    const signalStatuses = useMemo(() => Array.from(new Set(signals.map((s) => s.status))).sort(), [signals]);
    const filteredSignals = useMemo(() => signals.filter((s) => {
        return (signalSeverityFilter === "all" || s.severity === signalSeverityFilter) && (signalStatusFilter === "all" || s.status === signalStatusFilter);
    }), [signals, signalSeverityFilter, signalStatusFilter]);

    useEffect(() => {
        if (filteredSignals.length === 0) { setActiveSignalId(null); return; }
        if (!activeSignalId || !filteredSignals.some((s) => s.id === activeSignalId)) setActiveSignalId(filteredSignals[0].id);
    }, [filteredSignals, activeSignalId]);

    function getSignalDraft(signal: SignalItem) {
        return triageDrafts[signal.id] ?? { status: signal.status, note: signal.investigator_note ?? "" };
    }

    function validateCaseForm() {
        const nextErrors: { name?: string; referral?: string } = {};
        if (!newCaseName.trim()) nextErrors.name = "Case name is required.";
        else if (newCaseName.trim().length < 3) nextErrors.name = "Case name should be at least 3 characters.";
        if (newCaseReferral.trim() && newCaseReferral.trim().length < 3) nextErrors.referral = "Referral reference should be at least 3 characters if provided.";
        setFormErrors(nextErrors);
        return Object.keys(nextErrors).length === 0;
    }

    async function handleCreateCase(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!validateCaseForm()) { pushToast("error", "Review the new case form and fix the highlighted fields."); return; }
        setIsSubmittingCase(true);
        try {
            const created = await createCase({ name: newCaseName.trim(), referral_ref: newCaseReferral.trim(), notes: newCaseNotes.trim() });
            setCases((prev) => [created, ...prev]);
            setSelectedCaseId(created.id);
            setNewCaseName(""); setNewCaseReferral(""); setNewCaseNotes(""); setFormErrors({});
            pushToast("success", `Case created: ${created.name}`);
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setIsSubmittingCase(false); }
    }

    async function handleSignalSave(signal: SignalItem) {
        if (!selectedCaseId) return;
        const draft = getSignalDraft(signal);
        if (draft.status.toUpperCase() === "DISMISSED" && !draft.note.trim()) {
            setTriageError("A note is required when dismissing a signal."); return;
        }
        setSavingSignalId(signal.id);
        setTriageError(null);
        try {
            const updated = await updateSignal(selectedCaseId, signal.id, { status: draft.status, investigator_note: draft.note });
            setSignals((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
            setTriageDrafts((prev) => { const next = { ...prev }; delete next[signal.id]; return next; });
            pushToast("success", `Signal updated: ${updated.title}`);
        } catch (error) { pushToast("error", (error as Error).message); }
        finally { setSavingSignalId(null); }
    }

    function handleSignalDraftChange(signalId: string, draft: { status: string; note: string }) {
        setTriageDrafts((prev) => ({ ...prev, [signalId]: draft }));
    }

    // ── Keyboard shortcuts ──
    useEffect(() => {
        function isTypingTarget(target: EventTarget | null): boolean {
            if (!(target instanceof HTMLElement)) return false;
            const tag = target.tagName;
            return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
        }
        function onKeyDown(event: KeyboardEvent) {
            if (isTypingTarget(event.target)) return;
            const key = event.key.toLowerCase();
            if (key === "j" || key === "k") {
                if (filteredCases.length === 0) return;
                event.preventDefault();
                const idx = filteredCases.findIndex((c) => c.id === selectedCaseId);
                const base = idx >= 0 ? idx : 0;
                const next = key === "j" ? Math.min(filteredCases.length - 1, base + 1) : Math.max(0, base - 1);
                setSelectedCaseId(filteredCases[next].id);
                return;
            }
            const shortcutStatus: Record<string, "OPEN" | "REVIEWED" | "DISMISSED"> = { "1": "OPEN", "2": "REVIEWED", "3": "DISMISSED" };
            const nextStatus = shortcutStatus[key];
            if (!nextStatus || !activeSignalId) return;
            const signal = filteredSignals.find((s) => s.id === activeSignalId);
            if (!signal) return;
            event.preventDefault();
            const draft = getSignalDraft(signal);
            handleSignalDraftChange(signal.id, { ...draft, status: nextStatus });
            pushToast("success", `Draft status set to ${nextStatus} for ${signal.title}`);
        }
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [activeSignalId, filteredCases, filteredSignals, selectedCaseId]);

    return (
        <div className={styles.legacyAppShell}>
            <DashboardMetrics
                totalCases={cases.length}
                openCaseCount={openCaseCount}
                highSeveritySignals={highSeveritySignals}
                openSignals={openSignals}
            />

            <main className={styles.gridLayout}>
                <CasesPanel
                    filteredCases={filteredCases} selectedCaseId={selectedCaseId} caseSeverityMap={caseSeverityMap}
                    loadingCases={loadingCases} caseQuery={caseQuery} statusFilter={statusFilter} caseSort={caseSort}
                    availableStatuses={availableStatuses} newCaseName={newCaseName} newCaseReferral={newCaseReferral}
                    newCaseNotes={newCaseNotes} isSubmittingCase={isSubmittingCase} formErrors={formErrors}
                    onCreateCase={handleCreateCase} onSelectCase={setSelectedCaseId} onCaseQueryChange={setCaseQuery}
                    onStatusFilterChange={setStatusFilter} onCaseSortChange={setCaseSort}
                    onNewCaseNameChange={(v) => { setNewCaseName(v); if (formErrors.name) setFormErrors((p) => ({ ...p, name: undefined })); }}
                    onNewCaseReferralChange={(v) => { setNewCaseReferral(v); if (formErrors.referral) setFormErrors((p) => ({ ...p, referral: undefined })); }}
                    onNewCaseNotesChange={setNewCaseNotes} formatDate={formatDate}
                />
                <CaseDetailPanel
                    activeCaseName={activeCaseName} selectedCase={selectedCase} loadingCaseDetail={loadingCaseDetail}
                    filteredDocuments={filteredDocuments} documentTypes={documentTypes} ocrStatuses={ocrStatuses}
                    docTypeFilter={docTypeFilter} ocrFilter={ocrFilter} filteredSignals={filteredSignals}
                    activeSignalId={activeSignalId} signals={signals} signalSeverities={signalSeverities}
                    signalStatuses={signalStatuses} signalSeverityFilter={signalSeverityFilter}
                    signalStatusFilter={signalStatusFilter} triageError={triageError} savingSignalId={savingSignalId}
                    referrals={referrals} loadingReferrals={loadingReferrals} savingReferralId={savingReferralId}
                    detections={detections} loadingDetections={loadingDetections} savingDetectionId={savingDetectionId}
                    generatingMemo={generatingMemo} processingPendingOcr={processingPendingOcr}
                    reevaluatingSignals={reevaluatingSignals} deletingDocumentId={deletingDocumentId}
                    onDocTypeFilterChange={setDocTypeFilter} onOcrFilterChange={setOcrFilter}
                    onSignalSeverityFilterChange={setSignalSeverityFilter} onSignalStatusFilterChange={setSignalStatusFilter}
                    getSignalDraft={getSignalDraft} onSignalDraftChange={handleSignalDraftChange}
                    onActiveSignalChange={setActiveSignalId}
                    onSignalSave={(s) => { void handleSignalSave(s); }}
                    onCreateReferral={(p) => { void handleCreateReferral(p); }}
                    onUpdateReferral={(id, p) => { void handleUpdateReferral(id, p); }}
                    onDeleteReferral={(id) => { void handleDeleteReferral(id); }}
                    onUpdateDetection={(id, p) => { void handleUpdateDetection(id, p); }}
                    onDeleteDetection={(id) => { void handleDeleteDetection(id); }}
                    onDeleteDocument={(id) => { void handleDeleteDocument(id); }}
                    onGenerateMemo={() => { void handleGenerateMemo(); }}
                    onProcessPendingOcr={() => { void handleProcessPendingOcr(); }}
                    onReevaluateSignals={() => { void handleReevaluateSignals(); }}
                    onBulkUpload={handleBulkUpload} onBulkUploadComplete={handleBulkUploadComplete}
                    formatDate={formatDate} formatSize={formatSize}
                />
            </main>

            <ToastStack toasts={toasts} onDismiss={removeToast} />
        </div>
    );
}
