<script lang="ts">
import { defineComponent } from 'vue';
import { Plus, Pencil, RefreshCw, XCircle, Copy, Check } from 'lucide-vue-next';
import Heading from '../components/base/Heading.vue';
import Button from '../components/base/Button.vue';
import Badge from '../components/base/Badge.vue';
import DataTable from '../components/base/DataTable.vue';
import Modal from '../components/base/Modal.vue';
import Input from '../components/base/Input.vue';
import Toggle from '../components/base/Toggle.vue';
import JsonEditor from '../components/base/JsonEditor.vue';
import type { TrustMark, TrustMarks, TrustMarkType, TrustMarkTypes } from '../lib/admin-sdk';

interface FormData {
    tmt: number | null;
    domain: string;
    autorenew: boolean;
    active: boolean;
    additional_claims: Record<string, unknown> | null;
}

const defaultFormData: FormData = {
    tmt: null,
    domain: '',
    autorenew: true,
    active: true,
    additional_claims: {},
};

export default defineComponent({
    name: 'TrustMarksView',
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
        RefreshCw,
        XCircle,
        Copy,
        Check,
    },
    data() {
        return {
            loading: true,
            error: null as string | null,
            trustMarks: null as TrustMarks | null,
            trustMarkTypes: null as TrustMarkTypes | null,
            columns: [
                { key: 'id', label: 'ID', width: '80px' },
                { key: 'domain', label: 'Domain' },
                { key: 'tmt', label: 'Type' },
                { key: 'expire_at', label: 'Expires', width: '180px' },
                { key: 'autorenew', label: 'Autorenew', width: '120px' },
                { key: 'active', label: 'Status', width: '100px' },
            ],
            // Modal state
            showCreateModal: false,
            showEditModal: false,
            showRevokeModal: false,
            formData: { ...defaultFormData },
            editingItem: null as TrustMark | null,
            revokingItem: null as TrustMark | null,
            formLoading: false,
            formError: null as string | null,
            copiedId: null as number | null,
            showTypeModal: false,
            viewingType: null as TrustMarkType | null,
            jsonError: null as string | null,
        };
    },
    computed: {
        hasJsonError(): boolean {
            return !!this.jsonError;
        },
        trustMarkTypesMap(): Map<number, TrustMarkType> {
            const map = new Map<number, TrustMarkType>();
            if (this.trustMarkTypes?.items) {
                for (const type of this.trustMarkTypes.items) {
                    map.set(type.id, type);
                }
            }
            return map;
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
                const [marks, types] = await Promise.all([
                    this.$sdk.listTrustMarks({ limit: 25 }),
                    this.$sdk.listTrustMarkTypes({ limit: 100 }),
                ]);
                this.trustMarks = marks;
                this.trustMarkTypes = types;
            } catch (e) {
                this.error = 'Failed to load trust marks. Please try again later.';
                console.error(e);
            } finally {
                this.loading = false;
            }
        },
        formatDate(dateStr: string): string {
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        },
        getTypeName(row: TrustMark): string {
            const type = this.trustMarkTypesMap.get(row.tmt_id);
            return type?.tmtype || 'Unknown';
        },
        openTypeModal(row: TrustMark) {
            const type = this.trustMarkTypesMap.get(row.tmt_id);
            if (type) {
                this.viewingType = type;
                this.showTypeModal = true;
            }
        },
        closeTypeModal() {
            this.showTypeModal = false;
            this.viewingType = null;
        },
        openCreateModal() {
            this.formData = { ...defaultFormData };
            this.formError = null;
            this.jsonError = null;
            this.showCreateModal = true;
        },
        openEditModal(item: TrustMark) {
            this.editingItem = item;
            this.formData = {
                tmt: null,
                domain: item.domain,
                autorenew: item.autorenew ?? true,
                active: item.active ?? true,
                additional_claims: item.additional_claims ?? {},
            };
            this.formError = null;
            this.jsonError = null;
            this.showEditModal = true;
        },
        openRevokeModal(item: TrustMark) {
            this.revokingItem = item;
            this.showRevokeModal = true;
        },
        closeModals() {
            this.showCreateModal = false;
            this.showEditModal = false;
            this.showRevokeModal = false;
            this.showTypeModal = false;
            this.editingItem = null;
            this.revokingItem = null;
            this.viewingType = null;
            this.formError = null;
            this.jsonError = null;
        },
        setJsonError(error: string | null) {
            this.jsonError = error;
        },
        async handleCreate() {
            if (!this.formData.tmt) {
                this.formError = 'Please select a trust mark type';
                return;
            }
            if (this.hasJsonError) {
                this.formError = 'Please fix JSON syntax errors before submitting';
                return;
            }
            this.formLoading = true;
            this.formError = null;
            try {
                const trustMark = await this.$sdk.createTrustMark({
                    tmt: this.formData.tmt,
                    domain: this.formData.domain,
                    autorenew: this.formData.autorenew,
                    active: this.formData.active,
                    additional_claims: this.formData.additional_claims,
                });
                // Copy the trustmark JWT to clipboard
                if (trustMark.mark) {
                    await this.copyToClipboard(trustMark.mark, trustMark.id);
                }
                this.closeModals();
                await this.loadData();
            } catch (e: any) {
                this.formError = e.message || 'Failed to create trust mark';
                console.error(e);
            } finally {
                this.formLoading = false;
            }
        },
        async handleUpdate() {
            if (!this.editingItem) return;
            if (this.hasJsonError) {
                this.formError = 'Please fix JSON syntax errors before submitting';
                return;
            }
            this.formLoading = true;
            this.formError = null;
            try {
                await this.$sdk.updateTrustMark(this.editingItem.id, {
                    autorenew: this.formData.autorenew,
                    active: this.formData.active,
                    additional_claims: this.formData.additional_claims,
                });
                this.closeModals();
                await this.loadData();
            } catch (e: any) {
                this.formError = e.message || 'Failed to update trust mark';
                console.error(e);
            } finally {
                this.formLoading = false;
            }
        },
        async handleRenew(item: TrustMark) {
            try {
                await this.$sdk.renewTrustMark(item.id);
                await this.loadData();
            } catch (e: any) {
                this.error = e.message || 'Failed to renew trust mark';
                console.error(e);
            }
        },
        async handleRevoke() {
            if (!this.revokingItem) return;
            this.formLoading = true;
            this.formError = null;
            try {
                await this.$sdk.updateTrustMark(this.revokingItem.id, {
                    active: false,
                });
                this.closeModals();
                await this.loadData();
            } catch (e: any) {
                this.formError = e.message || 'Failed to revoke trust mark';
                console.error(e);
            } finally {
                this.formLoading = false;
            }
        },
        async copyToClipboard(text: string, id: number) {
            try {
                await navigator.clipboard.writeText(text);
                this.copiedId = id;
                // Reset after 2 seconds
                setTimeout(() => {
                    this.copiedId = null;
                }, 2000);
            } catch (e) {
                console.error('Failed to copy to clipboard:', e);
            }
        },
        async handleCopyMark(item: TrustMark) {
            if (item.mark) {
                await this.copyToClipboard(item.mark, item.id);
            }
        },
    },
});
</script>

<template>
    <div class="trust-marks-view">
        <header class="page-header">
            <Heading level="h1">Trust marks</Heading>
            <Button @click="openCreateModal">
                <Plus :size="18" />
                Issue Trust Mark
            </Button>
        </header>

        <p v-if="error" class="error-message">{{ error }}</p>

        <DataTable
            :columns="columns"
            :data="trustMarks?.items || []"
            :loading="loading"
            empty-message="No trust marks found. Issue one to get started."
        >
            <template #cell-domain="{ value, row }">
                <div class="domain-cell">
                    <code class="domain-url">{{ value }}</code>
                    <button
                        type="button"
                        class="copy-btn"
                        :class="{ 'copy-btn--copied': copiedId === (row as TrustMark).id }"
                        @click="handleCopyMark(row as TrustMark)"
                        :disabled="!(row as TrustMark).mark"
                        :title="(row as TrustMark).mark ? 'Copy trust mark JWT' : 'No trust mark available'"
                    >
                        <Check v-if="copiedId === (row as TrustMark).id" :size="14" />
                        <Copy v-else :size="14" />
                    </button>
                </div>
            </template>
            <template #cell-tmt="{ row }">
                <button
                    type="button"
                    class="type-link"
                    @click="openTypeModal(row as TrustMark)"
                    :title="getTypeName(row as TrustMark)"
                >
                    {{ getTypeName(row as TrustMark) }}
                </button>
            </template>
            <template #cell-expire_at="{ value }">
                {{ formatDate(value as string) }}
            </template>
            <template #cell-autorenew="{ value }">
                <Badge :variant="value ? 'success' : 'neutral'" size="sm">
                    {{ value ? 'enabled' : 'disabled' }}
                </Badge>
            </template>
            <template #cell-active="{ value }">
                <Badge :variant="value ? 'success' : 'danger'" size="sm">
                    {{ value ? 'active' : 'revoked' }}
                </Badge>
            </template>
            <template #actions="{ row }">
                <div class="action-buttons">
                    <Button variant="ghost" size="sm" @click="openEditModal(row as TrustMark)">
                        <Pencil :size="16" />
                        Edit
                    </Button>
                    <Button variant="ghost" size="sm" @click="handleRenew(row as TrustMark)" v-if="(row as TrustMark).active">
                        <RefreshCw :size="16" />
                        Renew
                    </Button>
                    <Button variant="ghost" size="sm" @click="openRevokeModal(row as TrustMark)" v-if="(row as TrustMark).active">
                        <XCircle :size="16" />
                        Revoke
                    </Button>
                </div>
            </template>
        </DataTable>

        <!-- Create Modal -->
        <Modal :open="showCreateModal" title="Issue Trust Mark" @close="closeModals">
            <form @submit.prevent="handleCreate" class="form">
                <div class="form-group">
                    <label class="form-label">Trust Mark Type <span class="required">*</span></label>
                    <select v-model="formData.tmt" class="form-select" required>
                        <option :value="null" disabled>Select a type...</option>
                        <option
                            v-for="type in trustMarkTypes?.items.filter(t => t.active)"
                            :key="type.id"
                            :value="type.id"
                        >
                            {{ type.tmtype }}
                        </option>
                    </select>
                </div>
                <Input
                    v-model="formData.domain"
                    label="Entity Domain"
                    type="url"
                    placeholder="https://example-rp.com"
                    required
                />
                <div class="form-toggles">
                    <Toggle v-model="formData.autorenew" label="Auto-renew" />
                    <Toggle v-model="formData.active" label="Active" />
                </div>
                <JsonEditor
                    v-model="formData.additional_claims"
                    label="Additional Claims (optional)"
                    placeholder='{ "key": "value" }'
                    :rows="4"
                    @error="setJsonError"
                />
                <p v-if="formError" class="form-error">{{ formError }}</p>
            </form>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Cancel</Button>
                <Button @click="handleCreate" :loading="formLoading" :disabled="hasJsonError">Issue Trust Mark</Button>
            </template>
        </Modal>

        <!-- Edit Modal -->
        <Modal :open="showEditModal" title="Edit Trust Mark" @close="closeModals">
            <form @submit.prevent="handleUpdate" class="form">
                <Input
                    :model-value="formData.domain"
                    label="Entity Domain"
                    type="url"
                    disabled
                />
                <div class="form-toggles">
                    <Toggle v-model="formData.autorenew" label="Auto-renew" />
                    <Toggle v-model="formData.active" label="Active" />
                </div>
                <JsonEditor
                    v-model="formData.additional_claims"
                    label="Additional Claims (optional)"
                    placeholder='{ "key": "value" }'
                    :rows="4"
                    @error="setJsonError"
                />
                <p v-if="formError" class="form-error">{{ formError }}</p>
            </form>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Cancel</Button>
                <Button @click="handleUpdate" :loading="formLoading" :disabled="hasJsonError">Save Changes</Button>
            </template>
        </Modal>

        <!-- Revoke Confirmation Modal -->
        <Modal :open="showRevokeModal" title="Revoke Trust Mark" size="sm" @close="closeModals">
            <p>Are you sure you want to revoke this trust mark?</p>
            <p v-if="revokingItem"><strong>{{ revokingItem.domain }}</strong></p>
            <p class="warning-text">This action will invalidate the trust mark. The entity will no longer be trusted for this mark type.</p>
            <p v-if="formError" class="form-error">{{ formError }}</p>
            <template #footer>
                <Button variant="secondary" @click="closeModals">Cancel</Button>
                <Button variant="danger" @click="handleRevoke" :loading="formLoading">Revoke</Button>
            </template>
        </Modal>

        <!-- Trust Mark Type Details Modal -->
        <Modal :open="showTypeModal" title="Trust Mark Type Details" @close="closeTypeModal">
            <div v-if="viewingType" class="type-details">
                <div class="detail-row">
                    <span class="detail-label">ID:</span>
                    <span class="detail-value">{{ viewingType.id }}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Type URL:</span>
                    <code class="detail-value detail-value--code">{{ viewingType.tmtype }}</code>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Auto-renew:</span>
                    <Badge :variant="viewingType.autorenew ? 'success' : 'neutral'" size="sm">
                        {{ viewingType.autorenew ? 'enabled' : 'disabled' }}
                    </Badge>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Valid for:</span>
                    <span class="detail-value">{{ viewingType.valid_for }} hours</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Renewal time:</span>
                    <span class="detail-value">{{ viewingType.renewal_time }} hours before expiration</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Status:</span>
                    <Badge :variant="viewingType.active ? 'success' : 'danger'" size="sm">
                        {{ viewingType.active ? 'active' : 'inactive' }}
                    </Badge>
                </div>
            </div>
            <template #footer>
                <Button variant="secondary" @click="closeTypeModal">Close</Button>
            </template>
        </Modal>
    </div>
</template>

<style scoped>
.trust-marks-view {
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

.domain-cell {
    display: flex;
    align-items: center;
    gap: var(--ir--space--2);
}

.domain-url {
    font-size: var(--ir--font-size--xs);
    background-color: var(--ir--color--gray-100);
    padding: 2px 6px;
    border-radius: 4px;
    word-break: break-all;
}

.copy-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 4px;
    border: none;
    border-radius: 4px;
    background-color: transparent;
    color: var(--ir--color--gray-500);
    cursor: pointer;
    transition: background-color 0.15s ease, color 0.15s ease;
}

.copy-btn:hover:not(:disabled) {
    background-color: var(--ir--color--gray-100);
    color: var(--ir--color--gray-700);
}

.copy-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
}

.copy-btn--copied {
    color: var(--ir--color--success);
}

.type-link {
    font-size: var(--ir--font-size--xs);
    color: var(--ir--color--primary);
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 2px;
    text-align: left;
    word-break: break-all;
}

.type-link:hover {
    color: var(--ir--color--primary-dark, #1d4ed8);
}

/* Type details modal */
.type-details {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--3);
}

.detail-row {
    display: flex;
    align-items: flex-start;
    gap: var(--ir--space--2);
}

.detail-label {
    font-weight: 500;
    color: var(--ir--color--gray-600);
    min-width: 100px;
    flex-shrink: 0;
}

.detail-value {
    color: var(--ir--color--gray-900);
}

.detail-value--code {
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

.form-group {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--1);
}

.form-label {
    font-size: var(--ir--font-size--s);
    font-weight: 500;
    color: #374151;
}

.required {
    color: var(--ir--color--danger);
}

.form-select {
    padding: var(--ir--space--2) var(--ir--space--3);
    border: var(--ir--border);
    border-radius: var(--ir--space--1);
    font-family: var(--ir--font-family);
    font-size: var(--ir--font-size--s);
    color: #1f2937;
    background-color: white;
}

.form-select:focus {
    outline: none;
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
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
