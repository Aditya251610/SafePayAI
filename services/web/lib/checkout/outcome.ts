import { isAllowedApproveUrl } from "@/lib/auth/roles";

export type OutcomeTone = "ok" | "pending" | "warn" | "neutral";

export interface Outcome {
  tone: OutcomeTone;
  title: string;
  text: string;
  /** What the primary action does next. */
  action: "receipt" | "check" | "cart" | "mandate" | "orders";
}

/** What to tell the buyer for an order status after PayPal sends them back. */
export function outcomeFor(status: string): Outcome {
  switch (status) {
    case "CAPTURED":
      return {
        tone: "ok",
        title: "Payment captured.",
        text: "Your order is placed. Protection for late or lost delivery starts now.",
        action: "receipt",
      };
    case "CAPTURE_PENDING":
    case "APPROVED":
      return {
        tone: "pending",
        title: "PayPal is still settling.",
        text: "The payment is not confirmed yet. We keep checking. Protection starts once it lands.",
        action: "check",
      };
    case "CAPTURE_UNKNOWN":
      return {
        tone: "warn",
        title: "We could not confirm the payment.",
        text: "Do not pay again. Check the payment below. If it says captured you are done.",
        action: "check",
      };
    case "CAPTURE_FAILED":
      return {
        tone: "warn",
        title: "The payment did not go through.",
        text: "Check your orders before you try again.",
        action: "orders",
      };
    case "CANCELLED_REVOKED":
      return {
        tone: "neutral",
        title: "Mandate was revoked. Order cancelled.",
        text: "You revoked the mandate before the payment was captured, so the order did not go through.",
        action: "mandate",
      };
    case "CANCELLED_BUYER":
      return {
        tone: "neutral",
        title: "You left PayPal. The order was cancelled.",
        text: "No payment was captured. Build a new cart to try again.",
        action: "orders",
      };
    case "AWAITING_APPROVAL":
      return {
        tone: "pending",
        title: "Waiting for your PayPal approval.",
        text: "The sandbox payment has not been approved yet.",
        action: "cart",
      };
    default:
      return {
        tone: "neutral",
        title: "Order status updated.",
        text: "Open the order to see where it stands.",
        action: "orders",
      };
  }
}

export function isFinalStatus(status: string): boolean {
  return [
    "CAPTURED",
    "CAPTURE_FAILED",
    "CANCELLED_REVOKED",
    "CANCELLED_BUYER",
    "CREATE_FAILED",
    "EXPIRED",
  ].includes(status);
}

export function approveHosts(): string[] {
  return (process.env.NEXT_PUBLIC_PS_WEB_PAYPAL_APPROVE_HOST_ALLOWLIST ?? "www.sandbox.paypal.com")
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean);
}

/** True only for an https URL on an allowed PayPal host. */
export function canRedirectToPayPal(url: string): boolean {
  return isAllowedApproveUrl(url, approveHosts());
}
