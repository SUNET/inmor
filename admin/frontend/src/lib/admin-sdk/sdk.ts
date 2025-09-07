import * as v from 'valibot';
import { TrustMarkTypesSchema, type HttpMethod, type TrustMarkTypes } from './resources';
import { FetchError, ValidationError } from './errors';

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
     * List of trust marks
     */
    async getTrustMarkTypes(): Promise<TrustMarkTypes> {
        const res = await this.#fetch('GET', '/trust_mark_type/list');

        const data = v.safeParse(TrustMarkTypesSchema, res);
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

