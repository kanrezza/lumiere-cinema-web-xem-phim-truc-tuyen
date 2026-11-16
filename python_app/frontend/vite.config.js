import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../static/bundles/catalog',
    emptyOutDir: true,
    manifest: 'manifest.json',
    rollupOptions: {
      input: {
        results: 'src/catalog/main.ts',
        home: 'src/home/main.ts',
        shell: 'src/shell/main.ts',
        public: 'src/public/main.ts',
        viewing: 'src/viewing/main.ts',
        studio: 'src/studio/main.ts',
      },
    },
  },
})
