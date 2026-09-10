<script setup lang="ts">
import { computed } from "vue";
import type { StudySummary } from "src/services/types";

const props = withDefaults(
  defineProps<{
    studies: StudySummary[];
    selectedId?: string | null;
    loading?: boolean;
    error?: string | null;
  }>(),
  { selectedId: null, loading: false, error: null },
);

const emit = defineEmits<{ select: [string] }>();

const isEmpty = computed(
  () => !props.loading && props.error === null && props.studies.length === 0,
);

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}
</script>

<template>
  <div class="study-table">
    <q-banner v-if="error" dense class="bg-negative text-white" role="alert">
      <template #avatar><q-icon name="error" /></template>
      {{ error }}
    </q-banner>

    <div v-if="loading" class="q-pa-md" data-testid="study-table-loading">
      <q-skeleton
        v-for="n in 5"
        :key="n"
        type="rect"
        height="36px"
        class="q-mb-sm"
      />
      <span class="sr-only" role="status">Loading studies</span>
    </div>

    <div
      v-else-if="isEmpty"
      class="q-pa-xl text-center text-grey-6"
      data-testid="study-table-empty"
    >
      <q-icon name="search_off" size="48px" aria-hidden="true" />
      <p class="q-mt-md">No studies match the current filters.</p>
    </div>

    <table
      v-else
      class="study-table__grid full-width"
      data-testid="study-table"
    >
      <caption class="sr-only">
        Available studies
      </caption>
      <thead>
        <tr>
          <th scope="col">Patient</th>
          <th scope="col">Study date</th>
          <th scope="col">Description</th>
          <th scope="col">Modality</th>
          <th scope="col">Series</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="study in studies"
          :key="study.id"
          :aria-selected="study.id === selectedId"
          :class="{ 'study-table__row--selected': study.id === selectedId }"
          tabindex="0"
          @click="emit('select', study.id)"
          @keydown.enter="emit('select', study.id)"
          @keydown.space.prevent="emit('select', study.id)"
        >
          <td>{{ study.patient.pseudonym }}</td>
          <td>{{ formatDate(study.studyDatetime) }}</td>
          <td>{{ study.description ?? "—" }}</td>
          <td>
            <q-badge v-for="m in study.modalities" :key="m" class="q-mr-xs">{{
              m
            }}</q-badge>
          </td>
          <td>{{ study.seriesCount }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped lang="scss">
.study-table__grid {
  border-collapse: collapse;

  th,
  td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  tbody tr {
    cursor: pointer;

    &:hover,
    &:focus-visible {
      background: rgba(255, 255, 255, 0.06);
    }
  }
}

.study-table__row--selected {
  background: rgba(25, 118, 210, 0.24);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
