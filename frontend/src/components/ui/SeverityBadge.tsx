import styles from "./SeverityBadge.module.css";

type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL";

interface SeverityBadgeProps {
    severity: Severity | string;
    /** Show a dot indicator before the text. Default: true */
    showDot?: boolean;
}

const SEVERITY_MAP: Record<string, string> = {
    CRITICAL: styles.critical,
    HIGH: styles.high,
    MEDIUM: styles.medium,
    LOW: styles.low,
    INFORMATIONAL: styles.informational,
};

/**
 * Consistent severity badge used across signal cards, detections, findings.
 * CRITICAL severity gets a pulsing animation to draw investigator attention.
 *
 * Usage:
 *   <SeverityBadge severity="HIGH" />
 *   <SeverityBadge severity="CRITICAL" showDot={false} />
 */
export function SeverityBadge({ severity, showDot = true }: SeverityBadgeProps) {
    const colorClass = SEVERITY_MAP[severity.toUpperCase()] ?? styles.informational;

    return (
        <span className={`${styles.badge} ${colorClass}`}>
            {showDot && <span className={styles.dot} aria-hidden="true" />}
            {severity}
        </span>
    );
}
