<script lang="ts">
import { defineComponent } from 'vue';
import { X } from 'lucide-vue-next';

export default defineComponent({
    name: 'Modal',
    components: { X },
    props: {
        open: {
            type: Boolean,
            required: true,
        },
        title: {
            type: String,
            default: '',
        },
        size: {
            type: String as () => 'sm' | 'md' | 'lg' | 'xl',
            default: 'md',
        },
    },
    emits: ['close'],
    computed: {
        sizeClass(): string {
            return `ir-modal__content--${this.size}`;
        },
    },
    methods: {
        onBackdropClick(event: MouseEvent) {
            if (event.target === event.currentTarget) {
                this.$emit('close');
            }
        },
        onEscKey(event: KeyboardEvent) {
            if (event.key === 'Escape' && this.open) {
                this.$emit('close');
            }
        },
    },
    watch: {
        open: {
            immediate: true,
            handler(isOpen) {
                if (isOpen) {
                    document.addEventListener('keydown', this.onEscKey);
                    document.body.style.overflow = 'hidden';
                } else {
                    document.removeEventListener('keydown', this.onEscKey);
                    document.body.style.overflow = '';
                }
            },
        },
    },
    unmounted() {
        document.removeEventListener('keydown', this.onEscKey);
        document.body.style.overflow = '';
    },
});
</script>

<template>
    <Teleport to="body">
        <Transition name="modal">
            <div v-if="open" class="ir-modal" @click="onBackdropClick">
                <div :class="['ir-modal__content', sizeClass]" role="dialog" aria-modal="true">
                    <header v-if="title || $slots.header" class="ir-modal__header">
                        <slot name="header">
                            <h2 class="ir-modal__title">{{ title }}</h2>
                        </slot>
                        <button
                            type="button"
                            class="ir-modal__close"
                            @click="$emit('close')"
                            aria-label="Close"
                        >
                            <X :size="20" />
                        </button>
                    </header>
                    <div class="ir-modal__body">
                        <slot></slot>
                    </div>
                    <footer v-if="$slots.footer" class="ir-modal__footer">
                        <slot name="footer"></slot>
                    </footer>
                </div>
            </div>
        </Transition>
    </Teleport>
</template>

<style scoped>
.ir-modal {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--ir--space--4);
    background-color: rgba(0, 0, 0, 0.5);
}

.ir-modal__content {
    background-color: white;
    border-radius: var(--ir--space--2);
    box-shadow: var(--ir--box-shadow);
    max-height: calc(100vh - var(--ir--space--4) * 2);
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.ir-modal__content--sm {
    width: 100%;
    max-width: 400px;
}

.ir-modal__content--md {
    width: 100%;
    max-width: 560px;
}

.ir-modal__content--lg {
    width: 100%;
    max-width: 800px;
}

.ir-modal__content--xl {
    width: 100%;
    max-width: 1140px;
}

.ir-modal__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--ir--space--3) var(--ir--space--4);
    border-bottom: var(--ir--border);
}

.ir-modal__title {
    font-size: var(--ir--font-size);
    font-weight: 600;
    margin: 0;
}

.ir-modal__close {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--ir--space--1);
    border: none;
    background: transparent;
    border-radius: var(--ir--space--1);
    cursor: pointer;
    color: #6b7280;
    transition: background-color 0.15s ease;
}

.ir-modal__close:hover {
    background-color: #f3f4f6;
    color: #1f2937;
}

.ir-modal__body {
    padding: var(--ir--space--4);
    overflow-y: auto;
    flex: 1;
}

.ir-modal__footer {
    display: flex;
    justify-content: flex-end;
    gap: var(--ir--space--2);
    padding: var(--ir--space--3) var(--ir--space--4);
    border-top: var(--ir--border);
    background-color: #f9fafb;
}

/* Transitions */
.modal-enter-active,
.modal-leave-active {
    transition: opacity 0.2s ease;
}

.modal-enter-active .ir-modal__content,
.modal-leave-active .ir-modal__content {
    transition: transform 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
    opacity: 0;
}

.modal-enter-from .ir-modal__content,
.modal-leave-to .ir-modal__content {
    transform: scale(0.95);
}
</style>
