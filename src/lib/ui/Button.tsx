"use client";

export function Button(props: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" }) {
  const v = props.variant ?? "primary";
  const cls =
    v === "primary"
      ? "rounded-lg bg-white/15 hover:bg-white/20 border border-white/10 px-3 py-2 text-sm disabled:opacity-50"
      : "rounded-lg hover:bg-white/10 border border-white/10 px-3 py-2 text-sm disabled:opacity-50";
  return <button {...props} className={[cls, props.className ?? ""].join(" ")} />;
}
