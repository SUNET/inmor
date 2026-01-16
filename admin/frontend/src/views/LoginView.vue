<script lang="ts">
import { defineComponent } from 'vue';
import Button from '../components/base/Button.vue';
import Input from '../components/base/Input.vue';

export default defineComponent({
    name: 'LoginView',
    components: { Button, Input },
    data() {
        return {
            username: '',
            password: '',
            error: null as string | null,
            loading: false,
        };
    },
    methods: {
        async handleLogin() {
            this.loading = true;
            this.error = null;
            try {
                await this.$sdk.login(this.username, this.password);
                // Reset auth state so router guard re-checks authentication
                this.$resetAuth();
                this.$router.push('/');
            } catch (e: any) {
                this.error = e.message || 'Invalid username or password';
            } finally {
                this.loading = false;
            }
        },
    },
});
</script>

<template>
    <div class="login-view">
        <div class="login-card">
            <header class="login-header">
                <div class="login-logo">SUNET</div>
                <h1 class="login-title">Inmor</h1>
                <p class="login-subtitle">Trust Anchor Admin</p>
            </header>

            <form @submit.prevent="handleLogin" class="login-form">
                <Input
                    v-model="username"
                    label="Username"
                    type="text"
                    placeholder="Enter your username"
                    required
                    :disabled="loading"
                />
                <Input
                    v-model="password"
                    label="Password"
                    type="password"
                    placeholder="Enter your password"
                    required
                    :disabled="loading"
                />
                <p v-if="error" class="login-error">{{ error }}</p>
                <Button type="submit" :loading="loading" class="login-button">
                    Sign In
                </Button>
            </form>
        </div>
    </div>
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

.login-form {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--3);
}

.login-error {
    color: var(--ir--color--danger);
    font-size: var(--ir--font-size--s);
    text-align: center;
    margin: 0;
    padding: var(--ir--space--2);
    background-color: var(--ir--color--danger-bg);
    border-radius: var(--ir--space--1);
}

.login-button {
    width: 100%;
    margin-top: var(--ir--space--2);
}
</style>
