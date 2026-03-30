import { TextareaHTMLAttributes } from "react";

type FormTextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export function FormTextarea({ className, ...props }: FormTextareaProps) {
    const classes = ["ui-control", className].filter(Boolean).join(" ");
    return <textarea className={classes} {...props} />;
}
