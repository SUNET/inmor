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

export type TrustMarkCreateOptions = v.InferOutput<typeof TrustMarkCreateOptionsSchema>;
export const TrustMarkCreateOptionsSchema = v.object({
  tmt: v.number(),
  domain: v.string(),
  autorenew: v.boolean(),
  valid_for: v.number(),
  renewal_time: v.number(),
  active: v.boolean(),
});

export type TrustMarkUpdateOptions = v.InferOutput<typeof TrustMarkUpdateOptionsSchema>;
export const TrustMarkUpdateOptionsSchema = v.object({
  autorenew: v.boolean(),
  active: v.boolean(),
})

export type TrustMark = v.InferOutput<typeof TrustMarkSchema>;
export const TrustMarkSchema = v.object({
  id: v.number(),
  domain: v.string(),
  expire_at: v.string(),
  autorenew: v.boolean(),
  valid_for: v.number(),
  renewal_time: v.number(),
  active: v.boolean(),
  mark: v.string(),
});

export type TrustMarks = v.InferOutput<typeof TrustMarksSchema>;
export const TrustMarksSchema = v.object({
  items: v.array(TrustMarkSchema),
  count: v.number(),
});