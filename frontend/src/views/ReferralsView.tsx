import { EmptyState } from "../components/ui/EmptyState";
import styles from "./ReferralsView.module.css";

export function ReferralsView() {
    return (
        <>
            <div className={styles.referralsViewHeader}>
                <h2>Government Referrals</h2>
            </div>

            <EmptyState
                title="Referral tracking is now managed through the Referrals tab in each case."
                detail="Navigate to a case and select the Referrals tab to generate and export referral packages."
            />
        </>
    );
}
