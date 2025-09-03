<script lang="ts">
import { defineComponent } from 'vue';
import { RouterView, useRouter, useRoute } from 'vue-router';

export default defineComponent({
  name: 'App',
  mounted() {
    const route = useRoute();
    const router = useRouter();

    if (route.fullPath !== 'trustmark-types') {
      router.push('/trustmark-types')
    }
  },
})
</script>

<template>
  <main>
    <RouterView />
  </main>
</template>