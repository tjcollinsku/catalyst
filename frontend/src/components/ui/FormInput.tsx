import { InputHTMLAttributes } from "react";

type FormInputProps = InputHTMLAttributes<HTMLInputElement>;

export function FormInput({ className, ...props }: FormInputProps) {
    const classes = ["ui-control", className].filter(Boolean).join(" ");
    return <input className={classes} {...props} />;
}
