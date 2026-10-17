import { z } from "zod";
import { lenientEnum } from "./common";

export const PROPOSAL_STATUSES = ["OK", "NO_MATCH", "NO_PROPOSAL", "AI_PAUSED"] as const;

export const proposeFormSchema = z.object({
  category: z.string().min(1),
  max_budget_minor: z.number().int().min(0),
  quantity: z.number().int().min(1).max(5),
  merchant_id: z.string().nullish(),
  keywords: z.string().nullish(),
});

export const proposeRequestSchema = z
  .object({
    mandate_id: z.string().min(1),
    mode: z.enum(["intent", "form"]),
    intent_text: z.string().max(500).nullish(),
    catalog_snapshot_id: z.string().nullish(),
    form: proposeFormSchema.nullish(),
  })
  .refine((v) => v.mode !== "form" || v.form != null, {
    message: "form mode needs form fields",
    path: ["form"],
  })
  .refine((v) => v.mode !== "intent" || (v.intent_text ?? "").trim().length > 0, {
    message: "intent mode needs intent_text",
    path: ["intent_text"],
  });
export type ProposeRequest = z.infer<typeof proposeRequestSchema>;

export const proposalLineSchema = z.object({
  sku: z.string(),
  quantity: z.number().int(),
  display_title: z.string().nullish(),
});
export type ProposalLine = z.infer<typeof proposalLineSchema>;

export const proposalSchema = z.object({
  proposal_id: z.string(),
  status: lenientEnum(PROPOSAL_STATUSES),
  source: z.string(),
  lines: z.array(proposalLineSchema),
  rationale: z.string().nullish(),
  confidence: z.number().nullish(),
  no_match_reason: z.string().nullish(),
  model: z.string().nullish(),
  latency_ms: z.number().nullish(),
  badge: z.string().nullish(),
  recorded_model: z.string().nullish(),
  trace_id: z.string().nullish(),
});
export type Proposal = z.infer<typeof proposalSchema>;
