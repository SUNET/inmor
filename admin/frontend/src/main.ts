import { createApp, nextTick } from 'vue'
import { createRouter, createWebHistory } from 'vue-router';
import { AdminSDK } from './lib/admin-sdk';
import './styles/reset.css';
import './styles/variables.css';
import './styles/global.css';
import { routes } from './routes';
import App from './App.vue'

const app = createApp(App);

const sdk = new AdminSDK({
    apiUrl: new URL(__API_URL__ || window.location.origin),
});

app.config.globalProperties.$sdk = sdk;

const router = createRouter({
    history: createWebHistory(),
    routes,
});

// Create a live region for route announcements
const announcer = document.createElement('div');
announcer.setAttribute('role', 'status');
announcer.setAttribute('aria-live', 'polite');
announcer.setAttribute('aria-atomic', 'true');
announcer.className = 'sr-only';
document.body.appendChild(announcer);

// Authentication guard
let isAuthenticated: boolean | null = null;
let csrfInitialized = false;

router.beforeEach(async (to, _from, next) => {
    // Initialize CSRF token on first navigation
    if (!csrfInitialized) {
        await sdk.initCSRF();
        csrfInitialized = true;
    }

    // Check if route requires authentication
    const requiresAuth = to.meta.requiresAuth !== false;

    // Check authentication status if we haven't yet
    if (isAuthenticated === null) {
        try {
            const user = await sdk.getCurrentUser();
            isAuthenticated = user !== null;
        } catch {
            isAuthenticated = false;
        }
    }

    if (requiresAuth && !isAuthenticated) {
        // Redirect to login if not authenticated
        next({ name: 'login', query: { redirect: to.fullPath } });
    } else if (to.name === 'login' && isAuthenticated) {
        // Redirect to home if already authenticated
        next({ name: 'home' });
    } else {
        next();
    }
});

// Reset auth state on logout (will be checked again on next navigation)
app.config.globalProperties.$resetAuth = () => {
    isAuthenticated = null;
};

// Route change announcements and document title updates
router.afterEach(async (to) => {
    const title = to.meta.title as string || 'Inmor';
    const fullTitle = `${title} - Inmor Admin`;

    // Update document title
    document.title = fullTitle;

    // Announce route change to screen readers
    await nextTick();
    announcer.textContent = `Navigated to ${title}`;

    // Move focus to main content heading after short delay
    setTimeout(() => {
        const mainContent = document.getElementById('main-content');
        const heading = mainContent?.querySelector('h1');
        if (heading && heading instanceof HTMLElement) {
            heading.setAttribute('tabindex', '-1');
            heading.focus();
            // Remove tabindex after focus to avoid tab stops
            heading.addEventListener('blur', () => {
                heading.removeAttribute('tabindex');
            }, { once: true });
        }
    }, 100);
});

app.use(router);
app.mount('#app');
