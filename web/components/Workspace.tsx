"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BrandSummary } from "@/lib/types";

export type Role = "creator" | "manager";

interface WorkspaceState {
  brand: BrandSummary | null;
  brandError: string | null;
  role: Role;
  setRole: (r: Role) => void;
  person: string;
}

const Ctx = createContext<WorkspaceState | null>(null);

const ROLE_KEY = "brandpilot.role";

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [brand, setBrand] = useState<BrandSummary | null>(null);
  const [brandError, setBrandError] = useState<string | null>(null);
  const [role, setRoleState] = useState<Role>("creator");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(ROLE_KEY);
      if (saved === "creator" || saved === "manager") setRoleState(saved);
    } catch {
      /* storage unavailable: keep default */
    }
    api<BrandSummary[]>("/brands")
      .then((list) => {
        if (list.length === 0) setBrandError("No brand yet. Run the seed script or add one in the Brand vault.");
        else setBrand(list[0]);
      })
      .catch((e: Error) => setBrandError(e.message));
  }, []);

  const setRole = useCallback((r: Role) => {
    setRoleState(r);
    try {
      localStorage.setItem(ROLE_KEY, r);
    } catch {
      /* ignore */
    }
  }, []);

  return (
    <Ctx.Provider
      value={{ brand, brandError, role, setRole, person: role === "creator" ? "Creator" : "Manager" }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useWorkspace(): WorkspaceState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return v;
}
