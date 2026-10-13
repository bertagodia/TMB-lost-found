// Run on a disposable PostgreSQL instance; creates test objects and a loss report.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:8002';
const photo=process.env.TEST_PHOTO_1;
if(!photo)throw new Error('Set TEST_PHOTO_1 to an object image.');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);
  await page.locator('#manualTransport').selectOption('bus');
  assert.equal(await page.locator('#manualLine option').count(),109);
  await page.locator('#manualTransport').selectOption('metro');
  assert.equal(await page.locator('#manualLine option').count(),12);
  assert.equal(await page.locator('#manualLine option[value="H12"]').count(),0);
  await page.locator('#manualLine').selectOption('L1');
  await page.locator('#manualVehicle').fill('BROWSER-TEST');await page.locator('#manualVehicleButton').click();await page.locator('#nextButton').click();
  for(const slot of [0,1]){
   const chooser=page.waitForEvent('filechooser');await page.locator(`.photo-button[data-photo="${slot}"]`).click();await(await chooser).setFiles(photo);
   await page.waitForFunction(i=>document.getElementById('preview'+i).style.backgroundImage!=='',slot);
  }
  await page.route('**/api/extract',route=>route.fulfill({json:{fields:{colors:['Taronja','Negre'],colorOrderKnown:true,objectType:'Ampolla',material:'Metall',description:'Ranking browser bottle'},quality:'usable',sensitive_content:false}}));
  await page.locator('#nextButton').click();
  await page.waitForFunction(()=>!document.getElementById('retryExtraction').disabled);
  assert.match(await page.locator('#colorRanking li').first().textContent(),/Taronja.*Principal/);
  await page.getByRole('button',{name:'Pujar Negre',exact:true}).click();
  assert.match(await page.locator('#colorRanking li').first().textContent(),/Negre.*Principal/);
  await page.locator('#foundTransport').selectOption('bus');await page.locator('#foundLine').selectOption('H12');
  await page.locator('#foundDate').fill('31/02/2026');await page.locator('#fieldsReviewed').check();await page.locator('#nextButton').click();
  assert.equal(await page.locator('[data-view="3"]').evaluate(e=>e.classList.contains('active')),true);
  await page.locator('#foundDate').fill('03/04/2026');await page.locator('#nextButton').click();
  assert.match(await page.locator('#reviewList').textContent(),/03\/04\/2026/);
  const response=page.waitForResponse(r=>r.url().endsWith('/lost-found'));await page.locator('#nextButton').click();const saved=await response;
  assert.equal(saved.status(),200,await saved.text());const id=(await saved.json()).id;
  await page.locator('#citizenTab').click();await page.locator('#citizenDescription').fill('Ranking browser bottle');
  await page.locator('#citizenTransport').selectOption('bus');await page.locator('#citizenLine').selectOption('H12');await page.locator('#citizenLossDate').fill('03/04/2026');
  await page.locator('#citizenColor input[value="Negre"]').check();await page.locator('#citizenColor input[value="Blau"]').check();
  const sr=page.waitForResponse(r=>r.url().endsWith('/api/search'));await page.locator('#searchButton').click();const result=await(await sr).json();const item=result.candidates.find(i=>i.id===id);
  assert(item);assert.deepEqual(item.colors,['Negre','Taronja']);assert.equal(item.foundDate,'2026-04-03');assert.equal(item.foundLine,'H12');assert(item.colorOrderKnown);
  await page.waitForFunction(id=>document.getElementById('searchResults').textContent.includes(id),id);
  assert.match(await page.locator('#searchResults').textContent(),/Principal/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:'/tmp/tmb-ranked-search.png',fullPage:true});
  const rr=page.waitForResponse(r=>r.url().endsWith('/api/lost-reports'));await page.locator('.citizen-submit').click();assert.equal((await rr).status(),200);
  await page.locator('#staffTab').click();await page.locator('#inventoryButton').click();
  const card=page.locator('#inventoryList article').filter({hasText:id});await card.getByRole('button',{name:'Revisar / corregir'}).click();
  assert.equal(await page.locator('#editFoundDate').inputValue(),'03/04/2026');
  await page.locator('#editFoundLine').selectOption('H14');await page.getByRole('button',{name:'Pujar Taronja',exact:true}).click();
  const er=page.waitForResponse(r=>r.url().endsWith('/api/review'));await page.locator('#editForm button[type="submit"]').click();assert.equal((await er).status(),200);
  await page.waitForFunction(()=>!document.getElementById('editDialog').open);
  await card.getByRole('button',{name:'Revisar / corregir'}).click();assert.equal(await page.locator('#editFoundLine').inputValue(),'H14');
  assert.match(await page.locator('#editColorsRanking li').first().textContent(),/Taronja.*Principal/);
  assert.deepEqual(errors,[]);
  console.log('PASS: dropdown catalogue, estimated color order, manual reorder, date validation, metadata save/search/report, responsive layout and corrections.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
