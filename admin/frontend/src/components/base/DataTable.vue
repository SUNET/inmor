<script lang="ts">
import { defineComponent, type PropType } from 'vue';

export interface Column {
    key: string;
    label: string;
    width?: string;
    title?: string; // Tooltip text on hover
}

export default defineComponent({
    name: 'DataTable',
    props: {
        columns: {
            type: Array as PropType<Column[]>,
            required: true,
        },
        data: {
            type: Array as PropType<Record<string, unknown>[]>,
            required: true,
        },
        loading: {
            type: Boolean,
            default: false,
        },
        emptyMessage: {
            type: String,
            default: 'No data available',
        },
        keyField: {
            type: String,
            default: 'id',
        },
    },
    computed: {
        hasActions(): boolean {
            return !!this.$slots.actions;
        },
    },
    methods: {
        getCellValue(row: Record<string, unknown>, key: string): unknown {
            return row[key];
        },
    },
});
</script>

<template>
    <div class="ir-table-container">
        <table class="ir-table">
            <thead>
                <tr>
                    <th
                        v-for="column in columns"
                        :key="column.key"
                        :style="column.width ? { width: column.width } : {}"
                        :title="column.title"
                    >
                        {{ column.label }}
                    </th>
                    <th v-if="hasActions" class="ir-table__actions-header">Actions</th>
                </tr>
            </thead>
            <tbody>
                <tr v-if="loading">
                    <td :colspan="columns.length + (hasActions ? 1 : 0)" class="ir-table__loading">
                        <span class="ir-table__spinner"></span>
                        Loading...
                    </td>
                </tr>
                <tr v-else-if="data.length === 0">
                    <td :colspan="columns.length + (hasActions ? 1 : 0)" class="ir-table__empty">
                        {{ emptyMessage }}
                    </td>
                </tr>
                <tr v-else v-for="row in data" :key="String(row[keyField])">
                    <td v-for="column in columns" :key="column.key">
                        <slot :name="`cell-${column.key}`" :row="row" :value="getCellValue(row, column.key)">
                            {{ getCellValue(row, column.key) }}
                        </slot>
                    </td>
                    <td v-if="hasActions" class="ir-table__actions">
                        <slot name="actions" :row="row"></slot>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
</template>

<style scoped>
.ir-table-container {
    overflow-x: auto;
    border: var(--ir--border);
    border-radius: var(--ir--space--2);
}

.ir-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--ir--font-size--s);
}

.ir-table thead {
    background-color: #f9fafb;
}

.ir-table th {
    padding: var(--ir--space--3);
    text-align: left;
    font-weight: 600;
    color: #374151;
    border-bottom: var(--ir--border);
    white-space: nowrap;
}

.ir-table td {
    padding: var(--ir--space--3);
    border-bottom: 1px solid #f3f4f6;
    color: #1f2937;
}

.ir-table tbody tr:hover {
    background-color: #f9fafb;
}

.ir-table tbody tr:last-child td {
    border-bottom: none;
}

.ir-table__actions-header {
    width: 1%;
    white-space: nowrap;
}

.ir-table__actions {
    white-space: nowrap;
}

.ir-table__loading,
.ir-table__empty {
    text-align: center;
    padding: var(--ir--space--5) !important;
    color: #6b7280;
}

.ir-table__spinner {
    display: inline-block;
    width: 1em;
    height: 1em;
    border: 2px solid #e5e7eb;
    border-right-color: #2563eb;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    margin-right: var(--ir--space--2);
    vertical-align: middle;
}

@keyframes spin {
    to {
        transform: rotate(360deg);
    }
}
</style>
