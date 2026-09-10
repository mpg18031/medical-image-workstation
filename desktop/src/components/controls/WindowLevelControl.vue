<script setup lang="ts">
import { computed } from 'vue';

const MIN_WIDTH = 1;
const MAX_WIDTH = 4000;

const props = withDefaults(
  defineProps<{
    center: number;
    width: number;
    disabled?: boolean;
  }>(),
  { disabled: false },
);

const emit = defineEmits<{
  change: [{ center: number; width: number }];
}>();

const widthText = computed(() => `${Math.round(props.width)} Hounsfield units`);
const centerText = computed(() => `${Math.round(props.center)} Hounsfield units`);

function emitWidth(next: number | null): void {
  // A non-positive width divides by zero in the shader's window transform.
  const clamped = Math.min(Math.max(next ?? MIN_WIDTH, MIN_WIDTH), MAX_WIDTH);
  emit('change', { center: props.center, width: clamped });
}

function emitCenter(next: number | null): void {
  emit('change', { center: next ?? 0, width: props.width });
}
</script>

<template>
  <div class="window-level-control column q-gutter-sm">
    <q-slider
      :model-value="props.center"
      :min="-1000"
      :max="1000"
      :step="1"
      :disable="props.disabled"
      label
      aria-label="Window center"
      :aria-valuenow="props.center"
      :aria-valuetext="centerText"
      @update:model-value="emitCenter"
    />
    <q-slider
      :model-value="props.width"
      :min="MIN_WIDTH"
      :max="MAX_WIDTH"
      :step="1"
      :disable="props.disabled"
      label
      aria-label="Window width"
      :aria-valuenow="props.width"
      :aria-valuetext="widthText"
      @update:model-value="emitWidth"
    />
  </div>
</template>
