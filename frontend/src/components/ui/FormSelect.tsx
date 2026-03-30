import { SelectHTMLAttributes } from "react";

type FormSelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export function FormSelect({ className, ...props }: FormSelectProps) {
    const classes = ["ui-control", className].filter(Boolean).join(" ");
    return <select className={classes} {...props} />;
}
