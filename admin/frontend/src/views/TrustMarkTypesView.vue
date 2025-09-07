<script lang="ts">
import { defineComponent } from 'vue';
import TrustMarkTypesList from '../components/TrustMarkTypesList.vue';

export default defineComponent({
  components: { TrustMarkTypesList }
});
</script>

<template>
  <h1>TrustMarkTypes</h1>
  <TrustMarkTypesList />
</template>
