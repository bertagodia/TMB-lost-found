// Run against a disposable/test prototype. Creates one object and one loss report.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:8001';
const photos=[process.env.TEST_PHOTO_1,process.env.TEST_PHOTO_2];
if(photos.some(p=>!p))throw new Error('Set TEST_PHOTO_1 and TEST_PHOTO_2 to two views of the same bottle.');
async function addPhoto(page,slot){const chooser=page.waitForEvent('filechooser');await page.locator(`.photo-button[data-photo="${slot}"]`).click();await(await chooser).setFiles(photos[slot]);await page.waitForFunction(slot=>document.getElementById('preview'+slot).style.backgroundImage!=='',slot);}
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.locator('#manualLine').fill('TEST');await page.locator('#manualVehicle').fill('PROTO');await page.locator('#manualVehicleButton').click();await page.locator('#nextButton').click();await addPhoto(page,0);await addPhoto(page,1);
  if(process.env.MOCK_EXTRACTION==='1')await page.route('**/api/extract',route=>route.fulfill({status:400,json:{error:'Manual-path test'}}));
  const extraction=page.waitForResponse(r=>r.url().endsWith('/api/extract'),{timeout:310000});
  await page.locator('#nextButton').click();const extracted=await extraction;
  if(process.env.MOCK_EXTRACTION!=='1'){assert.equal(extracted.status(),200);const result=await extracted.json();assert(result.id);console.log('Live extraction:',result.recognized_object,result.elapsed_seconds+'s');}
  await page.waitForFunction(()=>!document.getElementById('retryExtraction').disabled);
  for(const checkbox of await page.locator('#color input').all())await checkbox.uncheck();
  for(const color of ['Gris','Taronja','Negre'])await page.locator(`#color input[value="${color}"]`).check();
  await page.locator('#objectType').selectOption('Ampolla');await page.locator('#material').selectOption('Metall');await page.locator('#description').fill('Prototype test bottle: orange grip, black cap, silver body.');await page.locator('#fieldsReviewed').check();await page.locator('#nextButton').click();
  const savedResponse=page.waitForResponse(r=>r.url().endsWith('/lost-found'));await page.locator('#nextButton').click();const saved=await savedResponse;assert.equal(saved.status(),200);const record=await saved.json();assert.equal(record.status,'stored-postgres');
  // Separate browser context proves results are server-backed, not local history.
  const citizen=await browser.newPage({viewport:{width:390,height:844}});await citizen.goto(base);await citizen.locator('#citizenTab').click();await citizen.locator('#citizenDescription').fill('orange bottle');await citizen.locator('#citizenObjectType').selectOption('Ampolla');await citizen.locator('#citizenColor input[value="Taronja"]').check();await citizen.locator('#searchButton').click();
  await citizen.waitForFunction(id=>document.getElementById('searchResults').textContent.includes(id),record.id);
  await citizen.waitForFunction(()=>[...document.querySelectorAll('#searchResults img')].every(i=>i.complete&&i.naturalWidth>0));
  await citizen.locator('#citizenName').fill('Prototype Test');await citizen.locator('#citizenEmail').fill('prototype@example.invalid');
  const reportResponse=citizen.waitForResponse(r=>r.url().endsWith('/api/lost-reports'));await citizen.locator('.citizen-submit').click();const report=await reportResponse;assert.equal(report.status(),200);assert.equal((await report.json()).status,'stored-postgres');
  await citizen.screenshot({path:process.env.TEST_SCREENSHOT||'/tmp/tmb-prototype-citizen.png',fullPage:true});
  await page.locator('#inventoryButton').click();await page.waitForFunction(id=>document.getElementById('inventoryList').textContent.includes(id),record.id);
  let card=page.locator('#inventoryList article').filter({hasText:record.id});await card.getByRole('button',{name:'Revisar / corregir'}).click();await page.locator('#editDescription').fill('Prototype corrected bottle.');
  const reviewed=page.waitForResponse(r=>r.url().endsWith('/api/review'));await page.locator('#editForm button[type="submit"]').click();assert.equal((await reviewed).status(),200);
  await page.waitForFunction(()=>!document.getElementById('editDialog').open);
  card=page.locator('#inventoryList article').filter({hasText:record.id});await card.getByRole('button',{name:'Marcar com a retornat'}).click();await page.waitForFunction(id=>[...document.querySelectorAll('#inventoryList article')].find(e=>e.textContent.includes(id))?.textContent.includes('returned'),record.id);
  await citizen.locator('#searchButton').click();await citizen.waitForFunction(()=>document.getElementById('citizenConfirmation').textContent.includes('Cerca completada'));
  assert(!(await citizen.locator('#searchResults').textContent()).includes(record.id));
  // Leave a discoverable demonstration record for hand testing.
  card=page.locator('#inventoryList article').filter({hasText:record.id});const activated=page.waitForResponse(r=>r.url().endsWith('/api/status'));await card.getByRole('button',{name:'Tornar a activar'}).click();assert.equal((await activated).status(),200);
  assert.deepEqual(errors,[]);
  fs.writeFileSync('/tmp/tmb-prototype-browser-result.json',JSON.stringify({recordId:record.id,extractionStatus:extracted.status(),passed:true},null,2));
  console.log('PASS: live UI registration, PostgreSQL save, fresh-browser search and photo, loss report, correction, return exclusion and reactivation.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
