<script lang="ts">
import { defineComponent } from 'vue';
import { type TrustMarkTypes } from '../lib/admin-sdk';

export default defineComponent({
  name: 'TrustMarkTypesList',
  data() {
    return {
      loading: true,
      error: null as string | null,
      trustMarkTypes: null as TrustMarkTypes | null,
    };
  },
  async mounted() {
    try {
      this.trustMarkTypes = await this.$sdk.getTrustMarkTypes();
    } catch (e) {
      this.error = 'Failed to load trust mark types. Please try again later.';
      console.error(e);
    } finally {
      this.loading = false;
    }
  },
});
</script>

<template>
  <p v-if="loading">Loading trust mark types...</p>
  <p v-else-if="error" class="error">{{ error }}</p>
  <p v-else-if="!trustMarkTypes?.items?.length">
    No trust mark types available.
  </p>
  <ul v-else>
    <li v-for="item in trustMarkTypes.items" :key="item.tmtype">
      {{ item.tmtype }}
    </li>
  </ul>
</template>
