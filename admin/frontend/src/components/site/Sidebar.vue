<script lang="ts">
import { defineComponent, type FunctionalComponent } from 'vue';
import { RouterLink } from 'vue-router';
import { Home, FileLock2, Files, Server, ServerCog, RefreshCw, LogOut } from 'lucide-vue-next';
import packageJson from '../../../package.json';
import sunetLogo from '../../assets/sunet-logo.svg';

export default defineComponent({
    name: 'Sidebar',
    components: { RouterLink, LogOut, ServerCog, RefreshCw },
    data() {
        return {
            version: packageJson.version || '0.2.0',
            sunetLogo,
            regenerating: false,
            regenerateMessage: '',
            regenerateSuccess: false,
            nav: [
                {
                    icon: Home,
                    label: 'Home',
                    link: '/',
                },
                {
                    icon: FileLock2,
                    label: 'Trust mark types',
                    link: '/trustmark-types',
                },
                {
                    icon: Files,
                    label: 'Trust marks',
                    link: '/trustmarks',
                },
                {
                    icon: Server,
                    label: 'Subordinates',
                    link: '/subordinates',
                },
            ] satisfies Array<{ icon: FunctionalComponent; label: string; link: string; }>
        };
    },
    methods: {
        async handleLogout() {
            try {
                await this.$sdk.logout();
                this.$router.push('/login');
            } catch (e) {
                console.error('Logout failed:', e);
            }
        },
        async handleRegenerateEntity() {
            if (this.regenerating) return;

            this.regenerating = true;
            this.regenerateMessage = '';

            try {
                await Promise.all([
                    this.$sdk.regenerateServerEntity(),
                    this.$sdk.syncHistoricalKeys(),
                ]);
                this.regenerateSuccess = true;
                this.regenerateMessage = 'Configuration updated';
                // Clear message after 3 seconds
                setTimeout(() => {
                    this.regenerateMessage = '';
                }, 3000);
            } catch (e) {
                this.regenerateSuccess = false;
                this.regenerateMessage = e instanceof Error ? e.message : 'Failed to update';
                setTimeout(() => {
                    this.regenerateMessage = '';
                }, 5000);
            } finally {
                this.regenerating = false;
            }
        },
    },
});
</script>

<template>
    <aside class="ir-sidebar" aria-label="Sidebar">
        <header class="header">
            <img :src="sunetLogo" alt="SUNET" class="logo-img" />
            <RouterLink to="/" class="title">Inmor</RouterLink>
        </header>
        <nav class="nav" aria-label="Main navigation">
            <ul class="menu">
                <li v-for="item in nav" :key="item.link" class="item">
                    <RouterLink :to="item.link" class="link">
                        <component :is="item.icon" :size="18" />
                        {{ item.label }}
                    </RouterLink>
                </li>
            </ul>
        </nav>
        <div class="server-section">
            <button
                type="button"
                class="server-btn"
                :class="{ 'server-btn--loading': regenerating }"
                :disabled="regenerating"
                @click="handleRegenerateEntity"
            >
                <RefreshCw :size="16" :class="{ 'spin': regenerating }" />
                {{ regenerating ? 'Regenerating...' : 'Entity Configuration' }}
            </button>
            <div v-if="regenerateMessage" class="server-message" :class="{ 'server-message--success': regenerateSuccess, 'server-message--error': !regenerateSuccess }">
                {{ regenerateMessage }}
            </div>
        </div>
        <footer class="footer">
            <div class="version">v{{ version }}</div>
            <button type="button" class="logout-btn" @click="handleLogout">
                <LogOut :size="18" />
                Logout
            </button>
        </footer>
    </aside>
</template>

<style scoped>
.ir-sidebar {
    padding: var(--ir--space--4);
    min-height: calc(100dvh - (var(--ir--space--3) * 2));
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--4);
    border-radius: var(--ir--border-radius);
    border: var(--ir--border);
    background-color: #f7f7f7;
    min-width: 220px;
}

.header {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: var(--ir--space--3);
    padding: var(--ir--space--2);
}

.logo-img {
    height: 40px;
    width: auto;
}

.title {
    font-size: 1.5rem;
    font-weight: var(--ir--font-weight--bold);
    text-decoration: none;
    color: var(--ir--color--black);
}

.title:hover {
    opacity: 0.8;
}

.nav {
    flex: 1;
}

.menu {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--1);
}

.item .link {
    padding: var(--ir--space--2);
    display: flex;
    align-items: center;
    gap: var(--ir--space--2);
    border-radius: var(--ir--space--1);
    font-size: var(--ir--font-size--s);
    text-decoration: none;
    white-space: nowrap;
    color: var(--ir--color--gray-700);
    transition: background-color 0.15s ease;
}

.item .link:hover {
    background-color: rgba(0, 0, 0, 0.05);
}

.item .link.router-link-active {
    background-color: rgba(37, 99, 235, 0.1);
    color: var(--ir--color--primary);
}

.footer {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--2);
    padding-top: var(--ir--space--3);
    border-top: var(--ir--border);
}

.version {
    font-size: var(--ir--font-size--xs);
    color: var(--ir--color--gray-500);
    text-align: center;
}

.logout-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--ir--space--2);
    padding: var(--ir--space--2);
    border: none;
    border-radius: var(--ir--space--1);
    background-color: transparent;
    color: var(--ir--color--gray-600);
    font-family: var(--ir--font-family);
    font-size: var(--ir--font-size--s);
    cursor: pointer;
    transition: background-color 0.15s ease, color 0.15s ease;
}

.logout-btn:hover {
    background-color: var(--ir--color--danger-bg);
    color: var(--ir--color--danger);
}

.server-section {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--1);
}

.server-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--ir--space--2);
    padding: var(--ir--space--2);
    border: 1px solid #e5e7eb;
    border-radius: var(--ir--space--1);
    background-color: white;
    color: var(--ir--color--gray-700);
    font-family: var(--ir--font-family);
    font-size: var(--ir--font-size--s);
    cursor: pointer;
    transition: background-color 0.15s ease, border-color 0.15s ease;
}

.server-btn:hover:not(:disabled) {
    background-color: #f3f4f6;
    border-color: #d1d5db;
}

.server-btn:disabled {
    opacity: 0.7;
    cursor: not-allowed;
}

.server-btn--loading {
    color: var(--ir--color--primary);
}

.server-message {
    font-size: var(--ir--font-size--xs);
    text-align: center;
    padding: var(--ir--space--1);
    border-radius: 4px;
}

.server-message--success {
    color: #059669;
    background-color: #ecfdf5;
}

.server-message--error {
    color: var(--ir--color--danger);
    background-color: var(--ir--color--danger-bg);
}

@keyframes spin {
    from {
        transform: rotate(0deg);
    }
    to {
        transform: rotate(360deg);
    }
}

.spin {
    animation: spin 1s linear infinite;
}
</style>
