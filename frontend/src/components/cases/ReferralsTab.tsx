import { useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import { ReferralsPanel } from "../ReferralsPanel";
import { Button } from "../ui/Button";
import { exportCaseReport, generateReferralPdf } from "../../api";
import styles from "./ReferralsTab.module.css";

export function ReferralsTab() {
    const { caseId } = useParams<{ caseId: string }>();
    const { pushToast } = useOutletContext<CaseDetailContext>();

    const [exporting, setExporting] = useState<string | null>(null);
    const [generatingPdf, setGeneratingPdf] = useState(false);

    async function handleGenerateReferralPdf() {
        if (!caseId) return;
        setGeneratingPdf(true);
        try {
            const blob = await generateReferralPdf(caseId, {});
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `referral-package-${caseId}.pdf`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            pushToast("success", "Referral package PDF generated and downloaded");
        } catch (err) {
            pushToast(
                "error",
                `PDF generation failed: ${err instanceof Error ? err.message : "Unknown error"}`
            );
        } finally {
            setGeneratingPdf(false);
        }
    }

    async function handleExport(format: "json" | "csv") {
        if (!caseId) return;
        setExporting(format);
        try {
            const result = await exportCaseReport(caseId, format);
            // If the backend returns a download URL, open it
            if (result.download_url) {
                window.open(result.download_url, "_blank");
            }
            pushToast("success", `${format.toUpperCase()} export ready: ${result.filename}`);
        } catch (err) {
            pushToast("error", `Export failed: ${err instanceof Error ? err.message : "Unknown error"}`);
        } finally {
            setExporting(null);
        }
    }

    return (
        <>
            <ReferralsPanel
                caseId={caseId ?? ""}
                onGeneratePdf={handleGenerateReferralPdf}
                generatingPdf={generatingPdf}
            />

            {/* Generate referral package PDF */}
            <article className="info-card">
                <div className="card-toolbar">
                    <h3>{"📋"} Generate Referral Package (PDF)</h3>
                </div>
                <p className={styles.memoHint}>
                    Generate a deterministic, citation-bearing referral package PDF for
                    submission to government agencies. All findings and evidence traces are
                    included in the output.
                </p>
                <div className={styles.exportButtons}>
                    <Button
                        variant="primary"
                        disabled={generatingPdf}
                        onClick={handleGenerateReferralPdf}
                    >
                        {generatingPdf ? "Generating..." : "Generate Referral Package"}
                    </Button>
                </div>
            </article>

            {/* Report generation / export */}
            <article className="info-card">
                <div className="card-toolbar">
                    <h3>{"\uD83D\uDCE4"} Export Case Data</h3>
                </div>
                <p className={styles.memoHint}>
                    Export all case data including documents metadata, signals, detections, entities, and referrals.
                    Use the formal referral memo (Documents tab) for agency submissions, or export raw data here for analysis.
                </p>
                <div className={styles.exportButtons}>
                    <Button
                        variant="secondary"
                        disabled={exporting === "json"}
                        onClick={() => handleExport("json")}
                    >
                        {exporting === "json" ? "Exporting..." : "Export JSON"}
                    </Button>
                    <Button
                        variant="secondary"
                        disabled={exporting === "csv"}
                        onClick={() => handleExport("csv")}
                    >
                        {exporting === "csv" ? "Exporting..." : "Export CSV"}
                    </Button>
                </div>
            </article>
        </>
    );
}
