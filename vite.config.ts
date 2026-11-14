import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base: './' makes the built site work from any sub-path,
// so the same build runs on Vercel and on GitHub Pages (username.github.io/repo/).
export default defineConfig({
  plugins: [react()],
  base: './',
});
