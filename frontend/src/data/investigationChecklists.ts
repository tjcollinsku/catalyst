/**
 * Investigation checklist templates per signal type.
 * Framed as "Investigators typically..." — not prescriptive recommendations.
 * Checklist state per case is stored in localStorage.
 */

export interface ChecklistTemplate {
    id: string;
    label: string;
}

export const SIGNAL_CHECKLISTS: Record<string, ChecklistTemplate[]> = {
    "SR-001": [
        { id: "sr001-1", label: "Search Ohio death records / SSA Death Master File" },
        { id: "sr001-2", label: "Request certified death certificate" },
        { id: "sr001-3", label: "Verify signature date vs. date of death" },
        { id: "sr001-4", label: "Identify notary who witnessed signature" },
        { id: "sr001-5", label: "Check if power of attorney was in effect" },
    ],
    "SR-002": [
        { id: "sr002-1", label: "Verify notary commission status on filing date" },
        { id: "sr002-2", label: "Compare notary signature across documents" },
        { id: "sr002-3", label: "Pull notary journal entries for the date" },
        { id: "sr002-4", label: "Check for complaints filed with Ohio Secretary of State" },
    ],
    "SR-003": [
        { id: "sr003-1", label: "Obtain independent appraisal / fair market value" },
        { id: "sr003-2", label: "Review IRS Form 8283 (Noncash Charitable Contributions)" },
        { id: "sr003-3", label: "Compare assessed value to claimed deduction" },
        { id: "sr003-4", label: "Check county auditor records for parcel history" },
        { id: "sr003-5", label: "Review conservation easement deed restrictions" },
    ],
    "SR-004": [
        { id: "sr004-1", label: "Search IRS Tax Exempt Organization Search (TEOS)" },
        { id: "sr004-2", label: "Check Ohio Secretary of State business filings" },
        { id: "sr004-3", label: "Review Form 990 filing history on ProPublica Nonprofit Explorer" },
        { id: "sr004-4", label: "Verify if EIN was revoked or never issued" },
    ],
    "SR-005": [
        { id: "sr005-1", label: "Pull board meeting minutes for vote on transaction" },
        { id: "sr005-2", label: "Check Form 990 Part VI / Schedule L for disclosure" },
        { id: "sr005-3", label: "Search county recorder for related party transfers" },
        { id: "sr005-4", label: "Compare transaction value to fair market value" },
        { id: "sr005-5", label: "Identify all board members at time of transaction" },
    ],
    "SR-006": [
        { id: "sr006-1", label: "Pull UCC filings from Ohio SOS for all parties" },
        { id: "sr006-2", label: "Trace chain of secured interests / assignments" },
        { id: "sr006-3", label: "Check for circular references in filing chain" },
        { id: "sr006-4", label: "Verify collateral descriptions for consistency" },
    ],
    "SR-007": [
        { id: "sr007-1", label: "Verify dollar threshold for competitive bidding" },
        { id: "sr007-2", label: "Request procurement records and bid documentation" },
        { id: "sr007-3", label: "Check for sole-source justification documentation" },
        { id: "sr007-4", label: "Review vendor relationships to public officials" },
    ],
    "SR-008": [
        { id: "sr008-1", label: "Compare revenue across 3+ years of Form 990" },
        { id: "sr008-2", label: "Identify specific line items with anomalous changes" },
        { id: "sr008-3", label: "Check for corresponding program service changes" },
        { id: "sr008-4", label: "Verify revenue recognition methods" },
    ],
    "SR-009": [
        { id: "sr009-1", label: "Chart revenue and expense trends over 5+ years" },
        { id: "sr009-2", label: "Identify seasonal or cyclical patterns" },
        { id: "sr009-3", label: "Compare to peer organizations in same NTEE code" },
        { id: "sr009-4", label: "Check for unreported related entity transactions" },
    ],
    "SR-010": [
        { id: "sr010-1", label: "Verify officer names against Secretary of State records" },
        { id: "sr010-2", label: "Cross-reference officers across related entities" },
        { id: "sr010-3", label: "Check for officers who appear deceased" },
        { id: "sr010-4", label: "Review Form 990 Part VII for compensation reporting" },
    ],
};

/* ── localStorage helpers for checklist state ──────────────── */

const STORAGE_KEY = "catalyst_checklist_state";

interface ChecklistState {
    [caseId_ruleId_itemId: string]: boolean;
}

function loadChecklistState(): ChecklistState {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) : {};
    } catch {
        return {};
    }
}

function saveChecklistState(state: ChecklistState): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
        // localStorage full or unavailable — fail silently
    }
}

export function getChecklistItemChecked(caseId: string, ruleId: string, itemId: string): boolean {
    const state = loadChecklistState();
    return !!state[`${caseId}:${ruleId}:${itemId}`];
}

export function setChecklistItemChecked(
    caseId: string,
    ruleId: string,
    itemId: string,
    checked: boolean,
): void {
    const state = loadChecklistState();
    const key = `${caseId}:${ruleId}:${itemId}`;
    if (checked) {
        state[key] = true;
    } else {
        delete state[key];
    }
    saveChecklistState(state);
}
