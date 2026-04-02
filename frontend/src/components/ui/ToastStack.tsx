import styles from "./ToastStack.module.css";

export interface ToastItem {
    id: number;
    tone: "error" | "success";
    message: string;
}

interface ToastStackProps {
    toasts: ToastItem[];
    onDismiss: (id: number) => void;
}

export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
    if (toasts.length === 0) {
        return null;
    }

    return (
        <div className={styles.stack} aria-live="polite" aria-atomic="false">
            {toasts.map((toast) => (
                <div key={toast.id} className={`${styles.toast} ${styles[toast.tone]}`} role="status">
                    <p>{toast.message}</p>
                    <button
                        type="button"
                        className={styles.dismiss}
                        onClick={() => onDismiss(toast.id)}
                        aria-label="Dismiss notification"
                    >
                        x
                    </button>
                </div>
            ))}
        </div>
    );
}
