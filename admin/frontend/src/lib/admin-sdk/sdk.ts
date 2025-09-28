import * as v from 'valibot';
import { FetchError, ValidationError } from './errors';
import { 
    TrustMarkTypeCreationOptionsSchema, 
    TrustMarkTypeSchema, 
    TrustMarkTypesSchema, 
    type HttpMethod, 
    type TrustMarkType, 
    type TrustMarkTypeCreationOptions, 
    type TrustMarkTypes 
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
    async createTrustMarkType(options: TrustMarkTypeCreationOptions): Promise<void> {
        const body = v.safeParse(TrustMarkTypeCreationOptionsSchema, options);
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
    async listTrustMarkTypes(): Promise<TrustMarkTypes> {
        const res = await this.#fetch('GET', '/trustmarktypes');

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
     * @throws {FetchError}
     */
    async #fetch(method: HttpMethod, path: string|URL, options: RequestInit = {}): Promise<unknown> {
        const input = new URL(path, this.#apiUrl);
        input.pathname = `/api/v1/${input.pathname.replace(/^\/|\/$/g, '')}`; // Prepend api base path.

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

