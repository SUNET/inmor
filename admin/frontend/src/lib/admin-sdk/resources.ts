import {
    array,
    boolean,
    nullable,
    number,
    object,
    optional,
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
    autorenew: optional(boolean()),
    valid_for: optional(number()),
    renewal_time: optional(number()),
    active: optional(boolean()),
    additional_claims: optional(nullable(record(string(), unknown()))),
});

export type TrustMarkUpdateOptions = InferOutput<typeof TrustMarkUpdateOptionsSchema>;
export const TrustMarkUpdateOptionsSchema = object({
    autorenew: optional(boolean()),
    active: optional(boolean()),
    additional_claims: optional(nullable(record(string(), unknown()))),
});

export type TrustMark = InferOutput<typeof TrustMarkSchema>;
export const TrustMarkSchema = object({
    id: number(),
    tmt_id: number(),
    domain: string(),
    expire_at: string(),
    autorenew: nullable(boolean()),
    valid_for: nullable(number()),
    renewal_time: nullable(number()),
    active: nullable(boolean()),
    mark: nullable(string()),
    additional_claims: optional(nullable(record(string(), unknown()))),
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
    forced_metadata: record(string(), unknown()),
    jwks: record(string(), unknown()),
    required_trustmarks: optional(nullable(string())),
    valid_for: optional(nullable(number())),
    autorenew: optional(boolean()),
    active: optional(boolean()),
    additional_claims: optional(nullable(record(string(), unknown()))),
});

export type SubordinateUpdateOptions = InferOutput<typeof SubordinateUpdateOptionsSchema>;
export const SubordinateUpdateOptionsSchema = object({
    metadata: record(string(), unknown()),
    forced_metadata: record(string(), unknown()),
    jwks: record(string(), unknown()),
    required_trustmarks: optional(nullable(string())),
    valid_for: optional(nullable(number())),
    autorenew: optional(boolean()),
    active: optional(boolean()),
    additional_claims: optional(nullable(record(string(), unknown()))),
});

export type Subordinate = InferOutput<typeof SubordinateSchema>;
export const SubordinateSchema = object({
    id: number(),
    entityid: string(),
    metadata: record(string(), unknown()),
    forced_metadata: record(string(), unknown()),
    jwks: record(string(), unknown()),
    required_trustmarks: nullable(string()),
    valid_for: nullable(number()),
    expire_at: optional(nullable(string())),
    autorenew: nullable(boolean()),
    active: nullable(boolean()),
    additional_claims: optional(nullable(record(string(), unknown()))),
});

export type Subordinates = InferOutput<typeof SubordinatesSchema>;
export const SubordinatesSchema = object({
    items: array(SubordinateSchema),
    count: number(),
});

export type EntityConfig = InferOutput<typeof EntityConfigSchema>;
export const EntityConfigSchema = object({
    metadata: record(string(), unknown()),
    jwks: record(string(), unknown()),
    authority_hints: optional(nullable(array(string()))),
    trust_marks: optional(nullable(array(record(string(), unknown())))),
});
