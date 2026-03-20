"use client";

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={[
        "w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white outline-none",
        "focus:border-white/20",
        props.className ?? "",
      ].join(" ")}
    >
      {props.children}
    </select>
  );
}
