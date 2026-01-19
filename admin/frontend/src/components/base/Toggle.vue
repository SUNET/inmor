<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
    name: 'Toggle',
    props: {
        modelValue: {
            type: Boolean,
            default: false,
        },
        label: {
            type: String,
            default: '',
        },
        disabled: {
            type: Boolean,
            default: false,
        },
        id: {
            type: String,
            default: () => `toggle-${Math.random().toString(36).substr(2, 9)}`,
        },
    },
    emits: ['update:modelValue'],
    methods: {
        toggle() {
            if (!this.disabled) {
                this.$emit('update:modelValue', !this.modelValue);
            }
        },
    },
});
</script>

<template>
    <div class="ir-toggle" :class="{ 'ir-toggle--disabled': disabled }">
        <button
            type="button"
            role="switch"
            :id="id"
            :aria-checked="modelValue"
            :aria-labelledby="label ? `${id}-label` : undefined"
            :disabled="disabled"
            :class="['ir-toggle__switch', { 'ir-toggle__switch--on': modelValue }]"
            @click="toggle"
        >
            <span class="ir-toggle__thumb" aria-hidden="true"></span>
        </button>
        <label v-if="label" :id="`${id}-label`" :for="id" class="ir-toggle__label" @click="toggle">
            {{ label }}
        </label>
    </div>
</template>

<style scoped>
.ir-toggle {
    display: inline-flex;
    align-items: center;
    gap: var(--ir--space--2);
}

.ir-toggle--disabled {
    opacity: 0.5;
}

.ir-toggle__switch {
    position: relative;
    width: 44px;
    height: 24px;
    padding: 0;
    border: none;
    border-radius: 12px;
    background-color: #d1d5db;
    cursor: pointer;
    transition: background-color 0.2s ease;
}

.ir-toggle__switch:focus {
    outline: none;
}

.ir-toggle__switch:focus-visible {
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.3);
    outline: 2px solid var(--ir--color--primary, #1d4ed8);
    outline-offset: 2px;
}

.ir-toggle__switch--on {
    background-color: var(--ir--color--primary);
}

.ir-toggle__switch:disabled {
    cursor: not-allowed;
}

.ir-toggle__thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background-color: white;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    transition: transform 0.2s ease;
}

.ir-toggle__switch--on .ir-toggle__thumb {
    transform: translateX(20px);
}

.ir-toggle__label {
    font-size: var(--ir--font-size--s);
    color: #374151;
    cursor: pointer;
    user-select: none;
}

.ir-toggle--disabled .ir-toggle__label {
    cursor: not-allowed;
}
</style>
