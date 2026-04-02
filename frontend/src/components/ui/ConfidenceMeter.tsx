import styles from "./ConfidenceMeter.module.css";

interface ConfidenceMeterProps {
    /** Confidence score from 0 to 100 (or 0.0 to 1.0 — auto-detected) */
    value: number;
    /** Label shown before the bar. Default: "Confidence" */
    label?: string;
    /** Hide the label. Useful in compact layouts. */
    hideLabel?: boolean;
}

/**
 * Visual confidence meter with colored bar and percentage.
 * Color shifts: red (0-40) → amber (40-70) → green (70-100).
 *
 * Usage:
 *   <ConfidenceMeter value={0.92} />
 *   <ConfidenceMeter value={85} label="Match score" />
 */
export function ConfidenceMeter({
    value,
    label = "Confidence",
    hideLabel = false,
}: ConfidenceMeterProps) {
    // Normalize: accept both 0-1 and 0-100 scales
    const pct = value <= 1 ? Math.round(value * 100) : Math.round(value);
    const clamped = Math.max(0, Math.min(100, pct));

    // Color tier
    let valueClass: string;
    let fillClass: string;
    if (clamped < 40) {
        valueClass = styles.low;
        fillClass = styles.lowFill;
    } else if (clamped < 70) {
        valueClass = styles.medium;
        fillClass = styles.mediumFill;
    } else {
        valueClass = styles.high;
        fillClass = styles.highFill;
    }

    return (
        <div className={styles.container}>
            {!hideLabel && <span className={styles.label}>{label}</span>}
            <div className={styles.track}>
                <div
                    className={`${styles.fill} ${fillClass}`}
                    style={{ width: `${clamped}%` }}
                    role="meter"
                    aria-valuenow={clamped}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${label}: ${clamped}%`}
                />
            </div>
            <span className={`${styles.value} ${valueClass}`}>{clamped}%</span>
        </div>
    );
}
