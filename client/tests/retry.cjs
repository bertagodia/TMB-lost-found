const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage();await page.addInitScript(()=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key==='tmb-lost-found-queue')throw new DOMException('Test full storage','QuotaExceededError');return original.call(this,key,value);};});
  await page.goto(process.env.TEST_BASE_URL||'http://127.0.0.1:8001');
  await page.route('**/api/extract',route=>route.fulfill({status:400,json:{error:'Manual retry test'}}));
  let ids=[];await page.route('**/lost-found',route=>{ids.push(route.request().postDataJSON().id);return ids.length===1?route.fulfill({status:503,json:{error:'Simulated interruption'}}):route.continue();});
  await page.locator('#manualLine').fill('TEST');await page.locator('#manualVehicle').fill('RETRY');await page.locator('#manualVehicleButton').click();await page.locator('#nextButton').click();
  for(let slot=0;slot<2;slot++){const chooser=page.waitForEvent('filechooser');await page.locator(`.photo-button[data-photo="${slot}"]`).click();await(await chooser).setFiles(process.env[slot===0?'TEST_PHOTO_1':'TEST_PHOTO_2']);await page.waitForFunction(slot=>document.getElementById('preview'+slot).style.backgroundImage!=='',slot);}
  await page.locator('#nextButton').click();await page.waitForFunction(()=>!document.getElementById('retryExtraction').disabled);await page.locator('#color input[value="Taronja"]').check();await page.locator('#objectType').selectOption('Ampolla');await page.locator('#material').selectOption('Metall');await page.locator('#description').fill('Archived browser retry test');await page.locator('#fieldsReviewed').check();await page.locator('#nextButton').click();await page.locator('#nextButton').click();
  await page.waitForFunction(()=>document.getElementById('toast').textContent.includes('ni guardar la cua'));
  assert(await page.locator('[data-view="4"]').evaluate(e=>e.classList.contains('active')));
  const response=page.waitForResponse(r=>r.url().endsWith('/lost-found')&&r.status()===200);await page.locator('#nextButton').click();await response;assert.equal(ids.length,2);assert.equal(ids[0],ids[1]);
  await page.waitForFunction(()=>document.getElementById('toast').textContent.includes('desat al servidor'));
  const history=await page.evaluate(()=>localStorage.getItem('tmb-lost-found-requests'));assert(!history.includes('data:image/'));assert(history.length<3000);
  const archived=await page.evaluate(async id=>{const r=await fetch('/api/status',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':document.querySelector('meta[name="local-token"]').content},body:JSON.stringify({id,status:'archived'})});return r.status;},ids[0]);assert.equal(archived,200);
  console.log('PASS: network failure plus full browser storage retains the form; retry keeps its ID; online save succeeds with compact history. Test record archived.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
