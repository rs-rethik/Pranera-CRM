import { defineConfig } from 'vitest/config'
import path from 'path'

// Kept separate from vite.config.js: the tests only cover pure logic, so they
// don't need the frappe-ui / PWA plugins.
export default defineConfig({
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  test: { environment: 'node', include: ['tests/**/*.test.js'] },
})
