/**
 * The "Run the demo" walkthrough as data. The /guide page renders it and the tests check every
 * route against the app folder. docs/DEMO-GUIDE.md mirrors it in the same order.
 */

export type Actor = "paypal" | "ai" | "rules" | "person";

export const ACTOR_LABEL: Record<Actor, string> = {
  paypal: "PayPal",
  ai: "AI",
  rules: "Rules",
  person: "A person",
};

export interface GuideStep {
  n: string;
  title: string;
  /** Seeded handle to sign in as, or null when the step continues the previous session. */
  persona: string | null;
  /** Plain label for the role. */
  who: string;
  /** App route to open. Must exist in the app folder. */
  route: string;
  /** What to show for the route when it differs from the link target (a dynamic page). */
  routeLabel?: string;
  /** Where the persona link sends you after sign-in; defaults to `route`. */
  next?: string;
  click: string[];
  see: string;
  notice: { actor: Actor; text: string };
}

export const STEPS: readonly GuideStep[] = [
  {
    n: "01",
    title: "A buyer signs a mandate",
    persona: "buyer-alex",
    who: "Buyer",
    route: "/mandate/new",
    click: [
      "Fill in the cap, the per-cart limit, the shops in scope and the end date.",
      "Choose Preview terms and read the terms back.",
      "Choose Sign mandate before the signing window runs out. If it expires, preview again.",
    ],
    see: "A signed mandate with its terms. Nothing can be bought outside it.",
    notice: { actor: "person", text: "You sign. No one else can authorise spending." },
  },
  {
    n: "02",
    title: "State what you need, in words",
    persona: null,
    who: "Buyer",
    route: "/intent",
    click: [
      "Type what you want, for example a pair of headphones under a price you set.",
      "Choose Propose cart.",
    ],
    see: "A draft cart from the seeded catalog, with every rule check listed. If the agent fails or is unsure you get a form instead.",
    notice: {
      actor: "ai",
      text: "The AI drafts. Rules check the draft against your mandate. The AI cannot approve or pay.",
    },
  },
  {
    n: "03",
    title: "Approve the cart and pay at PayPal sandbox",
    persona: null,
    who: "Buyer",
    route: "/intent",
    routeLabel: "/cart/<id>, opened from your draft",
    click: [
      "On the cart, choose Approve cart. You are sent to the PayPal sandbox.",
      "Sign in there with your own sandbox personal (buyer) account and approve the payment.",
      "You land on the Back from PayPal page. Choose Check payment if it still says pending, then Track order.",
    ],
    see: "A captured order with its PayPal sandbox order and capture ids on the receipt.",
    notice: {
      actor: "paypal",
      text: "PayPal's sandbox creates and captures the order. Test funds only.",
    },
  },
  {
    n: "04",
    title: "The merchant ships it",
    persona: "merchant-trailhead",
    who: "Merchant",
    route: "/merchant",
    click: [
      "Sign in as the merchant that owns the item in your cart (merchant-trailhead, merchant-hearth or merchant-pixelwire). Sign out of the buyer first.",
      "Paste the buyer's mandate id (it is in the address of /mandate/<id>) and choose Show orders.",
      "Choose Ship this on the order. Set the outcome profile to late, then choose Mark shipped.",
    ],
    see: "A shipment labelled SIMULATED CARRIER, with a promised date.",
    notice: {
      actor: "rules",
      text: "The carrier is our own simulated clock, not real carrier or PayPal data.",
    },
  },
  {
    n: "05",
    title: "The operator makes it late",
    persona: "operator",
    who: "Operator",
    route: "/ops",
    click: [
      "In the Demo clock panel choose +7 days (use +1 day to go in steps).",
      "Watch the cases list below fill in.",
    ],
    see: "The simulated clock moves past the promised date. The late-order detector opens a case.",
    notice: {
      actor: "rules",
      text: "A deterministic detector opens the case, not a person and not the AI.",
    },
  },
  {
    n: "06",
    title: "The buyer accepts the refund offer",
    persona: "buyer-alex",
    who: "Buyer",
    route: "/home",
    click: [
      "Open the active case from your home page.",
      "Read why the rules made the offer, then choose Accept offer.",
      "If the refund is held, sign in as the operator, open /ops and choose Unfreeze refunds, then confirm.",
      "If the app asks for your approval, follow the approve link it shows.",
    ],
    see: "The case moves to a refund. It goes out through PayPal's refund API and is merchant-funded.",
    notice: {
      actor: "paypal",
      text: "The rules set the amount. PayPal's refund API sends it, in the sandbox.",
    },
  },
  {
    n: "07",
    title: "A reviewer decides what the rules could not",
    persona: "reviewer-demo",
    who: "Reviewer",
    route: "/review",
    click: [
      "Open a case from the queue, if there is one.",
      "Choose a decision (propose a refund, propose a reship, decline or close), add a note and submit.",
    ],
    see: "The case leaves the queue with your note attached. An empty queue means the rules decided everything so far.",
    notice: {
      actor: "person",
      text: "A person decides unusual cases. A refund the reviewer proposes still needs the buyer's approval.",
    },
  },
  {
    n: "08",
    title: "Read the hash-chained log",
    persona: null,
    who: "Any signed-in role",
    route: "/audit",
    click: ["Open the audit log and run the chain check."],
    see: "Every money action in order, each entry carrying the hash of the one before it.",
    notice: { actor: "rules", text: "The log is append-only. The check re-reads the chain." },
  },
];

export interface PersonaRow {
  handle: string;
  role: string;
  can: string;
}

export const PERSONA_TABLE: readonly PersonaRow[] = [
  {
    handle: "buyer-persona",
    role: "Buyer",
    can: "Has a signed mandate, four orders, a refund and open cases to look through.",
  },
  {
    handle: "buyer-alex",
    role: "Buyer",
    can: "Starts empty. Sign a mandate, state a need, pay, report a problem.",
  },
  {
    handle: "merchant-trailhead",
    role: "Merchant",
    can: "Ships that shop's orders on the simulated carrier.",
  },
  {
    handle: "merchant-hearth",
    role: "Merchant",
    can: "Ships that shop's orders on the simulated carrier.",
  },
  {
    handle: "merchant-pixelwire",
    role: "Merchant",
    can: "Ships that shop's orders on the simulated carrier.",
  },
  {
    handle: "operator",
    role: "Operator",
    can: "Moves the simulated carrier clock and holds or releases the refund kill switch.",
  },
  {
    handle: "reviewer-demo",
    role: "Reviewer",
    can: "Decides cases the rules hand to a person.",
  },
];

export const LIMITS: readonly string[] = [
  "Sandbox only. No real money moves and no real PayPal account is used.",
  "The catalog is seeded, not a live marketplace.",
  "Carrier and delivery status is simulated by our own clock. It is not real carrier or PayPal data.",
  "The AI classifies and drafts only. On any error or low confidence it hands the case to a person.",
  "Refunds are merchant-funded, via PayPal's refund API.",
  "Not affiliated with or endorsed by PayPal.",
];

/** Where the picker flow starts for a step's persona. */
export function personaHref(step: Pick<GuideStep, "persona" | "route" | "next">): string | null {
  if (!step.persona) return null;
  const next = step.next ?? step.route;
  return `/login?persona=${encodeURIComponent(step.persona)}&next=${encodeURIComponent(next)}`;
}
