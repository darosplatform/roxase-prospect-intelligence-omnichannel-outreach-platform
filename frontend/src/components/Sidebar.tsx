"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/discovery", label: "Discovery" },
  { href: "/companies", label: "Companies" },
  { href: "/contacts", label: "Contacts" },
  { href: "/leads", label: "Leads" },
  { href: "/evidence", label: "Evidence" },
  { href: "/signals", label: "Signals" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/outreach", label: "Outreach" },
  { href: "/audit", label: "Audit" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className="flex h-screen w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="px-4 py-5">
        <span className="text-lg font-semibold tracking-tight">ROXASE</span>
      </div>
      <nav className="flex-1 space-y-0.5 px-2">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname?.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded-md px-3 py-2 text-sm font-medium ${
                active
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-slate-200 p-3">
        <p className="truncate text-xs text-slate-500">{user?.sub}</p>
        <p className="mb-2 text-xs font-medium uppercase text-slate-400">{user?.role}</p>
        <button
          onClick={logout}
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
