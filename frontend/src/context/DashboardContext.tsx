"use client";

/**
 * Dashboard context.
 *
 * Separate from AuthContext -- this holds data specific to the dashboard
 * tree (the user's businesses) so the topbar, sidebar, and Overview page
 * can all share one fetch instead of each calling the API independently.
 *
 * Batch 10.1: a user can already own multiple businesses (the backend
 * has always supported this), but until now primaryBusiness was
 * hardcoded to businesses[0] -- creating a second business via the
 * existing "+ New business" flow left it permanently unreachable. This
 * adds a real selection, persisted across reloads via localStorage, so
 * switching between businesses actually works.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { useAuth } from "@/context/AuthContext";
import { apiFetch } from "@/lib/api";
import type { Business } from "@/types";

const SELECTED_BUSINESS_STORAGE_KEY = "bizintel:selectedBusinessId";

interface DashboardContextValue {
  businesses: Business[];
  primaryBusiness: Business | null;
  isLoadingBusinesses: boolean;
  refreshBusinesses: () => Promise<void>;
  selectBusiness: (businessId: string) => void;
}

const DashboardContext = createContext<DashboardContextValue | undefined>(undefined);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [isLoadingBusinesses, setIsLoadingBusinesses] = useState(true);
  const [selectedBusinessId, setSelectedBusinessId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedBusinessId(window.localStorage.getItem(SELECTED_BUSINESS_STORAGE_KEY));
  }, []);

  const selectBusiness = useCallback((businessId: string) => {
    setSelectedBusinessId(businessId);
    window.localStorage.setItem(SELECTED_BUSINESS_STORAGE_KEY, businessId);
  }, []);

  const refreshBusinesses = useCallback(async () => {
    if (!token) return;
    setIsLoadingBusinesses(true);
    try {
      const data = await apiFetch<Business[]>("/businesses", { authToken: token });
      setBusinesses(data);
    } catch {
      setBusinesses([]);
    } finally {
      setIsLoadingBusinesses(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      refreshBusinesses();
    }
  }, [token, refreshBusinesses]);

  // Falls back to the first business whenever the saved selection points
  // at one that no longer exists (deleted, or nothing saved yet) --
  // never silently shows nothing just because localStorage is stale.
  const primaryBusiness =
    businesses.find((b) => b.id === selectedBusinessId) ?? businesses[0] ?? null;

  return (
    <DashboardContext.Provider
      value={{ businesses, primaryBusiness, isLoadingBusinesses, refreshBusinesses, selectBusiness }}
    >
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard(): DashboardContextValue {
  const ctx = useContext(DashboardContext);
  if (!ctx) {
    throw new Error("useDashboard must be used within a DashboardProvider");
  }
  return ctx;
}
