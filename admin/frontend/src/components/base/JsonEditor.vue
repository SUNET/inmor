<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
    name: 'JsonEditor',
    props: {
        modelValue: {
            type: [Object, Array, String],
            default: () => ({}),
        },
        label: {
            type: String,
            default: '',
        },
        placeholder: {
            type: String,
            default: '{\n  \n}',
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
        rows: {
            type: Number,
            default: 10,
        },
        id: {
            type: String,
            default: () => `json-${Math.random().toString(36).substr(2, 9)}`,
        },
    },
    emits: ['update:modelValue', 'error'],
    data() {
        return {
            localValue: '',
            parseError: null as string | null,
        };
    },
    computed: {
        hasError(): boolean {
            return !!this.error || !!this.parseError;
        },
        displayError(): string {
            return this.error || this.parseError || '';
        },
    },
    watch: {
        modelValue: {
            immediate: true,
            handler(newVal) {
                if (typeof newVal === 'string') {
                    this.localValue = newVal;
                } else {
                    this.localValue = JSON.stringify(newVal, null, 2);
                }
            },
        },
    },
    methods: {
        handleInput(event: Event) {
            const target = event.target as HTMLTextAreaElement;
            this.localValue = target.value;
            this.parseError = null;

            try {
                const parsed = JSON.parse(target.value);
                this.$emit('update:modelValue', parsed);
                this.$emit('error', null);
            } catch (e) {
                this.parseError = 'Invalid JSON syntax';
                this.$emit('error', 'Invalid JSON syntax');
            }
        },
        formatJson() {
            try {
                const parsed = JSON.parse(this.localValue);
                this.localValue = JSON.stringify(parsed, null, 2);
                this.parseError = null;
                this.$emit('update:modelValue', parsed);
            } catch (e) {
                this.parseError = 'Cannot format: Invalid JSON';
            }
        },
    },
});
</script>

<template>
    <div class="ir-json-editor">
        <div class="ir-json-editor__header">
            <label v-if="label" :for="id" class="ir-json-editor__label">
                {{ label }}
                <span v-if="required" class="ir-json-editor__required">*</span>
            </label>
            <button
                type="button"
                class="ir-json-editor__format-btn"
                @click="formatJson"
                :disabled="disabled"
            >
                Format
            </button>
        </div>
        <textarea
            :id="id"
            :value="localValue"
            :placeholder="placeholder"
            :disabled="disabled"
            :required="required"
            :rows="rows"
            :class="['ir-json-editor__textarea', { 'ir-json-editor__textarea--error': hasError }]"
            @input="handleInput"
            spellcheck="false"
        ></textarea>
        <p v-if="displayError" class="ir-json-editor__error">{{ displayError }}</p>
    </div>
</template>

<style scoped>
.ir-json-editor {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--1);
}

.ir-json-editor__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.ir-json-editor__label {
    font-size: var(--ir--font-size--s);
    font-weight: 500;
    color: #374151;
}

.ir-json-editor__required {
    color: #ef4444;
}

.ir-json-editor__format-btn {
    padding: 2px 8px;
    border: var(--ir--border);
    border-radius: 4px;
    background-color: white;
    font-size: var(--ir--font-size--xs);
    color: #6b7280;
    cursor: pointer;
    transition: background-color 0.15s ease;
}

.ir-json-editor__format-btn:hover:not(:disabled) {
    background-color: #f3f4f6;
}

.ir-json-editor__format-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.ir-json-editor__textarea {
    padding: var(--ir--space--2) var(--ir--space--3);
    border: var(--ir--border);
    border-radius: var(--ir--space--1);
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 13px;
    line-height: 1.5;
    color: #1f2937;
    resize: vertical;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.ir-json-editor__textarea:focus {
    outline: none;
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.ir-json-editor__textarea:disabled {
    background-color: #f9fafb;
    color: #9ca3af;
    cursor: not-allowed;
}

.ir-json-editor__textarea--error {
    border-color: #ef4444;
}

.ir-json-editor__textarea--error:focus {
    border-color: #ef4444;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}

.ir-json-editor__error {
    font-size: var(--ir--font-size--xs);
    color: #ef4444;
    margin: 0;
}
</style>
