<script lang="ts">
import { defineComponent, type PropType } from 'vue';

export default defineComponent({
    name: 'Input',
    props: {
        modelValue: {
            type: [String, Number, null] as PropType<string | number | null>,
            default: '',
        },
        type: {
            type: String as PropType<'text' | 'email' | 'password' | 'number' | 'url'>,
            default: 'text',
        },
        label: {
            type: String,
            default: '',
        },
        placeholder: {
            type: String,
            default: '',
        },
        error: {
            type: String,
            default: '',
        },
        required: {
            type: Boolean,
            default: false,
        },
        disabled: {
            type: Boolean,
            default: false,
        },
        id: {
            type: String,
            default: () => `input-${Math.random().toString(36).substr(2, 9)}`,
        },
    },
    emits: ['update:modelValue'],
    computed: {
        inputClasses(): string[] {
            return [
                'ir-input__field',
                this.error ? 'ir-input__field--error' : '',
            ].filter(Boolean);
        },
        errorId(): string {
            return `${this.id}-error`;
        },
    },
});
</script>

<template>
    <div class="ir-input">
        <label v-if="label" :for="id" class="ir-input__label">
            {{ label }}
            <span v-if="required" class="ir-input__required" aria-hidden="true">*</span>
        </label>
        <input
            :id="id"
            :type="type"
            :value="modelValue"
            :placeholder="placeholder"
            :disabled="disabled"
            :required="required"
            :class="inputClasses"
            :aria-invalid="error ? 'true' : undefined"
            :aria-describedby="error ? errorId : undefined"
            :aria-required="required ? 'true' : undefined"
            @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
        />
        <p v-if="error" :id="errorId" class="ir-input__error" role="alert">{{ error }}</p>
    </div>
</template>

<style scoped>
.ir-input {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--1);
}

.ir-input__label {
    font-size: var(--ir--font-size--s);
    font-weight: 500;
    color: #374151;
}

.ir-input__required {
    color: #ef4444;
}

.ir-input__field {
    padding: var(--ir--space--2) var(--ir--space--3);
    border: var(--ir--border);
    border-radius: var(--ir--space--1);
    font-family: var(--ir--font-family);
    font-size: var(--ir--font-size--s);
    color: #1f2937;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.ir-input__field:focus {
    outline: none;
    border-color: var(--ir--color--primary);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.ir-input__field:disabled {
    background-color: #f9fafb;
    color: #9ca3af;
    cursor: not-allowed;
}

.ir-input__field--error {
    border-color: #ef4444;
}

.ir-input__field--error:focus {
    border-color: #ef4444;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}

.ir-input__error {
    font-size: var(--ir--font-size--xs);
    color: #ef4444;
    margin: 0;
}
</style>
