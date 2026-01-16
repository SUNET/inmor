<script lang="ts">
import { defineComponent } from 'vue';
import Layout from './components/site/Layout.vue';

export default defineComponent({
  name: 'App',
  components: { Layout },
  computed: {
    showLayout(): boolean {
      return this.$route.meta.layout !== 'none';
    },
  },
});
</script>

<template>
    <Layout v-if="showLayout">
        <RouterView />
    </Layout>
    <RouterView v-else />
</template>
