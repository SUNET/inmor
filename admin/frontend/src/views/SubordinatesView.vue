<script lang="ts">
import { defineComponent } from 'vue';
import { Plus, Pencil, Eye, Trash2, Download } from 'lucide-vue-next';
import Heading from '../components/base/Heading.vue';
import Button from '../components/base/Button.vue';
import Badge from '../components/base/Badge.vue';
import DataTable from '../components/base/DataTable.vue';
import Modal from '../components/base/Modal.vue';
import Input from '../components/base/Input.vue';
import Toggle from '../components/base/Toggle.vue';
import JsonEditor from '../components/base/JsonEditor.vue';
import type { Subordinate, Subordinates } from '../lib/admin-sdk';

interface FormData {
    entityid: string;
    metadata: Record<string, unknown>;
    forced_metadata: Record<string, unknown>;
    jwks: Record<string, unknown>;
    valid_for: number | null;
    autorenew: boolean;
    active: boolean;
}

const defaultFormData: FormData = {
    entityid: '',
    metadata: {},
    forced_metadata: {},
    jwks: { keys: [] },
    valid_for: null,
    autorenew: true,
    active: true,
};

export default defineComponent({
    name: 'SubordinatesView',
    components: {
        Heading,
        Button,
        Badge,
        DataTable,
        Modal,
        Input,
        Toggle,
        JsonEditor,
        Plus,
        Pencil,
        Eye,
        Trash2,
        Download,
    },
    data() {
        return {
            loading: true,
            error: null as string | null,
            subordinates: null as Subordinates | null,
            columns: [
                { key: 'id', label: 'ID', width: '80px' },
                { key: 'entityid', label: 'Entity ID' },
                { key: 'valid_for', label: 'Valid for', width: '120px' },
                { key: 'autorenew', label: 'Autorenew', width: '120px' },
                { key: 'active', label: 'Status', width: '100px' },
            ],
            // Modal state
            showCreateModal: false,
            showEditModal: false,
            showViewModal: false,
            showDeactivateModal: false,
            formData: { ...defaultFormData },
            editingItem: null as Subordinate | null,
            viewingItem: null as Subordinate | null,
            deactivatingItem: null as Subordinate | null,
            formLoading: false,
            formError: null as string | null,
            fetchLoading: false,
            jsonErrors: {
                metadata: null as string | null,
                forced_metadata: null as string | null,
                jwks: null as string | null,
            },
        };
    },
    computed: {
        hasJsonErrors(): boolean {
            return !!(this.jsonErrors.metadata || this.jsonErrors.forced_metadata || this.jsonErrors.jwks);
        },
    },
    async mounted() {
        await this.loadData();
    },
    methods: {
        async loadData() {
            this.loading = true;
            this.error = null;
            try {
                this.subordinates = await this.$sdk.listSubordinates({ limit: 25 });
            } catch (e) {
                this.error = 'Failed to load subordinates. Please try again later.';
                console.error(e);
            } finally {
                this.loading = false;
            }
        },
        formatHours(hours: number | null): string {
            if (hours === null) return 'Default';
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
            this.jsonErrors = { metadata: null, forced_metadata: null, jwks: null };
            this.showCreateModal = true;
        },
        openEditModal(item: Subordinate) {
            this.editingItem = item;
            this.formData = {
                entityid: item.entityid,
                metadata: item.metadata || {},
                forced_metadata: item.forced_metadata || {},
                jwks: item.jwks || { keys: [] },
                valid_for: item.valid_for,
                autorenew: item.autorenew ?? true,
                active: item.active ?? true,
            };
            this.formError = null;
            this.jsonErrors = { metadata: null, forced_metadata: null, jwks: null };
            this.showEditModal = true;
        },
        openViewModal(item: Subordinate) {
            this.viewingItem = item;
            this.showViewModal = true;
        },
        openDeactivateModal(item: Subordinate) {
            this.deactivatingItem = item;
            this.showDeactivateModal = true;
        },
        closeModals() {
            this.showCreateModal = false;
            this.showEditModal = false;
            this.showViewModal = false;
            this.showDeactivateModal = false;
            this.editingItem = null;
            this.viewingItem = null;
            this.deactivatingItem = null;
            this.formError = null;
        },
        setJsonError(field: 'metadata' | 'forced_metadata' | 'jwks', error: string | null) {
            this.jsonErrors[field] = error;
        },
        async handleCreate() {
            if (this.hasJsonErrors) {
                this.formError = 'Please fix JSON syntax errors before submitting';
                return;
            }
            this.formLoading = true;
            this.formError = null;
            try {
                await this.$sdk.createSubordinate({
                    entityid: this.formData.entityid,
                    metadata: this.formData.metadata,
                    forced_metadata: this.formData.forced_metadata,
                    jwks: this.formData.jwks,
                    valid_for: this.formData.valid_for,
                    autorenew: this.formData.autorenew,
                    active: this.formData.active,
                });
                this.closeModals();
                await this.loadData();
            } catch (e: any) {
                this.formError = e.message || 'Failed to create subordinate';
                console.error(e);
            } finally {
                this.formLoading = false;
            }
        },
        async handleUpdate() {
            if (!this.editingItem) return;
            if (this.hasJsonErrors) {
                this.formError = 'Please fix JSON syntax errors before submitting';
                return;
            }
            this.formLoading = true;
            this.formError = null;
            try {
                await this.$sdk.updateSubordinate(this.editingItem.id, {
                    metadata: this.formData.metadata,
                    forced_metadata: this.formData.forced_metadata,
                    jwks: this.formData.jwks,
                    valid_for: this.formData.valid_for,
                    autorenew: this.formData.autorenew,
                    active: this.formData.active,
                });
                this.closeModals();
                await this.loadData();
            } catch (e: any) {
                this.formError = e.message || 'Failed to update subordinate';
                console.error(e);
            } finally {
                this.formLoading = false;
            }
        },
        async handleDeactivate() {
            if (!this.deactivatingItem) return;
            this.formLoading = true;
            this.formError = null;
            try {
                await this.$sdk.updateSubordinate(this.deactivatingItem.id, {
                    metadata: this.deactivatingItem.metadata || {},
                    forced_metadata: this.deactivatingItem.forced_metadata || {},
                    jwks: this.deactivatingItem.jwks || { keys: [] },
                    active: false,
                });
                this.closeModals();
                await this.loadData();
            } catch (e: any) {
                this.formError = e.message || 'Failed to deactivate subordinate';
                console.error(e);
            } finally {
                this.formLoading = false;
            }
        },
        async fetchConfiguration() {
            if (!this.formData.entityid) {
                this.formError = 'Please enter an Entity ID (URL) first';
                return;
            }
            // Check if this entity ID already exists as a subordinate
            const existingSubordinate = this.subordinates?.items.find(
                (sub) => sub.entityid === this.formData.entityid
            );
            if (existingSubordinate) {
                this.formError = 'This entity is already registered as a subordinate.';
                return;
            }
            this.fetchLoading = true;
            this.formError = null;
            try {
                const config = await this.$sdk.fetchEntityConfig(this.formData.entityid);
                // Populate the form fields with fetched data
                this.formData.metadata = config.metadata || {};
                this.formData.jwks = config.jwks || { keys: [] };
                // Clear JSON errors since we just set valid JSON
                this.jsonErrors = { metadata: null, forced_metadata: null, jwks: null };
            } catch (e: any) {
                this.formError = e.message || 'Failed to fetch entity configuration';
                console.error(e);
            } finally {
                this.fetchLoading = false;
            }
        },
    },
});
</script>

<template>
    <div class="subordinates-view">
        <header class="page-header">
            <Heading level="h1">Subordinates</Heading>
            <Button @click="openCreateModal">
                <Plus :size="18" />
                Add Subordinate
            </Button>
        </header>

        <p v-if="error" class="error-message">{{ error }}</p>

        <DataTable
            :columns="columns"
            :data="subordinates?.items || []"
            :loading="loading"
            empty-message="No subordinates found. Add one to get started."
        >
            <template #cell-entityid="{ value }">
                <code class="entity-url">{{ value }}</code>
            </template>
            <template #cell-valid_for="{ value }">
                {{ formatHours(value as number | null) }}
            </template>
            <template #cell-autorenew="{ value }">
                <Badge :variant="value ? 'success' : 'neutral'" size="sm">
                    {{ value ? 'enabled' : 'disabled' }}
                </Badge>
            </template>
            <template #cell-active="{ value }">
                <Badge :variant="value ? 'success' : 'danger'" size="sm">
                    {{ value ? 'active' : 'inactive' }}
                </Badge>
            </template>
            <template #actions="{ row }">
                <div class="action-buttons">
                    <Button variant="ghost" size="sm" @click="openViewModal(row as Subordinate)">
                        <Eye :size="16" />
                        View
                    </Button>
                    <Button variant="ghost" size="sm" @click="openEditModal(row as Subordinate)">
                        <Pencil :size="16" />
                        Edit
                    </Button>
                    <Button variant="ghost" size="sm" @click="openDeactivateModal(row as Subordinate)" v-if="(row as Subordinate).active">
                        <Trash2 :size="16" />
                        Deactivate
                    </Button>
                </div>
            </template>
        </DataTable>

        <!-- Create Modal -->
        <Modal :open="showCreateModal" title="Add Subordinate" size="lg" @close="closeModals">
            <form @submit.prevent="handleCreate" class="form">
                <div class="entity-id-row">
                    <Input
                        v-model="formData.entityid"
                        label="Entity ID (URL)"
                        type="url"
                        placeholder="https://example-rp.com"
                        required
                        class="entity-id-input"
                    />
                    <Button
                        type="button"
                        :loading="fetchLoading"
                        @click="fetchConfiguration"
                        class="fetch-config-btn"
                    >
                        <Download :size="16" />
                        Fetch config
                    </Button>
                </div>
                <p v-if="formError" class="form-error">{{ formError }}</p>
                <JsonEditor
                    v-model="formData.metadata"
                    label="Metadata"
                    :rows="8"
                    required
                    @error="(e) => setJsonError('metadata', e)"
                />
                <JsonEditor
                    v-model="formData.forced_metadata"
                    label="Forced Metadata"
                    :rows="6"
                    @error="(e) => setJsonError('forced_metadata', e)"
                />
                <JsonEditor
                    v-model="formData.jwks"
                    label="JWKS (JSON Web Key Set)"
                    placeholder='{\n  "keys": []\n}'
                    :rows="8"
                    required
                    @error="(e) => setJsonError('jwks', e)"
                />
                <Input
                    v-model.number="formData.valid_for"
                    label="Valid for (hours, leave empty for default)"
                    type="number"
                    placeholder="8760"
                />
                <div class="form-toggles">
                    <Toggle v-model="formData.autorenew" label="Auto-renew" />
                    <Toggle v-model="formData.active" label="Active" />
                </div>
            </form>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Cancel</Button>
                <Button @click="handleCreate" :loading="formLoading" :disabled="hasJsonErrors">Add Subordinate</Button>
            </template>
        </Modal>

        <!-- Edit Modal -->
        <Modal :open="showEditModal" title="Edit Subordinate" size="lg" @close="closeModals">
            <form @submit.prevent="handleUpdate" class="form">
                <Input
                    :model-value="formData.entityid"
                    label="Entity ID (URL)"
                    type="url"
                    disabled
                />
                <JsonEditor
                    v-model="formData.metadata"
                    label="Metadata"
                    :rows="8"
                    required
                    @error="(e) => setJsonError('metadata', e)"
                />
                <JsonEditor
                    v-model="formData.forced_metadata"
                    label="Forced Metadata"
                    :rows="6"
                    @error="(e) => setJsonError('forced_metadata', e)"
                />
                <JsonEditor
                    v-model="formData.jwks"
                    label="JWKS (JSON Web Key Set)"
                    :rows="8"
                    required
                    @error="(e) => setJsonError('jwks', e)"
                />
                <Input
                    v-model.number="formData.valid_for"
                    label="Valid for (hours, leave empty for default)"
                    type="number"
                />
                <div class="form-toggles">
                    <Toggle v-model="formData.autorenew" label="Auto-renew" />
                    <Toggle v-model="formData.active" label="Active" />
                </div>
                <p v-if="formError" class="form-error">{{ formError }}</p>
            </form>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Cancel</Button>
                <Button @click="handleUpdate" :loading="formLoading" :disabled="hasJsonErrors">Save Changes</Button>
            </template>
        </Modal>

        <!-- View Modal -->
        <Modal :open="showViewModal" title="Subordinate Details" size="lg" @close="closeModals">
            <div v-if="viewingItem" class="view-details">
                <div class="detail-row">
                    <span class="detail-label">Entity ID:</span>
                    <code class="detail-value">{{ viewingItem.entityid }}</code>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Status:</span>
                    <Badge :variant="viewingItem.active ? 'success' : 'danger'" size="sm">
                        {{ viewingItem.active ? 'active' : 'inactive' }}
                    </Badge>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Auto-renew:</span>
                    <Badge :variant="viewingItem.autorenew ? 'success' : 'neutral'" size="sm">
                        {{ viewingItem.autorenew ? 'enabled' : 'disabled' }}
                    </Badge>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Valid for:</span>
                    <span>{{ formatHours(viewingItem.valid_for) }}</span>
                </div>
                <div class="detail-section">
                    <span class="detail-label">Metadata:</span>
                    <pre class="detail-json">{{ JSON.stringify(viewingItem.metadata, null, 2) }}</pre>
                </div>
                <div class="detail-section">
                    <span class="detail-label">Forced Metadata:</span>
                    <pre class="detail-json">{{ JSON.stringify(viewingItem.forced_metadata, null, 2) }}</pre>
                </div>
                <div class="detail-section">
                    <span class="detail-label">JWKS:</span>
                    <pre class="detail-json">{{ JSON.stringify(viewingItem.jwks, null, 2) }}</pre>
                </div>
            </div>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Close</Button>
                <Button @click="openEditModal(viewingItem!); showViewModal = false">Edit</Button>
            </template>
        </Modal>

        <!-- Deactivate Confirmation Modal -->
        <Modal :open="showDeactivateModal" title="Deactivate Subordinate" size="sm" @close="closeModals">
            <p>Are you sure you want to deactivate this subordinate?</p>
            <p v-if="deactivatingItem"><strong>{{ deactivatingItem.entityid }}</strong></p>
            <p class="warning-text">This will remove the entity from the federation. Their subordinate statement will no longer be served.</p>
            <p v-if="formError" class="form-error">{{ formError }}</p>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Cancel</Button>
                <Button variant="danger" @click="handleDeactivate" :loading="formLoading">Deactivate</Button>
            </template>
        </Modal>
    </div>
</template>

<style scoped>
.subordinates-view {
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

.entity-url {
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

.entity-id-row {
    display: flex;
    gap: var(--ir--space--2);
    align-items: flex-end;
}

.entity-id-input {
    flex: 1;
}

.fetch-config-btn {
    white-space: nowrap;
    height: 38px;
    background-color: #059669;
    border-color: #059669;
    color: white;
}

.fetch-config-btn:hover {
    background-color: #047857;
    border-color: #047857;
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

/* View details */
.view-details {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--3);
}

.detail-row {
    display: flex;
    align-items: center;
    gap: var(--ir--space--2);
}

.detail-label {
    font-weight: 500;
    color: var(--ir--color--gray-600);
    min-width: 100px;
}

.detail-value {
    font-size: var(--ir--font-size--s);
    background-color: var(--ir--color--gray-100);
    padding: 2px 6px;
    border-radius: 4px;
    word-break: break-all;
}

.detail-section {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--1);
}

.detail-json {
    background-color: var(--ir--color--gray-50);
    border: var(--ir--border);
    border-radius: var(--ir--space--1);
    padding: var(--ir--space--3);
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 12px;
    overflow-x: auto;
    max-height: 200px;
    margin: 0;
}
</style>
