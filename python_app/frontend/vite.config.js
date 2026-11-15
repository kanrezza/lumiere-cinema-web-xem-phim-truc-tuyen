import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../static/bundles/catalog',
    emptyOutDir: true,
    manifest: 'manifest.json',
    rollupOptions: { input: 'src/catalog/main.ts' },
  },
})
