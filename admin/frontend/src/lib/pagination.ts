import { ref, shallowRef } from 'vue';

export const PAGE_SIZE = 25;

type Filters = { limit: number; offset: number };
type Page = { items: unknown[]; count: number };

/** Keep the displayed rows and their offset together until the next page succeeds. */
export function usePagedList<T extends Page>(label: string) {
    const page = shallowRef<T | null>(null);
    const offset = ref(0);
    const loading = ref(true);
    const error = ref<string | null>(null);
    let sequence = 0;

    async function loadPage(fetchPage: (filters: Filters) => Promise<T>, start = offset.value) {
        const request = ++sequence;
        loading.value = true;
        error.value = null;
        try {
            let result = await fetchPage({ limit: PAGE_SIZE, offset: start });
            // A concurrent deletion can remove the last page between visits.
            if (start > 0 && !result.items.length && request === sequence) {
                start = 0;
                result = await fetchPage({ limit: PAGE_SIZE, offset: start });
            }
            if (request === sequence) {
                page.value = result;
                offset.value = start;
            }
        } catch {
            if (request === sequence) error.value = `Failed to load ${label}. Please try again.`;
        } finally {
            if (request === sequence) loading.value = false;
        }
    }

    return { page, offset, loading, error, loadPage };
}
