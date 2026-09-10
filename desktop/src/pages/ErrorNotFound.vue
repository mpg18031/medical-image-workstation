<template>
  <q-page class="column flex-center">
    <q-icon name="error_outline" size="64px" color="grey-6" />
    <h1 class="text-h5 q-mt-md">Page not found</h1>
    <q-btn
      flat
      no-caps
      label="Back to worklist"
      :to="{ name: 'worklist' }"
      class="q-mt-md"
    />
  </q-page>
</template>
