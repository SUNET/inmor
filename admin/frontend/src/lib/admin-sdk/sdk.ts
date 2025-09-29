import * as v from 'valibot';
import { FetchError, ValidationError } from './errors';
import { 
    SubordinateCreateOptionsSchema,
    SubordinateSchema,
    TrustMarkCreateOptionsSchema,
    TrustMarkSchema,
    TrustMarksSchema,
    TrustMarkTypeCreateOptionsSchema, 
    TrustMarkTypeSchema, 
    TrustMarkTypesSchema, 
    TrustMarkTypeUpdateOptionsSchema, 
    TrustMarkUpdateOptionsSchema, 
    type HttpMethod, 
    type Subordinate, 
    type SubordinateCreateOptions, 
    type TrustMark, 
    type TrustMarkCreateOptions, 
    type TrustMarks, 
    type TrustMarkType, 
    type TrustMarkTypeCreateOptions, 
    type TrustMarkTypes, 
    type TrustMarkTypeUpdateOptions,
    type TrustMarkUpdateOptions
} from './resources';

type Config = {
    apiUrl: URL;
};

export class AdminSDK {
    readonly #apiUrl: URL;

    constructor(config: Config) {
        const { apiUrl } = config;
        this.#apiUrl = apiUrl;
    }

    /**
     * Create Trust Mark Type.
     */
    async createTrustMarkType(options: TrustMarkTypeCreateOptions): Promise<void> {
        const body = v.safeParse(TrustMarkTypeCreateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError('Failed to validate trustmark type creation options');
        }

        await this.#fetch('POST', '/trustmarktypes', {
            body: JSON.stringify(body.output),
        });
    }

    /**
     * Lists all existing TrustMarkType(s).
     */
    async listTrustMarkTypes(filters?: { limit?: number; offset?: number; }): Promise<TrustMarkTypes> {
        const res = await this.#fetch('GET', '/trustmarktypes', {
            filters,
        });

        const data = v.safeParse(TrustMarkTypesSchema, res);
        if (!data.success) {
            throw new ValidationError('Failed to validate data');
        }

        return data.output;
    }

    /**
     * Gets a TrustMarkType by ID.
     */
    async getTrustMarkTypeById(id: number): Promise<TrustMarkType> {
        const res = await this.#fetch('GET', `/trustmarktypes/${id}`);

        const data = v.safeParse(TrustMarkTypeSchema, res);
        if (!data.success) {
            throw new ValidationError('Failed to validate data');
        }

        return data.output;
    }

    /**
     * Update a TrustMarkType by ID.
     */
    async updateTrustMarkType(id: number, options: TrustMarkTypeUpdateOptions): Promise<TrustMarkType> {
        const body = v.safeParse(TrustMarkTypeUpdateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError('Failed to validate trustmark type update options');
        }

        const res = await this.#fetch('PUT', `/trustmarktypes/${id}`, {
            body: JSON.stringify(body.output)
        });

        const data = v.safeParse(TrustMarkTypeSchema, res);
        if (!data.success) {
            throw new ValidationError('Failed to validate data');
        }

        return data.output;
    }

    /**
     * Create Trust Mark.
     */
    async createTrustMark(options: TrustMarkCreateOptions): Promise<void> {
        const body = v.safeParse(TrustMarkCreateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError('Failed to validate trustmark creation options');
        }

        await this.#fetch('POST', '/trustmarks', {
            body: JSON.stringify(body.output),
        });
    }

    /**
     * Lists all existing TrustMarks.
     */
    async listTrustMarks(filters?: { limit?: number; offset?: number; }): Promise<TrustMarks> {
        const res = await this.#fetch('GET', '/trustmarks', {
            filters,
        });

        const data = v.safeParse(TrustMarksSchema, res);
        if (!data.success) {
            throw new ValidationError('Failed to validate data');
        }

        return data.output;
    }

    /**
     * Returns a list of existing TrustMarks for a given domain.
     */
    async listTrustMarksByDomain(domain: string, filters?: { limit?: number; offset?: number; }): Promise<TrustMarks> {
        const res = await this.#fetch('POST', '/trustmarks/list', {
            filters,
            body: JSON.stringify({ domain })
        });

        const data = v.safeParse(TrustMarksSchema, res);
        if (!data.success) {
            throw new ValidationError('Failed to validate data');
        }

        return data.output;
    }

    /**
     * Renews a TrustMark.
     */
    async renewTrustMark(id: number): Promise<TrustMark> {
        const res = await this.#fetch('POST', `/trustmarks/${id}/renew`);

        const data = v.safeParse(TrustMarkSchema, res);
        if (!data.success) {
            throw new ValidationError('Failed to validate data');
        }

        return data.output;
    }

    /**
     * Create Subordinate.
     */
    async createSubordinate(options: SubordinateCreateOptions): Promise<Subordinate> {
        const body = v.safeParse(SubordinateCreateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError('Failed to validate subordinate creation options');
        }

        const res = await this.#fetch('POST', '/subordinates', {
            body: JSON.stringify(body.output),
        });

        const data = v.safeParse(SubordinateSchema, res);
        if (!data.success) {
            throw new ValidationError('Failed to validate data');
        }

        return data.output;
    }

    /**
     * Update a TrustMark.
     */
    async updateTrustMark(id: number, options: TrustMarkUpdateOptions): Promise<TrustMark> {
        const body = v.safeParse(TrustMarkUpdateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError('Failed to validate trustmark update options');
        }

        const res = await this.#fetch('POST', `/trustmarks/${id}`);

        const data = v.safeParse(TrustMarkSchema, res);
        if (!data.success) {
            throw new ValidationError('Failed to validate data');
        }

        return data.output;
    }

    /**
     * @throws {FetchError}
     */
    async #fetch(method: HttpMethod, path: string|URL, options: RequestInit & { filters?: Record<string, string|number|boolean> } = {}): Promise<unknown> {
        const input = new URL(path, this.#apiUrl);
        input.pathname = `/api/v1/${input.pathname.replace(/^\/|\/$/g, '')}`; // Prepend api base path.

        if (options.filters) {
            const params = new URLSearchParams();
            for (const [key, value] of Object.entries(options.filters)) {
                params.append(key, String(value));
            }

            // We don't want to pass this along to the RequestInit.
            delete options.filters;
        }

        const init: RequestInit = {
            ...options,
            method,
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                ...options.headers,
            },
        };

        try {
            const res = await fetch(input, init);

            if (!res.ok) {
                throw new FetchError({ status: res.status });
            }

            const data = await res.json();
            return data;
        } catch (error) {
            if (error instanceof FetchError) throw error;
            throw new FetchError({
                message: error instanceof Error ? error.message : 'An unexpected error occurred.',
            });
        }

    }
}

