<script lang="ts">
import { defineComponent } from 'vue';
import { RouterLink } from 'vue-router';
import Icon, { type Icons } from '../base/Icon.vue';

export default defineComponent({
    name: 'Sidebar',
    components: { RouterLink, Icon },
    data() {
        return {
            nav: [
                {
                    icon: 'documents-outline',
                    label: 'Trustmark types',
                    link: '/trustmark-types',
                },
                {
                    icon: 'document-lock-outline',
                    label: 'Trustmarks',
                    link: '/trustmarks',
                },
                {
                    icon: 'server',
                    label: 'Subordinates',
                    link: '/subordinates',
                },
            ] satisfies Array<{ icon: Icons; label: string; link: string; }>
        };
    },
    async mounted() {
    },
});
</script>

<template>
    <aside class="ir-sidebar" aria-label="Sidebar">
        <header class="header">
            <RouterLink to="/" class="title">Inmor</RouterLink>
        </header>
        <nav class="nav" aria-label="Main navigation">
            <ul class="menu">
                <li v-for="item in nav" class="item">
                    <RouterLink :to="item.link" class="link">
                        <span class="icon"><Icon :icon="item.icon" /></span>
                        {{ item.label }}
                    </RouterLink>
                </li>
            </ul>
        </nav>
    </aside>
</template>

<style>
    .ir-sidebar {
        padding: var(--ir--space--5) var(--ir--space--5) var(--ir--space--3) var(--ir--space--4);
        min-height: calc(100dvh - (var(--ir--space--3) * 2));
        display: grid;
        grid-template-rows: min-content;
        gap: 1rem;
        border-radius: var(--ir--border-radius);
        border: var(--ir--border);
        background-color: #f7f7f7;


        > .header > .title {
            padding: min(.2em, var(--ir--space--1)) min(.4em, var(--ir--space--2));
            margin-bottom: var(--ir--space--2);
            font-family: monospace;
            font-size: var(--ir--font-size--l);
            font-weight: var(--ir--font-weight--bold);
            text-decoration: none;
            border-radius: var(--ir--space--1);
            &:hover {
                background-color: rgba(0, 0, 0, 0.075);
            }
        }

        /* > .nav {} */
        /* > .nav > .menu {} */
        /* > .nav > .menu > .item {} */

        > .nav > .menu > .item > .link {
            padding: min(.2em, var(--ir--space--1)) min(.4em, var(--ir--space--2));
            display: inline-flex;
            align-items: center;
            border-radius: var(--ir--space--1);
            font-size: var(--ir--font-size);
            text-decoration: none;
            white-space: nowrap;

            &:hover {
                background-color: rgba(0, 0, 0, 0.075);
            }
        }

        > .nav > .menu > .item > .link > .icon {
            opacity: .75;
            width: var(--ir--space--4);
        }
    }
</style>
