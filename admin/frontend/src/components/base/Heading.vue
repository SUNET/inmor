<script lang="ts">
import { defineComponent, type PropType } from 'vue';

export default defineComponent({
    name: 'Heading',
    props: {
        level: {
            type: String as PropType<'h1'|'h2'|'h3'|'h4'>,
            required: true,
        },
        id: {
            type: String,
            default: undefined,
        }
    }
});
</script>

<template>
    <component :is="level" :id="id" :class="['heading', `-${level}`]">
        <slot></slot>
    </component>
</template>

<style>
    .heading {

        &.-h1 {
            font-size: var(--ir--font-size--l);
        }

        &.-h2 {
            font-size: var(--ir--font-size--m);
        }

        &.-h3 {
            font-size: var(--ir--font-size--m);
        }

        &.-h4 {
            font-size: var(--ir--font-size);
        }
    }
</style>
