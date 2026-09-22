import { defineRouter } from "@quasar/app-vite";
import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
} from "vue-router";
import routes from "./routes";

export default defineRouter(() => {
  const createHistory = import.meta.env.SSR
    ? createMemoryHistory
    : createWebHashHistory;

  return createRouter({
    scrollBehavior: () => ({ left: 0, top: 0 }),
    routes,
    history: createHistory(import.meta.env.BASE_URL),
  });
});
