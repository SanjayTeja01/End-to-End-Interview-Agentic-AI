import { defineConfig } from "@playwright/test";

// Requires the full stack (docker compose up) and seeded demo data (scripts/seed.py).
export default defineConfig({
  testDir: "tests/e2e",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    permissions: ["camera", "microphone"],
    launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] },
  },
});
