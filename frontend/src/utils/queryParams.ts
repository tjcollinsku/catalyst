export interface DashboardQueryState {
    selectedCaseId: string | null;
    caseQuery: string;
    statusFilter: string;
    caseSort: string;
    docTypeFilter: string;
    ocrFilter: string;
    signalSeverityFilter: string;
    signalStatusFilter: string;
}

export function readQueryParam(key: string, fallback: string): string {
    const params = new URLSearchParams(window.location.search);
    return params.get(key) ?? fallback;
}

export function readOptionalQueryParam(key: string): string | null {
    const params = new URLSearchParams(window.location.search);
    return params.get(key);
}

export function syncDashboardQueryParams({
    selectedCaseId,
    caseQuery,
    statusFilter,
    caseSort,
    docTypeFilter,
    ocrFilter,
    signalSeverityFilter,
    signalStatusFilter
}: DashboardQueryState): void {
    const params = new URLSearchParams(window.location.search);

    if (selectedCaseId) params.set("case", selectedCaseId);
    else params.delete("case");

    if (caseQuery) params.set("caseQuery", caseQuery);
    else params.delete("caseQuery");

    if (statusFilter !== "all") params.set("caseStatus", statusFilter);
    else params.delete("caseStatus");

    if (caseSort !== "updated_desc") params.set("caseSort", caseSort);
    else params.delete("caseSort");

    if (docTypeFilter !== "all") params.set("docType", docTypeFilter);
    else params.delete("docType");

    if (ocrFilter !== "all") params.set("ocr", ocrFilter);
    else params.delete("ocr");

    if (signalSeverityFilter !== "all") params.set("signalSeverity", signalSeverityFilter);
    else params.delete("signalSeverity");

    if (signalStatusFilter !== "all") params.set("signalStatus", signalStatusFilter);
    else params.delete("signalStatus");

    const query = params.toString();
    const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.history.replaceState(null, "", nextUrl);
}
