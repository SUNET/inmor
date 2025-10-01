<script lang="ts">
import { defineComponent, type FunctionalComponent } from 'vue';
import { RouterLink } from 'vue-router';
import { FileLock2, Files, Server } from 'lucide-vue-next';

export default defineComponent({
    name: 'Sidebar',
    components: { RouterLink },
    data() {
        return {
            nav: [
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
                        <span class="icon"><component :is="item.icon"></component></span>
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
            font-size: var(--ir--font-size--m);
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
