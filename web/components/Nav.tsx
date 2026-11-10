"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useWorkspace } from "./Workspace";

const LINKS = [
  { href: "/", label: "Write & check" },
  { href: "/review", label: "Review queue" },
  { href: "/vault", label: "Brand vault" },
  { href: "/insights", label: "Insights" },
];

export function Nav() {
  const path = usePathname();
  const { brand, role, setRole } = useWorkspace();

  return (
    <header className="border-b border-rule bg-paper">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" className="font-serif text-2xl italic tracking-tight text-ink">
          BrandPilot
        </Link>
        <nav className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto">
          {LINKS.map((l) => {
            const active = l.href === "/" ? path === "/" || path.startsWith("/scans") : path.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm ${
                  active ? "bg-desk font-semibold text-ink" : "text-muted hover:text-ink"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {brand && <span className="hidden text-muted md:inline">{brand.name}</span>}
          <label className="flex items-center gap-2">
            <span className="text-muted">Viewing as</span>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as "creator" | "manager")}
              className="rounded-md border border-rule bg-paper px-2 py-1 font-medium"
            >
              <option value="creator">Creator</option>
              <option value="manager">Manager</option>
            </select>
          </label>
        </div>
      </div>
    </header>
  );
}
