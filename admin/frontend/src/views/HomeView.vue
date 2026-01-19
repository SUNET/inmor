<script lang="ts">
import { defineComponent } from 'vue';
import { FileLock2, Files, Server, ArrowRight } from 'lucide-vue-next';
import Heading from '../components/base/Heading.vue';

export default defineComponent({
    name: 'HomeView',
    components: { Heading, FileLock2, Files, Server, ArrowRight },
    data() {
        return {
            stats: {
                trustMarkTypes: 0,
                trustMarks: 0,
                subordinates: 0,
            },
            loading: true,
        };
    },
    async mounted() {
        await this.loadStats();
    },
    methods: {
        async loadStats() {
            this.loading = true;
            try {
                const [types, marks, subs] = await Promise.all([
                    this.$sdk.listTrustMarkTypes({ limit: 1 }),
                    this.$sdk.listTrustMarks({ limit: 1 }),
                    this.$sdk.listSubordinates({ limit: 1 }),
                ]);
                this.stats = {
                    trustMarkTypes: types.count,
                    trustMarks: marks.count,
                    subordinates: subs.count,
                };
            } catch (e) {
                console.error('Failed to load stats:', e);
            } finally {
                this.loading = false;
            }
        },
    },
});
</script>

<template>
    <div class="home-view">
        <Heading level="h1">Dashboard</Heading>

        <div class="stats-grid" aria-live="polite">
            <RouterLink to="/trustmark-types" class="stat-card">
                <div class="stat-icon stat-icon--types" aria-hidden="true">
                    <FileLock2 :size="24" />
                </div>
                <div class="stat-content">
                    <div class="stat-value">{{ loading ? '...' : stats.trustMarkTypes }}</div>
                    <div class="stat-label">Trust Mark Types</div>
                </div>
                <ArrowRight :size="20" class="stat-arrow" aria-hidden="true" />
            </RouterLink>

            <RouterLink to="/trustmarks" class="stat-card">
                <div class="stat-icon stat-icon--marks" aria-hidden="true">
                    <Files :size="24" />
                </div>
                <div class="stat-content">
                    <div class="stat-value">{{ loading ? '...' : stats.trustMarks }}</div>
                    <div class="stat-label">Trust Marks</div>
                </div>
                <ArrowRight :size="20" class="stat-arrow" aria-hidden="true" />
            </RouterLink>

            <RouterLink to="/subordinates" class="stat-card">
                <div class="stat-icon stat-icon--subs" aria-hidden="true">
                    <Server :size="24" />
                </div>
                <div class="stat-content">
                    <div class="stat-value">{{ loading ? '...' : stats.subordinates }}</div>
                    <div class="stat-label">Subordinates</div>
                </div>
                <ArrowRight :size="20" class="stat-arrow" aria-hidden="true" />
            </RouterLink>
        </div>

        <section class="quick-start" aria-labelledby="quick-start-heading">
            <Heading id="quick-start-heading" level="h2">Quick Start</Heading>
            <div class="quick-start-content">
                <ol class="quick-start-list">
                    <li>
                        <strong>Create Trust Mark Types</strong> - Define the types of trust marks your federation will issue
                    </li>
                    <li>
                        <strong>Register Subordinates</strong> - Add entities (OpenID Providers, Relying Parties) to your federation
                    </li>
                    <li>
                        <strong>Issue Trust Marks</strong> - Issue trust marks to verified subordinates
                    </li>
                </ol>
            </div>
        </section>
    </div>
</template>

<style scoped>
.home-view {
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--5);
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: var(--ir--space--4);
}

.stat-card {
    display: flex;
    align-items: center;
    gap: var(--ir--space--3);
    padding: var(--ir--space--4);
    background-color: white;
    border: var(--ir--border);
    border-radius: var(--ir--space--2);
    text-decoration: none;
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
}

.stat-card:hover {
    border-color: var(--ir--color--primary);
    box-shadow: var(--ir--box-shadow);
}

.stat-card:focus-visible {
    outline: 2px solid var(--ir--color--primary);
    outline-offset: 2px;
}

.stat-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    border-radius: var(--ir--space--2);
}

.stat-icon--types {
    background-color: var(--ir--color--info-bg);
    color: var(--ir--color--info);
}

.stat-icon--marks {
    background-color: var(--ir--color--success-bg);
    color: var(--ir--color--success);
}

.stat-icon--subs {
    background-color: var(--ir--color--warning-bg);
    color: var(--ir--color--warning);
}

.stat-content {
    flex: 1;
}

.stat-value {
    font-size: var(--ir--font-size--l);
    font-weight: var(--ir--font-weight--bold);
    color: var(--ir--color--gray-900);
    line-height: 1;
}

.stat-label {
    font-size: var(--ir--font-size--s);
    color: var(--ir--color--gray-500);
    margin-top: var(--ir--space--1);
}

.stat-arrow {
    color: var(--ir--color--gray-400);
    transition: color 0.15s ease, transform 0.15s ease;
}

.stat-card:hover .stat-arrow {
    color: var(--ir--color--primary);
    transform: translateX(4px);
}

.quick-start {
    background-color: var(--ir--color--gray-50);
    border-radius: var(--ir--space--2);
    padding: var(--ir--space--4);
}

.quick-start h2 {
    margin-top: 0;
}

.quick-start-list {
    margin: 0;
    padding-left: var(--ir--space--4);
    display: flex;
    flex-direction: column;
    gap: var(--ir--space--3);
}

.quick-start-list li {
    font-size: var(--ir--font-size--s);
    color: var(--ir--color--gray-700);
}

.quick-start-list strong {
    color: var(--ir--color--gray-900);
}
</style>
