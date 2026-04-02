import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { CasesPanel } from "./CasesPanel";

const emptySeverityMap = {};

const cases = [
    {
        id: "case-1",
        name: "Alpha Case",
        status: "ACTIVE",
        notes: "",
        referral_ref: "REF-100",
        created_at: "2026-03-29T00:00:00Z",
        updated_at: "2026-03-29T00:00:00Z"
    }
];

describe("CasesPanel", () => {
    test("renders loading state", () => {
        render(
            <CasesPanel
                filteredCases={[]}
                selectedCaseId={null}
                caseSeverityMap={emptySeverityMap}
                loadingCases
                caseQuery=""
                statusFilter="all"
                caseSort="updated_desc"
                availableStatuses={["ACTIVE"]}
                newCaseName=""
                newCaseReferral=""
                newCaseNotes=""
                isSubmittingCase={false}
                formErrors={{}}
                onCreateCase={vi.fn()}
                onSelectCase={vi.fn()}
                onCaseQueryChange={vi.fn()}
                onStatusFilterChange={vi.fn()}
                onCaseSortChange={vi.fn()}
                onNewCaseNameChange={vi.fn()}
                onNewCaseReferralChange={vi.fn()}
                onNewCaseNotesChange={vi.fn()}
                formatDate={() => "Mar 29, 2026"}
            />
        );

        expect(screen.getByText("Loading cases...")).toBeInTheDocument();
    });

    test("calls handlers for filtering, selecting, and creating", () => {
        const onCreateCase = vi.fn((event: React.FormEvent<HTMLFormElement>) => event.preventDefault());
        const onSelectCase = vi.fn();
        const onCaseQueryChange = vi.fn();
        const onStatusFilterChange = vi.fn();
        const onCaseSortChange = vi.fn();

        render(
            <CasesPanel
                filteredCases={cases}
                selectedCaseId={null}
                caseSeverityMap={emptySeverityMap}
                loadingCases={false}
                caseQuery=""
                statusFilter="all"
                caseSort="updated_desc"
                availableStatuses={["ACTIVE", "PAUSED"]}
                newCaseName=""
                newCaseReferral=""
                newCaseNotes=""
                isSubmittingCase={false}
                formErrors={{}}
                onCreateCase={onCreateCase}
                onSelectCase={onSelectCase}
                onCaseQueryChange={onCaseQueryChange}
                onStatusFilterChange={onStatusFilterChange}
                onCaseSortChange={onCaseSortChange}
                onNewCaseNameChange={vi.fn()}
                onNewCaseReferralChange={vi.fn()}
                onNewCaseNotesChange={vi.fn()}
                formatDate={() => "Mar 29, 2026"}
            />
        );

        fireEvent.change(screen.getByLabelText("Search cases"), { target: { value: "alpha" } });
        fireEvent.change(screen.getByLabelText("Filter by case status"), { target: { value: "ACTIVE" } });
        fireEvent.change(screen.getByLabelText("Sort cases"), { target: { value: "name_asc" } });
        fireEvent.click(screen.getByRole("button", { name: /alpha case/i }));
        fireEvent.submit(screen.getByRole("button", { name: /create case/i }).closest("form") as HTMLFormElement);

        expect(onCaseQueryChange).toHaveBeenCalledWith("alpha");
        expect(onStatusFilterChange).toHaveBeenCalledWith("ACTIVE");
        expect(onCaseSortChange).toHaveBeenCalledWith("name_asc");
        expect(onSelectCase).toHaveBeenCalledWith("case-1");
        expect(onCreateCase).toHaveBeenCalledTimes(1);
    });

    test("renders inline validation messages", () => {
        render(
            <CasesPanel
                filteredCases={cases}
                selectedCaseId={null}
                caseSeverityMap={emptySeverityMap}
                loadingCases={false}
                caseQuery=""
                statusFilter="all"
                caseSort="updated_desc"
                availableStatuses={["ACTIVE"]}
                newCaseName=""
                newCaseReferral=""
                newCaseNotes=""
                isSubmittingCase={false}
                formErrors={{ name: "Case name is required.", referral: "Referral too short." }}
                onCreateCase={vi.fn()}
                onSelectCase={vi.fn()}
                onCaseQueryChange={vi.fn()}
                onStatusFilterChange={vi.fn()}
                onCaseSortChange={vi.fn()}
                onNewCaseNameChange={vi.fn()}
                onNewCaseReferralChange={vi.fn()}
                onNewCaseNotesChange={vi.fn()}
                formatDate={() => "Mar 29, 2026"}
            />
        );

        expect(screen.getByText("Case name is required.")).toBeInTheDocument();
        expect(screen.getByText("Referral too short.")).toBeInTheDocument();
    });
});
