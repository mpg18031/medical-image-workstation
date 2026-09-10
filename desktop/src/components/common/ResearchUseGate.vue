<script setup lang="ts">
import { ref } from "vue";

defineProps<{ modelValue: boolean }>();

const emit = defineEmits<{
  "update:modelValue": [boolean];
  acknowledge: [];
}>();

const confirmed = ref(false);

function acknowledge(): void {
  if (!confirmed.value) return;
  emit("acknowledge");
  emit("update:modelValue", false);
}
</script>

<template>
  <q-dialog
    :model-value="modelValue"
    persistent
    no-esc-dismiss
    no-backdrop-dismiss
    role="dialog"
    aria-labelledby="ruo-title"
  >
    <q-card class="research-use-gate" style="max-width: 560px">
      <q-card-section class="row items-center q-gutter-sm">
        <q-icon name="warning" color="warning" size="32px" aria-hidden="true" />
        <h2 id="ruo-title" class="text-h6 q-my-none">Research Use Only</h2>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <p>
          This software is <strong>not</strong> a cleared or approved medical
          device in any jurisdiction. It has not been evaluated by the FDA and
          is not CE-marked under the EU MDR.
        </p>
        <p>
          It must <strong>not</strong> be used for primary diagnosis, treatment
          planning, or any clinical decision-making. All output, including
          AI-generated segmentations, is for research purposes only and requires
          independent verification.
        </p>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <q-checkbox
          v-model="confirmed"
          data-testid="ruo-confirm"
          label="I understand and will not use this software for clinical purposes"
        />
      </q-card-section>

      <q-card-actions align="right">
        <q-btn
          flat
          color="primary"
          label="Acknowledge"
          :disable="!confirmed"
          data-testid="ruo-acknowledge"
          @click="acknowledge"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>
