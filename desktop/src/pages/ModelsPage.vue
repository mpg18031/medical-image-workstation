<script setup lang="ts">
import { onMounted } from "vue";
import { storeToRefs } from "pinia";
import { useModelsStore } from "src/stores/models";

const models = useModelsStore();
const { models: rows, isLoading, error } = storeToRefs(models);

onMounted(() => void models.load());
</script>

<template>
  <q-page padding>
    <h1 class="text-h6">Model registry</h1>
    <q-banner v-if="error" dense class="bg-negative text-white" role="alert">{{
      error
    }}</q-banner>
    <q-list v-else bordered separator>
      <q-item v-for="m in rows" :key="m.id">
        <q-item-section>
          <q-item-label>{{ m.name }} {{ m.version }}</q-item-label>
          <q-item-label caption>
            {{ m.outputKind }} · {{ m.inputSpec.spacingMm.join(" × ") }} mm ·
            {{ m.validatedAt ? "validated" : "not validated" }}
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-badge :color="m.isEnabled ? 'positive' : 'grey'">
            {{ m.isEnabled ? "enabled" : "disabled" }}
          </q-badge>
        </q-item-section>
      </q-item>
    </q-list>
    <q-inner-loading :showing="isLoading" />
  </q-page>
</template>
