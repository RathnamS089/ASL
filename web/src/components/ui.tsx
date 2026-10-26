import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost";

export function Button({ variant = "primary", className = "", children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const styles: Record<Variant, string> = {
    primary: "bg-lime text-ink hover:brightness-105 active:scale-[0.98] shadow-[0_8px_30px_-12px_rgb(204_245_99/0.6)]",
    secondary: "bg-raised text-paper ring-1 ring-white/10 hover:bg-white/10 active:scale-[0.98]",
    ghost: "text-muted hover:text-paper",
  };
  return (
    <button
      {...rest}
      className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl px-5 text-[15px] font-semibold transition disabled:pointer-events-none disabled:opacity-40 ${styles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-3xl bg-surface/80 ring-1 ring-white/[0.06] backdrop-blur ${className}`}>{children}</div>;
}

export function Badge({ tone = "muted", children }: { tone?: "muted" | "lime" | "violet" | "danger"; children: ReactNode }) {
  const tones = {
    muted: "bg-white/5 text-muted ring-white/10",
    lime: "bg-lime/10 text-lime ring-lime/30",
    violet: "bg-violet/10 text-violet ring-violet/30",
    danger: "bg-danger/10 text-danger ring-danger/30",
  };
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider ring-1 ${tones[tone]}`}>{children}</span>;
}

export function Icon({ name, className = "size-5" }: { name: "camera" | "flip" | "play" | "replay" | "copy" | "x" | "arrow" | "spark" | "check"; className?: string }) {
  const paths: Record<string, ReactNode> = {
    camera: <><path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><circle cx="12" cy="13" r="3.5" /></>,
    flip: <><path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3" /><path d="M18 3v4h-4M6 21v-4h4" /></>,
    play: <path d="M7 5v14l12-7z" />,
    replay: <><path d="M4 12a8 8 0 1 0 2.3-5.6" /><path d="M4 4v5h5" /></>,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
    x: <path d="M6 6l12 12M18 6L6 18" />,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    spark: <path d="M12 3v6m0 6v6M3 12h6m6 0h6" />,
    check: <path d="M5 12l5 5 9-10" />,
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {paths[name]}
    </svg>
  );
}
