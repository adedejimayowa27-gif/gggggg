"use client";

/**
 * Dashboard context.
 *
 * Separate from AuthContext -- this holds data specific to the dashboard
 * tree (the user's businesses) so the topbar, sidebar, and Overview page
 * can all share one fetch instead of each calling the API independently.
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

interface DashboardContextValue {
  businesses: Business[];
  primaryBusiness: Business | null;
  isLoadingBusinesses: boolean;
  refreshBusinesses: () => Promise<void>;
}

const DashboardContext = createContext<DashboardContextValue | undefined>(undefined);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [isLoadingBusinesses, setIsLoadingBusinesses] = useState(true);

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

  const primaryBusiness = businesses.length > 0 ? businesses[0] : null;

  return (
    <DashboardContext.Provider
      value={{ businesses, primaryBusiness, isLoadingBusinesses, refreshBusinesses }}
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
