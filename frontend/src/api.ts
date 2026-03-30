import {
    CaseDetail,
    CaseSummary,
    DetectionItem,
    DetectionUpdatePayload,
    DocumentItem,
    NewCasePayload,
    NewReferralPayload,
    PaginatedResponse,
    ReferralItem,
    ReferralUpdatePayload,
    SignalItem,
    SignalUpdatePayload
} from "./types";

const API_BASE = "";
const DEFAULT_TIMEOUT_MS = 15000;
const BULK_UPLOAD_TIMEOUT_MS = 300000;

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
