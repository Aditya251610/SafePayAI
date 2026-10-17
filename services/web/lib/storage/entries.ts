import { z } from "zod";

import { cartSchema } from "@/lib/api/schemas/checkout";
import { proposalSchema } from "@/lib/api/schemas/agent";

import { loadEntry, saveEntry } from "./session-cache";

const proposalEntrySchema = z.object({ proposal: proposalSchema, mandateId: z.string() });
const cartEntrySchema = z.object({ cart: cartSchema, mandateId: z.string() });

export type ProposalEntry = z.infer<typeof proposalEntrySchema>;
export type CartEntry = z.infer<typeof cartEntrySchema>;

export const saveProposal = (entry: ProposalEntry) =>
  saveEntry(`proposal:${entry.proposal.proposal_id}`, entry);
export const loadProposal = (id: string) => loadEntry(`proposal:${id}`, proposalEntrySchema);

export const saveCart = (entry: CartEntry) => saveEntry(`cart:${entry.cart.cart_id}`, entry);
export const loadCart = (id: string) => loadEntry(`cart:${id}`, cartEntrySchema);

const lastOrderSchema = z.object({ orderId: z.string(), mandateId: z.string().optional() });

/** The order the buyer is paying for, so the PayPal return can be matched and re-read. */
export const saveLastOrder = (orderId: string, mandateId?: string) =>
  saveEntry("last-order", { orderId, mandateId });
export const loadLastOrder = () => loadEntry("last-order", lastOrderSchema);
