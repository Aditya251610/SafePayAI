/**
 * Plain-language text for every error code the UI can meet. Screens branch on
 * `code` and show these strings; server wording is never trusted for display
 * except as a last-resort fallback.
 */
export interface ErrorCopy {
  title: string;
  text: string;
  /** Another try can help (shows a retry button). */
  retryable: boolean;
}

const COPY: Readonly<Record<string, ErrorCopy>> = {
  UNAUTHENTICATED: {
    title: "Sign in again",
    text: "Your session has ended or the details were not accepted.",
    retryable: false,
  },
  FORBIDDEN: {
    title: "Not available for this account",
    text: "This action belongs to a different kind of account.",
    retryable: false,
  },
  CSRF_INVALID: {
    title: "Please try again",
    text: "The page needed a fresh security token. Nothing was changed.",
    retryable: true,
  },
  NOT_FOUND: {
    title: "Not found",
    text: "We could not find that item. It may belong to another account.",
    retryable: false,
  },
  RATE_LIMITED: {
    title: "Too many tries",
    text: "Wait a moment, then try again.",
    retryable: true,
  },
  IDEMPOTENCY_KEY_REQUIRED: {
    title: "Please try again",
    text: "The request was incomplete. Nothing was changed.",
    retryable: true,
  },
  MONEY_ROUTES_DISABLED: {
    title: "Money actions are switched off",
    text: "Payments and refunds are paused on this deployment. You can still look around.",
    retryable: false,
  },
  UPSTREAM_UNAVAILABLE: {
    title: "Service is unavailable",
    text: "A part of the system is not answering. Try again shortly. The demo may be at capacity.",
    retryable: true,
  },
  UPSTREAM_WAKING: {
    title: "Waking up the demo server",
    text: "A cold start on free hosting can take about a minute.",
    retryable: true,
  },
  UPSTREAM_TIMEOUT: {
    title: "That took too long",
    text: "Check the current status before trying again.",
    retryable: true,
  },
  UPSTREAM_BAD_RESPONSE: {
    title: "Unexpected answer",
    text: "A service sent something we could not read. Try again shortly.",
    retryable: true,
  },
  OUTCOME_UNKNOWN: {
    title: "Checking what happened",
    text: "The request may have gone through. We are reading the current status. Do not pay twice.",
    retryable: false,
  },
  CONTRACT_MISMATCH: {
    title: "Unexpected answer",
    text: "The server replied in a shape this page does not understand.",
    retryable: false,
  },
  NETWORK_ERROR: {
    title: "No connection",
    text: "The request did not reach the server. Check your connection and try again.",
    retryable: true,
  },
  INVALID_ID: {
    title: "That link is not valid",
    text: "The address is missing or malformed.",
    retryable: false,
  },
  VALIDATION_ERROR: {
    title: "Check the highlighted fields",
    text: "Some details need attention before this can go through.",
    retryable: false,
  },
  validation_error: {
    title: "Check the highlighted fields",
    text: "Some details need attention before this can go through.",
    retryable: false,
  },
  internal_error: {
    title: "Something went wrong on our side",
    text: "Try again shortly.",
    retryable: true,
  },
  NONCE_INVALID: {
    title: "Terms refreshed",
    text: "The signing window passed. Review the terms again, then sign.",
    retryable: false,
  },
  SCREEN_TEXT_MISMATCH: {
    title: "Terms refreshed",
    text: "The text you were shown changed. Review it again, then sign.",
    retryable: false,
  },
  TERMS_OUT_OF_BOUNDS: {
    title: "Outside the allowed range",
    text: "One of the limits is too high or too far away. Adjust it and preview again.",
    retryable: false,
  },
  UNSUPPORTED_CURRENCY: {
    title: "Currency not supported",
    text: "Only the sandbox currency is available.",
    retryable: false,
  },
  MANDATE_NOT_FOUND: {
    title: "Mandate not found",
    text: "That mandate does not exist or is not yours.",
    retryable: false,
  },
  MANDATE_UNAVAILABLE: {
    title: "Mandate service is busy",
    text: "Try again in a moment.",
    retryable: true,
  },
  INVALID_REQUEST: {
    title: "That request was incomplete",
    text: "Check what you entered and try again.",
    retryable: false,
  },
  CATALOG_UNAVAILABLE: {
    title: "Catalog is busy",
    text: "Try again in a moment.",
    retryable: true,
  },
  OVER_CAP: {
    title: "Over your cap",
    text: "This cart is larger than what is left on your mandate.",
    retryable: false,
  },
  CART_NOT_CONFIRMABLE: {
    title: "This cart cannot be confirmed",
    text: "One of the checks blocked it. Review the checks below.",
    retryable: false,
  },
  CART_CHANGED: {
    title: "The cart changed",
    text: "Prices or items moved. Review the cart again before paying.",
    retryable: false,
  },
  NOT_APPROVED: {
    title: "PayPal approval is missing",
    text: "The sandbox payment has not been approved yet. Open the PayPal step to finish.",
    retryable: false,
  },
  RECEIPT_NOT_READY: {
    title: "Receipt is not ready",
    text: "It appears once the payment is captured.",
    retryable: true,
  },
  ORDER_NOT_FOUND: {
    title: "Order not found",
    text: "That order does not exist or is not yours.",
    retryable: false,
  },
  CASE_NOT_FOUND: {
    title: "Case not found",
    text: "That case does not exist or is not yours.",
    retryable: false,
  },
  OFFER_NOT_ACTIVE: {
    title: "Offer expired or changed",
    text: "Reload to see the current offer.",
    retryable: true,
  },
  PROPOSAL_HASH_MISMATCH: {
    title: "Offer expired or changed",
    text: "Reload to see the current offer.",
    retryable: true,
  },
  APPROVAL_NOT_FOUND: {
    title: "Link not valid",
    text: "This approval link does not exist.",
    retryable: false,
  },
  APPROVAL_EXPIRED: {
    title: "Link expired",
    text: "Ask for a new approval link from your case.",
    retryable: false,
  },
  APPROVAL_REPLAY: {
    title: "Link already used",
    text: "This approval link was used before.",
    retryable: false,
  },
  APPROVAL_REVOKED: {
    title: "Link withdrawn",
    text: "This approval link is no longer active.",
    retryable: false,
  },
};

const FALLBACK: ErrorCopy = {
  title: "Something went wrong",
  text: "The request did not complete. Try again, or come back later.",
  retryable: true,
};

export function errorCopy(code: string): ErrorCopy {
  return COPY[code] ?? FALLBACK;
}

export const KNOWN_ERROR_CODES: readonly string[] = Object.keys(COPY);
