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
        <section className="kpi-grid">
            <article className="kpi-card">
                <span>Total Cases</span>
                <strong>{totalCases}</strong>
                <p>Current investigative queue</p>
            </article>
            <article className="kpi-card">
                <span>Open Cases</span>
                <strong>{openCaseCount}</strong>
                <p>Cases marked ACTIVE by status</p>
            </article>
            <article className="kpi-card">
                <span>High-Risk Signals</span>
                <strong>{highSeveritySignals}</strong>
                <p>High or critical findings in active case</p>
            </article>
            <article className="kpi-card">
                <span>Signal Queue</span>
                <strong>{openSignals}</strong>
                <p>Open triage items for active case</p>
            </article>
        </section>
    );
}
