#!/bin/bash
set -e

echo "=== Worker Starting ==="
echo "Repository: ${REPO_URL}"
echo "Branch: ${BRANCH:-main}"
echo "Target URL: ${TARGET_URL:-http://localhost:5173}"

# Validate required environment variables
if [ -z "$REPO_URL" ]; then
  echo "Error: REPO_URL is required"
  exit 1
fi

# Step 1: Clone repository
echo "=== Cloning repository ==="
git clone --depth 1 --branch "${BRANCH:-main}" "$REPO_URL" /workspace/repo
cd /workspace/repo

# Step 2: Apply patch (if provided)
if [ -n "$PATCH_CONTENT" ]; then
  echo "=== Applying patch ==="
  echo "$PATCH_CONTENT" | git apply -v
fi

# Step 3: Install dependencies
echo "=== Installing dependencies ==="
if [ -f "package-lock.json" ]; then
  npm ci
elif [ -f "pnpm-lock.yaml" ]; then
  npm install -g pnpm
  pnpm install
else
  npm install
fi

# Step 4: Build project (background)
echo "=== Building and starting dev server ==="
npm run dev &
DEV_SERVER_PID=$!

# Wait for dev server to be ready
echo "=== Waiting for dev server ==="
for i in {1..60}; do
  if curl -s "${TARGET_URL:-http://localhost:5173}" > /dev/null; then
    echo "Dev server is ready"
    break
  fi
  echo "Waiting... ($i/60)"
  sleep 2
done

# Step 5: Take screenshot with Playwright
echo "=== Taking screenshot ==="
node - <<'EOF'
import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(process.env.TARGET_URL || 'http://localhost:5173');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: '/workspace/screenshot.png', fullPage: true });
  await browser.close();
  console.log('Screenshot saved to /workspace/screenshot.png');
})();
EOF

# Step 6: Cleanup
kill $DEV_SERVER_PID || true

echo "=== Worker Completed ==="
echo "Screenshot saved at: /workspace/screenshot.png"

# Keep container running to allow file extraction
tail -f /dev/null
