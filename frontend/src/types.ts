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
    display_name: string;
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

/* ── Cross-case signal (includes case_name from backend) ─────── */
export interface CrossCaseSignal extends SignalItem {
    case_name: string;
    case_id?: string;
}

/* ── Cross-case referral (includes case_name) ────────────────── */
export interface CrossCaseReferral extends ReferralItem {
    case_name: string;
}

/* ── Entities ────────────────────────────────────────────────── */
export type EntityType = "person" | "organization" | "property" | "financial_instrument";

export interface EntityItem {
    id: string;
    entity_type: EntityType;
    name: string;
    case_id: string;
    case_name: string;
    notes: string;
    created_at: string;
    updated_at: string;
    /* Person-specific */
    role_tags?: string[];
    aliases?: string[];
    date_of_death?: string | null;
    /* Organization-specific */
    org_type?: string;
    ein?: string | null;
    registration_state?: string | null;
    status?: string;
    formation_date?: string | null;
    /* Property-specific */
    parcel_number?: string | null;
    address?: string | null;
    county?: string | null;
    assessed_value?: string | null;
    purchase_price?: string | null;
    /* Financial instrument-specific */
    instrument_type?: string;
    filing_number?: string | null;
    filing_date?: string | null;
    amount?: string | null;
    anomaly_flags?: string[];
}

/* ── Activity feed ───────────────────────────────────────────── */
export interface ActivityEntry {
    id: string;
    case_id: string | null;
    table_name: string;
    record_id: string | null;
    action: string;
    performed_by: string;
    performed_at: string;
    notes: string;
}

/* ── Search ─────────────────────────────────────────────────── */
export type SearchResultType = "document" | "signal" | "entity" | "case" | "detection";

export interface SearchResult {
    type: SearchResultType;
    id: string;
    title: string;
    subtitle: string;
    snippet: string;
    relevance: number;
    case_id: string | null;
    case_name: string | null;
    route: string;
}

export interface SearchResponse {
    query: string;
    total: number;
    ai_overview: string;
    results: SearchResult[];
}

/* ── Financial snapshots ───────────────────────────────────── */
export interface FinancialSnapshotItem {
    id: string;
    document_id: string;
    document_filename: string | null;
    organization_id: string | null;
    organization_name: string | null;
    ein: string;
    tax_year: number;
    form_type: string;
    total_contributions: number | null;
    program_service_revenue: number | null;
    investment_income: number | null;
    other_revenue: number | null;
    total_revenue: number | null;
    grants_paid: number | null;
    salaries_and_compensation: number | null;
    professional_fundraising: number | null;
    other_expenses: number | null;
    total_expenses: number | null;
    revenue_less_expenses: number | null;
    total_assets_boy: number | null;
    total_assets_eoy: number | null;
    total_liabilities_boy: number | null;
    total_liabilities_eoy: number | null;
    net_assets_boy: number | null;
    net_assets_eoy: number | null;
    officer_compensation_total: number | null;
    num_employees: number | null;
    source: string;
    confidence: number;
}

/* ── Document detail (with linked entities + financials) ──── */
export interface DocumentPersonLink {
    id: string;
    full_name: string;
    role_tags: string[];
    address: string;
    phone: string;
    context_note: string;
}

export interface DocumentOrgLink {
    id: string;
    name: string;
    org_type: string;
    ein: string;
    address: string;
    phone: string;
    context_note: string;
}

export interface DocumentDetail extends DocumentItem {
    extraction_status: string;
    extraction_notes: string;
    extracted_text: string;
    persons: DocumentPersonLink[];
    organizations: DocumentOrgLink[];
    financial_snapshots: FinancialSnapshotItem[];
}

/* ── Findings ────────────────────────────────────────────── */
export type FindingSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL";
export type FindingConfidence = "CONFIRMED" | "PROBABLE" | "POSSIBLE";
export type FindingStatus = "DRAFT" | "REVIEWED" | "INCLUDED_IN_MEMO" | "EXCLUDED" | "REFERRED";

export interface FindingEntityLink {
    id: string;
    entity_id: string;
    entity_type: string;
    context_note: string;
}

export interface FindingDocumentLink {
    id: string;
    document_id: string;
    page_reference: string;
    context_note: string;
}

export interface FindingItem {
    id: string;
    case_id: string;
    detection_id: string | null;
    title: string;
    narrative: string;
    severity: FindingSeverity;
    confidence: FindingConfidence;
    status: FindingStatus;
    signal_type: string;
    signal_rule_id: string;
    legal_refs: string[];
    created_at: string;
    updated_at: string;
    entity_links: FindingEntityLink[];
    document_links: FindingDocumentLink[];
}

export interface FindingUpdatePayload {
    title?: string;
    narrative?: string;
    severity?: FindingSeverity;
    confidence?: FindingConfidence;
    status?: FindingStatus;
    legal_refs?: string[];
}

export interface NewFindingPayload {
    title: string;
    narrative: string;
    severity: FindingSeverity;
    confidence: FindingConfidence;
    signal_type?: string;
    signal_rule_id?: string;
    detection_id?: string;
    legal_refs?: string[];
}

/* ── External search launchers ───────────────────────────── */
export interface ExternalSearchLauncher {
    id: string;
    name: string;
    urlTemplate: string;
}

/* ── Legal citations ─────────────────────────────────────── */
export interface LegalCitation {
    code: string;
    title: string;
    url: string;
}

/* ── Entity-relationship graph ──────────────────────────── */
export type GraphNodeType = "person" | "organization" | "property" | "financial_instrument";

export interface GraphNodeMetadata {
    /* Shared */
    signal_count: number;
    detection_count: number;
    doc_count: number;
    /* Person */
    role_tags?: string[];
    aliases?: string[];
    date_of_death?: string | null;
    /* Organization */
    org_type?: string;
    ein?: string | null;
    status?: string;
    /* Property */
    parcel_number?: string | null;
    county?: string | null;
    assessed_value?: string | null;
    purchase_price?: string | null;
    /* Financial Instrument */
    instrument_type?: string;
    filing_number?: string | null;
    filing_date?: string | null;
    amount?: string | null;
}

export interface GraphNode {
    id: string;
    type: GraphNodeType;
    label: string;
    metadata: GraphNodeMetadata;
}

export type GraphRelationship =
    | "OFFICER_OF"
    | "CO_APPEARS_IN"
    | "PURCHASED"
    | "SOLD_BY"
    | "SOCIAL_CONNECTION"
    | "FAMILY"
    | "SPOUSE"
    | "PARENT_CHILD"
    | "SIBLING"
    | "BUSINESS_PARTNER"
    | "CO_OFFICER"
    | string;  // allow for future relationship types

export interface GraphEdgeMetadata {
    /* OFFICER_OF */
    start_date?: string | null;
    end_date?: string | null;
    /* CO_APPEARS_IN */
    document_ids?: string[];
    /* PURCHASED / SOLD_BY */
    transaction_date?: string | null;
    price?: string | null;
    instrument_number?: string;
    /* Relationship */
    source_type?: string;
    confidence?: number;
    notes?: string;
    /* SOCIAL_CONNECTION */
    platform?: string;
    connection_type?: string;
}

export interface GraphEdge {
    source: string;
    target: string;
    relationship: GraphRelationship;
    label: string;
    weight: number;
    metadata: GraphEdgeMetadata;
}

export interface GraphStats {
    total_nodes: number;
    total_edges: number;
    total_events: number;
    node_types: Record<GraphNodeType, number>;
}

/* ── Timeline events ────────────────────────────────────── */
export type TimelineLayer = "document" | "signal" | "financial" | "transaction";

export interface TimelineEvent {
    id: string;
    layer: TimelineLayer;
    date: string;  // ISO 8601
    label: string;
    metadata: {
        /* document */
        doc_type?: string;
        /* signal */
        severity?: string;
        rule_id?: string;
        entity_id?: string | null;
        /* financial */
        tax_year?: number;
        total_revenue?: string | null;
        total_expenses?: string | null;
        /* transaction */
        price?: string | null;
        property_id?: string;
        buyer_id?: string | null;
        seller_id?: string | null;
    };
}

export interface CaseGraphResponse {
    nodes: GraphNode[];
    edges: GraphEdge[];
    timeline_events: TimelineEvent[];
    stats: GraphStats;
}

/* ── AI response types (Phase 5) ──────────────────────────── */

export interface AISummarizeResponse {
    summary: string;
    key_facts: string[];
    risk_indicators: string[];
    confidence: number; // 0–1
}

export interface AIConnectionSuggestion {
    source_id: string;
    source_label: string;
    target_id: string;
    target_label: string;
    relationship: string;
    evidence: string;
    confidence: number;
}

export interface AIConnectionsResponse {
    suggestions: AIConnectionSuggestion[];
    reasoning: string;
}

export interface AINarrativeResponse {
    title: string;
    narrative: string;
    legal_references: string[];
    recommended_actions: string[];
}

export interface AIAskMessage {
    role: "user" | "assistant";
    content: string;
}

export interface AIAskResponse {
    answer: string;
    sources: Array<{
        type: string;
        id: string;
        label: string;
    }>;
    follow_up_questions: string[];
}

/* ── Research tab results (external data sources) ───────────── */
export interface ResearchResult {
    source: string;
    results: Record<string, unknown>[];
    count: number;
    notes: string[];
    error?: string;
    staleness_warning?: { level: string; message: string };
}
