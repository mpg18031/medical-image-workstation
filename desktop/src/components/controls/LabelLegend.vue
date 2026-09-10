<script setup lang="ts">
import { computed } from "vue";
import type { LabelInfo } from "src/services/types";

const props = withDefaults(
  defineProps<{
    labels: Record<string, LabelInfo>;
    visible: Set<number>;
    stats?: Record<string, { volumeMl?: number }>;
    disabled?: boolean;
  }>(),
  { stats: () => ({}), disabled: false },
);

const emit = defineEmits<{
  toggle: [index: number, visible: boolean];
  showAll: [];
}>();

const entries = computed(() =>
  Object.entries(props.labels)
    .map(([key, info]) => ({
      index: Number(key),
      ...info,
      volumeMl: props.stats[key]?.volumeMl ?? null,
    }))
    .sort((a, b) => a.index - b.index),
);

const allVisible = computed(() =>
  entries.value.every((e) => props.visible.has(e.index)),
);
</script>

<template>
  <div class="label-legend">
    <div class="row items-center justify-between q-mb-sm">
      <h3 class="text-subtitle2 q-my-none">Labels</h3>
      <q-btn
        flat
        dense
        size="sm"
        label="Show all"
        :disable="disabled || allVisible"
        data-testid="label-show-all"
        @click="emit('showAll')"
      />
    </div>

    <p
      v-if="entries.length === 0"
      class="text-grey-6"
      data-testid="label-legend-empty"
    >
      No segmentation loaded.
    </p>

    <ul v-else class="label-legend__list" role="list">
      <li v-for="entry in entries" :key="entry.index" role="listitem">
        <q-checkbox
          :model-value="visible.has(entry.index)"
          :disable="disabled"
          :aria-label="`Show ${entry.name}`"
          dense
          @update:model-value="(v: boolean) => emit('toggle', entry.index, v)"
        >
          <span
            class="label-legend__swatch"
            :style="{ backgroundColor: entry.color }"
            aria-hidden="true"
          />
          <span class="label-legend__name">{{ entry.name }}</span>
          <span v-if="entry.volumeMl !== null" class="label-legend__volume">
            {{ entry.volumeMl.toFixed(1) }} mL
          </span>
        </q-checkbox>
      </li>
    </ul>
  </div>
</template>

<style scoped lang="scss">
.label-legend__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.label-legend__swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 8px;
  border-radius: 2px;
  // Colour alone must not carry meaning; the name is always adjacent.
  border: 1px solid rgba(255, 255, 255, 0.4);
}

.label-legend__volume {
  margin-left: 8px;
  opacity: 0.7;
  font-variant-numeric: tabular-nums;
}
</style>
