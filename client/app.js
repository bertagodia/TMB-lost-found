const OPTIONS = await fetch('./form-options.json').then(response => {
  if (!response.ok) throw new Error('No es poden carregar les opcions del formulari.');
  return response.json();
});
const CONFIG={...OPTIONS,apiBaseUrl:localStorage.getItem('tmb_api_base_url')||location.origin};
const LOCAL_TOKEN=document.querySelector('meta[name="local-token"]').content;
const state={step:1,vehicle:null,photos:[null,null],details:{},activePhoto:0};const $=s=>document.querySelector(s);const $$=s=>[...document.querySelectorAll(s)];
class LocalQueue{constructor(key='tmb-lost-found-queue'){this.key=key}all(){return JSON.parse(localStorage.getItem(this.key)||'[]')}save(record){const queue=this.all().filter(item=>item.id!==record.id);queue.push(record);localStorage.setItem(this.key,JSON.stringify(queue));updatePendingCount()}remove(id){localStorage.setItem(this.key,JSON.stringify(this.all().filter(item=>item.id!==id)));updatePendingCount()}}
function historySummary(record){return {...record,photos:(record.photos||[]).map(photo=>photo?{name:photo.name,capturedAt:photo.capturedAt}:null)};}
class RequestHistory{
  constructor(key='tmb-lost-found-requests'){this.key=key;}
  all(){const records=new Map(JSON.parse(localStorage.getItem(this.key)||'[]').map(record=>[record.id,historySummary(record)]));queue.all().forEach(record=>{if(!records.has(record.id))records.set(record.id,historySummary(record));});return [...records.values()];}
  save(record){const records=this.all().filter(item=>item.id!==record.id);records.push(historySummary(record));localStorage.setItem(this.key,JSON.stringify(records));updatePendingCount();}
  setStatus(id,status){localStorage.setItem(this.key,JSON.stringify(this.all().map(record=>record.id===id?{...record,status}:record)));updatePendingCount();}
}
class CitizenReportStore{constructor(key='tmb-lost-found-citizen-reports'){this.key=key}save(report){const reports=JSON.parse(localStorage.getItem(this.key)||'[]');reports.push(report);localStorage.setItem(this.key,JSON.stringify(reports))}}
class NfcVehicleReader{async read(){if(!('NDEFReader'in window))throw new Error('NFC no disponible en aquest navegador');const reader=new NDEFReader();await reader.scan();return new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('No s’ha detectat cap tag NFC')),15000);reader.onreadingerror=()=>{clearTimeout(timeout);reject(new Error('No s’ha pogut llegir el tag NFC'))};reader.onreading=({serialNumber,message})=>{clearTimeout(timeout);const textRecord=[...message.records].find(record=>record.recordType==='text'||record.recordType==='url');const raw=textRecord?new TextDecoder(textRecord.encoding||'utf-8').decode(textRecord.data):serialNumber;resolve(parseVehiclePayload(raw,serialNumber))}})}}
function parseVehiclePayload(raw,serialNumber){try{const parsed=JSON.parse(raw);return{line:parsed.line||'—',vehicle:parsed.vehicle||serialNumber,source:'nfc'}}catch{return{line:raw||'—',vehicle:serialNumber||'—',source:'nfc'}}}
class ApiClient {
  async request(path, body) {
    const response = await fetch(`${CONFIG.apiBaseUrl.replace(/\/$/,'')}${path}`, {
      method:'POST', headers:{'Content-Type':'application/json','X-Local-Token':LOCAL_TOKEN},
      body:JSON.stringify(body)
    });
    if (!response.ok) {
      const result = await response.json().catch(()=>({}));
      throw new Error(result.error || `L’API ha respost amb ${response.status}. Inicia python -m backend.server.`);
    }
    return response.json();
  }
  submit(record) { return this.request('/lost-found',record); }
  extract(photo) { return this.request('/api/extract',{photo}); }
}

const queue=new LocalQueue();const history=new RequestHistory();const api=new ApiClient();function createId(){return crypto.randomUUID?crypto.randomUUID():`tmb-${Date.now()}-${Math.random().toString(16).slice(2)}`}function showToast(message){const toast=$('#toast');toast.textContent=message;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),3200)}function updatePendingCount(){$('#pendingCount').textContent=history.all().length}function setConnection(){const online=navigator.onLine;$('#connectionDot').classList.toggle('online',online);$('#connectionText').textContent=online?'Connexió disponible':'Sense connexió · mode pendent'}function populateSelect(id,values){const select=$(`#${id}`);values.forEach(value=>select.add(new Option(value,value)))}function setVehicle(vehicle){state.vehicle=vehicle;$('#nfcTitle').textContent=`${vehicle.line} · vehicle ${vehicle.vehicle}`;$('#nfcMessage').textContent=vehicle.source==='nfc'?'Vehicle identificat per NFC.':'Vehicle introduït en mode de proves.';$('#nextButton').disabled=false;$('#nextButton').textContent='Continuar amb les fotos';$('#draftText').textContent=`Vehicle ${vehicle.vehicle}`}
function setAudienceTab(audience){const isCitizen=audience==='citizen';$('#staffTab').classList.toggle('active',!isCitizen);$('#staffTab').setAttribute('aria-selected',String(!isCitizen));$('#citizenTab').classList.toggle('active',isCitizen);$('#citizenTab').setAttribute('aria-selected',String(isCitizen));$('#operatorPanel').hidden=isCitizen;$('#citizenPanel').hidden=!isCitizen;$('#pendingButton').hidden=isCitizen;if(isCitizen)$('#citizenDescription').focus({preventScroll:true})}
function updateCitizenPhoto(file){if(!file){state.citizenPhoto=null;$('#citizenPhotoPreview').hidden=true;$('#citizenPhotoImage').removeAttribute('src');return}if(!file.type.startsWith('image/')){showToast('Selecciona un fitxer d’imatge.');$('#citizenPhoto').value='';return}const reader=new FileReader();reader.onload=()=>{state.citizenPhoto={name:file.name,mimeType:file.type,data:reader.result};$('#citizenPhotoImage').src=reader.result;$('#citizenPhotoPreview').hidden=false};reader.onerror=()=>showToast('No s’ha pogut llegir la fotografia.');reader.readAsDataURL(file)}
let citizenEpoch=0, pendingReport=null;
function citizenPayload(){return {description:$('#citizenDescription').value.trim(),incident:{location:$('#citizenLocation').value.trim(),lossDate:$('#citizenLossDate').value},filters:{objectType:$('#citizenObjectType').value,colors:selectedColors('citizenColor')},referencePhoto:state.citizenPhoto,contact:{name:$('#citizenName').value.trim(),email:$('#citizenEmail').value.trim(),phone:$('#citizenPhone').value.trim()}};}
async function citizenSearch(save=false){
  if(!$('#citizenDescription').reportValidity())return;
  const payload=citizenPayload(),epoch=++citizenEpoch;
  $('#citizenConfirmation').hidden=false;$('#citizenConfirmation').textContent='Cercant…';
  $('#searchButton').disabled=true;$('.citizen-submit').disabled=true;
  try{
    let result;
    if(save){
      const signature=JSON.stringify(payload);
      if(!pendingReport||pendingReport.signature!==signature)pendingReport={signature,body:{...payload,id:createId(),createdAt:new Date().toISOString()}};
      result=await api.request('/api/lost-reports',pendingReport.body);pendingReport=null;
    }else result=await api.request('/api/search',{description:payload.description,filters:payload.filters,lostDate:payload.incident.lossDate});
    if(epoch!==citizenEpoch){if(save)showToast(`Declaració anterior desada. Referència: ${result.id}`);return;}
    $('#citizenConfirmation').textContent=save?`Declaració desada al servidor. Referència: ${result.id}`:'Cerca completada. No s’ha desat cap declaració.';
    renderSearch(result);
  }catch(error){if(epoch===citizenEpoch)$('#citizenConfirmation').textContent=`No s’ha completat: ${error.message} Les dades del formulari es conserven.`;}
  finally{$('#searchButton').disabled=false;$('.citizen-submit').disabled=false;}
}
function saveCitizenReport(event){event.preventDefault();citizenSearch(true);}
function node(tag,text,className){const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(className)item.className=className;return item;}
function renderSearch(result){
  const target=$('#searchResults');target.replaceChildren();
  target.append(node('h2',`${result.candidates.length} possibles coincidències`));
  target.append(node('p','Les coincidències no confirmen la propietat. Cal verificar l’objecte.','muted'));
  if(!result.candidates.length)target.append(node('p','No s’han trobat coincidències. Prova una altra descripció o menys filtres.'));
  for(const item of result.candidates){
    const card=node('article',undefined,'result-card');
    if(item.photo_url){const image=node('img');image.src=item.photo_url;image.alt=item.objectType||'Objecte trobat';image.loading='lazy';card.append(image);}
    const body=node('div');body.append(node('h3',item.objectType||'Objecte'),node('p',item.colors.join(', ')),node('p',item.material||''),node('p',item.description),node('small',`Referència: ${item.id}`));card.append(body);target.append(card);
  }
}
function renderRequests(){const records=history.all().sort((a,b)=>new Date(b.capturedAt)-new Date(a.capturedAt));const list=$('#requestList');list.replaceChildren();$('#requestsSummary').textContent=`${records.length} ${records.length===1?'sol·licitud guardada':'sol·licituds guardades'} en aquest dispositiu`;$('#emptyRequests').hidden=records.length>0;records.forEach(record=>{const item=document.createElement('article');item.className=`request-item${record.status==='sent'?' sent':''}`;const heading=document.createElement('div');heading.className='request-item-heading';const title=document.createElement('h3');title.textContent=`${record.details?.objectType||'Objecte'} · ${(record.details?.colors || [record.details?.color]).filter(Boolean).join(', ')||'Color no indicat'}`;const status=document.createElement('span');status.className='request-status';status.textContent=record.status==='sent'?'Enviada':'Pendent d’enviament';heading.append(title,status);const date=new Date(record.capturedAt);const lines=[`Vehicle ${record.vehicle?.vehicle||'—'} · línia ${record.vehicle?.line||'—'}`,`${Number.isNaN(date.getTime())?'Data no disponible':new Intl.DateTimeFormat('ca-ES',{dateStyle:'medium',timeStyle:'short'}).format(date)} · ${record.photos?.filter(Boolean).length||0} fotos`,record.details?.description||'Sense descripció'];item.append(heading,...lines.map(text=>{const paragraph=document.createElement('p');paragraph.textContent=text;return paragraph}));list.append(item)})}
function openRequests(){renderRequests();$('#requestsDialog').showModal()}
async function readNfc(){$('#scanNfcButton').disabled=true;$('#nfcTitle').textContent='Apropa el tag...';try{setVehicle(await new NfcVehicleReader().read())}catch(error){showToast(error.message);$('#nfcTitle').textContent='A punt per llegir'}finally{$('#scanNfcButton').disabled=false}}function openPhoto(slot){state.activePhoto=slot;$('#photoInput').value='';$('#photoInput').click()}function inspectPhoto(file,slot){const reader=new FileReader();reader.onload=()=>{if(slot===0)invalidateExtraction();state.photos[slot]={data:reader.result,name:file.name,capturedAt:new Date().toISOString()};renderPhotos();$('#nextButton').disabled=!validStep(2);if(slot===0)$('.photo-button[data-photo="1"]').disabled=false};reader.readAsDataURL(file)}function renderPhotos(){state.photos.forEach((photo,index)=>{const preview=$(`#preview${index}`);const status=$(`#photoStatus${index}`);if(!photo)return;preview.style.backgroundImage=`url("${photo.data}")`;preview.innerHTML='';status.textContent='Revisada · confirma abans de continuar'});$('#qualityNote').hidden=!state.photos.some(Boolean);if(state.photos.some(Boolean))$('#qualityNote').textContent='Revisa que l’objecte sigui visible, la imatge no sigui fosca i la perspectiva sigui útil.'}
function renderReview() {
  $('#reviewPhotos').replaceChildren(...state.photos.filter(Boolean).map(photo=>{
    const img=document.createElement('img'); img.src=photo.data; img.alt='Fotografia de l’objecte'; return img;
  }));
  const entries=[['Vehicle',`${state.vehicle.line} · ${state.vehicle.vehicle}`],['Colors',state.details.colors.join(', ')],['Tipus',state.details.objectType],['Material',state.details.material],['Descripció',state.details.description||'Sense descripció']];
  $('#reviewList').replaceChildren(...entries.map(([label,value])=>{
    const row=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');
    dt.textContent=label;dd.textContent=value;row.append(dt,dd);return row;
  }));
}
function validStep(step) {
  if(step===1)return Boolean(state.vehicle);
  if(step===2)return state.photos.every(Boolean);
  if(step===3)return Boolean(selectedColors('color').length && $('#objectType').value && $('#material').value && $('#fieldsReviewed').checked && !extractionBusy);
  return true;
}

function goToStep(step){if(step>state.step&&Array.from({length:step-1},(_,i)=>i+1).some(previous=>!validStep(previous))){showToast(state.step===1?'Identifica primer el vehicle.':state.step===2?'Cal confirmar les dues fotografies.':'Completa els camps i confirma que els has revisat.');return}state.step=step;$$('.view').forEach(view=>view.classList.toggle('active',Number(view.dataset.view)===step));$$('.step').forEach(item=>item.classList.toggle('active',Number(item.dataset.step)<=step));$('#backButton').hidden=step===1;$('#nextButton').textContent=step===1?'Comença amb el vehicle':step===2?'Continuar amb els detalls':step===3?'Revisar registre':'Guardar i enviar';$('#nextButton').disabled=step===1?!state.vehicle:step===2?!validStep(2):false;if(step===4){state.details={colors:selectedColors('color'),objectType:$('#objectType').value,material:$('#material').value,description:$('#description').value.trim()};renderReview()}if(step===3)autoExtract();window.scrollTo({top:0,behavior:'smooth'})}
let pendingSubmission=null;
async function submitRecord() {
  const body={vehicle:state.vehicle,photos:state.photos,details:state.details,
    extractionId:state.extraction?.id||null,reviewed:true,status:'pending'};
  const signature=JSON.stringify(body);
  if(!pendingSubmission||pendingSubmission.signature!==signature)pendingSubmission={signature,record:{...body,id:createId(),capturedAt:new Date().toISOString()}};
  const record=pendingSubmission.record;
  $('#nextButton').disabled=true;
  try{
    const result=await api.submit(record);
    if(result.queued)throw new Error('El servidor no ha confirmat el registre.');
    try{history.save({...record,status:'sent'});}catch{ /* Server inventory remains authoritative. */ }
    showToast('Registre desat al servidor.');resetForm();
  }catch(error){
    try{
      queue.save(record);history.save(record);
      showToast(`Guardat a la cua per reintentar: ${error.message}`);resetForm();
    }catch{
      showToast('No s’ha pogut enviar ni guardar la cua. Les fotos es conserven al formulari; reintenta amb connexió.');
    }
  }finally{$('#nextButton').disabled=state.step===1&&!state.vehicle;}
}
function resetForm(){pendingSubmission=null;invalidateExtraction();state.step=1;state.vehicle=null;state.photos=[null,null];state.details={};$('#draftText').textContent='Cap esborrany actiu';$('#nfcTitle').textContent='A punt per llegir';$('#nfcMessage').textContent='La lectura NFC associarà el registre a la línia o vehicle.';$('#nextButton').disabled=true;$('#nextButton').textContent='Comença amb el vehicle';$('#detailsForm').reset();$$('.photo-preview').forEach((item,index)=>{item.style.backgroundImage='';item.innerHTML=`<span>Foto ${index+1}</span>`});$('.photo-button[data-photo="1"]').disabled=true;goToStep(1)}let syncing=false;
async function syncQueue(){
  if(syncing||!navigator.onLine||!CONFIG.apiBaseUrl)return;
  syncing=true;
  try {for(const record of queue.all())try{
    const result=await api.submit(record);
    if(result.queued)break;
    queue.remove(record.id);history.setStatus(record.id,'sent');
  }catch{break}}
  finally{syncing=false;}
}

function selectedColors(id){return [...document.querySelectorAll(`#${id} input:checked`)].map(input=>input.value);}
function setColors(id,values){document.querySelectorAll(`#${id} input`).forEach(input=>input.checked=values.includes(input.value));}
function populateColors(id){
  CONFIG.colors.forEach(color=>{
    const label=document.createElement('label'),input=document.createElement('input');
    input.type='checkbox';input.value=color;label.append(input,document.createTextNode(color));$('#'+id).append(label);
  });
}
let extractionBusy=false, extractionEpoch=0, attemptedPhoto=null;
let autoValues=null, pendingExtraction=null;
const fieldVersions={colors:0,objectType:0,material:0,description:0};
function currentFields(){return {colors:selectedColors('color'),objectType:$('#objectType').value||null,material:$('#material').value||null,description:$('#description').value};}
function setField(key,value){if(key==='colors')setColors('color',value);else $('#'+key).value=value||'';}
function invalidateExtraction(){
  extractionEpoch++;attemptedPhoto=null;state.extraction=null;extractionBusy=false;
  if(autoValues){const current=currentFields();for(const key of Object.keys(autoValues))if(JSON.stringify(current[key])===JSON.stringify(autoValues[key]))setField(key,key==='colors'?[]:'');}
  autoValues=null;$('#fieldsReviewed').checked=false;$('#extractionDetails').hidden=true;
  $('#descriptionCount').textContent=$('#description').value.length;
  $('#retryExtraction').disabled=false;
  $('#extractionStatus').textContent='Els camps s’ompliran a partir de la foto principal. Revisa’ls abans de continuar.';
}
async function autoExtract(force=false){
  const photo=state.photos[0];
  if(!photo||extractionBusy||(!force&&attemptedPhoto===photo))return;
  const epoch=++extractionEpoch,versions={...fieldVersions},before=currentFields();
  attemptedPhoto=photo;extractionBusy=true;$('#fieldsReviewed').checked=false;
  $('#retryExtraction').disabled=true;
  $('#extractionStatus').textContent='Extraient els camps de la foto principal amb Ollama… Pots escriure mentre esperes; conservarem els teus canvis.';
  const started=performance.now();
  const elapsedTimer=setInterval(()=>{if(epoch===extractionEpoch)$('#extractionStatus').textContent=`Extraient els camps… ${Math.floor((performance.now()-started)/1000)} s. La primera petició després d’una pausa pot trigar més. Pots escriure mentre esperes; conservarem els teus canvis.`;},1000);
  try{
    if(pendingExtraction)await pendingExtraction.catch(()=>{});
    if(epoch!==extractionEpoch||state.photos[0]!==photo)return;
    const request=api.extract(photo);pendingExtraction=request;
    let result;
    try{result=await request;}finally{if(pendingExtraction===request)pendingExtraction=null;}
    if(epoch!==extractionEpoch||state.photos[0]!==photo)return;
    const fields=result.fields;
    if(!fields||!Array.isArray(fields.colors)||!fields.colors.every(c=>CONFIG.colors.includes(c))||
       (fields.objectType!==null&&!CONFIG.objectTypes.includes(fields.objectType))||
       (fields.material!==null&&!CONFIG.materials.includes(fields.material))||typeof fields.description!=='string'||fields.description.length>250)
      throw new Error('La resposta no compleix els camps del formulari.');
    state.extraction=result;
    $('#fieldsReviewed').checked=false;
    for(const key of ['colors','objectType','material','description']){
      const empty=key==='colors'?!before[key].length:!before[key];
      const previousAuto=autoValues&&JSON.stringify(before[key])===JSON.stringify(autoValues[key]);
      if(fieldVersions[key]===versions[key]&&(empty||previousAuto))setField(key,fields[key]);
    }
    autoValues=fields;$('#descriptionCount').textContent=$('#description').value.length;
    $('#extractionJson').textContent=JSON.stringify({recognized_object:result.recognized_object,fields,warnings:result.warnings||[],timings:result.timings,cached:result.cached},null,2);$('#extractionDetails').hidden=false;
    $('#extractionStatus').textContent=result.quality==='usable'&&!result.sensitive_content
      ?'Camps extrets. Revisa els colors, el tipus, el material i la descripció abans de confirmar.'
      :'La foto no ha produït un esborrany utilitzable. Completa els camps manualment.';
    if(result.recognized_object)$('#extractionStatus').textContent+=` Objecte: ${result.recognized_object}.`;
    if(Array.isArray(result.warnings)&&result.warnings.length)$('#extractionStatus').textContent+=' '+result.warnings.join(' ');
    $('#extractionStatus').textContent+=` Temps d’aquesta petició: ${((performance.now()-started)/1000).toFixed(1)} s${result.cached?' (resultat guardat)':''}.`;
  }catch(error){if(epoch===extractionEpoch)$('#extractionStatus').textContent=`No s’ha pogut extreure: ${error.message} Pots omplir els camps manualment o reintentar.`;}
  finally{clearInterval(elapsedTimer);if(epoch===extractionEpoch){extractionBusy=false;$('#retryExtraction').disabled=false;}}
}

populateColors('color');populateSelect('objectType',CONFIG.objectTypes);populateSelect('material',CONFIG.materials);populateColors('citizenColor');populateSelect('citizenObjectType',CONFIG.objectTypes);updatePendingCount();setConnection();$('#staffTab').addEventListener('click',()=>setAudienceTab('staff'));$('#citizenTab').addEventListener('click',()=>setAudienceTab('citizen'));$('#citizenDescription').addEventListener('input',event=>$('#citizenDescriptionCount').textContent=event.target.value.length);$('#citizenPhoto').addEventListener('change',event=>updateCitizenPhoto(event.target.files[0]));$('#removeCitizenPhoto').addEventListener('click',()=>{$('#citizenPhoto').value='';updateCitizenPhoto(null)});$('#citizenForm').addEventListener('submit',saveCitizenReport);$('#pendingButton').addEventListener('click',openRequests);$('#closeRequestsButton').addEventListener('click',()=>$('#requestsDialog').close());$('#requestsDialog').addEventListener('click',event=>{if(event.target===$('#requestsDialog'))$('#requestsDialog').close()});$('#scanNfcButton').addEventListener('click',readNfc);$('#manualVehicleButton').addEventListener('click',()=>{const line=$('#manualLine').value.trim();const vehicle=$('#manualVehicle').value.trim();if(!line||!vehicle)return showToast('Escriu la línia i el vehicle per continuar.');setVehicle({line,vehicle,source:'manual'})});$('#photoInput').addEventListener('change',event=>{const file=event.target.files[0];if(file)inspectPhoto(file,state.activePhoto)});$$('.photo-button').forEach(button=>button.addEventListener('click',()=>openPhoto(Number(button.dataset.photo))));$('#description').addEventListener('input',event=>$('#descriptionCount').textContent=event.target.value.length);$('#nextButton').addEventListener('click',()=>state.step===4?submitRecord():goToStep(state.step+1));$('#backButton').addEventListener('click',()=>goToStep(state.step-1));$$('.step').forEach(button=>button.addEventListener('click',()=>goToStep(Number(button.dataset.step))));window.addEventListener('online',()=>{setConnection();syncQueue()});window.addEventListener('offline',setConnection);syncQueue();
$('#retryExtraction').addEventListener('click',()=>autoExtract(true));
for(const [key,id] of [['colors','color'],['objectType','objectType'],['material','material'],['description','description']]){
  $('#'+id).addEventListener('input',()=>{fieldVersions[key]++;$('#fieldsReviewed').checked=false;});
}

$('#skipExtraction').addEventListener('click',()=>{invalidateExtraction();attemptedPhoto=state.photos[0];$('#extractionStatus').textContent='Mode manual. Completa els camps i confirma la revisió.';});
$('#searchButton').addEventListener('click',()=>citizenSearch(false));
$('#citizenForm').addEventListener('input',()=>{citizenEpoch++;$('#searchResults').replaceChildren();$('#citizenConfirmation').hidden=true;});
let editingObject=null;
async function refreshInventory(){
  $('#inventoryStatus').textContent='Carregant…';
  try{
    const result=await api.request('/api/inventory',{});
    $('#inventoryStatus').textContent=`${result.objects.length} registres al servidor (màxim 200).`;
    $('#inventoryList').replaceChildren();
    for(const item of result.objects){
      const card=node('article',undefined,'request-item');
      card.append(node('h3',item.object_type||'Objecte'),node('p',`Vehicle ${item.registered_vehicle||'—'} · línia ${item.registered_line||'—'}`),node('p',`${(item.colors||[]).join(', ')} · ${item.material||''}`),node('p',item.description||''),node('p',`${item.status} · revisió ${item.revision}: ${item.review_status}`),node('small',item.id));
      if(item.photo_id&&item.status==='registered'&&item.review_status==='approved'){const image=node('img');image.src='/api/photos/'+encodeURIComponent(item.photo_id);image.alt='Foto principal';image.className='inventory-photo';card.prepend(image);}
      const edit=node('button','Revisar / corregir','secondary-button');edit.type='button';edit.addEventListener('click',()=>openEdit(item));
      const status=node('button',item.status==='registered'?'Marcar com a retornat':'Tornar a activar','secondary-button');status.type='button';status.addEventListener('click',async()=>{status.disabled=true;try{await api.request('/api/status',{id:item.id,status:item.status==='registered'?'returned':'registered'});await refreshInventory();}catch(error){$('#inventoryStatus').textContent=error.message;status.disabled=false;}});
      card.append(edit,status);$('#inventoryList').append(card);
    }
  }catch(error){$('#inventoryStatus').textContent=error.message;}
}
function openEdit(item){editingObject=item;setColors('editColors',item.colors||[]);$('#editType').value=item.object_type||'';$('#editMaterial').value=item.material||'';$('#editDescription').value=item.description||'';$('#editDecision').value=item.review_status||'approved';$('#editStatus').textContent='';$('#editDialog').showModal();}
populateColors('editColors');populateSelect('editType',CONFIG.objectTypes);populateSelect('editMaterial',CONFIG.materials);
$('#inventoryButton').addEventListener('click',()=>{$('#inventoryDialog').showModal();refreshInventory();});
$('#refreshInventory').addEventListener('click',refreshInventory);
$('#closeInventory').addEventListener('click',()=>$('#inventoryDialog').close());
$('#cancelEdit').addEventListener('click',()=>$('#editDialog').close());
$('#editForm').addEventListener('submit',async event=>{
  event.preventDefault();const button=$('#editForm button[type="submit"]');button.disabled=true;
  try{
    await api.request('/api/review',{id:editingObject.id,revision:editingObject.revision,reviewed:true,status:$('#editDecision').value,details:{colors:selectedColors('editColors'),objectType:$('#editType').value,material:$('#editMaterial').value,description:$('#editDescription').value}});
    $('#editDialog').close();await refreshInventory();
  }catch(error){$('#editStatus').textContent=error.message;}finally{button.disabled=false;}
});
