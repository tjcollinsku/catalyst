import { SelectHTMLAttributes } from "react";
import styles from "./FormSelect.module.css";

type FormSelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export function FormSelect({ className, ...props }: FormSelectProps) {
    const classes = [styles.control, className].filter(Boolean).join(" ");
    return <select className={classes} {...props} />;
}
