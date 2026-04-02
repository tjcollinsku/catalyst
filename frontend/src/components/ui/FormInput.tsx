import { InputHTMLAttributes } from "react";
import styles from "./FormInput.module.css";

type FormInputProps = InputHTMLAttributes<HTMLInputElement>;

export function FormInput({ className, ...props }: FormInputProps) {
    const classes = [styles.control, className].filter(Boolean).join(" ");
    return <input className={classes} {...props} />;
}
