import styles from "./EmptyState.module.css";

interface EmptyStateProps {
    title: string;
    detail: string;
    icon?: string;
    action?: {
        label: string;
        onClick: () => void;
    };
}

export function EmptyState({ title, detail, icon, action }: EmptyStateProps) {
    return (
        <div className={styles.root} role="status">
            {icon && <span className={styles.icon} aria-hidden="true">{icon}</span>}
            <strong>{title}</strong>
            <p>{detail}</p>
            {action && (
                <button className={styles.actionBtn} onClick={action.onClick}>
                    {action.label}
                </button>
            )}
        </div>
    );
}
