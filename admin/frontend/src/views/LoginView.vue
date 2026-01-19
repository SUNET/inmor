<script lang="ts">
import { defineComponent } from 'vue';
import Button from '../components/base/Button.vue';

export default defineComponent({
    name: 'LoginView',
    components: { Button },
    data() {
        return {
            checking: true,
        };
    },
    async mounted() {
        // Check if already authenticated
        try {
            const user = await this.$sdk.getCurrentUser();
            if (user) {
                // Already logged in, redirect to home
                this.$router.push('/');
            } else {
                // Not authenticated, show login options
                this.checking = false;
            }
        } catch {
            // Error occurred, show login options
            this.checking = false;
        }
    },
    methods: {
        redirectToLogin() {
            // Redirect to Django allauth login page
            // After successful login (including MFA), Django redirects back to frontend
            const backendUrl = import.meta.env.VITE_API_URL || '';
            window.location.href = `${backendUrl}/accounts/login/?next=${encodeURIComponent(window.location.origin + '/')}`;
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

            <div v-if="checking" class="login-checking">
                Checking authentication...
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

.login-checking {
    text-align: center;
    color: var(--ir--color--gray-500);
    font-size: var(--ir--font-size--s);
}

.login-button {
    width: 100%;
}
</style>
