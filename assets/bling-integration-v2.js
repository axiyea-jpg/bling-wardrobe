InvalidOperation: 
Line |
   2 |  [Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Content -Literal ��
     |  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Cannot set property. Property setting is supported only on core types in this language mode.
(function(){
  'use strict';
  const API_KEY='bling-generation-api-v2',TOKEN_KEY='bling-generation-token-v2',MODE_KEY='bling-model-mode-v2',BODY_KEY='bling-body-model-id-v2',REF_KEY='bling-reference-photo-id-v2';
  function migrate(){
    if(localStorage.getItem('bling-generation-schema-v2')==='2')return;
    ['bling-current-outfit-v1','bling-tryon-cache-v1','bling-thumb-cache','bling-image-cache','bling-item-image-cache','bling-item-thumbnail-cache'].forEach(k=>localStorage.removeItem(k));
    let rows=[];try{rows=JSON.parse(localStorage.getItem('bling-items')||'[]')}catch(e){}
    rows=Array.isArray(rows)?rows.filter(x=>Array.isArray(x)&&typeof x[3]==='string'&&/^(data:image\/|blob:|https?:)/.test(x[3])):[];
    localStorage.setItem('bling-items',JSON.stringify(rows));
    for(const key of ['bling-item-meta','bling-seasons']){let value=[];try{value=JSON.parse(localStorage.getItem(key)||'[]')}catch(e){}localStorage.setItem(key,JSON.stringify(Array.isArray(value)?value.slice(0,rows.length):[]))}
    localStorage.setItem('bling-generation-schema-v2','2');
  }
  const config={get base(){return(window.BLING_API_BASE||localStorage.getItem(API_KEY)||'').replace(/\/$/,'')},get token(){return localStorage.getItem(TOKEN_KEY)||''},set(base,token){localStorage.setItem(API_KEY,String(base||'').replace(/\/$/,''));localStorage.setItem(TOKEN_KEY,token||'')}};
  async function request(path,options={}){if(!config.base){const e=Error('�������Ӳ������ɷ���');e.code='generation_not_configured';throw e}const headers=new Headers(options.headers||{});if(config.token)headers.set('X-Bling-Token',config.token);if(options.body&&typeof options.body==='string')headers.set('Content-Type','application/json');const response=await fetch(config.base+path,{...options,headers});let body={};try{body=await response.json()}catch(e){}if(!response.ok){const d=body.detail||body,e=Error(d.message||'���ɷ�����ʱ������');e.code=d.code||'api_error';e.detail=d;throw e}return body}
  function dataUrlFile(url,name){const p=url.split(','),mime=(p[0].match(/data:([^;]+)/)||[])[1]||'image/png',raw=atob(p[1]||''),out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return new File([out],name,{type:mime})}
  function persistId(item,id){let rows=[];try{rows=JSON.parse(localStorage.getItem('bling-items')||'[]')}catch(e){}const row=rows.find(x=>x[0]===item[0]&&x[3]===item[3]);if(row){row[9]=id;localStorage.setItem('bling-items',JSON.stringify(rows))}item[9]=id}
  async function ensureGarment(item){if(item[9])return item[9];if(!item[3])throw Error(item[0]+' û�п���ͼƬ�������µ���');const file=/^data:image\//.test(item[3])?dataUrlFile(item[3],item[0]+'.png'):await fetch(item[3]).then(async r=>new File([await r.blob()],item[0]+'.png',{type:r.headers.get('content-type')||'image/png'}));const form=new FormData();form.append('files',file);const job=await request('/api/import/jobs',{method:'POST',body:form}),g=job.result?.garments?.[0];if(!g)throw Error('���ﵼ��û�з��ص�Ʒ');const m=item[5]||[];await request('/api/garments/'+g.id,{method:'PATCH',body:JSON.stringify({name:item[0],category:item[1]==='ȹ��'&&/����/.test(item[0])?'����ȹ':item[1],season:item[6]||'�ļ�',color:m[0]||'��ȷ��',material:m[1]||'��ȷ��',style:m[2]||'��ȷ��',fit:m[3]||'��ȷ��',tags:m.slice(0,4).filter(Boolean)})});await request('/api/garments/'+g.id+'/approve',{method:'POST'});persistId(item,g.id);return g.id}
  async function poll(id){for(let i=0;i<90;i++){const j=await request('/api/jobs/'+id);if(j.status==='ready')return j.result;if(j.status==='failed'){const e=Error(j.error?.message||'��������ʧ��');e.code=j.error?.code;throw e}await new Promise(r=>setTimeout(r,1200))}throw Error('����ʱ��ϳ������Ժ�����')}
  async function generateTryOn(payload){const ids=[];for(const item of payload.garments||[])ids.push(await ensureGarment(item));const mode=localStorage.getItem(MODE_KEY)||'digital',body={model_mode:mode,garment_ids:ids,scene:payload.scene||'�ճ�ͨ��',quality:payload.quality==='final'?'final':'draft'};if(mode==='digital')body.body_model_id=localStorage.getItem(BODY_KEY)||'';else body.reference_photo_id=localStorage.getItem(REF_KEY)||'';const job=await request('/api/tryon/jobs',{method:'POST',body:JSON.stringify(body)});return poll(job.id)}
  async function createBodyModel(profile){const result=await request('/api/body-models',{method:'POST',body:JSON.stringify(profile)});localStorage.setItem(BODY_KEY,result.body_model_id);return result}
  async function uploadReference(file){const form=new FormData();form.append('file',file);const result=await request('/api/reference-photo',{method:'POST',body:form});localStorage.setItem(REF_KEY,result.reference_photo_id);localStorage.setItem(MODE_KEY,'real');return result}
  async function deleteReference(){const id=localStorage.getItem(REF_KEY);if(id)await request('/api/reference-photo/'+id,{method:'DELETE'});localStorage.removeItem(REF_KEY);localStorage.setItem(MODE_KEY,'digital')}
  function installBodyEditor(){
    const fallback=window.openBodyEditor3D;
    window.openBodyEditor3D=function(){
      if(!document.querySelector('#subContent'))return fallback&&fallback();
      let saved={};try{saved=JSON.parse(localStorage.getItem('bling-body')||'{}')}catch(e){}
      const values={height:162,weight:52,bust:84,waist:66,hip:92,shoulder:38,...saved};
      const base=[['height','����','cm',140,205],['weight','����','kg',35,180],['bust','��Χ','cm',65,155],['waist','��Χ','cm',45,150],['hip','��Χ','cm',65,165],['shoulder','���','cm',28,60]];
      const advanced=[['neck','��Χ','cm',25,60],['natural_waist','��Ȼ��Χ','cm',45,150],['thigh','����Χ','cm',30,100],['knee','ϥΧ','cm',25,75],['upper_arm','�ϱ�Χ','cm',18,70],['wrist','��Χ','cm',10,35],['leg_length','�ȳ�','cm',60,125]];
      const field=m=>'<div class="metric-control"><header><b>'+m[1]+'</b><span class="metric-value"><input id="body-'+m[0]+'" type="number" min="'+m[3]+'" max="'+m[4]+'" value="'+(values[m[0]]??'')+'"><em>'+m[2]+'</em></span></header></div>';
      document.querySelector('#subTitle').textContent='��������';
      document.querySelector('#subContent').innerHTML='<div class="body-visualizer"><div class="human-viewport" id="anthroViewport"><div class="tryon-service-state" id="bodyModelState">�������ݺ��������� 3D ��������</div></div><div class="metric-panel">'+base.map(field).join('')+'<details class="body-advanced"><summary>�߼��������ݣ�ѡ���߾��ȣ�</summary><div class="advanced-grid">'+advanced.map(field).join('')+'</div></details><button class="primary" id="generateBodyModel">���沢���� 3D ����</button><div class="service-connect-card"><b>�������ɷ���</b><input id="blingApiBase" placeholder="https://������ɷ����ַ" value="'+config.base+'"><input id="blingApiToken" type="password" placeholder="˽��������" value="'+config.token+'"><button class="soft-btn" id="saveBlingService">��������</button></div><label class="service-connect-card"><b>���˲ο��գ���ѡ��</b><small>��������ģʽ AI ���£�����ʱ�滻��ɾ��</small><input id="blingReferenceInput" type="file" accept="image/png,image/jpeg"></label><p class="visualizer-tip">������������������ع�ģ�����ɣ�AI ���½��������Ӿ��ο�������ŵ��ʵ���롣</p></div></div>';
      document.querySelector('#overlay').classList.add('show');
      const read=()=>Object.fromEntries([...base,...advanced].map(m=>{const raw=document.querySelector('#body-'+m[0]).value;return[m[0],raw===''?null:+raw]}));
      document.querySelector('#saveBlingService').onclick=()=>{config.set(document.querySelector('#blingApiBase').value,document.querySelector('#blingApiToken').value);document.querySelector('#bodyModelState').textContent='���ɷ��������ѱ���'};
      document.querySelector('#blingReferenceInput').onchange=async e=>{const f=e.target.files[0];if(!f)return;const s=document.querySelector('#bodyModelState');s.textContent='����˽���ϴ����˲ο��ա�';try{await uploadReference(f);s.textContent='���˲ο����ѱ��棬����ʱ���л�����ģʽ'}catch(err){s.textContent=err.message}};
      document.querySelector('#generateBodyModel').onclick=async()=>{const profile=read();Object.keys(profile).forEach(k=>profile[k]==null&&delete profile[k]);localStorage.setItem('bling-body',JSON.stringify(profile));const state=document.querySelector('#bodyModelState');state.textContent='��������������������';try{const result=await createBodyModel(profile);state.textContent='3D ����������';await showBodyGlb(result.glb_url,document.querySelector('#anthroViewport'))}catch(err){state.textContent=err.message||'��������ʧ��'}};
    };
  }
  async function showBodyGlb(url,host){
    if(!window.THREE||!THREE.GLTFLoader)return;
    const headers={};if(config.token)headers['X-Bling-Token']=config.token;const response=await fetch((/^https?:/.test(url)?'':config.base)+url,{headers});if(!response.ok)throw Error('3D �����ȡʧ��');const buffer=await response.arrayBuffer();
    new THREE.GLTFLoader().parse(buffer,'',gltf=>{host.innerHTML='';const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(25,host.clientWidth/host.clientHeight,.01,100),renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setSize(host.clientWidth,host.clientHeight);renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.appendChild(renderer.domElement);scene.add(new THREE.HemisphereLight(0xcfdcff,0x302641,2));const key=new THREE.DirectionalLight(0xffffff,2.4);key.position.set(3,5,5);scene.add(key);const model=gltf.scene,box=new THREE.Box3().setFromObject(model),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());model.position.sub(center);scene.add(model);camera.position.set(0,size.y*.03,Math.max(size.x,size.y)*2.25);camera.lookAt(0,0,0);const controls=new THREE.OrbitControls(camera,renderer.domElement);controls.enablePan=false;controls.minDistance=camera.position.z*.75;controls.maxDistance=camera.position.z*1.15;controls.target.set(0,0,0);(function draw(){requestAnimationFrame(draw);controls.update();renderer.render(scene,camera)})()});
  }
  function scrubLegacySprites(){document.documentElement.style.removeProperty('--items-img');document.querySelectorAll('.itempic.p1,.itempic.p2,.itempic.p3,.itempic.p4,.itempic.p5,.itempic.p6,.itempic.p7,.itempic.p8').forEach(el=>{for(let i=1;i<=8;i++)el.classList.remove('p'+i);el.style.backgroundImage='none'})}
  migrate();window.BlingGeneration={config,request,generateTryOn,createBodyModel,uploadReference,deleteReference,ensureGarment};installBodyEditor();window.BlingGeneration.openBodyEditor=window.openBodyEditor3D;
  document.addEventListener('click',event=>{const button=event.target.closest?.('[data-open="body"]');if(!button)return;event.preventDefault();event.stopImmediatePropagation();window.BlingGeneration.openBodyEditor()},true);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',scrubLegacySprites);else scrubLegacySprites();
})();

