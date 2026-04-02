import { TextareaHTMLAttributes } from "react";
import styles from "./FormTextarea.module.css";

type FormTextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export function FormTextarea({ className, ...props }: FormTextareaProps) {
    const classes = [styles.control, className].filter(Boolean).join(" ");
    return <textarea className={classes} {...props} />;
}
