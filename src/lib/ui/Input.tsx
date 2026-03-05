"use client";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={[
        "w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none",
        "focus:border-white/20",
        props.className ?? "",
      ].join(" ")}
    />
  );
}
