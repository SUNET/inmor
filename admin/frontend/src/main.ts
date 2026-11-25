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

// Recheck the session on navigation so permission changes take effect in an open tab.
router.beforeEach(async to => {
    if (to.name === 'access-denied' || to.name === 'service-unavailable') return;
    try {
        const user = await sdk.getCurrentUser();
        if (!user && to.meta.requiresAuth !== false) {
            return { name: 'login', query: { redirect: to.fullPath } };
        }
        if (user && !user.can_manage_federation) return { name: 'access-denied' };
        if (user && to.name === 'login') return { name: 'home' };
    } catch {
        return { name: 'service-unavailable' };
    }
});

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
