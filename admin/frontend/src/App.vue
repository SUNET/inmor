<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
  name: 'App',
  mounted() {

    if (this.$route.fullPath !== 'trustmark-types') {
        this.$router.push('/trustmark-types')
    }
  },
})
</script>

<template>
    <main>
        <RouterView />
    </main>
</template>
