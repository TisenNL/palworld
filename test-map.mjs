import { chromium } from 'playwright';

async function testMap() {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  // Listen for console messages
  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    console.log(`[Browser ${type}] ${text}`);
  });
  
  // Listen for page errors
  page.on('pageerror', error => {
    console.error(`[Browser Error] ${error.message}`);
  });
  
  // Navigate to the app
  console.log('Opening http://127.0.0.1:5173/');
  await page.goto('http://127.0.0.1:5173/');
  
  // Wait for the page to load
  await page.waitForTimeout(2000);
  
  // Check if there's a "Try again" button and click it
  const tryAgainButton = await page.locator('text=Try again').first();
  if (await tryAgainButton.isVisible()) {
    console.log('Found "Try again" button, clicking...');
    await tryAgainButton.click();
    await page.waitForTimeout(2000);
  }
  
  // Check if there are any errors on the page
  const hasError = await page.evaluate(() => {
    const errorElement = document.querySelector('.error');
    return errorElement ? errorElement.textContent : null;
  });
  
  if (hasError) {
    console.log('Error found on page:', hasError);
  } else {
    console.log('No error element found');
  }
  
  // Try to click on Map tab
  console.log('Looking for Map button...');
  const mapButton = await page.locator('text=Map').first();
  if (await mapButton.isVisible()) {
    console.log('Clicking Map button...');
    await mapButton.click();
    await page.waitForTimeout(3000);
    
    // Expand "Notes and maps" category to see Ancient Ruin
    console.log('Expanding Notes and maps category...');
    const notesCategory = await page.locator('text=Notes and maps').first();
    if (await notesCategory.isVisible()) {
      await notesCategory.click();
      await page.waitForTimeout(1000);
    }
    
    // Take a screenshot
    await page.screenshot({ path: 'map-screenshot.png', fullPage: true });
    console.log('Screenshot saved to map-screenshot.png');
    
    // Check for Ancient Ruin in the page
    const ancientRuinInfo = await page.evaluate(() => {
      // Check if Ancient Ruin is in the icon lookup
      const scripts = Array.from(document.querySelectorAll('script'));
      let hasAncientRuin = false;
      for (const script of scripts) {
        if (script.textContent && script.textContent.includes('Ancient Ruin')) {
          hasAncientRuin = true;
          break;
        }
      }
      
      // Try to find Ancient Ruin markers on canvas
      const canvases = Array.from(document.querySelectorAll('canvas'));
      
      return {
        hasAncientRuin,
        canvasCount: canvases.length
      };
    });
    
    console.log('Ancient Ruin info:', ancientRuinInfo);
    
    // Check console for any SVG loading errors
    console.log('\nCheck the browser window to see if Ancient Ruin icons are visible on the map');
  } else {
    console.log('Map button not found');
  }
  
  // Keep browser open for inspection
  console.log('\nBrowser is open. Check the map manually.');
  console.log('Press Ctrl+C to close when done.');
  
  // Wait indefinitely until user closes
  await new Promise(() => {});
}

testMap().catch(console.error);
