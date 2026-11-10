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
  reloadBrand: () => Promise<void>;
  seedDemoBrand: () => Promise<void>;
}

const Ctx = createContext<WorkspaceState | null>(null);

const ROLE_KEY = "brandpilot.role";

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [brand, setBrand] = useState<BrandSummary | null>(null);
  const [brandError, setBrandError] = useState<string | null>(null);
  const [role, setRoleState] = useState<Role>("creator");

  const loadBrands = useCallback(async () => {
    try {
      const list = await api<BrandSummary[]>("/brands");
      if (list.length === 0) {
        setBrand(null);
        setBrandError("No brand yet. Click below to load the NutriCrunch sample brand kit, or create one in the Brand vault.");
      } else {
        setBrand(list[0]);
        setBrandError(null);
      }
    } catch (e: unknown) {
      setBrand(null);
      setBrandError((e as Error).message || "Could not connect to the API server.");
    }
  }, []);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(ROLE_KEY);
      if (saved === "creator" || saved === "manager") setRoleState(saved);
    } catch {
      /* storage unavailable: keep default */
    }
    loadBrands();
  }, [loadBrands]);

  const seedDemoBrand = useCallback(async () => {
    try {
      setBrandError(null);
      await api<{ ok: boolean; brand: BrandSummary }>("/seed", { method: "POST" });
      await loadBrands();
    } catch (e: unknown) {
      setBrandError((e as Error).message || "Failed to load sample brand kit.");
    }
  }, [loadBrands]);

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
      value={{
        brand,
        brandError,
        role,
        setRole,
        person: role === "creator" ? "Creator" : "Manager",
        reloadBrand: loadBrands,
        seedDemoBrand,
      }}
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
