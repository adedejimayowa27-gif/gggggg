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
import { listTeamMembers } from "@/lib/team";
import type { Business, TeamRole } from "@/types";

const SELECTED_BUSINESS_STORAGE_KEY = "bizintel:selectedBusinessId";

interface DashboardContextValue {
  businesses: Business[];
  primaryBusiness: Business | null;
  isLoadingBusinesses: boolean;
  refreshBusinesses: () => Promise<void>;
  selectBusiness: (businessId: string) => void;
  // Batch 10.15 (frontend): the current user's role on primaryBusiness --
  // "owner" for a business they own, one of the TeamMember roles
  // otherwise, or null while it's still loading. Pages that gate
  // admin-only actions (team management, billing, the audit log) read
  // this instead of each independently re-deriving it.
  currentUserRole: TeamRole | null;
}

const DashboardContext = createContext<DashboardContextValue | undefined>(undefined);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const { token, user } = useAuth();
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [isLoadingBusinesses, setIsLoadingBusinesses] = useState(true);
  const [selectedBusinessId, setSelectedBusinessId] = useState<string | null>(null);
  const [currentUserRole, setCurrentUserRole] = useState<TeamRole | null>(null);

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

  // The backend has no "my role on this business" endpoint -- every real
  // business always has an explicit TeamMember row for its owner (role
  // "owner", created alongside the business -- see
  // app.services.team.create_owner_membership), so fetching the team
  // list and matching on user_id is how the frontend learns its own
  // role, the same way it would learn anyone else's.
  useEffect(() => {
    if (!token || !user || !primaryBusiness) {
      setCurrentUserRole(null);
      return;
    }
    let cancelled = false;
    listTeamMembers(primaryBusiness.id, token)
      .then((members) => {
        if (cancelled) return;
        const mine = members.find((m) => m.user_id === user.id);
        setCurrentUserRole(mine?.role ?? null);
      })
      .catch(() => {
        if (!cancelled) setCurrentUserRole(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token, user, primaryBusiness]);

  return (
    <DashboardContext.Provider
      value={{
        businesses, primaryBusiness, isLoadingBusinesses, refreshBusinesses, selectBusiness,
        currentUserRole,
      }}
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
