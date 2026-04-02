import { FormEvent } from "react";
import { CaseSummary } from "../types";
import { Button } from "./ui/Button";
import { FormInput } from "./ui/FormInput";
import { FormSelect } from "./ui/FormSelect";
import { FormTextarea } from "./ui/FormTextarea";
import { StateBlock } from "./ui/StateBlock";
import styles from "./CasesPanel.module.css";

interface CasesPanelProps {
    filteredCases: CaseSummary[];
    selectedCaseId: string | null;
    caseSeverityMap: Record<string, string>;
    loadingCases: boolean;
    caseQuery: string;
    statusFilter: string;
    caseSort: string;
    availableStatuses: string[];
    newCaseName: string;
    newCaseReferral: string;
    newCaseNotes: string;
    isSubmittingCase: boolean;
    formErrors: { name?: string; referral?: string };
    onCreateCase: (event: FormEvent<HTMLFormElement>) => void;
    onSelectCase: (caseId: string) => void;
    onCaseQueryChange: (value: string) => void;
    onStatusFilterChange: (value: string) => void;
    onCaseSortChange: (value: string) => void;
    onNewCaseNameChange: (value: string) => void;
    onNewCaseReferralChange: (value: string) => void;
    onNewCaseNotesChange: (value: string) => void;
    formatDate: (value: string) => string;
}

export function CasesPanel({
    filteredCases,
    selectedCaseId,
    caseSeverityMap,
    loadingCases,
    caseQuery,
    statusFilter,
    caseSort,
    availableStatuses,
    newCaseName,
    newCaseReferral,
    newCaseNotes,
    isSubmittingCase,
    formErrors,
    onCreateCase,
    onSelectCase,
    onCaseQueryChange,
    onStatusFilterChange,
    onCaseSortChange,
    onNewCaseNameChange,
    onNewCaseReferralChange,
    onNewCaseNotesChange,
    formatDate
}: CasesPanelProps) {
    return (
        <section className="panel panel-list">
            <div className="panel-heading">
                <h2>Cases</h2>
                <span>{filteredCases.length} shown</span>
            </div>
            <form className={styles.createCaseForm} onSubmit={onCreateCase}>
                <h3>New Case</h3>
                <FormInput
                    type="text"
                    value={newCaseName}
                    onChange={(event) => onNewCaseNameChange(event.target.value)}
                    placeholder="Case name"
                    aria-label="Case name"
                    aria-invalid={formErrors.name ? "true" : "false"}
                    required
                />
                {formErrors.name && <p className={styles.fieldError}>{formErrors.name}</p>}
                <div className={styles.inlineFields}>
                    <FormInput
                        type="text"
                        value={newCaseReferral}
                        onChange={(event) => onNewCaseReferralChange(event.target.value)}
                        placeholder="Referral reference"
                        aria-label="Referral reference"
                        aria-invalid={formErrors.referral ? "true" : "false"}
                    />
                </div>
                {formErrors.referral && <p className={styles.fieldError}>{formErrors.referral}</p>}
                <FormTextarea
                    value={newCaseNotes}
                    onChange={(event) => onNewCaseNotesChange(event.target.value)}
                    placeholder="Initial case notes"
                    aria-label="Initial case notes"
                    rows={3}
                />
                <Button type="submit" variant="primary" disabled={isSubmittingCase}>
                    {isSubmittingCase ? "Creating..." : "Create Case"}
                </Button>
            </form>
            <div className={styles.filterRow}>
                <FormInput
                    type="search"
                    value={caseQuery}
                    onChange={(event) => onCaseQueryChange(event.target.value)}
                    placeholder="Search name or referral"
                    aria-label="Search cases"
                />
                <FormSelect
                    value={statusFilter}
                    onChange={(event) => onStatusFilterChange(event.target.value)}
                    aria-label="Filter by case status"
                >
                    <option value="all">All statuses</option>
                    {availableStatuses.map((status) => (
                        <option key={status} value={status}>
                            {status}
                        </option>
                    ))}
                </FormSelect>
                <FormSelect
                    value={caseSort}
                    onChange={(event) => onCaseSortChange(event.target.value)}
                    aria-label="Sort cases"
                >
                    <option value="updated_desc">Newest updated</option>
                    <option value="updated_asc">Oldest updated</option>
                    <option value="name_asc">Name A-Z</option>
                    <option value="name_desc">Name Z-A</option>
                    <option value="status_asc">Status A-Z</option>
                </FormSelect>
            </div>
            {loadingCases ? (
                <StateBlock
                    title="Loading cases..."
                    detail="Fetching the latest investigation queue from the API."
                />
            ) : filteredCases.length === 0 ? (
                <StateBlock
                    title="No cases matched your filter."
                    detail="Try clearing the search or switching to a different status filter."
                />
            ) : (
                <ul className={styles.caseList}>
                    {filteredCases.map((caseItem) => {
                        const topSeverity = caseSeverityMap[caseItem.id];
                        return (
                            <li key={caseItem.id}>
                                <button
                                    type="button"
                                    className={caseItem.id === selectedCaseId ? `${styles.casePill} ${styles.active}` : styles.casePill}
                                    onClick={() => onSelectCase(caseItem.id)}
                                >
                                    <span className={styles.caseName}>{caseItem.name}</span>
                                    <span className={styles.casePillBadges}>
                                        <span className={styles.caseMeta}>{caseItem.status}</span>
                                        {topSeverity && (
                                            <span className={`tag ${topSeverity.toLowerCase()} ${styles.caseSeverityBadge}`}>
                                                {topSeverity}
                                            </span>
                                        )}
                                    </span>
                                    {caseItem.referral_ref && (
                                        <span className={styles.caseMeta}>Ref: {caseItem.referral_ref}</span>
                                    )}
                                    <span className={styles.caseMeta}>{formatDate(caseItem.created_at)}</span>
                                </button>
                            </li>
                        );
                    })}
                </ul>
            )}
        </section>
    );
}
