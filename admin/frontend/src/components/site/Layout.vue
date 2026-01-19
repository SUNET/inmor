<script lang="ts">
import { defineComponent } from 'vue';
import Sidebar from './Sidebar.vue';

export default defineComponent({
    name: 'Layout',
	components: { Sidebar },
});
</script>

<template>
  <div class="ir-site">
    <a href="#main-content" class="skip-link">Skip to main content</a>
    <Sidebar />
    <main id="main-content" class="main" role="main">
        <slot></slot>
    </main>
  </div>
</template>

<style>
    .ir-site {
        padding: var(--ir--space--3);
        display: grid;
        grid-template-columns: min-content auto;
        gap: var(--ir--space--5);

        > .main {
            padding-top: var(--ir--space--6);
        }
    }

    .skip-link {
        position: absolute;
        top: -100%;
        left: 0;
        z-index: 9999;
        padding: var(--ir--space--2) var(--ir--space--3);
        background-color: var(--ir--color--primary, #1d4ed8);
        color: white;
        font-weight: 600;
        text-decoration: none;
        border-radius: 0 0 var(--ir--space--1) 0;
        transition: top 0.2s ease;
    }

    .skip-link:focus {
        top: 0;
        outline: 2px solid var(--ir--color--black);
        outline-offset: 2px;
    }
</style>
