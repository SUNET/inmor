<script lang="ts">
import { defineComponent } from 'vue';
import { Plus, Pencil, Trash2 } from 'lucide-vue-next';
import Heading from '../components/base/Heading.vue';
import Button from '../components/base/Button.vue';
import Badge from '../components/base/Badge.vue';
import DataTable from '../components/base/DataTable.vue';
import Modal from '../components/base/Modal.vue';
import Input from '../components/base/Input.vue';
import Toggle from '../components/base/Toggle.vue';
import type { TrustMarkType, TrustMarkTypes } from '../lib/admin-sdk';

interface FormData {
    tmtype: string;
    valid_for: number;
    renewal_time: number;
    autorenew: boolean;
    active: boolean;
}

const defaultFormData: FormData = {
    tmtype: '',
    valid_for: 8760,
    renewal_time: 48,
    autorenew: true,
    active: true,
};

export default defineComponent({
    name: 'TrustMarkTypesView',
    components: {
        Heading,
        Button,
        Badge,
        DataTable,
        Modal,
        Input,
        Toggle,
        Plus,
        Pencil,
        Trash2,
    },
    data() {
        return {
            loading: true,
            error: null as string | null,
            trustMarkTypes: null as TrustMarkTypes | null,
            columns: [
                { key: 'id', label: 'ID', width: '80px' },
                { key: 'tmtype', label: 'Trust mark type' },
                { key: 'autorenew', label: 'Autorenew', width: '120px' },
                { key: 'valid_for', label: 'Valid for', width: '120px' },
                { key: 'renewal_time', label: 'Renewal time', width: '140px', title: 'Autorenew time before expiration' },
                { key: 'active', label: 'Status', width: '100px' },
            ],
            // Modal state
            showCreateModal: false,
            showEditModal: false,
            showDeleteModal: false,
            formData: { ...defaultFormData },
            editingId: null as number | null,
            deletingItem: null as TrustMarkType | null,
            formLoading: false,
            formError: null as string | null,
        };
    },
    async mounted() {
        await this.loadData();
    },
    methods: {
        async loadData() {
            this.loading = true;
            this.error = null;
            try {
                this.trustMarkTypes = await this.$sdk.listTrustMarkTypes({ limit: 25 });
            } catch (e) {
                this.error = 'Failed to load trust mark types. Please try again later.';
                console.error(e);
            } finally {
                this.loading = false;
            }
        },
        formatHours(hours: number): string {
            if (hours >= 8760) {
                const years = Math.floor(hours / 8760);
                return `${years} year${years > 1 ? 's' : ''}`;
            } else if (hours >= 720) {
                const months = Math.floor(hours / 720);
                return `${months} month${months > 1 ? 's' : ''}`;
            } else if (hours >= 24) {
                const days = Math.floor(hours / 24);
                return `${days} day${days > 1 ? 's' : ''}`;
            }
            return `${hours} hour${hours > 1 ? 's' : ''}`;
        },
        openCreateModal() {
            this.formData = { ...defaultFormData };
            this.formError = null;
            this.showCreateModal = true;
        },
        openEditModal(item: TrustMarkType) {
            this.editingId = item.id;
            this.formData = {
                tmtype: item.tmtype,
                valid_for: item.valid_for,
                renewal_time: item.renewal_time,
                autorenew: item.autorenew,
                active: item.active,
            };
            this.formError = null;
            this.showEditModal = true;
        },
        openDeleteModal(item: TrustMarkType) {
            this.deletingItem = item;
            this.showDeleteModal = true;
        },
        closeModals() {
            this.showCreateModal = false;
            this.showEditModal = false;
            this.showDeleteModal = false;
            this.editingId = null;
            this.deletingItem = null;
            this.formError = null;
        },
        async handleCreate() {
            this.formLoading = true;
            this.formError = null;
            try {
                await this.$sdk.createTrustMarkType(this.formData);
                this.closeModals();
                await this.loadData();
            } catch (e: any) {
                this.formError = e.message || 'Failed to create trust mark type';
                console.error(e);
            } finally {
                this.formLoading = false;
            }
        },
        async handleUpdate() {
            if (!this.editingId) return;
            this.formLoading = true;
            this.formError = null;
            try {
                await this.$sdk.updateTrustMarkType(this.editingId, {
                    valid_for: this.formData.valid_for,
                    renewal_time: this.formData.renewal_time,
                    autorenew: this.formData.autorenew,
                    active: this.formData.active,
                });
                this.closeModals();
                await this.loadData();
            } catch (e: any) {
                this.formError = e.message || 'Failed to update trust mark type';
                console.error(e);
            } finally {
                this.formLoading = false;
            }
        },
        async handleDelete() {
            if (!this.deletingItem) return;
            this.formLoading = true;
            this.formError = null;
            try {
                // Soft delete - set active to false
                await this.$sdk.updateTrustMarkType(this.deletingItem.id, {
                    active: false,
                    autorenew: this.deletingItem.autorenew,
                    valid_for: this.deletingItem.valid_for,
                    renewal_time: this.deletingItem.renewal_time,
                });
                this.closeModals();
                await this.loadData();
            } catch (e: any) {
                this.formError = e.message || 'Failed to deactivate trust mark type';
                console.error(e);
            } finally {
                this.formLoading = false;
            }
        },
    },
});
</script>

<template>
    <div class="trust-mark-types-view">
        <header class="page-header">
            <Heading level="h1">Trust mark types</Heading>
            <Button @click="openCreateModal">
                <Plus :size="18" />
                Add Trust Mark Type
            </Button>
        </header>

        <p v-if="error" class="error-message" role="alert" aria-live="polite">{{ error }}</p>

        <DataTable
            :columns="columns"
            :data="trustMarkTypes?.items || []"
            :loading="loading"
            empty-message="No trust mark types found. Create one to get started."
        >
            <template #cell-tmtype="{ value }">
                <code class="tmtype-url">{{ value }}</code>
            </template>
            <template #cell-autorenew="{ value }">
                <Badge :variant="value ? 'success' : 'neutral'" size="sm">
                    {{ value ? 'enabled' : 'disabled' }}
                </Badge>
            </template>
            <template #cell-valid_for="{ value }">
                {{ formatHours(value as number) }}
            </template>
            <template #cell-renewal_time="{ value }">
                {{ formatHours(value as number) }}
            </template>
            <template #cell-active="{ value }">
                <Badge :variant="value ? 'success' : 'danger'" size="sm">
                    {{ value ? 'active' : 'inactive' }}
                </Badge>
            </template>
            <template #actions="{ row }">
                <div class="action-buttons">
                    <Button variant="ghost" size="sm" @click="openEditModal(row as TrustMarkType)">
                        <Pencil :size="16" />
                        Edit
                    </Button>
                    <Button variant="ghost" size="sm" @click="openDeleteModal(row as TrustMarkType)">
                        <Trash2 :size="16" />
                        Delete
                    </Button>
                </div>
            </template>
        </DataTable>

        <!-- Create Modal -->
        <Modal :open="showCreateModal" title="Create Trust Mark Type" @close="closeModals">
            <form @submit.prevent="handleCreate" class="form">
                <Input
                    v-model="formData.tmtype"
                    label="Trust Mark Type URL"
                    type="url"
                    placeholder="https://example.com/trustmarks/member"
                    required
                    :error="formError || ''"
                />
                <div class="form-row">
                    <Input
                        v-model.number="formData.valid_for"
                        label="Valid for (hours)"
                        type="number"
                        placeholder="8760"
                        required
                    />
                    <Input
                        v-model.number="formData.renewal_time"
                        label="Renewal time (hours)"
                        type="number"
                        placeholder="48"
                        required
                    />
                </div>
                <div class="form-toggles">
                    <Toggle v-model="formData.autorenew" label="Auto-renew" />
                    <Toggle v-model="formData.active" label="Active" />
                </div>
            </form>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Cancel</Button>
                <Button @click="handleCreate" :loading="formLoading">Create</Button>
            </template>
        </Modal>

        <!-- Edit Modal -->
        <Modal :open="showEditModal" title="Edit Trust Mark Type" @close="closeModals">
            <form @submit.prevent="handleUpdate" class="form">
                <Input
                    :model-value="formData.tmtype"
                    label="Trust Mark Type URL"
                    type="url"
                    disabled
                />
                <div class="form-row">
                    <Input
                        v-model.number="formData.valid_for"
                        label="Valid for (hours)"
                        type="number"
                        required
                    />
                    <Input
                        v-model.number="formData.renewal_time"
                        label="Renewal time (hours)"
                        type="number"
                        required
                    />
                </div>
                <div class="form-toggles">
                    <Toggle v-model="formData.autorenew" label="Auto-renew" />
                    <Toggle v-model="formData.active" label="Active" />
                </div>
                <p v-if="formError" class="form-error" role="alert" aria-live="assertive">{{ formError }}</p>
            </form>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Cancel</Button>
                <Button @click="handleUpdate" :loading="formLoading">Save Changes</Button>
            </template>
        </Modal>

        <!-- Delete Confirmation Modal -->
        <Modal :open="showDeleteModal" title="Deactivate Trust Mark Type" size="sm" @close="closeModals">
            <p>Are you sure you want to deactivate this trust mark type?</p>
            <p v-if="deletingItem"><strong>{{ deletingItem.tmtype }}</strong></p>
            <p class="warning-text">This will prevent new trust marks from being issued with this type.</p>
            <p v-if="formError" class="form-error" role="alert" aria-live="assertive">{{ formError }}</p>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Cancel</Button>
                <Button variant="danger" @click="handleDelete" :loading="formLoading">Deactivate</Button>
            </template>
        </Modal>
    </div>
</template>

<style scoped>
.trust-mark-types-view {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--4);
}

.page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--ir--space--4);
}

.page-header h1 {
    margin: 0;
}

.error-message {
    padding: var(--ir--space--3);
    background-color: var(--ir--color--danger-bg);
    color: var(--ir--color--danger-text);
    border-radius: var(--ir--space--1);
    margin: 0;
}

.tmtype-url {
    font-size: var(--ir--font-size--xs);
    background-color: var(--ir--color--gray-100);
    padding: 2px 6px;
    border-radius: 4px;
    word-break: break-all;
}

.action-buttons {
    display: flex;
    gap: var(--ir--space--1);
}

.form {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--3);
}

.form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--ir--space--3);
}

.form-toggles {
    display: flex;
    gap: var(--ir--space--4);
}

.form-error {
    color: var(--ir--color--danger);
    font-size: var(--ir--font-size--s);
    margin: 0;
}

.warning-text {
    color: var(--ir--color--warning-text);
    font-size: var(--ir--font-size--s);
}
</style>
