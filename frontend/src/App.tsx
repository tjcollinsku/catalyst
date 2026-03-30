import { useEffect, useMemo, useRef, useState } from "react";
import { BulkUploadResult, bulkUploadDocuments, createCase, createReferral, deleteDetection, deleteDocument, deleteReferral, fetchCaseDetail, fetchCases, fetchCaseSignals, fetchDetections, fetchReferrals, fetchSignalSummary, generateReferralMemo, isAbortError, processPendingOcr, updateDetection, updateReferral, updateSignal } from "./api";
import { CaseDetailPanel } from "./components/CaseDetailPanel";
import { CasesPanel } from "./components/CasesPanel";
import { DashboardMetrics } from "./components/DashboardMetrics";
import { ToastItem, ToastStack } from "./components/ui/ToastStack";
import { CaseDetail, CaseSummary, DetectionItem, DetectionUpdatePayload, NewReferralPayload, ReferralItem, ReferralUpdatePayload, SignalItem } from "./types";
import { formatDate, formatSize } from "./utils/format";
import { readOptionalQueryParam, readQueryParam, syncDashboardQueryParams } from "./utils/queryParams";

export default function App() {
    const [cases, setCases] = useState<CaseSummary[]>([]);
    const [selectedCaseId, setSelectedCaseId] = useState<string | null>(() => readOptionalQueryParam("case"));
    const [selectedCase, setSelectedCase] = useState<CaseDetail | null>(null);
    const [signals, setSignals] = useState<SignalItem[]>([]);
    const [activeSignalId, setActiveSignalId] = useState<string | null>(null);
    const [caseQuery, setCaseQuery] = useState(() => readQueryParam("caseQuery", ""));
    const [statusFilter, setStatusFilter] = useState(() => readQueryParam("caseStatus", "all"));
    const [caseSort, setCaseSort] = useState(() => readQueryParam("caseSort", "updated_desc"));
    const [docTypeFilter, setDocTypeFilter] = useState(() => readQueryParam("docType", "all"));
    const [ocrFilter, setOcrFilter] = useState(() => readQueryParam("ocr", "all"));
    const [signalSeverityFilter, setSignalSeverityFilter] = useState(() => readQueryParam("signalSeverity", "all"));
    const [signalStatusFilter, setSignalStatusFilter] = useState(() => readQueryParam("signalStatus", "all"));
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
    const [loadingCases, setLoadingCases] = useState(true);
    const [loadingCaseDetail, setLoadingCaseDetail] = useState(false);
    const toastIdRef = useRef(0);

    function removeToast(id: number) {
        setToasts((previous) => previous.filter((toast) => toast.id !== id));
    }

    function pushToast(tone: "error" | "success", message: string) {
        const id = ++toastIdRef.current;
        setToasts((previous) => [...previous, { id, tone, message }]);
        window.setTimeout(() => {
            removeToast(id);
        }, 3400);
    }

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
                    if (current && response.results.some((caseItem) => caseItem.id === current)) {
                        return current;
                    }
                    return response.results[0]?.id ?? null;
                });
                const map: Record<string, string> = {};
                for (const item of summaryResponse.results) {
                    map[item.case_id] = item.highest_severity;
                }
                setCaseSeverityMap(map);
            } catch (error) {
                if (!isAbortError(error)) {
                    pushToast("error", (error as Error).message);
                }
            } finally {
                if (!controller.signal.aborted) {
                    setLoadingCases(false);
                }
            }
        }

        void loadCases();

        return () => controller.abort();
    }, []);

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
                    if (current && signalResponse.results.some((signal) => signal.id === current)) {
                        return current;
                    }
                    return signalResponse.results[0]?.id ?? null;
                });
            } catch (error) {
                if (!isAbortError(error)) {
                    pushToast("error", (error as Error).message);
                }
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

    async function handleCreateReferral(payload: NewReferralPayload) {
        if (!selectedCaseId) return;
        try {
            const created = await createReferral(selectedCaseId, payload);
            setReferrals((prev) => [created, ...prev]);
            pushToast("success", `Referral to ${created.agency_name} created.`);
        } catch (error) {
            pushToast("error", (error as Error).message);
        }
    }

    async function handleUpdateReferral(referralId: number, payload: ReferralUpdatePayload) {
        if (!selectedCaseId) return;
        setSavingReferralId(referralId);
        try {
            const updated = await updateReferral(selectedCaseId, referralId, payload);
            setReferrals((prev) => prev.map((r) => (r.referral_id === updated.referral_id ? updated : r)));
            pushToast("success", `Referral updated.`);
        } catch (error) {
            pushToast("error", (error as Error).message);
        } finally {
            setSavingReferralId(null);
        }
    }

    async function handleDeleteReferral(referralId: number) {
        if (!selectedCaseId) return;
        setSavingReferralId(referralId);
        try {
            await deleteReferral(selectedCaseId, referralId);
            setReferrals((prev) => prev.filter((r) => r.referral_id !== referralId));
            pushToast("success", "Referral deleted.");
        } catch (error) {
            pushToast("error", (error as Error).message);
        } finally {
            setSavingReferralId(null);
        }
    }

    async function handleUpdateDetection(detectionId: string, payload: DetectionUpdatePayload) {
        if (!selectedCaseId) return;
        setSavingDetectionId(detectionId);
        try {
            const updated = await updateDetection(selectedCaseId, detectionId, payload);
            setDetections((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
            pushToast("success", "Detection updated.");
        } catch (error) {
            pushToast("error", (error as Error).message);
        } finally {
            setSavingDetectionId(null);
        }
    }

    async function handleDeleteDetection(detectionId: string) {
        if (!selectedCaseId) return;
        setSavingDetectionId(detectionId);
        try {
            await deleteDetection(selectedCaseId, detectionId);
            setDetections((prev) => prev.filter((d) => d.id !== detectionId));
            pushToast("success", "Detection removed.");
        } catch (error) {
            pushToast("error", (error as Error).message);
        } finally {
            setSavingDetectionId(null);
        }
    }

    async function handleBulkUpload(files: File[]): Promise<BulkUploadResult> {
        if (!selectedCaseId) return { created: [], errors: [] };
        try {
            return await bulkUploadDocuments(selectedCaseId, files);
        } catch (error) {
            const message = (error as Error).message || "Upload failed.";
            pushToast("error", message);
            return {
                created: [],
                errors: files.map((file) => ({ filename: file.name, error: message })),
            };
        }
    }

    function handleBulkUploadComplete(result: BulkUploadResult) {
        if (result.created.length > 0) {
            setSelectedCase((prev) => {
                if (!prev) return prev;
                return { ...prev, documents: [...result.created, ...prev.documents] };
            });
            pushToast("success", `${result.created.length} document${result.created.length > 1 ? "s" : ""} uploaded.`);
        }
        if (result.errors.length > 0) {
            pushToast("error", `${result.errors.length} file${result.errors.length > 1 ? "s" : ""} failed to upload.`);
        }
    }

    async function handleDeleteDocument(documentId: string) {
        if (!selectedCaseId || !selectedCase) return;

        const target = selectedCase.documents.find((document) => document.id === documentId);
        if (!target) return;

        const confirmed = window.confirm(`Delete \"${target.filename}\" from this case?`);
        if (!confirmed) return;

        setDeletingDocumentId(documentId);
        try {
            await deleteDocument(selectedCaseId, documentId);
            setSelectedCase((prev) => {
                if (!prev) return prev;
                return {
                    ...prev,
                    documents: prev.documents.filter((document) => document.id !== documentId),
                };
            });
            pushToast("success", `Deleted document: ${target.filename}`);
        } catch (error) {
            pushToast("error", (error as Error).message);
        } finally {
            setDeletingDocumentId(null);
        }
    }

    async function handleGenerateMemo() {
        if (!selectedCaseId) return;
        setGeneratingMemo(true);
        try {
            const doc = await generateReferralMemo(selectedCaseId);
            setSelectedCase((prev) => {
                if (!prev) return prev;
                return { ...prev, documents: [doc, ...prev.documents] };
            });
            pushToast("success", "Referral memo generated and added to documents.");
        } catch (error) {
            pushToast("error", (error as Error).message);
        } finally {
            setGeneratingMemo(false);
        }
    }

    async function handleProcessPendingOcr() {
        if (!selectedCaseId) return;
        setProcessingPendingOcr(true);
        try {
            const result = await processPendingOcr(selectedCaseId);
            if (result.processed.length > 0) {
                const processedById = new Map(result.processed.map((document) => [document.id, document]));
                setSelectedCase((prev) => {
                    if (!prev) return prev;
                    return {
                        ...prev,
                        documents: prev.documents.map((document) => processedById.get(document.id) ?? document),
                    };
                });
            }

            pushToast(
                "success",
                `OCR processing complete: ${result.processed.length} processed, ${result.errors.length} failed, ${result.skipped} skipped.`
            );

            if (result.errors.length > 0) {
                pushToast("error", `OCR errors: ${result.errors.map((error) => error.filename).join(", ")}`);
            }
        } catch (error) {
            pushToast("error", (error as Error).message);
        } finally {
            setProcessingPendingOcr(false);
        }
    }

    useEffect(() => {
        syncDashboardQueryParams({
            selectedCaseId,
            caseQuery,
            statusFilter,
            caseSort,
            docTypeFilter,
            ocrFilter,
            signalSeverityFilter,
            signalStatusFilter
        });
    }, [
        selectedCaseId,
        caseQuery,
        statusFilter,
        caseSort,
        docTypeFilter,
        ocrFilter,
        signalSeverityFilter,
        signalStatusFilter
    ]);

    const activeCaseName = useMemo(
        () => selectedCase?.name ?? "No case selected",
        [selectedCase]
    );

    const availableStatuses = useMemo(
        () => Array.from(new Set(cases.map((caseItem) => caseItem.status))).sort(),
        [cases]
    );

    const filteredCases = useMemo(() => {
        const normalizedQuery = caseQuery.trim().toLowerCase();
        const visibleCases = cases.filter((caseItem) => {
            const statusMatch =
                statusFilter === "all" || caseItem.status === statusFilter;
            const queryMatch =
                normalizedQuery.length === 0 ||
                caseItem.name.toLowerCase().includes(normalizedQuery) ||
                caseItem.referral_ref.toLowerCase().includes(normalizedQuery);
            return statusMatch && queryMatch;
        });

        const sortedCases = [...visibleCases];
        sortedCases.sort((left, right) => {
            if (caseSort === "updated_asc") {
                return new Date(left.updated_at).getTime() - new Date(right.updated_at).getTime();
            }

            if (caseSort === "name_asc") {
                return left.name.localeCompare(right.name);
            }

            if (caseSort === "name_desc") {
                return right.name.localeCompare(left.name);
            }

            if (caseSort === "status_asc") {
                return left.status.localeCompare(right.status);
            }

            return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
        });

        return sortedCases;
    }, [cases, caseQuery, statusFilter, caseSort]);

    useEffect(() => {
        if (filteredCases.length === 0) {
            setSelectedCaseId(null);
            return;
        }

        const selectedStillVisible = filteredCases.some(
            (caseItem) => caseItem.id === selectedCaseId
        );
        if (!selectedStillVisible) {
            setSelectedCaseId(filteredCases[0].id);
        }
    }, [filteredCases, selectedCaseId]);

    const openCaseCount = useMemo(
        () => cases.filter((caseItem) => caseItem.status.toUpperCase() === "ACTIVE").length,
        [cases]
    );

    const highSeveritySignals = useMemo(
        () => signals.filter((signal) => {
            const severity = signal.severity.toLowerCase();
            return severity === "high" || severity === "critical";
        }).length,
        [signals]
    );

    const openSignals = useMemo(
        () => signals.filter((signal) => signal.status.toLowerCase() === "open").length,
        [signals]
    );

    const documentTypes = useMemo(
        () => Array.from(new Set((selectedCase?.documents ?? []).map((document) => document.doc_type))).sort(),
        [selectedCase]
    );

    const ocrStatuses = useMemo(
        () => Array.from(new Set((selectedCase?.documents ?? []).map((document) => document.ocr_status))).sort(),
        [selectedCase]
    );

    const filteredDocuments = useMemo(
        () => (selectedCase?.documents ?? []).filter((document) => {
            const docTypeMatch = docTypeFilter === "all" || document.doc_type === docTypeFilter;
            const ocrMatch = ocrFilter === "all" || document.ocr_status === ocrFilter;
            return docTypeMatch && ocrMatch;
        }),
        [selectedCase, docTypeFilter, ocrFilter]
    );

    const signalSeverities = useMemo(
        () => Array.from(new Set(signals.map((signal) => signal.severity))).sort(),
        [signals]
    );

    const signalStatuses = useMemo(
        () => Array.from(new Set(signals.map((signal) => signal.status))).sort(),
        [signals]
    );

    const filteredSignals = useMemo(
        () => signals.filter((signal) => {
            const severityMatch = signalSeverityFilter === "all" || signal.severity === signalSeverityFilter;
            const statusMatch = signalStatusFilter === "all" || signal.status === signalStatusFilter;
            return severityMatch && statusMatch;
        }),
        [signals, signalSeverityFilter, signalStatusFilter]
    );

    useEffect(() => {
        if (filteredSignals.length === 0) {
            setActiveSignalId(null);
            return;
        }

        if (!activeSignalId || !filteredSignals.some((signal) => signal.id === activeSignalId)) {
            setActiveSignalId(filteredSignals[0].id);
        }
    }, [filteredSignals, activeSignalId]);

    function getSignalDraft(signal: SignalItem) {
        return triageDrafts[signal.id] ?? { status: signal.status, note: signal.investigator_note ?? "" };
    }

    function validateCaseForm() {
        const nextErrors: { name?: string; referral?: string } = {};

        if (!newCaseName.trim()) {
            nextErrors.name = "Case name is required.";
        } else if (newCaseName.trim().length < 3) {
            nextErrors.name = "Case name should be at least 3 characters.";
        }

        if (newCaseReferral.trim() && newCaseReferral.trim().length < 3) {
            nextErrors.referral = "Referral reference should be at least 3 characters if provided.";
        }

        setFormErrors(nextErrors);
        return Object.keys(nextErrors).length === 0;
    }

    async function handleCreateCase(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!validateCaseForm()) {
            pushToast("error", "Review the new case form and fix the highlighted fields.");
            return;
        }

        setIsSubmittingCase(true);
        try {
            const created = await createCase({
                name: newCaseName.trim(),
                referral_ref: newCaseReferral.trim(),
                notes: newCaseNotes.trim()
            });

            setCases((previous) => [created, ...previous]);
            setSelectedCaseId(created.id);
            setNewCaseName("");
            setNewCaseReferral("");
            setNewCaseNotes("");
            setFormErrors({});
            pushToast("success", `Case created: ${created.name}`);
        } catch (error) {
            pushToast("error", (error as Error).message);
        } finally {
            setIsSubmittingCase(false);
        }
    }

    async function handleSignalSave(signal: SignalItem) {
        if (!selectedCaseId) {
            return;
        }

        const draft = getSignalDraft(signal);
        if (draft.status.toUpperCase() === "DISMISSED" && !draft.note.trim()) {
            setTriageError("A note is required when dismissing a signal.");
            return;
        }

        setSavingSignalId(signal.id);
        setTriageError(null);
        try {
            const updated = await updateSignal(selectedCaseId, signal.id, {
                status: draft.status,
                investigator_note: draft.note
            });

            setSignals((previous) => previous.map((item) => (item.id === updated.id ? updated : item)));
            setTriageDrafts((previous) => {
                const next = { ...previous };
                delete next[signal.id];
                return next;
            });
            pushToast("success", `Signal updated: ${updated.title}`);
        } catch (error) {
            pushToast("error", (error as Error).message);
        } finally {
            setSavingSignalId(null);
        }
    }

    function handleSignalDraftChange(signalId: string, draft: { status: string; note: string }) {
        setTriageDrafts((previous) => ({
            ...previous,
            [signalId]: draft
        }));
    }

    useEffect(() => {
        function isTypingTarget(target: EventTarget | null): boolean {
            if (!(target instanceof HTMLElement)) {
                return false;
            }

            const tag = target.tagName;
            return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
        }

        function onKeyDown(event: KeyboardEvent) {
            if (isTypingTarget(event.target)) {
                return;
            }

            const normalizedKey = event.key.toLowerCase();

            if (normalizedKey === "j" || normalizedKey === "k") {
                if (filteredCases.length === 0) {
                    return;
                }

                event.preventDefault();
                const currentIndex = filteredCases.findIndex((caseItem) => caseItem.id === selectedCaseId);
                const fallbackIndex = currentIndex >= 0 ? currentIndex : 0;
                const nextIndex = normalizedKey === "j"
                    ? Math.min(filteredCases.length - 1, fallbackIndex + 1)
                    : Math.max(0, fallbackIndex - 1);
                setSelectedCaseId(filteredCases[nextIndex].id);
                return;
            }

            const shortcutStatus: Record<string, "OPEN" | "REVIEWED" | "DISMISSED"> = {
                "1": "OPEN",
                "2": "REVIEWED",
                "3": "DISMISSED"
            };

            const nextStatus = shortcutStatus[normalizedKey];
            if (!nextStatus || !activeSignalId) {
                return;
            }

            const signal = filteredSignals.find((item) => item.id === activeSignalId);
            if (!signal) {
                return;
            }

            event.preventDefault();
            const draft = getSignalDraft(signal);
            handleSignalDraftChange(signal.id, {
                ...draft,
                status: nextStatus
            });
            pushToast("success", `Draft status set to ${nextStatus} for ${signal.title}`);
        }

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [activeSignalId, filteredCases, filteredSignals, selectedCaseId]);

    return (
        <div className="app-shell">
            <header className="hero">
                <p className="eyebrow">Catalyst Platform</p>
                <h1>Investigation Frontend Prototype</h1>
                <p>
                    Live view over backend APIs for case queues, evidence documents, and
                    signal triage.
                </p>
            </header>

            <ToastStack toasts={toasts} onDismiss={removeToast} />

            <DashboardMetrics
                totalCases={cases.length}
                openCaseCount={openCaseCount}
                highSeveritySignals={highSeveritySignals}
                openSignals={openSignals}
            />

            <main className="grid-layout">
                <CasesPanel
                    filteredCases={filteredCases}
                    selectedCaseId={selectedCaseId}
                    caseSeverityMap={caseSeverityMap}
                    loadingCases={loadingCases}
                    caseQuery={caseQuery}
                    statusFilter={statusFilter}
                    caseSort={caseSort}
                    availableStatuses={availableStatuses}
                    newCaseName={newCaseName}
                    newCaseReferral={newCaseReferral}
                    newCaseNotes={newCaseNotes}
                    isSubmittingCase={isSubmittingCase}
                    formErrors={formErrors}
                    onCreateCase={handleCreateCase}
                    onSelectCase={setSelectedCaseId}
                    onCaseQueryChange={setCaseQuery}
                    onStatusFilterChange={setStatusFilter}
                    onCaseSortChange={setCaseSort}
                    onNewCaseNameChange={(value) => {
                        setNewCaseName(value);
                        if (formErrors.name) {
                            setFormErrors((previous) => ({ ...previous, name: undefined }));
                        }
                    }}
                    onNewCaseReferralChange={(value) => {
                        setNewCaseReferral(value);
                        if (formErrors.referral) {
                            setFormErrors((previous) => ({ ...previous, referral: undefined }));
                        }
                    }}
                    onNewCaseNotesChange={setNewCaseNotes}
                    formatDate={formatDate}
                />

                <CaseDetailPanel
                    activeCaseName={activeCaseName}
                    selectedCase={selectedCase}
                    loadingCaseDetail={loadingCaseDetail}
                    filteredDocuments={filteredDocuments}
                    documentTypes={documentTypes}
                    ocrStatuses={ocrStatuses}
                    docTypeFilter={docTypeFilter}
                    ocrFilter={ocrFilter}
                    filteredSignals={filteredSignals}
                    activeSignalId={activeSignalId}
                    signals={signals}
                    signalSeverities={signalSeverities}
                    signalStatuses={signalStatuses}
                    signalSeverityFilter={signalSeverityFilter}
                    signalStatusFilter={signalStatusFilter}
                    triageError={triageError}
                    savingSignalId={savingSignalId}
                    referrals={referrals}
                    loadingReferrals={loadingReferrals}
                    savingReferralId={savingReferralId}
                    detections={detections}
                    loadingDetections={loadingDetections}
                    savingDetectionId={savingDetectionId}
                    generatingMemo={generatingMemo}
                    processingPendingOcr={processingPendingOcr}
                    deletingDocumentId={deletingDocumentId}
                    onDocTypeFilterChange={setDocTypeFilter}
                    onOcrFilterChange={setOcrFilter}
                    onSignalSeverityFilterChange={setSignalSeverityFilter}
                    onSignalStatusFilterChange={setSignalStatusFilter}
                    getSignalDraft={getSignalDraft}
                    onSignalDraftChange={handleSignalDraftChange}
                    onActiveSignalChange={setActiveSignalId}
                    onSignalSave={(signal) => { void handleSignalSave(signal); }}
                    onCreateReferral={(payload) => { void handleCreateReferral(payload); }}
                    onUpdateReferral={(id, payload) => { void handleUpdateReferral(id, payload); }}
                    onDeleteReferral={(id) => { void handleDeleteReferral(id); }}
                    onUpdateDetection={(id, payload) => { void handleUpdateDetection(id, payload); }}
                    onDeleteDetection={(id) => { void handleDeleteDetection(id); }}
                    onDeleteDocument={(id) => { void handleDeleteDocument(id); }}
                    onGenerateMemo={() => { void handleGenerateMemo(); }}
                    onProcessPendingOcr={() => { void handleProcessPendingOcr(); }}
                    onBulkUpload={handleBulkUpload}
                    onBulkUploadComplete={handleBulkUploadComplete}
                    formatDate={formatDate}
                    formatSize={formatSize}
                />
            </main>
        </div>
    );
}
