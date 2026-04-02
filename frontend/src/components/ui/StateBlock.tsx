import styles from "./StateBlock.module.css";

interface StateBlockProps {
    title: string;
    detail?: string;
}

export function StateBlock({ title, detail }: StateBlockProps) {
    return (
        <div className={styles.root}>
            <p className={styles.loading}>{title}</p>
            {detail && <p className={styles.detail}>{detail}</p>}
        </div>
    );
}
