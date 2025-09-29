import { 
  array, 
  boolean, 
  number, 
  object, 
  record, 
  string, 
  unknown, 
  type InferOutput 
} from 'valibot';

export type HttpMethod = 'GET'|'POST'|'DELETE'|'PATCH'|'PUT';

export type TrustMarkTypeCreateOptions = InferOutput<typeof TrustMarkTypeCreateOptionsSchema>;
export const TrustMarkTypeCreateOptionsSchema = object({
  tmtype: string(),
  autorenew: boolean(),
  valid_for: number(),
  renewal_time: number(),
  active: boolean(),
})

export type TrustMarkTypeUpdateOptions = InferOutput<typeof TrustMarkTypeUpdateOptionsSchema>;
export const TrustMarkTypeUpdateOptionsSchema = object({
  autorenew: boolean(),
  valid_for: number(),
  renewal_time: number(),
  active: boolean(),
});

export type TrustMarkType = InferOutput<typeof TrustMarkTypeSchema>;
export const TrustMarkTypeSchema = object({
  id: number(),
  tmtype: string(),
  autorenew: boolean(),
  valid_for: number(),
  renewal_time: number(),
  active: boolean(),
});

export type TrustMarkTypes = InferOutput<typeof TrustMarkTypesSchema>;
export const TrustMarkTypesSchema = object({
  items: array(TrustMarkTypeSchema),
  count: number(),
});

export type TrustMarkCreateOptions = InferOutput<typeof TrustMarkCreateOptionsSchema>;
export const TrustMarkCreateOptionsSchema = object({
  tmt: number(),
  domain: string(),
  autorenew: boolean(),
  valid_for: number(),
  renewal_time: number(),
  active: boolean(),
});

export type TrustMarkUpdateOptions = InferOutput<typeof TrustMarkUpdateOptionsSchema>;
export const TrustMarkUpdateOptionsSchema = object({
  autorenew: boolean(),
  active: boolean(),
})

export type TrustMark = InferOutput<typeof TrustMarkSchema>;
export const TrustMarkSchema = object({
  id: number(),
  domain: string(),
  expire_at: string(),
  autorenew: boolean(),
  valid_for: number(),
  renewal_time: number(),
  active: boolean(),
  mark: string(),
});

export type TrustMarks = InferOutput<typeof TrustMarksSchema>;
export const TrustMarksSchema = object({
  items: array(TrustMarkSchema),
  count: number(),
});

export type SubordinateCreateOptions = InferOutput<typeof SubordinateCreateOptionsSchema>;
export const SubordinateCreateOptionsSchema = object({
  entityid: string(),
  metadata: record(string(), unknown()),
  jwks: record(string(), unknown()),
  required_trustmarks: string(),
  valid_for: number(),
  autorenew: boolean(),
  active: boolean(),
});

export type Subordinate = InferOutput<typeof SubordinateSchema>;
export const SubordinateSchema = object({
  id: number(),
  entityid: string(),
  metadata: record(string(), unknown()),
  jwks: record(string(), unknown()), 
  required_trustmarks: string(),
  valid_for: number(), 
  autorenew: boolean(),  
  active: boolean(),  
})

export type Subordinates = InferOutput<typeof SubordinatesSchema>;
export const SubordinatesSchema = object({
  items: array(SubordinateSchema),
  count: number(),
});