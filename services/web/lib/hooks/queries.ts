"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { requireUuid } from "@/lib/api/ids";

export const keys = {
  buyerHome: ["buyer-home"] as const,
  mandate: (id: string) => ["mandate", id] as const,
  mandateTerms: (id: string) => ["mandate-terms", id] as const,
  catalog: ["catalog-items"] as const,
};

export function useBuyerHome() {
  return useQuery({
    queryKey: keys.buyerHome,
    queryFn: ({ signal }) => api.bff.buyerHome(signal),
  });
}

export function useMandate(id: string) {
  return useQuery({
    queryKey: keys.mandate(id),
    queryFn: ({ signal }) => api.mandate.get(requireUuid(id, "mandate id"), signal),
  });
}

export function useMandateTerms(id: string) {
  return useQuery({
    queryKey: keys.mandateTerms(id),
    queryFn: ({ signal }) => api.mandate.terms(requireUuid(id, "mandate id"), signal),
  });
}

/** Active catalog items; the allowlist picker reads its merchants from here. */
export function useCatalogMerchants() {
  return useQuery({
    queryKey: keys.catalog,
    queryFn: ({ signal }) => api.catalog.items({ limit: 100 }, signal),
    staleTime: 5 * 60_000,
  });
}
