import { useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { CaseDetailContext } from "../../views/CaseDetailView";
import { ReferralsPanel } from "../ReferralsPanel";
import { Button } from "../ui/Button";
import { formatDate } from "../../utils/format";
import { exportCaseReport } from "../../api";
import styles from "./ReferralsTab.module.css";

export function ReferralsTab() {
    const { caseId } = useParams<{ caseId: string }>();
    const {
        referrals,
        loadingReferrals,
        savingReferralId,
        onCreateReferral,
        onUpdateReferral,
        onDeleteReferral,
        pushToast,
    } = useOutletContext<CaseDetailContext>();

    const [exporting, setExporting] = useState<string | null>(null);

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
                referrals={referrals}
                loadingReferrals={loadingReferrals}
                savingReferralId={savingReferralId}
                onCreateReferral={onCreateReferral}
                onUpdateReferral={onUpdateReferral}
                onDeleteReferral={onDeleteReferral}
                formatDate={formatDate}
            />

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
