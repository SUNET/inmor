import * as v from 'valibot';
import { TrustMarkTypesSchema, type HttpMethod, type TrustMarkTypes } from './resources';
import { ValidationError } from './errors';

type Config = {
    apiUrl: URL;
};

export class AdminSDK {
    #apiUrl: URL;

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

    async #fetch(method: HttpMethod, path: string|URL, options: RequestInit = {}): Promise<any> {
        const input = new URL(path, this.#apiUrl);
        input.pathname = `/api/v1/${input.pathname.replace(/^\/|\/$/g, '')}`; // Prepend api base path.

        const init: RequestInit = {
            ...options,
            method,
            headers: {
                'Accept': 'application/json',
                ...options.headers,
            },
        };

        const res = await fetch(input, init);
        
        // ..validation & error handling

        const data = await res.json();

        return data;
    }
}

