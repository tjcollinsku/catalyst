import { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "primary" | "secondary" | "danger";
    size?: "sm" | "md";
}

export function Button({ className, variant = "secondary", size = "md", type = "button", ...props }: ButtonProps) {
    const classes = [
        styles.button,
        styles[variant],
        size === "sm" ? styles.sm : undefined,
        className,
    ].filter(Boolean).join(" ");
    return <button type={type} className={classes} {...props} />;
}
