<script lang="ts">
import { defineComponent } from 'vue';
import Layout from './components/site/Layout.vue';

export default defineComponent({
  name: 'App',
  components: { Layout },
  mounted() {

    // if (this.$route.fullPath !== 'trustmark-types') {
    //     this.$router.push('/trustmark-types')
    // }
  },
})
</script>

<template>
    <Layout>
        <RouterView />
    </Layout>
</template>
