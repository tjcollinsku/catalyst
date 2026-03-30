interface BannerProps {
    tone: "error" | "success";
    message: string;
}

export function Banner({ tone, message }: BannerProps) {
    return <div className={`banner banner-${tone}`}>{message}</div>;
}
