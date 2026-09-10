<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";
import StudyTable from "components/worklist/StudyTable.vue";
import { useStudiesStore } from "src/stores/studies";

const router = useRouter();
const studies = useStudiesStore();
const {
  studies: rows,
  isLoading,
  error,
  filters,
  hasMore,
  series,
  selectedStudyId,
} = storeToRefs(studies);

const modality = ref<string | null>(null);
const patientRef = ref("");

onMounted(() => void studies.fetchStudies());

watch([modality], () => {
  studies.setFilters({ modality: modality.value });
  void studies.fetchStudies();
});

function search(): void {
  studies.setFilters({ patientRef: patientRef.value || null });
  void studies.fetchStudies();
}

async function openStudy(studyId: string): Promise<void> {
  await studies.selectStudy(studyId);
  if (studies.selectedSeriesId) {
    await router.push({
      name: "viewer",
      params: { seriesId: studies.selectedSeriesId },
    });
  }
}
</script>

<template>
  <q-page padding>
    <div class="row items-end q-gutter-md q-mb-md">
      <q-select
        v-model="modality"
        :options="['CT', 'MR', 'PT']"
        label="Modality"
        clearable
        dense
        outlined
        style="min-width: 140px"
        aria-label="Filter by modality"
      />
      <q-input
        v-model="patientRef"
        label="Patient reference"
        dense
        outlined
        clearable
        style="min-width: 240px"
        aria-label="Search by patient reference"
        @keyup.enter="search"
      >
        <template #append>
          <q-btn flat dense icon="search" aria-label="Search" @click="search" />
        </template>
      </q-input>
    </div>

    <StudyTable
      :studies="rows"
      :selected-id="selectedStudyId"
      :loading="isLoading"
      :error="error"
      @select="openStudy"
    />

    <div v-if="hasMore" class="row justify-center q-mt-md">
      <q-btn
        flat
        no-caps
        label="Load more"
        :loading="isLoading"
        @click="studies.fetchStudies({ append: true })"
      />
    </div>

    <q-banner
      v-if="studies.quarantinedCount > 0"
      dense
      class="bg-orange-9 text-white q-mt-md"
      role="status"
    >
      {{ studies.quarantinedCount }} series quarantined pending burned-in
      annotation review.
    </q-banner>

    <p v-if="series.length" class="text-caption q-mt-md">
      {{ series.length }} series in the selected study.
    </p>
  </q-page>
</template>
