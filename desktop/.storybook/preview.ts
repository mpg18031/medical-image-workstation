import type { Preview } from '@storybook/vue3';
import { Quasar } from 'quasar';
import { setup } from '@storybook/vue3';
import 'quasar/src/css/index.sass';

setup((app) => {
  app.use(Quasar, {});
});

const preview: Preview = {
  parameters: {
    // Reading rooms are dim; the dark theme is the real default.
    backgrounds: {
      default: 'workstation',
      values: [
        { name: 'workstation', value: '#101014' },
        { name: 'light', value: '#ffffff' },
      ],
    },
    a11y: {
      // Accessibility violations fail the build: a clinical tool that only
      // works with a mouse is not acceptable.
      test: 'error',
    },
    controls: { matchers: { color: /(background|color)$/i } },
  },
};

export default preview;
