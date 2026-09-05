import type { ReactNode } from "react";

const STATUS_COLORS: Record<string, string> = {
  // generic
  new: "bg-blue-100 text-blue-800",
  active: "bg-green-100 text-green-800",
  ok: "bg-green-100 text-green-800",
  // discovery
  draft: "bg-slate-100 text-slate-700",
  queued: "bg-blue-100 text-blue-800",
  running: "bg-amber-100 text-amber-800",
  fetched: "bg-green-100 text-green-800",
  extracted: "bg-green-100 text-green-800",
  done: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  rejected: "bg-red-100 text-red-800",
  cancelled: "bg-slate-100 text-slate-700",
  skipped: "bg-slate-100 text-slate-700",
  pending: "bg-slate-100 text-slate-700",
  eligible: "bg-blue-100 text-blue-800",
  // qualification / lead
  unqualified: "bg-slate-100 text-slate-700",
  candidate: "bg-amber-100 text-amber-800",
  qualified: "bg-green-100 text-green-800",
  disqualified: "bg-red-100 text-red-800",
  // signal / policy
  reviewed: "bg-blue-100 text-blue-800",
  dismissed: "bg-slate-100 text-slate-700",
  ALLOW: "bg-green-100 text-green-800",
  DENY: "bg-red-100 text-red-800",
  REVIEW: "bg-amber-100 text-amber-800",
  // outreach
  approved: "bg-blue-100 text-blue-800",
  dispatching: "bg-amber-100 text-amber-800",
  sent: "bg-green-100 text-green-800",
  delivered: "bg-green-100 text-green-800",
  denied: "bg-red-100 text-red-800",
  // campaign
  paused: "bg-amber-100 text-amber-800",
  archived: "bg-slate-100 text-slate-700",
};

export function Badge({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-slate-400">—</span>;
  const cls = STATUS_COLORS[value] ?? "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {value}
    </span>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex items-start justify-between">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

export function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
      {label}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      {message}
    </div>
  );
}

export function Spinner() {
  return <div className="py-8 text-center text-sm text-slate-400">Loading...</div>;
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled = false,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const base = "rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50";
  const variants: Record<string, string> = {
    primary: "bg-slate-900 text-white hover:bg-slate-800",
    secondary: "border border-slate-300 text-slate-700 hover:bg-slate-50",
    danger: "bg-red-600 text-white hover:bg-red-500",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${variants[variant]}`}
    >
      {children}
    </button>
  );
}

export function Table({
  columns,
  children,
}: {
  columns: string[];
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            {columns.map((c) => (
              <th
                key={c}
                className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">{children}</tbody>
      </table>
    </div>
  );
}
