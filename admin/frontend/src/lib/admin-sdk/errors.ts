export class AdminSDKError extends Error {};

export class ValidationError extends AdminSDKError {};


type FetchErrorProps = {
    status?: number;
    message?: string;
};
export type FetchErrorType = 'client_error' | 'auth_error' | 'server_error' | 'unknown_error';
export class FetchError extends AdminSDKError {
    readonly status?: number;
    readonly type: FetchErrorType;
    readonly message: string;

    constructor({ status, message }: FetchErrorProps) {
        const errors: Record<number, { type: FetchErrorType; message: string }> = {
            400: { type: 'client_error', message: 'Request is invalid.' },
            405: { type: 'client_error', message: 'Method not allowed.' },
            401: { type: 'auth_error',   message: 'Authorization failed.' },
            403: { type: 'auth_error',   message: 'Access is forbidden.' },
            500: { type: 'server_error', message: 'Internal server error.' },
            501: { type: 'server_error', message: 'Requested functionality is not supported.' },
            502: { type: 'server_error', message: 'Invalid response received from upstream server.' },
            503: { type: 'server_error', message: 'Service unavailable.' },
            504: { type: 'server_error', message: 'Gateway timeout: server did not respond in time.' },
        };

        const error = status && errors[status] || {
            type: 'unknown_error',
            message: 'An unexpected error occurred.'
        };

        if (message) {
            error.message = message;
        }


        super(`Fetch error: ${error.message}`);
        this.status = status;
        this.type = error.type;
        this.message = error.message;
    }
}
