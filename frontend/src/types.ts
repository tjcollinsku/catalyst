export interface CaseSummary {
    id: string;
    name: string;
    status: string;
    notes: string;
    referral_ref: string;
    created_at: string;
    updated_at: string;
}

export interface DocumentItem {
    id: string;
    filename: string;
    file_path: string;
    sha256_hash: string;
    file_size: number;
    doc_type: string;
    is_generated: boolean;
    doc_subtype: string;
    source_url: string | null;
    ocr_status: string;
    uploaded_at: string;
    updated_at: string;
}

export interface SignalItem {
    id: string;
    rule_id: string;
    title: string;
    description: string;
    detected_summary: string;
    trigger_entity_id: string | null;
    trigger_doc_id: string | null;
    investigator_note: string;
    severity: string;
    status: string;
    detected_at: string;
}

export interface CaseDetail extends CaseSummary {
    documents: DocumentItem[];
}

export interface PaginatedResponse<T> {
    count: number;
    limit: number;
    offset: number;
    next_offset: number | null;
    previous_offset: number | null;
    results: T[];
}

export interface NewCasePayload {
    name: string;
    status?: string;
    notes?: string;
    referral_ref?: string;
}

export interface SignalUpdatePayload {
    status?: string;
    investigator_note?: string;
}

export type ReferralStatus = "DRAFT" | "SUBMITTED" | "ACKNOWLEDGED" | "CLOSED";

export interface ReferralItem {
    referral_id: number;
    case_id: string | null;
    agency_name: string;
    submission_id: string;
    contact_alias: string;
    status: ReferralStatus;
    notes: string;
    filing_date: string;
}

export interface NewReferralPayload {
    agency_name: string;
    submission_id?: string;
    contact_alias?: string;
    notes?: string;
}

export interface ReferralUpdatePayload {
    agency_name?: string;
    submission_id?: string;
    contact_alias?: string;
    notes?: string;
    status?: ReferralStatus;
}

export type DetectionStatus = "OPEN" | "REVIEWED" | "CONFIRMED" | "DISMISSED" | "ESCALATED";
export type DetectionSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL";

export interface DetectionItem {
    id: string;
    case_id: string;
    signal_type: string;
    severity: DetectionSeverity;
    status: DetectionStatus;
    detection_method: string;
    primary_document_id: string | null;
    secondary_document_id: string | null;
    person_id: string | null;
    organization_id: string | null;
    property_record_id: string | null;
    financial_instrument_id: string | null;
    evidence_snapshot: Record<string, unknown>;
    confidence_score: number;
    investigator_note: string;
    detected_at: string;
    reviewed_at: string | null;
    reviewed_by: string;
}

export interface DetectionUpdatePayload {
    status?: DetectionStatus;
    investigator_note?: string;
    reviewed_by?: string;
    confidence_score?: number;
}
