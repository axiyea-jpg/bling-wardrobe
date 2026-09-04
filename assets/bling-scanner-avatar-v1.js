(function(){
  'use strict';
  const API=String(window.BLING_API_BASE||'http://127.0.0.1:8765').replace(/\/$/,'');
  const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

  async function api(path,options={}){
    const response=await fetch(API+path,options);let body={};
    try{body=await response.json()}catch(_){ }
    if(!response.ok){const detail=body.detail||body||{};throw Error(detail.message||'本地扫描抠图失败')}
    return body;
  }
  function loadImage(src){return new Promise((resolve,reject)=>{const image=new Image();image.crossOrigin='anonymous';image.onload=()=>resolve(image);image.onerror=()=>reject(Error('图片读取失败'));image.src=src})}
  function canvasBlob(canvas){return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(Error('扫描图片生成失败')),'image/png'))}

  async function openScanner(index){
    const legacy=window.BlingLegacyImport,draft=legacy?.getDrafts()?.[index];if(!draft?.original)return legacy?.toast('这件衣服缺少可编辑的原图');
    const original=await loadImage(draft.original),processed=draft.cutoutUrl?await loadImage(draft.cutoutUrl).catch(()=>null):null,white=draft.image?await loadImage(draft.image).catch(()=>null):null;
    const saved=draft.scan||{},state={zoom:+saved.zoom||1,rotation:+saved.rotation||0,x:+saved.x||0,y:+saved.y||0,view:'original',grid:true};
    const layer=document.createElement('div');layer.className='scanner-layer';
    layer.innerHTML='<section class="scanner-card"><header class="scanner-head"><h3>扫描衣服图片</h3><button class="scanner-close" aria-label="关闭">×</button></header><div class="scanner-tabs"><button class="on" data-scan-view="original">原图调整</button><button data-scan-view="cutout" '+(processed?'':'disabled')+'>透明抠图</button><button data-scan-view="white" '+(white?'':'disabled')+'>暖白成品</button></div><div class="scanner-stage grid-on"><canvas width="900" height="900"></canvas></div><p class="scanner-hint">拖动衣服调整位置；旋转支持完整 360°，网格帮助校正水平与垂直。保存后会重新扫描边缘并生成干净背景的 2D 单品图。</p><div class="scanner-quick"><button data-scan-turn="-90">左转 90°</button><button data-scan-turn="90">右转 90°</button><button class="on" data-scan-grid>网格线</button><button data-scan-reset>恢复</button></div><div class="scanner-controls"><label class="scanner-control"><span>旋转</span><input data-scan-rotation type="range" min="-180" max="180" step="1" value="'+state.rotation+'"><output>'+Math.round(state.rotation)+'°</output></label><label class="scanner-control"><span>缩放</span><input data-scan-zoom type="range" min="0.5" max="3" step="0.01" value="'+state.zoom+'"><output>'+state.zoom.toFixed(2)+'×</output></label></div><div class="scanner-actions"><button class="scanner-soft scanner-close">取消</button><button class="primary" data-scan-save>扫描抠图并应用</button></div><div class="scanner-status"></div></section>';
    document.body.appendChild(layer);
    const canvas=layer.querySelector('canvas'),ctx=canvas.getContext('2d'),stage=layer.querySelector('.scanner-stage'),rotation=layer.querySelector('[data-scan-rotation]'),zoom=layer.querySelector('[data-scan-zoom]'),status=layer.querySelector('.scanner-status');
    const currentImage=()=>state.view==='cutout'&&processed?processed:state.view==='white'&&white?white:original;
    function draw(forceTransparent=false){
      const image=currentImage(),size=canvas.width;ctx.clearRect(0,0,size,size);
      if(!forceTransparent){ctx.fillStyle=state.view==='cutout'?'#ece6e2':'#fffdfc';ctx.fillRect(0,0,size,size)}
      ctx.save();ctx.translate(size/2+state.x,size/2+state.y);ctx.rotate(state.rotation*Math.PI/180);
      const fit=Math.min(size/image.naturalWidth,size/image.naturalHeight)*.84*(state.view==='original'?state.zoom:1),w=image.naturalWidth*fit,h=image.naturalHeight*fit;
      ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(image,-w/2,-h/2,w,h);ctx.restore();
    }
    function setOriginal(){if(state.view==='original')return;state.view='original';layer.querySelectorAll('[data-scan-view]').forEach(b=>b.classList.toggle('on',b.dataset.scanView==='original'));draw()}
    draw();let dragging=false,lastX=0,lastY=0;
    stage.onpointerdown=event=>{if(state.view!=='original')return;dragging=true;lastX=event.clientX;lastY=event.clientY;stage.setPointerCapture(event.pointerId)};
    stage.onpointermove=event=>{if(!dragging)return;const rect=stage.getBoundingClientRect();state.x+=(event.clientX-lastX)*canvas.width/rect.width;state.y+=(event.clientY-lastY)*canvas.height/rect.height;lastX=event.clientX;lastY=event.clientY;draw()};stage.onpointerup=()=>dragging=false;stage.onpointercancel=()=>dragging=false;
    rotation.oninput=()=>{setOriginal();state.rotation=+rotation.value;rotation.nextElementSibling.textContent=Math.round(state.rotation)+'°';draw()};
    zoom.oninput=()=>{setOriginal();state.zoom=+zoom.value;zoom.nextElementSibling.textContent=state.zoom.toFixed(2)+'×';draw()};
    layer.querySelectorAll('[data-scan-view]').forEach(button=>button.onclick=()=>{if(button.disabled)return;state.view=button.dataset.scanView;layer.querySelectorAll('[data-scan-view]').forEach(b=>b.classList.toggle('on',b===button));draw()});
    layer.querySelectorAll('[data-scan-turn]').forEach(button=>button.onclick=()=>{setOriginal();state.rotation=clamp(state.rotation+(+button.dataset.scanTurn),-180,180);rotation.value=state.rotation;rotation.nextElementSibling.textContent=Math.round(state.rotation)+'°';draw()});
    layer.querySelector('[data-scan-grid]').onclick=event=>{state.grid=!state.grid;stage.classList.toggle('grid-on',state.grid);event.currentTarget.classList.toggle('on',state.grid)};
    layer.querySelector('[data-scan-reset]').onclick=()=>{state.zoom=1;state.rotation=0;state.x=0;state.y=0;rotation.value=0;zoom.value=1;rotation.nextElementSibling.textContent='0°';zoom.nextElementSibling.textContent='1.00×';setOriginal();draw()};
    layer.querySelectorAll('.scanner-close').forEach(button=>button.onclick=()=>layer.remove());
    layer.querySelector('[data-scan-save]').onclick=async event=>{
      const button=event.currentTarget;button.disabled=true;button.textContent='正在扫描衣服边缘…';status.textContent='本地抠图模型正在生成透明图和暖白商品图';
      try{
        state.view='original';draw(true);const blob=await canvasBlob(canvas);
        if(draft.garmentId){const form=new FormData();form.append('file',blob,'scanner.png');const garment=await api('/api/garments/'+encodeURIComponent(draft.garmentId)+'/scan',{method:'POST',body:form}),stamp=(garment.white_bg_url||garment.thumbnail_url||garment.cutout_url).includes('?')?'&':'?';draft.image=(garment.white_bg_url||garment.thumbnail_url||garment.cutout_url)+stamp+'v='+Date.now();draft.cutoutUrl=garment.cutout_url||'';draft.whiteUrl=garment.white_bg_url||'';draft.selectedVariant='white';draft.reconstructionLabel='真实基础抠图'}
        else{draft.image=canvas.toDataURL('image/png')}
        draft.scan={zoom:state.zoom,rotation:state.rotation,x:state.x,y:state.y};draft.needImage=false;layer.remove();legacy.renderImportDrafts();legacy.toast('扫描抠图已应用，背景已清理 ✦');
      }catch(error){status.textContent=error.message;button.disabled=false;button.textContent='重新扫描抠图'}
    };
  }
  window.openImportCropEditor=openScanner;
  document.addEventListener('click',event=>{const button=event.target.closest?.('[data-crop-draft]');if(!button)return;event.preventDefault();event.stopImmediatePropagation();openScanner(+button.dataset.cropDraft)},true);

  function pair(influences,dict,positive,negative,value){
    if(dict[positive]!=null)influences[dict[positive]]=Math.max(0,value);
    if(dict[negative]!=null)influences[dict[negative]]=Math.max(0,-value);
  }
  function applyFemaleProfile(model,profile={}){
    const height=+profile.height||162,weight=+profile.weight||52,bmi=weight/Math.pow(height/100,2);
    const normalized=(value,base,span)=>clamp(((+value||base)-base)/span,-1,1);
    const morph={
      height:normalized(height,162,30),heavy:normalized(bmi,19.8,12),bust:normalized(profile.bust,84,35),waist:normalized(profile.waist,66,38),hips:normalized(profile.hip,92,38),shoulders:normalized(profile.shoulder,38,13),thighs:normalized(profile.thigh||((+profile.hip||92)*.57),52,24),arms:normalized(profile.upper_arm||27,27,17),legs:normalized(profile.leg_length||82,82,24),neck:normalized(profile.neck||34,34,14)
    };
    const mass=clamp(1+morph.heavy*.16,.84,1.18),mix=(a,b,t)=>a+(b-a)*t;
    const widths={
      'mixamorig:Hips':clamp(1+morph.hips*.16,mass*.9,1.24),'mixamorig:Spine':clamp(1+morph.waist*.13,.84,1.2),
      'mixamorig:Spine1':clamp(1+morph.bust*.12,.86,1.18),'mixamorig:Spine2':clamp(1+mix(morph.bust,morph.shoulders,.58)*.12,.86,1.2),
      'mixamorig:LeftShoulder':clamp(1+morph.shoulders*.1,.9,1.15),'mixamorig:RightShoulder':clamp(1+morph.shoulders*.1,.9,1.15),
      'mixamorig:LeftUpLeg':clamp(1+morph.thighs*.14,mass*.88,1.2),'mixamorig:RightUpLeg':clamp(1+morph.thighs*.14,mass*.88,1.2),
      'mixamorig:LeftLeg':clamp(1+mix(morph.thighs,morph.heavy,.45)*.08,.9,1.13),'mixamorig:RightLeg':clamp(1+mix(morph.thighs,morph.heavy,.45)*.08,.9,1.13),
      'mixamorig:LeftArm':clamp(1+morph.arms*.11,.9,1.15),'mixamorig:RightArm':clamp(1+morph.arms*.11,.9,1.15),
      'mixamorig:LeftForeArm':clamp(1+morph.arms*.06,.94,1.1),'mixamorig:RightForeArm':clamp(1+morph.arms*.06,.94,1.1),
      'mixamorig:Neck':clamp(1+morph.neck*.08,.93,1.1)
    };
    model.traverse(node=>{if(node.isSkinnedMesh&&node.morphTargetDictionary){const dict=node.morphTargetDictionary,values=node.morphTargetInfluences;values.fill(0);pair(values,dict,'bodyHeavier','bodyThinner',morph.heavy);pair(values,dict,'bustBigger','bustSmaller',morph.bust);pair(values,dict,'waistWider','waistNarrower',morph.waist);pair(values,dict,'hipsWider','hipsNarrower',morph.hips);pair(values,dict,'shouldersWider','shouldersNarrower',morph.shoulders)}if(node.isBone){if(!node.userData.blingBaseScale)node.userData.blingBaseScale=node.scale.clone();const base=node.userData.blingBaseScale,width=widths[node.name]||1;node.scale.set(base.x*width,base.y,base.z*width)}});
    if(!model.userData.blingBaseScale)model.userData.blingBaseScale=model.scale.clone();const base=model.userData.blingBaseScale,heightScale=clamp(height/162,.88,1.14);model.scale.set(base.x,base.y*heightScale,base.z);model.updateMatrixWorld(true);
  }
  async function mountFemaleModel(host,profile){
    if(!window.THREE?.GLTFLoader)throw Error('3D 查看组件未加载');
    if(!THREE.Mesh.prototype.__blingSafeMorphTargets){
      THREE.Mesh.prototype.__blingSafeMorphTargets=true;
      THREE.Mesh.prototype.updateMorphTargets=function(){
        const morphAttributes=this.geometry?.morphAttributes||{},keys=Object.keys(morphAttributes);if(!keys.length)return;
        const attributes=morphAttributes[keys[0]]||[];this.morphTargetInfluences=[];this.morphTargetDictionary={};
        for(let i=0;i<attributes.length;i++){const attribute=attributes[i];this.morphTargetInfluences.push(0);if(attribute)this.morphTargetDictionary[attribute.name||String(i)]=i}
      };
    }
    window.__blingFemaleBody?.destroy?.();
    const response=await fetch(new URL('assets/models/female-rigged-web.glb?v=1',location.href));if(!response.ok)throw Error('女性基础模型读取失败');const buffer=await response.arrayBuffer();
    return new Promise((resolve,reject)=>new THREE.GLTFLoader().parse(buffer,'',gltf=>{
      host.querySelectorAll('canvas').forEach(x=>x.remove());const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(24,host.clientWidth/host.clientHeight,.01,100),renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setSize(host.clientWidth,host.clientHeight);renderer.outputEncoding=THREE.sRGBEncoding;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.72;host.appendChild(renderer.domElement);
      scene.add(new THREE.HemisphereLight(0xfff5f2,0x62535b,.78));const key=new THREE.DirectionalLight(0xfff8f2,1.05);key.position.set(3,5,5);scene.add(key);const fill=new THREE.DirectionalLight(0xdc9caf,.34);fill.position.set(-4,2,3);scene.add(fill);const rim=new THREE.DirectionalLight(0xadc9e8,.42);rim.position.set(2,3,-4);scene.add(rim);
      const model=gltf.scene;let skinned=0,bones=0;model.traverse(node=>{if(node.isBone)bones++;if(!node.isMesh)return;if(node.isSkinnedMesh){skinned++;node.normalizeSkinWeights()}node.frustumCulled=false;const count=node.geometry.attributes.position.count;Object.values(node.geometry.morphAttributes||{}).forEach(attributes=>{for(let i=0;i<attributes.length;i++)if(!attributes[i])attributes[i]=new THREE.Float32BufferAttribute(new Float32Array(count*3),3)});node.geometry.computeVertexNormals();if(/Eyes/i.test(node.name))node.material=new THREE.MeshPhysicalMaterial({color:0x30272b,roughness:.32,clearcoat:.4,morphTargets:true,skinning:true});else if(/Teeth|Tongue/i.test(node.name))node.visible=false;else node.material=new THREE.MeshPhysicalMaterial({color:0xa87e81,roughness:.74,metalness:0,clearcoat:.03,side:THREE.DoubleSide,skinning:true,morphTargets:true})});
      if(!skinned||!bones){reject(Error('女性 GLB 缺少有效骨骼'));return}applyFemaleProfile(model,profile);const box=new THREE.Box3().setFromObject(model),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());model.position.sub(center);scene.add(model);const fitDistance=(size.y*.56)/Math.tan(THREE.MathUtils.degToRad(camera.fov*.5));camera.position.set(0,size.y*.015,fitDistance);camera.lookAt(0,0,0);const controls=new THREE.OrbitControls(camera,renderer.domElement);controls.enablePan=false;controls.enableDamping=true;controls.dampingFactor=.08;controls.minDistance=fitDistance*.72;controls.maxDistance=fitDistance*1.45;controls.minPolarAngle=Math.PI*.28;controls.maxPolarAngle=Math.PI*.72;controls.target.set(0,0,0);
      let active=true,frame=0;const draw=()=>{if(!active)return;frame=requestAnimationFrame(draw);controls.update();renderer.render(scene,camera)};draw();const resize=()=>{if(!active)return;camera.aspect=host.clientWidth/host.clientHeight;camera.updateProjectionMatrix();renderer.setSize(host.clientWidth,host.clientHeight)};addEventListener('resize',resize);
      window.__blingFemaleBody={model,apply:p=>applyFemaleProfile(model,p),skinnedMeshes:skinned,bones,destroy(){active=false;cancelAnimationFrame(frame);removeEventListener('resize',resize);controls.dispose();renderer.dispose()}};resolve(window.__blingFemaleBody);
    },reject));
  }
  function openFemaleBodyEditor(){
    let saved={};try{saved=JSON.parse(localStorage.getItem('bling-body')||'{}')}catch(_){ }
    const values={height:162,weight:52,bust:84,waist:66,hip:92,shoulder:38,...saved},base=[['height','身高','cm',140,205],['weight','体重','kg',35,180],['bust','胸围','cm',65,155],['waist','腰围','cm',45,150],['hip','臀围','cm',65,165],['shoulder','肩宽','cm',28,60]],advanced=[['neck','颈围','cm',25,60],['thigh','大腿围','cm',30,100],['knee','膝围','cm',25,75],['upper_arm','上臂围','cm',18,70],['wrist','腕围','cm',10,35],['leg_length','腿长','cm',60,125]];
    const field=m=>'<div class="metric-control"><header><b>'+m[1]+'</b><span class="metric-value"><input id="body-'+m[0]+'" type="number" min="'+m[3]+'" max="'+m[4]+'" value="'+(values[m[0]]??'')+'"><em>'+m[2]+'</em></span></header></div>';
    document.querySelector('#subTitle').textContent='身体数据';document.querySelector('#subContent').innerHTML='<div class="body-visualizer bling-female-editor"><div class="human-viewport" id="femaleBodyViewport"><span class="female-model-state" id="femaleModelState">正在加载同款数字衣模</span><span class="female-model-help">手指拖动可 360° 旋转 · 双指缩放</span></div><div class="metric-panel">'+base.map(field).join('')+'<div class="bmi-card body-bmi-card"><header><b>BMI</b><span id="bodyBmiState">健康范围</span></header><div class="bmi-reading"><strong id="bodyBmiValue">--</strong><small>kg/m²</small></div><div class="bmi-scale"><i id="bodyBmiMarker"></i></div><div class="bmi-labels"><span>16.5</span><span>18.5</span><span>25</span><span>30</span><span>35+</span></div></div><details class="body-advanced"><summary>高级身体数据（选填，提高精度）</summary><div class="advanced-grid">'+advanced.map(field).join('')+'</div></details><button class="primary" id="saveBody">保存身体数据</button></div></div>';document.querySelector('#overlay').classList.add('show');
    const read=()=>Object.fromEntries([...base,...advanced].map(m=>{const input=document.querySelector('#body-'+m[0]);return[m[0],input&&input.value!==''?+input.value:null]})),updateBmi=()=>{const p=read(),value=p.height&&p.weight?p.weight/Math.pow(p.height/100,2):0,v=document.querySelector('#bodyBmiValue'),s=document.querySelector('#bodyBmiState'),marker=document.querySelector('#bodyBmiMarker');v.textContent=value?value.toFixed(1):'--';s.textContent=!value?'等待数据':value<18.5?'偏轻':value<25?'健康范围':value<30?'偏高':value<35?'肥胖 I 级':'肥胖 II 级';marker.style.left=clamp((value-16.5)/(40-16.5)*100,0,100)+'%'};
    const host=document.querySelector('#femaleBodyViewport'),state=document.querySelector('#femaleModelState');mountFemaleModel(host,read()).then(()=>state.textContent='我的数字衣模 · 已同步身形').catch(error=>{console.error('Female GLB load failed',error);state.textContent=error.message});document.querySelectorAll('[id^="body-"]').forEach(input=>input.addEventListener('input',()=>{updateBmi();window.__blingFemaleBody?.apply(read())}));updateBmi();document.querySelector('#saveBody').onclick=()=>{const profile=read();Object.keys(profile).forEach(key=>profile[key]==null&&delete profile[key]);localStorage.setItem('bling-body',JSON.stringify(profile));state.textContent='身形数据已保存并同步到首页';window.BlingLegacyImport?.toast?.('身体数据与数字衣模已同步 ✦')};
  }
  window.openBodyEditor3D=openFemaleBodyEditor;if(window.BlingGeneration)window.BlingGeneration.openBodyEditor=openFemaleBodyEditor;
})();
