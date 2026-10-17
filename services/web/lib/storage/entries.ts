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
