import styles from "./Skeleton.module.css";

interface SkeletonProps {
    width?: string;
    height?: string;
    borderRadius?: string;
    className?: string;
}

/** Single skeleton shimmer line/block */
export function Skeleton({ width, height = "1rem", borderRadius, className }: SkeletonProps) {
    return (
        <div
            className={`${styles.skeleton} ${className ?? ""}`}
            style={{ width, height, borderRadius }}
        />
    );
}

/** Graph-shaped skeleton with fake nodes and edges */
export function GraphSkeleton() {
    return (
        <div className={styles.graphSkeleton}>
            <div className={styles.graphShimmer} />
            <div className={styles.graphLabel}>Building investigation map...</div>
        </div>
    );
}

/** Pipeline card skeleton (3 placeholder cards) */
export function PipelineCardsSkeleton({ count = 3 }: { count?: number }) {
    return (
        <div className={styles.cardStack}>
            {Array.from({ length: count }).map((_, i) => (
                <div key={i} className={styles.cardSkeleton} style={{ animationDelay: `${i * 100}ms` }}>
                    <div className={styles.cardSkeletonHeader}>
                        <Skeleton width="55%" height="0.85rem" />
                        <Skeleton width="3.5rem" height="0.75rem" borderRadius="999px" />
                    </div>
                    <Skeleton width="80%" height="0.75rem" />
                    <Skeleton width="45%" height="0.75rem" />
                </div>
            ))}
        </div>
    );
}

/** Horizontal timeline skeleton */
export function TimelineSkeleton() {
    return (
        <div className={styles.timelineSkeleton}>
            <div className={styles.timelineShimmerBar} />
            <div className={styles.timelineLabel}>Loading timeline...</div>
        </div>
    );
}
