import { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "primary" | "secondary";
}

export function Button({ className, variant = "secondary", type = "button", ...props }: ButtonProps) {
    const classes = ["ui-button", `ui-button-${variant}`, className].filter(Boolean).join(" ");
    return <button type={type} className={classes} {...props} />;
}
