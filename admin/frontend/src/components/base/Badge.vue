<script lang="ts">
import { defineComponent, type PropType } from 'vue';

export default defineComponent({
    name: 'Badge',
    props: {
        variant: {
            type: String as PropType<'success' | 'danger' | 'warning' | 'info' | 'neutral'>,
            default: 'neutral',
        },
        size: {
            type: String as PropType<'sm' | 'md'>,
            default: 'md',
        },
    },
    computed: {
        classes(): string[] {
            return [
                'ir-badge',
                `ir-badge--${this.variant}`,
                `ir-badge--${this.size}`,
            ];
        },
    },
});
</script>

<template>
    <span :class="classes" role="status">
        <slot></slot>
    </span>
</template>

<style scoped>
.ir-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 9999px;
    font-weight: 500;
    white-space: nowrap;
}

/* Sizes */
.ir-badge--sm {
    padding: 2px 8px;
    font-size: 0.75rem;
}

.ir-badge--md {
    padding: 4px 12px;
    font-size: 0.875rem;
}

/* Variants */
.ir-badge--success {
    background-color: #dcfce7;
    color: #166534;
}

.ir-badge--danger {
    background-color: #fee2e2;
    color: #991b1b;
}

.ir-badge--warning {
    background-color: #fef3c7;
    color: #92400e;
}

.ir-badge--info {
    background-color: #dbeafe;
    color: #1e40af;
}

.ir-badge--neutral {
    background-color: #f3f4f6;
    color: #4b5563;
}
</style>
