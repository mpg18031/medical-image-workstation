import type { RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    component: () => import("layouts/MainLayout.vue"),
    children: [
      {
        path: "",
        name: "worklist",
        component: () => import("pages/WorklistPage.vue"),
      },
      {
        path: "viewer/:seriesId",
        name: "viewer",
        props: true,
        component: () => import("pages/ViewerPage.vue"),
      },
      {
        path: "models",
        name: "models",
        component: () => import("pages/ModelsPage.vue"),
      },
    ],
  },
  {
    path: "/:catchAll(.*)*",
    component: () => import("pages/ErrorNotFound.vue"),
  },
];

export default routes;
