import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}", "components/**/*.test.{ts,tsx}"],
    globals: false,
    env: { NEXT_PUBLIC_API_URL: "http://api.test" },
  },
});
