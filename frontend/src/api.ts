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
    CrossCaseFinding,
    DocumentDetail,
    DocumentItem,
    EntityItem,
    FinancialSnapshotItem,
    FindingItem,
    FindingUpdatePayload,
    InvestigatorNote,
    NewCasePayload,
    NewFindingPayload,
    PaginatedResponse,
    SearchJobSummary,
    SearchResponse,
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

export async function fetchCaseFindings(
    caseId: string,
    options?: ApiRequestOptions
): Promise<PaginatedResponse<FindingItem>> {
    return request<PaginatedResponse<FindingItem>>(
        `/api/cases/${caseId}/findings/?limit=100&offset=0&order_by=created_at&direction=desc`,
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


export async function deleteDocument(
    caseId: string,
    documentId: string,
    options?: ApiRequestOptions
): Promise<void> {
    return request<void>(`/api/cases/${caseId}/documents/${documentId}/`, {
        method: "DELETE"
    }, options);
}

export interface FindingSummaryItem {
    case_id: string;
    highest_severity: string;
    open_count: number;
}

export async function fetchFindingSummary(options?: ApiRequestOptions): Promise<{ results: FindingSummaryItem[] }> {
    return request<{ results: FindingSummaryItem[] }>("/api/signal-summary/", {}, options);
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



export async function generateReferralPdf(
    caseId: string,
    options?: { include_confirmed_only?: boolean; min_evidence_weight?: string }
): Promise<Blob> {
    const resp = await fetch(`/api/cases/${caseId}/referral-pdf/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCSRFToken(),
        },
        credentials: "include",
        body: JSON.stringify(options ?? {}),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: "PDF generation failed" }));
        throw new Error(err.error || "PDF generation failed");
    }
    return resp.blob();
}

export interface ReevaluateFindingsResult {
    documents_evaluated: number;
    triggers_found: number;
    new_findings: FindingItem[];
}

export async function reevaluateFindings(
    caseId: string,
    options?: ApiRequestOptions
): Promise<ReevaluateFindingsResult> {
    return request<ReevaluateFindingsResult>(`/api/cases/${caseId}/reevaluate-findings/`, {
        method: "POST"
    }, options);
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
   Cross-case endpoints
   ═══════════════════════════════════════════════════════════════ */

export interface CrossCaseFindingFilters {
    status?: string;
    severity?: string;
    case_id?: string;
    rule_id?: string;
}

export async function fetchCrossCaseFindings(
    filters: CrossCaseFindingFilters = {},
    limit = 100,
    offset = 0,
    options?: ApiRequestOptions
): Promise<PaginatedResponse<CrossCaseFinding>> {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    params.set("order_by", "created_at");
    params.set("direction", "desc");
    if (filters.status) params.set("status", filters.status);
    if (filters.severity) params.set("severity", filters.severity);
    if (filters.case_id) params.set("case_id", filters.case_id);
    if (filters.rule_id) params.set("rule_id", filters.rule_id);
    return request<PaginatedResponse<CrossCaseFinding>>(`/api/findings/?${params}`, {}, options);
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

export async function fetchEntityDetail(
    entityType: string,
    entityId: string,
    options?: ApiRequestOptions
): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>(
        `/api/entities/${entityType}/${entityId}/`, {}, options,
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

/* ═══════════════════════════════════════════════════════════════
   Research endpoints (external data source connectors)
   ═══════════════════════════════════════════════════════════════ */

export interface ResearchResult {
    source: string;
    results: Record<string, unknown>[];
    count: number;
    notes: string[];
    error?: string;
    staleness_warning?: { level: string; message: string };
}

export async function searchParcels(
    caseId: string,
    query: string,
    searchType: "owner" | "parcel",
    county?: string,
    options?: ApiRequestOptions
): Promise<ResearchResult> {
    return request<ResearchResult>(`/api/cases/${caseId}/research/parcels/`, {
        method: "POST",
        body: JSON.stringify({ query, search_type: searchType, county }),
    }, {
        ...options,
        timeoutMs: options?.timeoutMs ?? 60000,
    });
}

export async function searchOhioSOS(
    caseId: string,
    query: string,
    fuzzy = false,
    options?: ApiRequestOptions
): Promise<ResearchResult> {
    return request<ResearchResult>(`/api/cases/${caseId}/research/ohio-sos/`, {
        method: "POST",
        body: JSON.stringify({ query, fuzzy }),
    }, {
        ...options,
        timeoutMs: options?.timeoutMs ?? 60000,
    });
}

export async function searchOhioAOS(
    caseId: string,
    query: string,
    options?: ApiRequestOptions
): Promise<ResearchResult> {
    return request<ResearchResult>(`/api/cases/${caseId}/research/ohio-aos/`, {
        method: "POST",
        body: JSON.stringify({ query }),
    }, {
        ...options,
        timeoutMs: options?.timeoutMs ?? 30000,
    });
}

export async function searchIRS(
    caseId: string,
    query: string,
    options?: ApiRequestOptions
): Promise<ResearchResult> {
    return request<ResearchResult>(`/api/cases/${caseId}/research/irs/`, {
        method: "POST",
        body: JSON.stringify({ query }),
    }, {
        ...options,
        timeoutMs: options?.timeoutMs ?? 120000,
    });
}

export interface Fetch990Result {
    fetched: number;
    skipped: number;
    errors: Array<{ filing: string; error: string }>;
    filings: Array<{
        tax_year: number;
        return_type: string;
        taxpayer_name: string;
        total_revenue: number | null;
        total_expenses: number | null;
        total_assets: number | null;
        officers_count: number;
        parse_quality: number;
        snapshot_id: string | null;
        status?: string;
        governance?: {
            conflict_of_interest_policy: boolean | null;
            whistleblower_policy: boolean | null;
            document_retention_policy: boolean | null;
            voting_members: number | null;
            independent_members: number | null;
        };
    }>;
}

export async function fetch990Data(
    caseId: string,
    ein: string,
    options?: ApiRequestOptions
): Promise<Fetch990Result> {
    return request<Fetch990Result>(
        `/api/cases/${caseId}/fetch-990s/`,
        {
            method: "POST",
            body: JSON.stringify({ ein }),
        },
        {
            ...options,
            timeoutMs: options?.timeoutMs ?? 180000,
        }
    );
}

export async function fetchJob(
    jobId: string,
    options?: ApiRequestOptions,
): Promise<SearchJobSummary> {
    return request<SearchJobSummary>(
        `/api/jobs/${jobId}/`,
        { method: "GET" },
        { ...options, timeoutMs: options?.timeoutMs ?? 10000 },
    );
}

export async function fetchCaseJobs(
    caseId: string,
    limit = 5,
    options?: ApiRequestOptions,
): Promise<SearchJobSummary[]> {
    return request<SearchJobSummary[]>(
        `/api/cases/${caseId}/jobs/?limit=${limit}`,
        { method: "GET" },
        { ...options, timeoutMs: options?.timeoutMs ?? 10000 },
    );
}

export async function searchRecorder(
    caseId: string,
    county: string,
    name: string,
    options?: ApiRequestOptions
): Promise<ResearchResult> {
    return request<ResearchResult>(`/api/cases/${caseId}/research/recorder/`, {
        method: "POST",
        body: JSON.stringify({ county, name }),
    }, {
        ...options,
        timeoutMs: options?.timeoutMs ?? 15000,
    });
}

export interface AddToCaseResult {
    created: string;
    entity: Record<string, unknown>;
    duplicate: boolean;
    message?: string;
}

export async function addResearchToCase(
    caseId: string,
    source: string,
    data: Record<string, unknown>,
    options?: ApiRequestOptions
): Promise<AddToCaseResult> {
    return request<AddToCaseResult>(`/api/cases/${caseId}/research/add-to-case/`, {
        method: "POST",
        body: JSON.stringify({ source, data }),
    }, options);
}

/* ═══════════════════════════════════════════════════════════════
   Investigator notes (sticky notes)
   ═══════════════════════════════════════════════════════════════ */

export interface FetchNotesResult {
    count: number;
    results: InvestigatorNote[];
}

export async function fetchNotes(
    caseId: string,
    targetType?: string,
    targetId?: string,
    options?: ApiRequestOptions
): Promise<FetchNotesResult> {
    const params = new URLSearchParams();
    if (targetType) params.set("target_type", targetType);
    if (targetId) params.set("target_id", targetId);
    const query = params.toString() ? `?${params}` : "";
    return request<FetchNotesResult>(
        `/api/cases/${caseId}/notes/${query}`,
        {},
        options
    );
}

export async function createNote(
    caseId: string,
    targetType: string,
    targetId: string,
    content: string,
    options?: ApiRequestOptions
): Promise<InvestigatorNote> {
    return request<InvestigatorNote>(`/api/cases/${caseId}/notes/`, {
        method: "POST",
        body: JSON.stringify({
            target_type: targetType,
            target_id: targetId,
            content,
        }),
    }, options);
}

export async function deleteNote(
    caseId: string,
    noteId: string,
    options?: ApiRequestOptions
): Promise<void> {
    return request<void>(`/api/cases/${caseId}/notes/${noteId}/`, {
        method: "DELETE",
    }, options);
}
