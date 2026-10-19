// Optional browser QA: npm install --no-save --package-lock=false playwright
// Then: npx playwright install chromium; python tools/preview_ui.py
const {chromium} = require('playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({headless:true});
  fs.mkdirSync('outputs', {recursive:true});
  const page = await browser.newPage({viewport:{width:1180,height:760}});
  try {
    await page.goto('http://127.0.0.1:8766', {waitUntil:'domcontentloaded'});
    await page.waitForTimeout(4000);
    await page.locator('flt-semantics-placeholder').evaluate(e => e.click());
    await page.getByRole('button', {name:'Nova credencial', exact:true}).click();
    await page.waitForTimeout(700);
    const results = [];
    for (const [width,height] of [[1180,760],[940,620],[800,500]]) {
      await page.setViewportSize({width,height});
      await page.waitForTimeout(500);
      const save = page.getByRole('button', {name:'Guardar', exact:true});
      const box = await save.boundingBox();
      if (!box || box.y < 0 || box.y + box.height > height || box.x + box.width > width) throw Error('Guardar outside viewport '+width+'x'+height);
      await page.screenshot({path:`outputs/editor-${width}x${height}.png`});
      results.push({viewport:`${width}x${height}`,saveVisible:true,box});
    }
    await page.getByRole('button', {name:'Guardar', exact:true}).click();
    await page.getByText('Dê um nome a esta credencial.',{exact:true}).waitFor();
    const fields = page.getByRole('textbox');
    console.log('TEXTBOXES', await fields.count());
    await fields.nth(0).fill('Credencial QA');
    await fields.nth(0).press('Tab');
    await page.waitForTimeout(500);
    await page.getByRole('button', {name:'Guardar', exact:true}).click();
    await page.waitForTimeout(1200);
    console.log('AFTER_SAVE', await page.locator('body').innerText());
    await page.screenshot({path:'outputs/after-save.png'});
    await page.getByText('O seu cofre',{exact:true}).waitFor();
    await page.setViewportSize({width:1180,height:760});
    await page.waitForTimeout(500);
    await page.screenshot({path:'outputs/dashboard-saved.png'});
    fs.writeFileSync('outputs/ui-validation.json', JSON.stringify({results,requiredValidation:true,saveFlow:true},null,2));
    console.log('PASS', JSON.stringify(results));
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});
