import * as v from 'valibot';

export type HttpMethod = 'GET'|'POST'|'DELETE'|'PATCH'|'PUT';

export type TrustMarkType = v.InferOutput<typeof TrustMarkTypeSchema>;
export const TrustMarkTypeSchema = v.object({
  tmtype: v.string(),
  valid_for: v.number(),
});

export type TrustMarkTypes = v.InferOutput<typeof TrustMarkTypesSchema>;
export const TrustMarkTypesSchema = v.object({
  items: v.array(TrustMarkTypeSchema),
  count: v.number(),
});
