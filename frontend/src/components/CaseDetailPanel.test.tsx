import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { CaseDetailPanel } from "./CaseDetailPanel";

const selectedCase = {
    id: "case-1",
    name: "Alpha Case",
    status: "OPEN",
    notes: "Review ownership chain.",
    referral_ref: "REF-100",
    created_at: "2026-03-29T00:00:00Z",
    updated_at: "2026-03-29T00:00:00Z",
    documents: [
        {
            id: "doc-1",
            filename: "deed.pdf",
            display_name: "",
            file_path: "cases/deed.pdf",
            sha256_hash: "abc",
            file_size: 2048,
            doc_type: "DEED",
            is_generated: false,
            doc_subtype: "",
            source_url: null,
            ocr_status: "PENDING",
            uploaded_at: "2026-03-29T00:00:00Z",
            updated_at: "2026-03-29T00:00:00Z"
        }
    ]
};

const signals = [
    {
        id: "sig-1",
        rule_id: "RULE-1",
        title: "Potential conflict",
        description: "Entity overlap detected.",
        detected_summary: "summary",
        trigger_entity_id: null,
        trigger_doc_id: null,
        investigator_note: "",
        severity: "HIGH",
        status: "OPEN",
        detected_at: "2026-03-29T00:00:00Z"
    }
];

const referralProps = {
    referrals: [],
    loadingReferrals: false,
    savingReferralId: null,
    detections: [],
    loadingDetections: false,
    savingDetectionId: null,
    deletingDocumentId: null,
    generatingMemo: false,
    processingPendingOcr: false,
    onCreateReferral: vi.fn(),
    onUpdateReferral: vi.fn(),
    onDeleteReferral: vi.fn(),
    onUpdateDetection: vi.fn(),
    onDeleteDetection: vi.fn(),
    onDeleteDocument: vi.fn(),
    onGenerateMemo: vi.fn(),
    onProcessPendingOcr: vi.fn(),
    onReevaluateSignals: vi.fn(),
    reevaluatingSignals: false,
    onBulkUpload: vi.fn().mockResolvedValue({ created: [], errors: [] }),
    onBulkUploadComplete: vi.fn(),
};

describe("CaseDetailPanel", () => {
    test("renders loading and unselected states", () => {
        const { rerender } = render(
            <CaseDetailPanel
                {...referralProps}
                activeCaseName="No case selected"
                selectedCase={null}
                loadingCaseDetail
                filteredDocuments={[]}
                documentTypes={[]}
                ocrStatuses={[]}
                docTypeFilter="all"
                ocrFilter="all"
                filteredSignals={[]}
                signals={[]}
                signalSeverities={[]}
                signalStatuses={[]}
                signalSeverityFilter="all"
                signalStatusFilter="all"
                triageError={null}
                savingSignalId={null}
                activeSignalId={null}
                onDocTypeFilterChange={vi.fn()}
                onOcrFilterChange={vi.fn()}
                onSignalSeverityFilterChange={vi.fn()}
                onSignalStatusFilterChange={vi.fn()}
                getSignalDraft={() => ({ status: "OPEN", note: "" })}
                onSignalDraftChange={vi.fn()}
                onActiveSignalChange={vi.fn()}
                onSignalSave={vi.fn()}
                formatDate={() => "Mar 29, 2026"}
                formatSize={() => "2.0 KB"}
            />
        );

        expect(screen.getByText("Loading case details...")).toBeInTheDocument();

        rerender(
            <CaseDetailPanel
                {...referralProps}
                activeCaseName="No case selected"
                selectedCase={null}
                loadingCaseDetail={false}
                filteredDocuments={[]}
                documentTypes={[]}
                ocrStatuses={[]}
                docTypeFilter="all"
                ocrFilter="all"
                filteredSignals={[]}
                signals={[]}
                signalSeverities={[]}
                signalStatuses={[]}
                signalSeverityFilter="all"
                signalStatusFilter="all"
                triageError={null}
                savingSignalId={null}
                activeSignalId={null}
                onDocTypeFilterChange={vi.fn()}
                onOcrFilterChange={vi.fn()}
                onSignalSeverityFilterChange={vi.fn()}
                onSignalStatusFilterChange={vi.fn()}
                getSignalDraft={() => ({ status: "OPEN", note: "" })}
                onSignalDraftChange={vi.fn()}
                onActiveSignalChange={vi.fn()}
                onSignalSave={vi.fn()}
                formatDate={() => "Mar 29, 2026"}
                formatSize={() => "2.0 KB"}
            />
        );

        expect(screen.getByText("Choose a case to load investigation details.")).toBeInTheDocument();
    });

    test("renders case detail and triage handlers fire", () => {
        const onSignalDraftChange = vi.fn();
        const onSignalSave = vi.fn();
        const onDocTypeFilterChange = vi.fn();
        const onActiveSignalChange = vi.fn();
        const onProcessPendingOcr = vi.fn();
        const onDeleteDocument = vi.fn();

        render(
            <CaseDetailPanel
                {...referralProps}
                activeCaseName="Alpha Case"
                selectedCase={selectedCase}
                loadingCaseDetail={false}
                filteredDocuments={selectedCase.documents}
                documentTypes={["DEED"]}
                ocrStatuses={["COMPLETE"]}
                docTypeFilter="all"
                ocrFilter="all"
                filteredSignals={signals}
                signals={signals}
                signalSeverities={["HIGH"]}
                signalStatuses={["OPEN", "DISMISSED"]}
                signalSeverityFilter="all"
                signalStatusFilter="all"
                triageError={null}
                savingSignalId={null}
                activeSignalId="sig-1"
                onDocTypeFilterChange={onDocTypeFilterChange}
                onOcrFilterChange={vi.fn()}
                onSignalSeverityFilterChange={vi.fn()}
                onSignalStatusFilterChange={vi.fn()}
                getSignalDraft={() => ({ status: "OPEN", note: "" })}
                onSignalDraftChange={onSignalDraftChange}
                onActiveSignalChange={onActiveSignalChange}
                onSignalSave={onSignalSave}
                onProcessPendingOcr={onProcessPendingOcr}
                onDeleteDocument={onDeleteDocument}
                formatDate={() => "Mar 29, 2026"}
                formatSize={() => "2.0 KB"}
            />
        );

        expect(screen.getByText("Review ownership chain.")).toBeInTheDocument();
        expect(screen.getByText("Potential conflict")).toBeInTheDocument();
        expect(screen.getByText("deed.pdf")).toBeInTheDocument();

        fireEvent.change(screen.getByLabelText("Filter documents by type"), { target: { value: "DEED" } });
        fireEvent.click(screen.getByRole("button", { name: /process pending ocr/i }));
        fireEvent.click(screen.getByRole("button", { name: "Delete file deed.pdf" }));
        fireEvent.click(screen.getByLabelText("Focus signal Potential conflict"));
        fireEvent.click(screen.getByRole("button", { name: "Set signal status to REVIEWED" }));
        fireEvent.change(screen.getAllByDisplayValue("OPEN")[0], { target: { value: "DISMISSED" } });
        fireEvent.change(screen.getByPlaceholderText("Investigator note"), { target: { value: "Needs review" } });
        fireEvent.click(screen.getByRole("button", { name: "Save" }));

        expect(onDocTypeFilterChange).toHaveBeenCalledWith("DEED");
        expect(onProcessPendingOcr).toHaveBeenCalledTimes(1);
        expect(onDeleteDocument).toHaveBeenCalledWith("doc-1");
        expect(onActiveSignalChange).toHaveBeenCalledWith("sig-1");
        expect(onSignalDraftChange).toHaveBeenCalledTimes(3);
        expect(onSignalDraftChange).toHaveBeenCalledWith("sig-1", { status: "REVIEWED", note: "" });
        expect(onSignalSave).toHaveBeenCalledWith(signals[0]);
    });

    test("shows empty states when filters remove all results", () => {
        render(
            <CaseDetailPanel
                {...referralProps}
                activeCaseName="Alpha Case"
                selectedCase={{ ...selectedCase, documents: [] }}
                loadingCaseDetail={false}
                filteredDocuments={[]}
                documentTypes={[]}
                ocrStatuses={[]}
                docTypeFilter="all"
                ocrFilter="all"
                filteredSignals={[]}
                signals={[]}
                signalSeverities={[]}
                signalStatuses={[]}
                signalSeverityFilter="all"
                signalStatusFilter="all"
                triageError="A note is required when dismissing a signal."
                savingSignalId={null}
                activeSignalId={null}
                onDocTypeFilterChange={vi.fn()}
                onOcrFilterChange={vi.fn()}
                onSignalSeverityFilterChange={vi.fn()}
                onSignalStatusFilterChange={vi.fn()}
                getSignalDraft={() => ({ status: "OPEN", note: "" })}
                onSignalDraftChange={vi.fn()}
                onActiveSignalChange={vi.fn()}
                onSignalSave={vi.fn()}
                formatDate={() => "Mar 29, 2026"}
                formatSize={() => "2.0 KB"}
            />
        );

        expect(screen.getByText("No documents have been attached to this case yet.")).toBeInTheDocument();
        expect(screen.getByText("No signals detected for this case yet.")).toBeInTheDocument();
        expect(screen.getByText("A note is required when dismissing a signal.")).toBeInTheDocument();
    });
});
