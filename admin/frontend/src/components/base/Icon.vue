<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import serverOutline from '../../../node_modules/ionicons/dist/svg/server-outline.svg?raw';
import documentLockOutline from '../../../node_modules/ionicons/dist/svg/document-lock-outline.svg?raw';
import documentsOutline from '../../../node_modules/ionicons/dist/svg/documents-outline.svg?raw';

export type Icons = keyof typeof icons;

const icons = {
    'documents-outline': documentsOutline,
    'document-lock-outline': documentLockOutline,
    'server': serverOutline
} satisfies Record<string, string>;

export default defineComponent({
    name: 'Icon',
    props: {
        icon: {
            type: String as PropType<Icons>,
            required: true,
        },
    },
    data() {
        return {
            icons,
        }
    }
});
</script>

<template>
    <span class="icon" v-html="icons[icon]"></span>
</template>


<style>
    .icon {
        > svg {
            box-sizing: content-box;
            display: inline-block;
            height: 1em;
            overflow: visible;
            vertical-align: -0.125em;
            width: 1.25em;
        }
    }
</style>
