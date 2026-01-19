<script lang="ts">
import { defineComponent, ref, watch, shallowRef } from 'vue';
import { Codemirror } from 'vue-codemirror';
import { json, jsonParseLinter } from '@codemirror/lang-json';
import { linter, lintGutter } from '@codemirror/lint';
import { EditorView } from '@codemirror/view';

export default defineComponent({
    name: 'JsonEditor',
    components: { Codemirror },
    props: {
        modelValue: {
            type: [Object, Array, String, null],
            default: null,
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
    setup(props, { emit }) {
        const localValue = ref('');
        const parseError = ref<string | null>(null);
        const view = shallowRef<EditorView>();

        // Extensions for CodeMirror
        const extensions = [
            json(),
            linter(jsonParseLinter()),
            lintGutter(),
            EditorView.lineWrapping,
            EditorView.theme({
                '&': {
                    fontSize: '13px',
                    border: '1px solid #e5e7eb',
                    borderRadius: '6px',
                },
                '&.cm-focused': {
                    outline: 'none',
                    borderColor: '#1d4ed8',
                    boxShadow: '0 0 0 3px rgba(29, 78, 216, 0.1)',
                },
                '.cm-content': {
                    fontFamily: "'Monaco', 'Menlo', 'Ubuntu Mono', monospace",
                    padding: '8px 0',
                },
                '.cm-line': {
                    padding: '0 8px',
                },
                '.cm-gutters': {
                    backgroundColor: '#f9fafb',
                    borderRight: '1px solid #e5e7eb',
                    borderRadius: '6px 0 0 6px',
                },
                '.cm-activeLineGutter': {
                    backgroundColor: '#f3f4f6',
                },
                '.cm-activeLine': {
                    backgroundColor: '#f9fafb',
                },
                // Lint error styling
                '.cm-lintRange-error': {
                    backgroundImage: 'none',
                    textDecoration: 'wavy underline #ef4444',
                    textDecorationSkipInk: 'none',
                },
                '.cm-lintRange-warning': {
                    backgroundImage: 'none',
                    textDecoration: 'wavy underline #f59e0b',
                    textDecorationSkipInk: 'none',
                },
                '.cm-diagnostic-error': {
                    borderLeft: '3px solid #ef4444',
                    backgroundColor: '#fef2f2',
                    padding: '3px 6px 3px 8px',
                    marginLeft: '-1px',
                },
                '.cm-diagnostic-warning': {
                    borderLeft: '3px solid #f59e0b',
                    backgroundColor: '#fffbeb',
                    padding: '3px 6px 3px 8px',
                    marginLeft: '-1px',
                },
                '.cm-tooltip-lint': {
                    backgroundColor: 'white',
                    border: '1px solid #e5e7eb',
                    borderRadius: '4px',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
                },
            }),
        ];

        // Calculate height based on rows
        const editorHeight = `${props.rows * 20 + 16}px`;

        // Convert modelValue to string
        const toStringValue = (val: unknown): string => {
            if (val === null || val === undefined) {
                return '';
            }
            if (typeof val === 'string') {
                return val;
            }
            return JSON.stringify(val, null, 2);
        };

        // Initialize local value from prop
        localValue.value = toStringValue(props.modelValue);

        // Watch for external changes to modelValue
        watch(() => props.modelValue, (newVal) => {
            const stringVal = toStringValue(newVal);
            // Only update if the parsed values differ to avoid cursor jumps
            if (localValue.value.trim() === '') {
                localValue.value = stringVal;
            } else {
                try {
                    const currentParsed = JSON.parse(localValue.value);
                    const newParsed = newVal;
                    if (JSON.stringify(currentParsed) !== JSON.stringify(newParsed)) {
                        localValue.value = stringVal;
                    }
                } catch {
                    // Current value is invalid, update it
                    localValue.value = stringVal;
                }
            }
        });

        const handleChange = (value: string) => {
            localValue.value = value;
            parseError.value = null;

            // Handle empty input
            if (value.trim() === '') {
                emit('update:modelValue', null);
                emit('error', null);
                return;
            }

            try {
                const parsed = JSON.parse(value);
                emit('update:modelValue', parsed);
                emit('error', null);
            } catch (e) {
                const errorMessage = e instanceof Error ? e.message : 'Invalid JSON syntax';
                parseError.value = errorMessage;
                emit('error', errorMessage);
            }
        };

        const handleReady = ({ view: editorView }: { view: EditorView }) => {
            view.value = editorView;
        };

        const formatJson = () => {
            try {
                const parsed = JSON.parse(localValue.value);
                localValue.value = JSON.stringify(parsed, null, 2);
                parseError.value = null;
                emit('update:modelValue', parsed);
                emit('error', null);
            } catch (e) {
                parseError.value = 'Cannot format: Invalid JSON';
            }
        };

        return {
            localValue,
            parseError,
            extensions,
            editorHeight,
            handleChange,
            handleReady,
            formatJson,
        };
    },
    computed: {
        hasError(): boolean {
            return !!this.error || !!this.parseError;
        },
        displayError(): string {
            return this.error || this.parseError || '';
        },
        errorId(): string {
            return `${this.id}-error`;
        },
    },
});
</script>

<template>
    <div class="ir-json-editor">
        <div class="ir-json-editor__header">
            <label v-if="label" :for="id" class="ir-json-editor__label">
                {{ label }}
                <span v-if="required" class="ir-json-editor__required" aria-hidden="true">*</span>
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
        <div
            class="ir-json-editor__wrapper"
            :class="{ 'ir-json-editor__wrapper--error': hasError, 'ir-json-editor__wrapper--disabled': disabled }"
            :style="{ minHeight: editorHeight }"
            :aria-invalid="hasError ? 'true' : undefined"
            :aria-describedby="hasError ? errorId : undefined"
        >
            <Codemirror
                v-model="localValue"
                :placeholder="placeholder"
                :extensions="extensions"
                :disabled="disabled"
                :style="{ height: editorHeight }"
                @change="handleChange"
                @ready="handleReady"
            />
        </div>
        <p v-if="displayError" :id="errorId" class="ir-json-editor__error" role="alert">
            {{ displayError }}
        </p>
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

.ir-json-editor__wrapper {
    border-radius: 6px;
    overflow: hidden;
}

.ir-json-editor__wrapper--error :deep(.cm-editor) {
    border-color: #ef4444;
}

.ir-json-editor__wrapper--error :deep(.cm-editor.cm-focused) {
    border-color: #ef4444;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}

.ir-json-editor__wrapper--disabled {
    opacity: 0.6;
    pointer-events: none;
}

.ir-json-editor__wrapper--disabled :deep(.cm-editor) {
    background-color: #f9fafb;
}

.ir-json-editor__error {
    font-size: var(--ir--font-size--xs);
    color: #ef4444;
    margin: var(--ir--space--1) 0 0;
}

.ir-json-editor__format-btn:focus-visible {
    outline: 2px solid var(--ir--color--primary, #1d4ed8);
    outline-offset: 2px;
}
</style>
