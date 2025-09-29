<script lang="ts">
import { defineComponent } from 'vue';
import TrustMarkTypesList from '../components/TrustMarkTypesList.vue';
import Heading from '../components/base/Heading.vue';

export default defineComponent({
    components: { Heading, TrustMarkTypesList }
});
</script>

<template>
    <Heading level="h1">Trust mark types</Heading>
    <TrustMarkTypesList />
</template>
