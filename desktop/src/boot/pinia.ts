import { defineBoot } from "@quasar/app-vite";
import { createPinia } from "pinia";

export default defineBoot(({ app }) => {
  app.use(createPinia());
});
