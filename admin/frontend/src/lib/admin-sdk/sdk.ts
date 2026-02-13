import { safeParse } from 'valibot';
import { FetchError, ValidationError } from './errors';
import {
    EntityConfigSchema,
    SubordinateCreateOptionsSchema,
    SubordinateSchema,
    SubordinatesSchema,
    SubordinateUpdateOptionsSchema,
    TrustMarkCreateOptionsSchema,
    TrustMarkSchema,
    TrustMarksSchema,
    TrustMarkTypeCreateOptionsSchema,
    TrustMarkTypeSchema,
    TrustMarkTypesSchema,
    TrustMarkTypeUpdateOptionsSchema,
    TrustMarkUpdateOptionsSchema,
    type EntityConfig,
    type HttpMethod,
    type Subordinate,
    type SubordinateCreateOptions,
    type Subordinates,
    type SubordinateUpdateOptions,
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

export type User = {
    id: number;
    username: string;
    email: string;
    is_staff: boolean;
    is_superuser: boolean;
};

export class AdminSDK {
    readonly #apiUrl: URL;
    #csrfInitialized = false;

    constructor(config: Config) {
        const { apiUrl } = config;
        this.#apiUrl = apiUrl;
    }

    /**
     * Initialize CSRF token by fetching the csrf endpoint.
     * This sets the csrftoken cookie needed for subsequent requests.
     */
    async initCSRF(): Promise<void> {
        if (this.#csrfInitialized) return;

        const url = new URL('/api/v1/auth/csrf', this.#apiUrl);
        await fetch(url, {
            method: 'GET',
            credentials: 'include',
        });
        this.#csrfInitialized = true;
    }

    /**
     * Get CSRF token from cookies.
     */
    #getCSRFToken(): string | null {
        const match = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='));
        return match ? match.split('=')[1] : null;
    }

    /**
     * Login with username and password.
     */
    async login(username: string, password: string): Promise<User> {
        const res = await this.#fetch('POST', '/auth/login', {
            body: JSON.stringify({ username, password }),
        });
        return res as User;
    }

    /**
     * Logout current user.
     */
    async logout(): Promise<void> {
        await this.#fetch('POST', '/auth/logout');
    }

    /**
     * Get current authenticated user.
     * Returns null if not authenticated.
     */
    async getCurrentUser(): Promise<User | null> {
        try {
            const res = await this.#fetch('GET', '/auth/me');
            return res as User;
        } catch (e) {
            if (e instanceof FetchError && e.status === 401) {
                return null;
            }
            throw e;
        }
    }

    /**
     * Get CSRF token for forms.
     */
    async getCSRFToken(): Promise<string> {
        const res = await this.#fetch('GET', '/auth/csrf') as { csrf_token: string };
        return res.csrf_token;
    }

    /**
     * Create Trust Mark Type.
     */
    async createTrustMarkType(options: TrustMarkTypeCreateOptions): Promise<TrustMarkType> {
        const body = safeParse(TrustMarkTypeCreateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError({
                message: 'Failed to validate trustmark type creation options',
                issues: body.issues,
            });
        }

        const res = await this.#fetch('POST', '/trustmarktypes', {
            body: JSON.stringify(body.output),
        });

        const data = safeParse(TrustMarkTypeSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: 'Invalid response when creating trustmark type',
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Lists all existing TrustMarkType(s).
     */
    async listTrustMarkTypes(filters?: { limit?: number; offset?: number; }): Promise<TrustMarkTypes> {
        const res = await this.#fetch('GET', '/trustmarktypes', {
            filters,
        });

        const data = safeParse(TrustMarkTypesSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: 'Invalid response when listing trustmark types',
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Gets a TrustMarkType by ID.
     */
    async getTrustMarkTypeById(id: number): Promise<TrustMarkType> {
        const res = await this.#fetch('GET', `/trustmarktypes/${id}`);

        const data = safeParse(TrustMarkTypeSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: `Invalid reponse when getting trustmark type by id ${id}`,
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Update a TrustMarkType by ID.
     */
    async updateTrustMarkType(id: number, options: TrustMarkTypeUpdateOptions): Promise<TrustMarkType> {
        const body = safeParse(TrustMarkTypeUpdateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError({
                message: 'Failed to validate trustmark type update options',
                issues: body.issues,
            });
        }

        const res = await this.#fetch('PUT', `/trustmarktypes/${id}`, {
            body: JSON.stringify(body.output)
        });

        const data = safeParse(TrustMarkTypeSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: `Invalid response when updating trustmark with id ${id}`,
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Create Trust Mark.
     */
    async createTrustMark(options: TrustMarkCreateOptions): Promise<TrustMark> {
        const body = safeParse(TrustMarkCreateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError({
                message: 'Failed to validate trustmark creation options',
                issues: body.issues,
            });
        }

        const res = await this.#fetch('POST', '/trustmarks', {
            body: JSON.stringify(body.output),
        });

        const data = safeParse(TrustMarkSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: 'Invalid response when creating trustmark',
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Lists all existing TrustMarks.
     */
    async listTrustMarks(filters?: { limit?: number; offset?: number; }): Promise<TrustMarks> {
        const res = await this.#fetch('GET', '/trustmarks', {
            filters,
        });

        const data = safeParse(TrustMarksSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: 'Invalid response when listing trustmarks',
                issues: data.issues,
            });
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

        const data = safeParse(TrustMarksSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: `Invalid reponse when listing trustmarks by domain ${domain}`,
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Renews a TrustMark.
     */
    async renewTrustMark(id: number): Promise<TrustMark> {
        const res = await this.#fetch('POST', `/trustmarks/${id}/renew`);

        const data = safeParse(TrustMarkSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: `Invalid response when renewing trustmark with id ${id}`,
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Update a TrustMark.
     */
    async updateTrustMark(id: number, options: TrustMarkUpdateOptions): Promise<TrustMark> {
        const body = safeParse(TrustMarkUpdateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError({
                message: 'Failed to validate trustmark update options',
                issues: body.issues,
            });
        }

        const res = await this.#fetch('PUT', `/trustmarks/${id}`, {
            body: JSON.stringify(body.output),
        });

        const data = safeParse(TrustMarkSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: `Invalid response when updating trust mark with id ${id}`,
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Create Subordinate.
     */
    async createSubordinate(options: SubordinateCreateOptions): Promise<Subordinate> {
        const body = safeParse(SubordinateCreateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError({
                message: 'Failed to validate subordinate creation options',
                issues: body.issues,
            });
        }

        const res = await this.#fetch('POST', '/subordinates', {
            body: JSON.stringify(body.output),
        });

        const data = safeParse(SubordinateSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: 'Invalid response when creating subordinate',
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Renew a subordinate by re-fetching and verifying its entity configuration.
     */
    async renewSubordinate(id: number): Promise<Subordinate> {
        const res = await this.#fetch('POST', `/subordinates/${id}/renew`);

        const data = safeParse(SubordinateSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: 'Invalid response when renewing subordinate',
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Lists all existing subordinates.
     */
    async listSubordinates(filters?: { limit?: number; offset?: number; }): Promise<Subordinates> {
        const res = await this.#fetch('GET', '/subordinates', {
            filters,
        });

        const data = safeParse(SubordinatesSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: 'Invalid response when listing subordinates',
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Gets a subordinate by ID.
     */
    async getSubordinateById(id: number): Promise<Subordinate> {
        const res = await this.#fetch('GET', `/subordinates/${id}`);

        const data = safeParse(SubordinateSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: `Invalid response when getting subordinate by id ${id}`,
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Update a Subordinate.
     */
    async updateSubordinate(id: number, options: SubordinateUpdateOptions): Promise<Subordinate> {
        const body = safeParse(SubordinateUpdateOptionsSchema, options);
        if (!body.success) {
            throw new ValidationError({
                message: 'Failed to validate subordinate update options',
                issues: body.issues,
            });
        }

        const res = await this.#fetch('POST', `/subordinates/${id}`, {
            body: JSON.stringify(body.output),
        });

        const data = safeParse(SubordinateSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: `Invalid response when updating subordinate with id ${id}`,
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Fetch and self-validate entity configuration from a URL.
     * Returns the verified metadata and JWKS.
     */
    async fetchEntityConfig(url: string): Promise<EntityConfig> {
        const res = await this.#fetch('POST', '/subordinates/fetch-config', {
            body: JSON.stringify({ url }),
        });

        const data = safeParse(EntityConfigSchema, res);
        if (!data.success) {
            throw new ValidationError({
                message: 'Invalid response when fetching entity configuration',
                issues: data.issues,
            });
        }

        return data.output;
    }

    /**
     * Regenerate the server's entity configuration.
     * This updates the entity statement in Redis.
     */
    async regenerateServerEntity(): Promise<{ entity_statement: string }> {
        const res = await this.#fetch('POST', '/server/entity');
        return res as { entity_statement: string };
    }

    /**
     * Sync historical keys to Redis.
     */
    async syncHistoricalKeys(): Promise<void> {
        await this.#fetch('POST', '/server/historical_keys');
    }

    /**
     * @throws {FetchError}
     */
    async #fetch(method: HttpMethod, path: string|URL, options: RequestInit & { filters?: Record<string, string|number|boolean> } = {}): Promise<unknown> {
        const input = new URL(path, this.#apiUrl);
        input.pathname = `/api/v1/${input.pathname.replace(/^\/|\/$/g, '')}`; // Prepend api base path.

        if (options.filters) {
            for (const [key, value] of Object.entries(options.filters)) {
                input.searchParams.append(key, String(value));
            }

            // We don't want to pass this along to the RequestInit.
            delete options.filters;
        }

        // Build headers with CSRF token for non-GET requests
        const headers: Record<string, string> = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            ...options.headers as Record<string, string>,
        };

        // Include CSRF token for state-changing requests
        if (method !== 'GET') {
            const csrfToken = this.#getCSRFToken();
            if (csrfToken) {
                headers['X-CSRFToken'] = csrfToken;
            }
        }

        const init: RequestInit = {
            ...options,
            method,
            credentials: 'include', // Include cookies for session auth
            headers,
        };

        try {
            const res = await fetch(input, init);

            // Handle empty responses (e.g., logout)
            const text = await res.text();
            const data = text ? JSON.parse(text) : {};

            if (!res.ok) {
                const message = 'message' in data && typeof data.message === 'string' ? data.message : undefined;
                throw new FetchError({ status: res.status, message: message });
            }

            return data;
        } catch (error) {
            if (error instanceof FetchError) throw error;
            throw new FetchError({
                message: error instanceof Error ? error.message : 'An unexpected error occurred.',
            });
        }

    }
}

