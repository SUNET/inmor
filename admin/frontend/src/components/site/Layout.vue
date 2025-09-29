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
    <Sidebar />
    <main class="main">
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
</style>
