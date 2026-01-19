<script lang="ts">
import { defineComponent, type PropType } from 'vue';

export default defineComponent({
    name: 'Button',
    props: {
        variant: {
            type: String as PropType<'primary' | 'secondary' | 'danger' | 'ghost'>,
            default: 'primary',
        },
        size: {
            type: String as PropType<'sm' | 'md' | 'lg'>,
            default: 'md',
        },
        loading: {
            type: Boolean,
            default: false,
        },
        disabled: {
            type: Boolean,
            default: false,
        },
        type: {
            type: String as PropType<'button' | 'submit' | 'reset'>,
            default: 'button',
        },
    },
    emits: ['click'],
    computed: {
        classes(): string[] {
            return [
                'ir-button',
                `ir-button--${this.variant}`,
                `ir-button--${this.size}`,
                this.loading ? 'ir-button--loading' : '',
            ].filter(Boolean);
        },
    },
});
</script>

<template>
    <button
        :type="type"
        :class="classes"
        :disabled="disabled || loading"
        :aria-busy="loading ? 'true' : undefined"
        @click="$emit('click', $event)"
    >
        <span v-if="loading" class="ir-button__spinner" aria-hidden="true"></span>
        <span :class="{ 'ir-button__content--hidden': loading }">
            <slot></slot>
        </span>
        <span v-if="loading" class="sr-only">Loading</span>
    </button>
</template>

<style scoped>
.ir-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--ir--space--2);
    border: none;
    border-radius: var(--ir--space--1);
    font-family: var(--ir--font-family);
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.15s ease, opacity 0.15s ease;
    position: relative;
}

.ir-button:disabled {
    cursor: not-allowed;
    opacity: 0.6;
}

.ir-button:focus-visible {
    outline: 2px solid var(--ir--color--primary, #1d4ed8);
    outline-offset: 2px;
}

/* Sizes */
.ir-button--sm {
    padding: var(--ir--space--1) var(--ir--space--2);
    font-size: var(--ir--font-size--xs);
}

.ir-button--md {
    padding: var(--ir--space--2) var(--ir--space--3);
    font-size: var(--ir--font-size--s);
}

.ir-button--lg {
    padding: var(--ir--space--3) var(--ir--space--4);
    font-size: var(--ir--font-size);
}

/* Variants */
.ir-button--primary {
    background-color: var(--ir--color--primary);
    color: white;
}

.ir-button--primary:hover:not(:disabled) {
    background-color: #1d4ed8;
}

.ir-button--secondary {
    background-color: #e5e7eb;
    color: #374151;
}

.ir-button--secondary:hover:not(:disabled) {
    background-color: #d1d5db;
}

.ir-button--danger {
    background-color: #ef4444;
    color: white;
}

.ir-button--danger:hover:not(:disabled) {
    background-color: #dc2626;
}

.ir-button--ghost {
    background-color: transparent;
    color: #374151;
}

.ir-button--ghost:hover:not(:disabled) {
    background-color: rgba(0, 0, 0, 0.05);
}

/* Loading state */
.ir-button--loading .ir-button__content--hidden {
    visibility: hidden;
}

.ir-button__spinner {
    position: absolute;
    width: 1em;
    height: 1em;
    border: 2px solid currentColor;
    border-right-color: transparent;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
}

@keyframes spin {
    to {
        transform: rotate(360deg);
    }
}
</style>
