<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";
import ResearchUseGate from "components/common/ResearchUseGate.vue";
import { useAuthStore } from "src/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const { researchUseAcknowledged, session } = storeToRefs(auth);

const gateOpen = ref(true);
const appVersion = ref("0.0.0");
const e2eMode = ref(false);

onMounted(async () => {
  const info = await window.mivw?.getAppInfo();
  if (info) {
    appVersion.value = info.version;
    e2eMode.value = info.e2e ?? false;
  }
});
</script>

<template>
  <q-layout view="hHh LpR fFf">
    <q-header elevated class="bg-dark">
      <q-toolbar>
        <q-toolbar-title class="text-subtitle1">
          MIVW Workstation
          <q-badge color="warning" text-color="black" class="q-ml-sm">
            Research Use Only
          </q-badge>
        </q-toolbar-title>

        <q-btn flat dense no-caps label="Worklist" :to="{ name: 'worklist' }" />
        <q-btn
          v-if="auth.canAdminister"
          flat
          dense
          no-caps
          label="Models"
          :to="{ name: 'models' }"
        />

        <q-separator vertical inset class="q-mx-sm" />

        <div v-if="session" class="text-caption q-mr-sm">
          {{ session.displayName }} · {{ session.role }}
        </div>
        <q-select
          v-if="e2eMode"
          :model-value="session?.role"
          :options="['viewer', 'annotator', 'researcher', 'admin']"
          dense
          borderless
          dark
          emit-value
          map-options
          data-testid="e2e-switch-role"
          aria-label="Switch role"
          @update:model-value="auth.setRole"
        />
        <q-btn
          flat
          dense
          icon="logout"
          aria-label="Sign out"
          @click="auth.signOut()"
        />
      </q-toolbar>
    </q-header>

    <q-page-container>
      <router-view v-if="researchUseAcknowledged" />
    </q-page-container>

    <q-footer class="bg-dark text-caption">
      <div class="row items-center justify-between q-px-md q-py-xs">
        <span>Not for clinical use · v{{ appVersion }}</span>
        <span>{{ router.currentRoute.value.name }}</span>
      </div>
    </q-footer>

    <ResearchUseGate
      v-model="gateOpen"
      @acknowledge="auth.acknowledgeResearchUse()"
    />
  </q-layout>
</template>
