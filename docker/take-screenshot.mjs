import { chromium } from 'playwright';

const targetUrl = process.argv[2] || 'http://localhost:5173';
const outputPath = process.argv[3] || '/workspace/screenshot.png';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: outputPath, fullPage: true });
  await browser.close();
  console.log(`Screenshot saved to ${outputPath}`);
})();
