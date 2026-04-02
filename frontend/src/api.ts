import {
    ActivityEntry,
    AIAskMessage,
    AIAskResponse,
    AIConnectionsResponse,
    AINarrativeResponse,
    AISummarizeResponse,
    CaseDetail,
    CaseGraphResponse,
    CaseSummary,
    CrossCaseReferral,
    CrossCaseSignal,
    DetectionItem,
    DetectionUpdatePayload,
    DocumentDetail,
    DocumentItem,
    EntityItem,
    FinancialSnapshotItem,
    FindingItem,
    FindingUpdatePayload,
    NewCasePayload,
    NewFindingPayload,
    NewReferralPayload,
    PaginatedResponse,
    ReferralItem,
    ReferralUpdatePayload,
    SearchResponse,
    SignalItem,
    SignalUpdatePayload
} from "./types";

const API_BASE = "";
const DEFAULT_TIMEOUT_MS = 15000;
const BULK_UPLOAD_TIMEOUT_MS = 300000;

// ---------------------------------------------------------------------------
// SEC-033: CSRF token handling for write requests
// ---------------------------------------------------------------------------

/** Read the Django csrftoken cookie value. */
function getCSRFToken(): string {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : "";
}

/** HTTP methods that require a CSRF token. */
const CSRF_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** Fetch the CSRF cookie from the backend (called once on app startup). */
export async function initCSRF(): Promise<void> {
    try {
        await fetch(`${API_BASE}/api/csrf/`, { credentials: "include" });
    } catch {
        // Non-fatal — CSRF cookie may already be set from a prior request
    }
}

export interface ApiRequestOptions {
    signal?: AbortSignal;
    timeoutMs?: number;
}

function formatErrorDetails(details: unknown): string {
    if (typeof details === "string") {
        return details;
    }

    if (details && typeof details === "object") {
        const record = details as Record<string, unknown>;

        if (typeof record.detail === "string") {
            return record.detail;
        }

        const messages = Object.entries(record)
            .flatMap(([key, value]) => {
                if (Array.isArray(value)) {
                    return value.map((item) => `${key}: ${String(item)}`);
                }
                if (typeof value === "string") {
                    return `${key}: ${value}`;
                }
                return [];
            })
            .filter(Boolean);

        if (messages.length > 0) {
            return messages.join("; ");
        }

        return JSON.stringify(details);
    }

    return "Unexpected error response.";
}

function isAbortDomException(error: unknown): boolean {
    return error instanceof Error && error.name === "AbortError";
}

export function isAbortError(error: unknown): boolean {
    return isAbortDomException(error);
}

async function request<T>(path: string, init: RequestInit = {}, options: ApiRequestOptions = {}): Promise<T> {
    const headers = new Headers(init.headers ?? {});
    headers.set("Accept", "application/json");
    const shouldSetJsonContentType = typeof init.body === "string";
    if (!headers.has("Content-Type") && shouldSetJsonContentType) {
        headers.set("Content-Type", "application/json");
    }

    // SEC-033: Include CSRF token on write requests
    const method = (init.method ?? "GET").toUpperCase();
    if (CSRF_METHODS.has(method)) {
        const csrfToken = getCSRFToken();
        if (csrfToken) {
            headers.set("X-CSRFToken", csrfToken);
        }
    }

    const controller = new AbortController();
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    let didTimeout = false;

    const abortFromCaller = () => controller.abort(options.signal?.reason);
    if (options.signal) {
        if (options.signal.aborted) {
            controller.abort(options.signal.reason);
        } else {
            options.signal.addEventListener("abort", abortFromCaller);
        }
    }

    const timeoutId = globalThis.setTimeout(() => {
        didTimeout = true;
        controller.abort(new Error("Request timed out"));
    }, timeoutMs);

    try {
        const response = await fetch(`${API_BASE}${path}`, {
            ...init,
            headers,
            credentials: "include",    // SEC-033: send cookies (CSRF token)
            signal: controller.signal
        });

        if (!response.ok) {
            let details: unknown = response.statusText;
            try {
                const contentType = response.headers.get("content-type") ?? "";
                if (contentType.includes("application/json")) {
                    details = await response.json();
                } else {
                    details = await response.text();
                }
            } catch {
                details = response.statusText;
            }
            throw new Error(`Request failed (${response.status}): ${formatErrorDetails(details)}`);
        }

        if (response.status === 204) {
            return undefined as T;
        }

        const contentType = response.headers.get("content-type") ?? "";
        if (!contentType.includes("application/json")) {
            return undefined as T;
        }

        return response.json() as Promise<T>;
    } catch (error) {
        if (didTimeout) {
            throw new Error(`Request timed out after ${timeoutMs}ms.`);
        }

        if (isAbortDomException(error)) {
            throw error;
        }

        if (error instanceof Error) {
            if (error.message.startsWith("Request failed (")) {
                throw error;
            }
            throw new Error(`Network request failed: ${error.message}`);
        }

        throw new Error("Network request failed.");
    } finally {
        globalThis.clearTimeout(timeoutId);
        if (options.signal) {
            options.signal.removeEventListener("abort", abortFromCaller);
        }
    }
}

export async function fetchCases(
    limit = 25,
    offset = 0,
    options?: ApiRequestOptions
): Promise<PaginatedResponse<CaseSummary>> {
    return request<PaginatedResponse<CaseSummary>>(
        `/api/cases/?limit=${limit}&offset=${offset}&order_by=created_at&direction=desc`,
        {},
        options
    );
}

export async function fetchCaseDetail(caseId: string, options?: ApiRequestOptions): Promise<CaseDetail> {
    return request<CaseDetail>(`/api/cases/${caseId}/`, {}, options);
}

export async function fetchDocumentDetail(
    caseId: string,
    documentId: string,
    options?: ApiRequestOptions
): Promise<DocumentDetail> {
    return request<DocumentDetail>(`/api/cases/${caseId}/documents/${documentId}/`, {}, options);
}

export async function fetchCaseFinancials(
    caseId: string,
    options?: ApiRequestOptions
): Promise<{ results: FinancialSnapshotItem[] }> {
    return request<{ results: FinancialSnapshotItem[] }>(`/api/cases/${caseId}/financials/`, {}, options);
}

export async function fetchCaseSignals(
    caseId: string,
    options?: ApiRequestOptions
): Promise<PaginatedResponse<SignalItem>> {
    return request<PaginatedResponse<SignalItem>>(
        `/api/cases/${caseId}/signals/?limit=100&offset=0&order_by=detected_at&direction=desc`,
        {},
        options
    );
}

export async function createCase(payload: NewCasePayload, options?: ApiRequestOptions): Promise<CaseSummary> {
    return request<CaseSummary>("/api/cases/", {
        method: "POST",
        body: JSON.stringify(payload)
    }, options);
}

export async function updateSignal(
    caseId: string,
    signalId: string,
    payload: SignalUpdatePayload,
    options?: ApiRequestOptions
): Promise<SignalItem> {
    return request<SignalItem>(`/api/cases/${caseId}/signals/${signalId}/`, {
        method: "PATCH",
        body: JSON.stringify(payload)
    }, options);
}

export async function fetchReferrals(caseId: string, options?: ApiRequestOptions): Promise<{ results: ReferralItem[] }> {
    return request<{ results: ReferralItem[] }>(`/api/cases/${caseId}/referrals/`, {}, options);
}

export async function createReferral(
    caseId: string,
    payload: NewReferralPayload,
    options?: ApiRequestOptions
): Promise<ReferralItem> {
    return request<ReferralItem>(`/api/cases/${caseId}/referrals/`, {
        method: "POST",
        body: JSON.stringify(payload)
    }, options);
}

export async function updateReferral(
    caseId: string,
    referralId: number,
    payload: ReferralUpdatePayload,
    options?: ApiRequestOptions
): Promise<ReferralItem> {
    return request<ReferralItem>(`/api/cases/${caseId}/referrals/${referralId}/`, {
        method: "PATCH",
        body: JSON.stringify(payload)
    }, options);
}

export async function deleteReferral(
    caseId: string,
    referralId: number,
    options?: ApiRequestOptions
): Promise<void> {
    return request<void>(`/api/cases/${caseId}/referrals/${referralId}/`, {
        method: "DELETE"
    }, options);
}

export async function deleteDocument(
    caseId: string,
    documentId: string,
    options?: ApiRequestOptions
): Promise<void> {
    return request<void>(`/api/cases/${caseId}/documents/${documentId}/`, {
        method: "DELETE"
    }, options);
}

export interface SignalSummaryItem {
    case_id: string;
    highest_severity: string;
    open_count: number;
}

export async function fetchSignalSummary(options?: ApiRequestOptions): Promise<{ results: SignalSummaryItem[] }> {
    return request<{ results: SignalSummaryItem[] }>("/api/signal-summary/", {}, options);
}

export interface BulkUploadResult {
    created: DocumentItem[];
    errors: { filename: string; error: string }[];
}

export interface ProcessPendingOcrResult {
    requested: number;
    processed: DocumentItem[];
    errors: { document_id: string; filename: string; error: string }[];
    skipped: number;
}

export async function bulkUploadDocuments(
    caseId: string,
    files: File[],
    options?: ApiRequestOptions
): Promise<BulkUploadResult> {
    const form = new FormData();
    for (const file of files) {
        form.append("files", file);
    }
    // Don't set Content-Type — browser sets it with boundary for multipart
    const headers = new Headers();
    headers.set("Accept", "application/json");
    return request<BulkUploadResult>(`/api/cases/${caseId}/documents/bulk/`, {
        method: "POST",
        headers,
        body: form,
    }, {
        ...options,
        timeoutMs: options?.timeoutMs ?? BULK_UPLOAD_TIMEOUT_MS,
    });
}

export async function processPendingOcr(
    caseId: string,
    options?: ApiRequestOptions
): Promise<ProcessPendingOcrResult> {
    return request<ProcessPendingOcrResult>(`/api/cases/${caseId}/documents/process-pending/`, {
        method: "POST"
    }, options);
}

export async function generateReferralMemo(caseId: string, options?: ApiRequestOptions): Promise<DocumentItem> {
    return request<DocumentItem>(`/api/cases/${caseId}/referral-memo/`, {
        method: "POST"
    }, options);
}

export async function fetchDetections(
    caseId: string,
    options?: ApiRequestOptions
): Promise<PaginatedResponse<DetectionItem>> {
    return request<PaginatedResponse<DetectionItem>>(
        `/api/cases/${caseId}/detections/?limit=100&offset=0&order_by=detected_at&direction=desc`,
        {},
        options
    );
}

export async function updateDetection(
    caseId: string,
    detectionId: string,
    payload: DetectionUpdatePayload,
    options?: ApiRequestOptions
): Promise<DetectionItem> {
    return request<DetectionItem>(`/api/cases/${caseId}/detections/${detectionId}/`, {
        method: "PATCH",
        body: JSON.stringify(payload)
    }, options);
}

export async function deleteDetection(
    caseId: string,
    detectionId: string,
    options?: ApiRequestOptions
): Promise<void> {
    return request<void>(`/api/cases/${caseId}/detections/${detectionId}/`, {
        method: "DELETE"
    }, options);
}

export interface ReevaluateSignalsResult {
    documents_evaluated: number;
    new_detections: DetectionItem[];
}

export async function reevaluateSignals(
    caseId: string,
    options?: ApiRequestOptions
): Promise<ReevaluateSignalsResult> {
    return request<ReevaluateSignalsResult>(`/api/cases/${caseId}/reevaluate-signals/`, {
        method: "POST"
    }, options);
}

/* ═══════════════════════════════════════════════════════════════
   Findings (Milestone 2)
   ═══════════════════════════════════════════════════════════════ */

export async function fetchFindings(
    caseId: string,
    options?: ApiRequestOptions
): Promise<PaginatedResponse<FindingItem>> {
    return request<PaginatedResponse<FindingItem>>(
        `/api/cases/${caseId}/findings/?limit=100&offset=0&order_by=created_at&direction=desc`,
        {},
        options
    );
}

export async function createFinding(
    caseId: string,
    payload: NewFindingPayload,
    options?: ApiRequestOptions
): Promise<FindingItem> {
    return request<FindingItem>(`/api/cases/${caseId}/findings/`, {
        method: "POST",
        body: JSON.stringify(payload)
    }, options);
}

export async function updateFinding(
    caseId: string,
    findingId: string,
    payload: FindingUpdatePayload,
    options?: ApiRequestOptions
): Promise<FindingItem> {
    return request<FindingItem>(`/api/cases/${caseId}/findings/${findingId}/`, {
        method: "PATCH",
        body: JSON.stringify(payload)
    }, options);
}

export async function deleteFinding(
    caseId: string,
    findingId: string,
    options?: ApiRequestOptions
): Promise<void> {
    return request<void>(`/api/cases/${caseId}/findings/${findingId}/`, {
        method: "DELETE"
    }, options);
}

/* ═══════════════════════════════════════════════════════════════
   Cross-case endpoints (Phase C)
   ═══════════════════════════════════════════════════════════════ */

export interface CrossCaseSignalFilters {
    status?: string;
    severity?: string;
    case_id?: string;
    rule_id?: string;
}

export async function fetchCrossCaseSignals(
    filters: CrossCaseSignalFilters = {},
    limit = 100,
    offset = 0,
    options?: ApiRequestOptions
): Promise<PaginatedResponse<CrossCaseSignal>> {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    params.set("order_by", "detected_at");
    params.set("direction", "desc");
    if (filters.status) params.set("status", filters.status);
    if (filters.severity) params.set("severity", filters.severity);
    if (filters.case_id) params.set("case_id", filters.case_id);
    if (filters.rule_id) params.set("rule_id", filters.rule_id);
    return request<PaginatedResponse<CrossCaseSignal>>(`/api/signals/?${params}`, {}, options);
}

export async function fetchCrossCaseReferrals(
    filters: { status?: string; agency?: string; case_id?: string } = {},
    limit = 100,
    offset = 0,
    options?: ApiRequestOptions
): Promise<PaginatedResponse<CrossCaseReferral>> {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    if (filters.status) params.set("status", filters.status);
    if (filters.agency) params.set("agency", filters.agency);
    if (filters.case_id) params.set("case_id", filters.case_id);
    return request<PaginatedResponse<CrossCaseReferral>>(`/api/referrals/?${params}`, {}, options);
}

export async function fetchEntities(
    filters: { type?: string; q?: string; case_id?: string } = {},
    limit = 100,
    offset = 0,
    options?: ApiRequestOptions
): Promise<{ count: number; limit: number; offset: number; results: EntityItem[] }> {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    if (filters.type) params.set("type", filters.type);
    if (filters.q) params.set("q", filters.q);
    if (filters.case_id) params.set("case_id", filters.case_id);
    return request<{ count: number; limit: number; offset: number; results: EntityItem[] }>(
        `/api/entities/?${params}`, {}, options,
    );
}

export async function fetchActivityFeed(
    limit = 20,
    options?: ApiRequestOptions
): Promise<{ results: ActivityEntry[] }> {
    return request<{ results: ActivityEntry[] }>(`/api/activity-feed/?limit=${limit}`, {}, options);
}

/* ═══════════════════════════════════════════════════════════════
   Search endpoint (Phase D)
   ═══════════════════════════════════════════════════════════════ */

export async function searchAll(
    query: string,
    filters: { type?: string; case_id?: string } = {},
    options?: ApiRequestOptions
): Promise<SearchResponse> {
    const params = new URLSearchParams();
    params.set("q", query);
    if (filters.type) params.set("type", filters.type);
    if (filters.case_id) params.set("case_id", filters.case_id);
    return request<SearchResponse>(`/api/search/?${params}`, {}, options);
}

/* ═══════════════════════════════════════════════════════════════
   Report generation (Phase D)
   ═══════════════════════════════════════════════════════════════ */

export interface ReportExportResult {
    format: string;
    filename: string;
    download_url: string;
}

export async function exportCaseReport(
    caseId: string,
    format: "json" | "csv" = "json",
    options?: ApiRequestOptions
): Promise<ReportExportResult> {
    return request<ReportExportResult>(`/api/cases/${caseId}/export/?format=${format}`, {}, options);
}

/* ═══════════════════════════════════════════════════════════════
   Case intelligence dashboard & coverage audit
   ═══════════════════════════════════════════════════════════════ */

export interface CaseDashboardData {
    case: {
        id: string;
        name: string;
        status: string;
        created_at: string;
        referral_ref: string;
    };
    documents: {
        total: number;
        by_type: Record<string, number>;
        by_extraction_status: Record<string, number>;
        renamed_count: number;
    };
    entities: {
        persons: number;
        organizations: number;
        properties: number;
        financial_instruments: number;
        total: number;
    };
    signals: {
        total: number;
        by_severity: Record<string, number>;
        by_status: Record<string, number>;
        top_rules: Array<{ rule_id: string; summary: string; count: number }>;
    };
    detections: {
        total: number;
        confirmed: number;
        pending: number;
    };
    findings: {
        total: number;
        by_severity: Record<string, number>;
        by_status: Record<string, number>;
    };
    financials: {
        years_covered: number;
        total_revenue: string;
        total_expenses: string;
        timeline: Array<{ year: number; revenue: string; expenses: string }>;
    };
    pipeline: {
        extraction_success_rate: number;
        ai_enhanced_count: number;
        total_documents_processed: number;
    };
}

export async function fetchCaseDashboard(
    caseId: string,
    options?: ApiRequestOptions
): Promise<CaseDashboardData> {
    return request<CaseDashboardData>(`/api/cases/${caseId}/dashboard/`, {}, options);
}

export interface CoverageGapItem {
    rule_id: string;
    rule_title: string;
    gap_type: string;
    message: string;
    recommendation: string;
}

export interface CaseCoverageData {
    gaps: CoverageGapItem[];
    coverage_score: number;
    total_rules: number;
    active_rules: number;
    blind_rules: number;
}

export async function fetchCaseCoverage(
    caseId: string,
    options?: ApiRequestOptions
): Promise<CaseCoverageData> {
    return request<CaseCoverageData>(`/api/cases/${caseId}/coverage/`, {}, options);
}

/* ── Case entity-relationship graph ────────────────────────── */

export async function fetchCaseGraph(
    caseId: string,
    options?: ApiRequestOptions
): Promise<CaseGraphResponse> {
    return request<CaseGraphResponse>(`/api/cases/${caseId}/graph/`, {}, options);
}

/* ── AI endpoints (Phase 5) ──────────────────────────────── */

export async function aiSummarize(
    caseId: string,
    targetType: string,
    targetId: string,
    options?: ApiRequestOptions
): Promise<AISummarizeResponse> {
    return request<AISummarizeResponse>(`/api/cases/${caseId}/ai/summarize/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: targetType, target_id: targetId }),
    }, options);
}

export async function aiConnections(
    caseId: string,
    entityId?: string,
    options?: ApiRequestOptions
): Promise<AIConnectionsResponse> {
    return request<AIConnectionsResponse>(`/api/cases/${caseId}/ai/connections/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_id: entityId ?? null }),
    }, options);
}

export async function aiNarrative(
    caseId: string,
    detectionIds: string[],
    tone: "formal" | "executive" | "technical" = "formal",
    options?: ApiRequestOptions
): Promise<AINarrativeResponse> {
    return request<AINarrativeResponse>(`/api/cases/${caseId}/ai/narrative/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ detection_ids: detectionIds, tone }),
    }, options);
}

export async function aiAsk(
    caseId: string,
    question: string,
    conversationHistory: AIAskMessage[] = [],
    options?: ApiRequestOptions
): Promise<AIAskResponse> {
    return request<AIAskResponse>(`/api/cases/${caseId}/ai/ask/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, conversation_history: conversationHistory }),
    }, options);
}