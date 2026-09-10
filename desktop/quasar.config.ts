import { defineConfig } from "#q-app/wrappers";

export default defineConfig((ctx) => ({
  boot: ["pinia", "bridge"],
  css: ["app.scss"],
  extras: ["roboto-font", "material-icons"],

  build: {
    target: { browser: ["es2022"], node: "node20" },
    typescript: { strict: true, vueShim: true },
    vueRouterMode: "hash", // file:// in a packaged Electron app has no history API
    sourcemap: ctx.debug,
    env: {
      MIVW_API_ORIGIN: process.env.MIVW_API_ORIGIN ?? "http://127.0.0.1:8000",
      MIVW_OIDC_ISSUER:
        process.env.MIVW_OIDC_ISSUER ?? "http://127.0.0.1:8080/realms/mivw",
      MIVW_OIDC_CLIENT_ID:
        process.env.MIVW_OIDC_CLIENT_ID ?? "mivw-workstation",
      MIVW_DEV_USERNAME: process.env.MIVW_DEV_USERNAME ?? "researcher",
      MIVW_DEV_PASSWORD:
        process.env.MIVW_DEV_PASSWORD ?? "devonly_not_for_deployment",
      MIVW_E2E: process.env.MIVW_E2E ?? "0",
    },
  },

  devServer: {
    open: false,
    port: 9300,
    forwardConsole: { unhandledErrors: false, logLevels: ["error", "warn"] },
  },

  framework: {
    config: { dark: true }, // reading rooms are dim
    plugins: ["Notify", "Dialog", "Loading"],
  },

  electron: {
    preloadScripts: ["electron-preload"],
    inspectPort: 5858,
    bundler: "builder",
    builder: {
      appId: "health.research.mivw",
      productName: "MIVW Workstation",
      asar: true,
      asarUnpack: ["**/*.node"],
      afterSign: "build/notarize.cjs",
      mac: {
        hardenedRuntime: true,
        gatekeeperAssess: false,
        category: "public.app-category.medical",
      },
      win: {
        signingHashAlgorithms: ["sha256"],
      },
      linux: {
        target: ["AppImage", "deb"],
        category: "Science",
      },
    },
  },

  sourceFiles: {
    electronMain: "src-electron/electron-main.ts",
  },
}));
