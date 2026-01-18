<script lang="ts">
import { defineComponent, ref, nextTick } from 'vue';
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
    setup() {
        const modalId = `modal-${Math.random().toString(36).substr(2, 9)}`;
        const titleId = `${modalId}-title`;
        const modalContent = ref<HTMLElement | null>(null);
        const previousActiveElement = ref<HTMLElement | null>(null);

        return {
            modalId,
            titleId,
            modalContent,
            previousActiveElement,
        };
    },
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
        onKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape' && this.open) {
                this.$emit('close');
                return;
            }
            // Handle focus trapping
            if (event.key === 'Tab' && this.open) {
                this.trapFocus(event);
            }
        },
        trapFocus(event: KeyboardEvent) {
            const modal = this.modalContent;
            if (!modal) return;

            const focusableSelectors = [
                'button:not([disabled])',
                'input:not([disabled])',
                'select:not([disabled])',
                'textarea:not([disabled])',
                'a[href]',
                '[tabindex]:not([tabindex="-1"])',
            ];
            const focusableElements = modal.querySelectorAll<HTMLElement>(
                focusableSelectors.join(', ')
            );
            const firstElement = focusableElements[0];
            const lastElement = focusableElements[focusableElements.length - 1];

            if (!firstElement) return;

            if (event.shiftKey && document.activeElement === firstElement) {
                event.preventDefault();
                lastElement?.focus();
            } else if (!event.shiftKey && document.activeElement === lastElement) {
                event.preventDefault();
                firstElement?.focus();
            }
        },
        async focusFirstElement() {
            await nextTick();
            const modal = this.modalContent;
            if (!modal) return;

            const focusableSelectors = [
                'button:not([disabled])',
                'input:not([disabled])',
                'select:not([disabled])',
                'textarea:not([disabled])',
                'a[href]',
                '[tabindex]:not([tabindex="-1"])',
            ];
            const firstFocusable = modal.querySelector<HTMLElement>(
                focusableSelectors.join(', ')
            );
            firstFocusable?.focus();
        },
        returnFocus() {
            this.previousActiveElement?.focus();
        },
    },
    watch: {
        open: {
            immediate: true,
            async handler(isOpen, wasOpen) {
                if (isOpen) {
                    // Store the element that was focused before opening
                    this.previousActiveElement = document.activeElement as HTMLElement;
                    document.addEventListener('keydown', this.onKeyDown);
                    document.body.style.overflow = 'hidden';
                    // Focus first focusable element in modal
                    await this.focusFirstElement();
                } else {
                    document.removeEventListener('keydown', this.onKeyDown);
                    document.body.style.overflow = '';
                    // Return focus to trigger element on close
                    if (wasOpen) {
                        this.returnFocus();
                    }
                }
            },
        },
    },
    unmounted() {
        document.removeEventListener('keydown', this.onKeyDown);
        document.body.style.overflow = '';
    },
});
</script>

<template>
    <Teleport to="body">
        <Transition name="modal">
            <div v-if="open" class="ir-modal" @click="onBackdropClick">
                <div
                    ref="modalContent"
                    :class="['ir-modal__content', sizeClass]"
                    role="dialog"
                    aria-modal="true"
                    :aria-labelledby="title ? titleId : undefined"
                >
                    <header v-if="title || $slots.header" class="ir-modal__header">
                        <slot name="header">
                            <h2 :id="titleId" class="ir-modal__title">{{ title }}</h2>
                        </slot>
                        <button
                            type="button"
                            class="ir-modal__close"
                            @click="$emit('close')"
                            aria-label="Close modal"
                        >
                            <X :size="20" aria-hidden="true" />
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

.ir-modal__close:focus-visible {
    outline: 2px solid var(--ir--color--primary, #1d4ed8);
    outline-offset: 2px;
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
