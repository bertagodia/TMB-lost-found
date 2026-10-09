const OPTIONS = await fetch('./form-options.json').then(response => {
  if (!response.ok) throw new Error('No es poden carregar les opcions del formulari.');
  return response.json();
});
const CONFIG={...OPTIONS,apiBaseUrl:localStorage.getItem('tmb_api_base_url')||location.origin};
const LOCAL_TOKEN=document.querySelector('meta[name="local-token"]').content;
const state={step:1,vehicle:null,photos:[null,null],details:{},activePhoto:0};const $=s=>document.querySelector(s);const $$=s=>[...document.querySelectorAll(s)];
class LocalQueue{constructor(key='tmb-lost-found-queue'){this.key=key}all(){return JSON.parse(localStorage.getItem(this.key)||'[]')}save(record){const queue=this.all().filter(item=>item.id!==record.id);queue.push(record);localStorage.setItem(this.key,JSON.stringify(queue));updatePendingCount()}remove(id){localStorage.setItem(this.key,JSON.stringify(this.all().filter(item=>item.id!==id)));updatePendingCount()}}
class RequestHistory{constructor(key='tmb-lost-found-requests'){this.key=key}all(){const records=new Map(JSON.parse(localStorage.getItem(this.key)||'[]').map(record=>[record.id,record]));queue.all().forEach(record=>{if(!records.has(record.id))records.set(record.id,record)});return[...records.values()]}save(record){const records=this.all().filter(item=>item.id!==record.id);records.push(record);localStorage.setItem(this.key,JSON.stringify(records));updatePendingCount()}setStatus(id,status){const records=this.all().map(record=>record.id===id?{...record,status}:record);localStorage.setItem(this.key,JSON.stringify(records));updatePendingCount()}}
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
function saveCitizenReport(event){event.preventDefault();const report={id:createId(),createdAt:new Date().toISOString(),status:'saved-local',description:$('#citizenDescription').value.trim(),incident:{location:$('#citizenLocation').value.trim(),lossDate:$('#citizenLossDate').value},filters:{objectType:$('#citizenObjectType').value,colors:selectedColors('citizenColor')},referencePhoto:state.citizenPhoto,contact:{name:$('#citizenName').value.trim(),email:$('#citizenEmail').value.trim(),phone:$('#citizenPhone').value.trim()}};try{new CitizenReportStore().save(report);$('#citizenForm').reset();$('#citizenDescriptionCount').textContent='0';updateCitizenPhoto(null);$('#citizenConfirmation').textContent='La declaració s’ha desat en aquest navegador. Encara no s’ha enviat a TMB.';$('#citizenConfirmation').hidden=false}catch(error){showToast(error.name==='QuotaExceededError'?'No hi ha prou espai local per desar la declaració. Prova de treure la foto.':'No s’ha pogut desar la declaració en aquest navegador.')}}
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
async function submitRecord() {
  const record={id:createId(),vehicle:state.vehicle,photos:state.photos,details:state.details,
    extractionId:state.extraction?.id||null,reviewed:true,capturedAt:new Date().toISOString(),status:'pending'};
  $('#nextButton').disabled=true;
  try {
    queue.save(record);history.save(record);
    try {
      const result=await api.submit(record);
      if(!result.queued){queue.remove(record.id);history.setStatus(record.id,'sent');showToast('Registre desat al servidor local.');}
    } catch(error) {showToast(`Guardat com a pendent: ${error.message}`);}
    resetForm();
  } catch(error) {showToast('No s’ha pogut desar la cua local. Allibera espai abans de continuar.');}
  finally {$('#nextButton').disabled=state.step===1&&!state.vehicle;}
}
function resetForm(){invalidateExtraction();state.step=1;state.vehicle=null;state.photos=[null,null];state.details={};$('#draftText').textContent='Cap esborrany actiu';$('#nfcTitle').textContent='A punt per llegir';$('#nfcMessage').textContent='La lectura NFC associarà el registre a la línia o vehicle.';$('#nextButton').disabled=true;$('#nextButton').textContent='Comença amb el vehicle';$('#detailsForm').reset();$$('.photo-preview').forEach((item,index)=>{item.style.backgroundImage='';item.innerHTML=`<span>Foto ${index+1}</span>`});$('.photo-button[data-photo="1"]').disabled=true;goToStep(1)}let syncing=false;
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
let autoValues=null;
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
    const result=await api.extract(photo);
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
