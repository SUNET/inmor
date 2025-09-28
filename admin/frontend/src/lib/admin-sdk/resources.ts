import * as v from 'valibot';

export type HttpMethod = 'GET'|'POST'|'DELETE'|'PATCH'|'PUT';

export type TrustMarkTypeCreationOptions = v.InferOutput<typeof TrustMarkTypeCreationOptionsSchema>;
export const TrustMarkTypeCreationOptionsSchema = v.object({
  tmtype: v.string(),
  autorenew: v.boolean(),
  valid_for: v.number(),
  renewal_time: v.number(),
  active: v.boolean(),
})

export type TrustMarkType = v.InferOutput<typeof TrustMarkTypeSchema>;
export const TrustMarkTypeSchema = v.object({
  id: v.number(),
  tmtype: v.string(),
  autorenew: v.boolean(),
  valid_for: v.number(),
  renewal_time: v.number(),
  active: v.boolean(),
});

export type TrustMarkTypes = v.InferOutput<typeof TrustMarkTypesSchema>;
export const TrustMarkTypesSchema = v.object({
  items: v.array(TrustMarkTypeSchema),
  count: v.number(),
});
