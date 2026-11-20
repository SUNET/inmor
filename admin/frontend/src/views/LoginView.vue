<script lang="ts">
import { defineComponent } from 'vue';
import Button from '../components/base/Button.vue';

export default defineComponent({
    name: 'LoginView',
    components: { Button },
    computed: {
        /** Browser authentication always runs through Django allauth. */
        accountsUrl(): string {
            return `${import.meta.env.VITE_API_URL || ''}/accounts`;
        },
    },
    methods: {
        redirectToLogin() {
            // Redirect to Django allauth login page
            // After successful login (including MFA), Django redirects back to frontend
            window.location.href = `${this.accountsUrl}/login/?next=${encodeURIComponent(window.location.origin + '/')}`;
        },
    },
});
</script>

<template>
    <main class="login-view" role="main">
        <div class="login-card">
            <header class="login-header">
                <div class="login-logo">SUNET</div>
                <h1 class="login-title">Inmor</h1>
                <p class="login-subtitle">Trust Anchor Admin</p>
            </header>

            <div v-if="$route.name === 'access-denied'" class="login-content">
                <p class="login-message" role="alert">
                    Your account does not have permission to manage this federation.
                    Ask a federation administrator for access.
                </p>
                <RouterLink to="/">Check access again</RouterLink> · <a :href="`${accountsUrl}/logout/`">Sign out</a>
            </div>

            <div v-else-if="$route.name === 'service-unavailable'" class="login-content">
                <p class="login-message" role="alert">Unable to check your access. The admin API is unavailable.</p>
                <RouterLink to="/">Try again</RouterLink>
            </div>

            <div v-else class="login-content">
                <p class="login-message">
                    Sign in to access the Trust Anchor administration panel.
                </p>
                <Button @click="redirectToLogin" class="login-button">
                    Sign In
                </Button>
            </div>
        </div>
    </main>
</template>

<style scoped>
.login-view {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: var(--ir--color--gray-50);
    padding: var(--ir--space--4);
}

.login-card {
    width: 100%;
    max-width: 400px;
    background-color: white;
    border-radius: var(--ir--space--3);
    box-shadow: var(--ir--box-shadow);
    padding: var(--ir--space--5);
}

.login-header {
    text-align: center;
    margin-bottom: var(--ir--space--5);
}

.login-logo {
    font-size: var(--ir--font-size--s);
    font-weight: 600;
    color: var(--ir--color--gray-500);
    letter-spacing: 0.1em;
    margin-bottom: var(--ir--space--2);
}

.login-title {
    font-size: var(--ir--font-size--l);
    font-weight: var(--ir--font-weight--bold);
    color: var(--ir--color--gray-900);
    margin: 0;
}

.login-subtitle {
    font-size: var(--ir--font-size--s);
    color: var(--ir--color--gray-500);
    margin: var(--ir--space--1) 0 0;
}

.login-content {
    text-align: center;
}

.login-message {
    color: var(--ir--color--gray-600);
    font-size: var(--ir--font-size--s);
    margin-bottom: var(--ir--space--4);
}

.login-button {
    width: 100%;
}
</style>
