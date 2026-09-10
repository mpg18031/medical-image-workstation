import { fileURLToPath } from "node:url";
import type { StorybookConfig } from "@storybook/vue3-vite";
import vue from "@vitejs/plugin-vue";
import { quasar, transformAssetUrls } from "@quasar/vite-plugin";

const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: [
    "@storybook/addon-essentials",
    "@storybook/addon-interactions",
    "@storybook/addon-a11y",
  ],
  framework: { name: "@storybook/vue3-vite", options: {} },
  core: { disableTelemetry: true },
  typescript: { check: false },

  // The framework preset supplies neither the Quasar SFC transform nor the
  // project's path aliases, so both are added explicitly.
  viteFinal(viteConfig) {
    viteConfig.plugins = [
      ...(viteConfig.plugins ?? []),
      vue({ template: { transformAssetUrls } }),
      quasar(),
    ];

    viteConfig.resolve = {
      ...viteConfig.resolve,
      alias: {
        ...(viteConfig.resolve?.alias as Record<string, string>),
        src: fileURLToPath(new URL("../src", import.meta.url)),
        components: fileURLToPath(
          new URL("../src/components", import.meta.url),
        ),
        stores: fileURLToPath(new URL("../src/stores", import.meta.url)),
        layouts: fileURLToPath(new URL("../src/layouts", import.meta.url)),
        pages: fileURLToPath(new URL("../src/pages", import.meta.url)),
      },
    };

    return viteConfig;
  },
};

export default config;
