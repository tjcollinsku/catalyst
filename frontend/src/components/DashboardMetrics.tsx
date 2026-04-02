import styles from "./DashboardMetrics.module.css";

interface DashboardMetricsProps {
    totalCases: number;
    openCaseCount: number;
    highSeveritySignals: number;
    openSignals: number;
}

export function DashboardMetrics({
    totalCases,
    openCaseCount,
    highSeveritySignals,
    openSignals
}: DashboardMetricsProps) {
    return (
        <section className={styles.kpiGrid}>
            <article className={styles.kpiCard}>
                <span>Total Cases</span>
                <strong>{totalCases}</strong>
                <p>Current investigative queue</p>
            </article>
            <article className={styles.kpiCard}>
                <span>Open Cases</span>
                <strong>{openCaseCount}</strong>
                <p>Cases marked ACTIVE by status</p>
            </article>
            <article className={styles.kpiCard}>
                <span>High-Risk Signals</span>
                <strong>{highSeveritySignals}</strong>
                <p>High or critical findings in active case</p>
            </article>
            <article className={styles.kpiCard}>
                <span>Signal Queue</span>
                <strong>{openSignals}</strong>
                <p>Open triage items for active case</p>
            </article>
        </section>
    );
}
