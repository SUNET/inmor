<script setup lang="ts">
import Button from './Button.vue';
import { PAGE_SIZE } from '../../lib/pagination';

/** Navigate a server-paginated list using the offset of its displayed rows. */
defineProps<{ offset: number; count: number; loading: boolean }>();
const emit = defineEmits<{ navigate: [offset: number] }>();
</script>

<template>
    <nav v-if="count > PAGE_SIZE || offset > 0" class="pagination" aria-label="Pagination">
        <Button variant="secondary" size="sm" :disabled="loading || offset === 0"
            @click="emit('navigate', offset - PAGE_SIZE)">Previous</Button>
        <span aria-live="polite">{{ offset + 1 }}–{{ Math.min(offset + PAGE_SIZE, count) }} of {{ count }}</span>
        <Button variant="secondary" size="sm" :disabled="loading || offset + PAGE_SIZE >= count"
            @click="emit('navigate', offset + PAGE_SIZE)">Next</Button>
    </nav>
</template>

<style scoped>
.pagination {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--ir--space--3);
}
</style>
