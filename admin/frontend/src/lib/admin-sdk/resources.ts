import * as v from 'valibot';

export type HttpMethod = 'GET'|'POST'|'DELETE'|'PATCH'|'PUT';

export type TrustMarkTypeCreateOptions = v.InferOutput<typeof TrustMarkTypeCreateOptionsSchema>;
export const TrustMarkTypeCreateOptionsSchema = v.object({
  tmtype: v.string(),
  autorenew: v.boolean(),
  valid_for: v.number(),
  renewal_time: v.number(),
  active: v.boolean(),
})

export type TrustMarkTypeUpdateOptions = v.InferOutput<typeof TrustMarkTypeUpdateOptionsSchema>;
export const TrustMarkTypeUpdateOptionsSchema = v.object({
  autorenew: v.boolean(),
  valid_for: v.number(),
  renewal_time: v.number(),
  active: v.boolean(),
});

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
