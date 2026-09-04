(function(){
  'use strict';
  const API=String(window.BLING_API_BASE||'http://127.0.0.1:8765').replace(/\/$/,'');
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

  async function request(path,options={}){
    const response=await fetch(API+path,options);
    let body=null;try{body=await response.json()}catch(_){ }
    if(!response.ok){const detail=body?.detail||body||{};throw Error(detail.message||'本地抠图服务暂时不可用')}
    return body;
  }

  async function uploadAndCutout(files){
    const form=new FormData();files.forEach(file=>form.append('files',file,file.name));
    const job=await request('/api/import/photos',{method:'POST',body:form});
    let transient=0;
    for(let i=0;i<180;i++){
      try{
        const row=await request('/api/jobs/'+encodeURIComponent(job.id));transient=0;
        if(row.status==='ready'||row.status==='review')return row.result?.garments||[];
        if(row.status==='failed')throw Error(row.error?.message||'本地抠图失败');
        window.BlingLegacyImport?.showImportProgress('正在进行本地 AI 抠图',Math.max(1,row.progress||1),100);
      }catch(error){if(++transient>5)throw error}
      await sleep(800);
    }
    throw Error('抠图处理时间较长，请重新尝试');
  }

  const legacy=window.BlingLegacyImport;
  if(!legacy)return;

  const placeholder=value=>!String(value||'').trim()||/^(待确认|待识别|未知|未命名单品|待命名单品)$/.test(String(value).trim());
  const noisyName=value=>placeholder(value)||/^(?:\d+[_-])|来自|网页|商品图|白底图|原图|实拍|截图|小红书|淘宝|拼多多|codex|clipboard/i.test(String(value||''));
  function mergeAnalysis(garment,local){
    const confidence=garment.confidence||{},low=key=>Number(confidence[key]||0)<.6;
    return {
      name:(!noisyName(garment.name)&&!low('name'))?garment.name:local.name,
      category:(!placeholder(garment.category)&&!low('category'))?garment.category:local.category,
      season:(!placeholder(garment.season)&&!low('season'))?garment.season:local.season,
      color:(!placeholder(garment.color)&&!low('color'))?garment.color:local.color,
      material:(!placeholder(garment.material)&&!low('material'))?garment.material:local.material,
      style:(!placeholder(garment.style)&&!low('style'))?garment.style:local.style,
      shape:(!placeholder(garment.fit)&&!low('fit'))?garment.fit:local.shape
    };
  }

  async function processAlbumFilesWithCutout(files,append){
    const list=[...files].filter(file=>file.type.startsWith('image/'));
    if(!list.length)return legacy.toast('请选择图片文件');
    let drafts=append?legacy.getDrafts().slice():[];
    const locallyAnalyzed=[];
    for(let i=0;i<list.length;i++){
      legacy.showImportProgress('正在分析衣服细节',i+1,list.length);
      try{
        const src=await legacy.readImportFile(list[i]),crop={zoom:1,offsetX:0,offsetY:0},pic=await legacy.cropAndAnalyzeImport(src,crop),meta=legacy.analyzeImportText(list[i].name,pic.visual);
        locallyAnalyzed.push({meta,src,crop,visual:pic.visual,fallbackImage:pic.image});
      }catch(_){
        locallyAnalyzed.push({meta:legacy.analyzeImportText(list[i].name,null),src:'',crop:{zoom:1,offsetX:0,offsetY:0},visual:null,fallbackImage:''});
      }
    }
    try{
      const garments=await uploadAndCutout(list);
      garments.forEach((garment,index)=>{
        const sourceIndex=Number.isInteger(garment.source_position)?garment.source_position:Math.min(index,locallyAnalyzed.length-1),local=locallyAnalyzed[sourceIndex]||locallyAnalyzed[0];
        const labels=mergeAnalysis(garment,local.meta);
        const variant=garment.display_variant||'white',variants={original:garment.original_url||local.src,cutout:garment.cutout_url||'',white:garment.white_bg_url||'',ai:garment.ai_url||''};
        drafts.push({
          name:labels.name,category:labels.category,season:labels.season,
          color:labels.color,material:labels.material,style:labels.style,shape:labels.shape,
          image:variants[variant]||variants.white||variants.cutout||local.fallbackImage,original:variants.original,
          crop:local.crop,visual:local.visual,source:'相册：'+list[sourceIndex].name,needImage:false,
          garmentId:garment.id||'',cutoutUrl:variants.cutout,whiteUrl:variants.white,aiUrl:variants.ai,
          sourceImage:garment.source_image_url||local.src,detectionBBox:garment.detection_bbox||null,
          inputType:garment.input_type||'clean_product',aiRequired:!!garment.ai_required,aiStatus:garment.ai_status||'not_needed',
          aiReason:garment.ai_reason||'',reconstructionLabel:garment.reconstruction_label||'真实基础抠图',selectedVariant:variant,
          candidateIndex:garment.candidate_index||0,candidateCount:garment.candidate_count||1,selected:true
        });
      });
      legacy.setDrafts(drafts);legacy.renderImportDrafts();
      legacy.toast('已完成本地抠图和标签分析 ✦');
    }catch(error){
      legacy.toast(error.message+'，已保留原版图片分析');
      locallyAnalyzed.forEach((local,index)=>drafts.push({...local.meta,image:local.fallbackImage,original:local.src,crop:local.crop,visual:local.visual,source:'相册：'+list[index].name,needImage:!local.fallbackImage}));
      legacy.setDrafts(drafts);legacy.renderImportDrafts();
    }
  }

  async function approveDrafts(drafts){
    for(const draft of drafts.filter(d=>d.selected!==false&&d.garmentId)){
      await request('/api/garments/'+encodeURIComponent(draft.garmentId),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:draft.name,category:draft.category,season:draft.season,color:draft.color,material:draft.material,style:draft.style,fit:draft.shape,display_variant:draft.selectedVariant||'white'})});
      await request('/api/garments/'+encodeURIComponent(draft.garmentId)+'/approve',{method:'POST'});
    }
  }
  window.BlingCutoutBridge={processAlbumFiles:processAlbumFilesWithCutout,approveDrafts};
  document.addEventListener('change',event=>{
    const input=event.target;if(input?.id!=='quickAlbumInput'&&input?.id!=='batchAlbumInput')return;
    event.preventDefault();event.stopImmediatePropagation();
    if(input.id==='quickAlbumInput')legacy.openImportHub();
    processAlbumFilesWithCutout(input.files,false);
  },true);
})();
