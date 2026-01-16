import type { AdminSDK } from '../lib/admin-sdk';
import type { Router } from 'vue-router';

declare module 'vue' {
    interface ComponentCustomProperties {
        $sdk: AdminSDK;
        $router: Router;
        $resetAuth: () => void;
    }
}

export {};
