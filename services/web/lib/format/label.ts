/** Short, readable form of a UUID for headings and tables. */
export function shortId(id: string, len = 8): string {
  return id.replace(/-/g, "").slice(0, len).toUpperCase();
}

/** "mrc_northwind" becomes "Northwind". Used only when the catalog sends no display name. */
export function merchantLabel(merchantId: string): string {
  const base = merchantId.replace(/^mrc[_-]/, "");
  return base
    .split(/[_-]/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

const CASE_STATE_LABEL: Record<string, string> = {
  PROTECTED: "Protected",
  MONITORING: "Watching",
  PROBLEM_DETECTED: "Problem found",
  TRIAGED: "Sorted",
  OFFERED: "Offer ready",
  HUMAN_REVIEW: "With a reviewer",
  APPROVED: "Approved",
  REFUNDING: "Refund in progress",
  RESOLVED_REFUNDED: "Refunded",
  RESOLVED_RESHIP: "Reshipping",
  DECLINED: "Declined",
  CLOSED: "Closed",
};

export function caseStateLabel(state: string): string {
  return CASE_STATE_LABEL[state] ?? state;
}

const CASE_KIND_LABEL: Record<string, string> = {
  LATE: "Late",
  LOST: "Lost",
  DAMAGED: "Damaged",
  WRONG_ITEM: "Wrong item",
  NOT_AS_DESCRIBED: "Not as described",
  OTHER: "Other",
};

export function caseKindLabel(kind: string): string {
  return CASE_KIND_LABEL[kind] ?? kind;
}

const ORDER_STATUS_LABEL: Record<string, string> = {
  CREATING: "Creating",
  CREATE_UNKNOWN: "Checking",
  CREATE_FAILED: "Not created",
  AWAITING_APPROVAL: "Waiting for PayPal approval",
  APPROVED: "Approved",
  CAPTURE_PENDING: "Capturing",
  CAPTURE_UNKNOWN: "Checking payment",
  CAPTURED: "Captured",
  CAPTURE_FAILED: "Payment failed",
  CANCELLED_REVOKED: "Cancelled (mandate revoked)",
  CANCELLED_BUYER: "Cancelled",
  EXPIRED: "Expired",
};

export function orderStatusLabel(status: string): string {
  return ORDER_STATUS_LABEL[status] ?? status;
}

const MANDATE_STATUS_LABEL: Record<string, string> = {
  active: "Mandate active",
  revoked: "Revoked",
  expired: "Expired",
  exhausted: "Cap used up",
};

export function mandateStatusLabel(status: string): string {
  return MANDATE_STATUS_LABEL[status] ?? status;
}
