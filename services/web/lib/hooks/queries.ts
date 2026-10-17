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

/** Deployment switches. Money screens read this to show the kill switch state up front. */
export function useOpsStatus() {
  return useQuery({
    queryKey: ["ops-status"] as const,
    queryFn: ({ signal }) => api.ops.status(signal),
    staleTime: 30_000,
  });
}

export function useOrders(limit = 20) {
  return useQuery({
    queryKey: ["orders", limit] as const,
    queryFn: ({ signal }) => api.checkout.orders({ limit }, signal),
  });
}

export function useBffOrder(id: string) {
  return useQuery({
    queryKey: ["bff-order", id] as const,
    queryFn: ({ signal }) => api.bff.order(requireUuid(id, "order id"), signal),
  });
}

/** Only fetched once the order is captured; before that the receipt does not exist. */
export function useReceipt(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["receipt", id] as const,
    queryFn: ({ signal }) => api.checkout.receipt(requireUuid(id, "order id"), signal),
    enabled,
    retry: false,
  });
}

const CASE_IN_MOTION = new Set(["APPROVED", "REFUNDING"]);

export function useCase(id: string) {
  return useQuery({
    queryKey: ["case", id] as const,
    queryFn: ({ signal }) => api.resolution.case(requireUuid(id, "case id"), signal),
    // A refund in flight is worth watching; everything else waits for the buyer.
    refetchInterval: (q) => (q.state.data && CASE_IN_MOTION.has(q.state.data.state) ? 5000 : false),
  });
}

export function useApproval(token: string) {
  return useQuery({
    queryKey: ["approval", token] as const,
    queryFn: ({ signal }) => api.resolution.approvalPreview(token, signal),
    retry: false,
  });
}

export function useMerchantQueue() {
  return useQuery({
    queryKey: ["merchant-queue"] as const,
    queryFn: ({ signal }) => api.bff.merchantQueue(signal),
  });
}
