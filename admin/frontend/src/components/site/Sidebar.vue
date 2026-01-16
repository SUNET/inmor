<script lang="ts">
import { defineComponent, type FunctionalComponent } from 'vue';
import { RouterLink } from 'vue-router';
import { Home, FileLock2, Files, Server, LogOut } from 'lucide-vue-next';
import packageJson from '../../../package.json';
import sunetLogo from '../../assets/sunet-logo.svg';

export default defineComponent({
    name: 'Sidebar',
    components: { RouterLink, LogOut },
    data() {
        return {
            version: packageJson.version || '0.2.0',
            sunetLogo,
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
    },
});
</script>

<template>
    <aside class="ir-sidebar" aria-label="Sidebar">
        <header class="header">
            <div class="logo">
                <img :src="sunetLogo" alt="SUNET" class="logo-img" />
            </div>
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
    flex-direction: column;
    gap: var(--ir--space--2);
}

.logo {
    display: flex;
    align-items: center;
    gap: var(--ir--space--2);
    padding: var(--ir--space--2);
}

.logo-img {
    height: 48px;
    width: auto;
}

.logo-text {
    font-size: var(--ir--font-size--s);
    font-weight: 600;
    color: #6b7280;
    letter-spacing: 0.05em;
}

.title {
    padding: var(--ir--space--2);
    font-size: var(--ir--font-size--m);
    font-weight: var(--ir--font-weight--bold);
    text-decoration: none;
    border-radius: var(--ir--space--1);
    color: var(--ir--color--black);
}

.title:hover {
    background-color: rgba(0, 0, 0, 0.05);
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
</style>
