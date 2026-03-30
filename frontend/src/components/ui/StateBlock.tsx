interface StateBlockProps {
    title: string;
    detail?: string;
}

export function StateBlock({ title, detail }: StateBlockProps) {
    return (
        <div className="state-block">
            <p className="loading">{title}</p>
            {detail && <p className="state-detail">{detail}</p>}
        </div>
    );
}
