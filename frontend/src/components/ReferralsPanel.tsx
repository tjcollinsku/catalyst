import { Button } from "./ui/Button";
import styles from "./ReferralsPanel.module.css";

interface ReferralsPanelProps {
    caseId: string;
    onGeneratePdf: () => void;
    generatingPdf: boolean;
}

export function ReferralsPanel({
    // caseId,
    onGeneratePdf,
    generatingPdf,
}: ReferralsPanelProps) {
    return (
        <div className={styles.referralsPanel}>
            <div className={styles.referralsPanelHeader}>
                <h3>Referral Export</h3>
            </div>

            <div className={`${styles.referralCard} ${styles.card}`}>
                <p>
                    Generate a deterministic referral package PDF with all findings,
                    evidence, and recommended actions.
                </p>
                <div className={styles.formActions}>
                    <Button
                        variant="primary"
                        disabled={generatingPdf}
                        onClick={onGeneratePdf}
                    >
                        {generatingPdf ? "Generating PDF…" : "Generate Referral PDF"}
                    </Button>
                </div>
            </div>
        </div>
    );
}
