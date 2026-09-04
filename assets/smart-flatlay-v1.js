(function(){
  'use strict';
  const legacy=window.BlingLegacyImport;if(!legacy)return;
  const API=String(window.BLING_API_BASE||'http://127.0.0.1:8765').replace(/\/$/,'');
  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const types={clean_product:'干净背景单件图',worn:'真人穿着图',multi_flatlay:'多件穿搭图',complex_single:'复杂背景/透视图'};
  async function request(path,options={}){const response=await fetch(API+path,options);let body={};try{body=await response.json()}catch(_){ }if(!response.ok){const detail=body.detail||body||{};throw Error(detail.message||'本地智能平铺处理失败')}return body}
  function variantUrl(draft,variant){return {original:draft.original,cutout:draft.cutoutUrl,ai:draft.aiUrl,white:draft.whiteUrl}[variant]||''}
  function sourcePreview(draft){
    if(!draft.sourceImage)return '';
    const box=draft.detectionBBox,style=box?'left:'+(box[0]*100)+'%;top:'+(box[1]*100)+'%;width:'+(box[2]*100)+'%;height:'+(box[3]*100)+'%':'';
    return '<div class="smart-source"><img src="'+esc(draft.sourceImage)+'" alt="上传原图">'+(box?'<i style="'+style+'"></i>':'')+'<small>原图'+(draft.candidateCount>1?' · 检测框 '+(draft.candidateIndex+1):'')+'</small></div>';
  }
  function render(){
    const host=document.querySelector('#importWorkspace'),drafts=legacy.getDrafts();if(!host)return;
    if(!drafts.length){host.innerHTML='<p class="import-note">选择照片后会先判断单件图、真人穿着图或多件穿搭图，再进入审核。</p>';return}
    const categories=['上衣','外套','裤子','裙子','鞋','包','配饰','头巾'],seasons=['春','夏','秋','冬','春夏','秋冬','四季'];
    host.innerHTML='<div class="smart-import-summary"><b>智能平铺审核</b><span>已检测 '+drafts.length+' 件候选单品，请勾选要导入的衣服</span></div><div class="batch-import-list smart-review-list">'+drafts.map((d,i)=>{
      const aiText=d.aiStatus==='ready'?'AI 平铺重建已生成':d.aiRequired?(d.aiStatus==='failed'?'AI 重建失败，已保留基础抠图':d.aiStatus==='unavailable'?'需要 AI 补全，但本机模型未就绪':'等待 AI 平铺重建'):'图片完整，无需 AI 重绘';
      const tabs=[['original','原图'],['cutout','基础抠图'],['ai','AI 平铺重建'],['white','暖白成品']].map(([key,label])=>'<button type="button" data-smart-variant="'+key+'" data-smart-index="'+i+'" class="'+(d.selectedVariant===key?'on':'')+'" '+(!variantUrl(d,key)?'disabled':'')+'>'+label+'</button>').join('');
      return '<article class="import-draft smart-draft '+(d.selected===false?'is-skipped':'')+'"><label class="smart-pick"><input type="checkbox" data-smart-select="'+i+'" '+(d.selected===false?'':'checked')+'><span>导入此单品</span></label><div class="smart-visuals"><button type="button" class="draft-picture can-crop" data-crop-draft="'+i+'" style="background-image:url(\''+esc(d.image)+'\')" aria-label="扫描编辑单品"></button></div><div class="smart-variant-tabs">'+tabs+'</div><div class="smart-process-state '+(d.aiRequired?'needs-ai':'')+'"><b>'+esc(types[d.inputType]||'单件商品图')+'</b><span>'+esc(aiText)+'</span>'+(d.aiRequired&&d.aiStatus!=='ready'?'<button type="button" data-smart-ai="'+i+'">生成 AI 平铺图</button>':'')+'</div><div class="draft-main"><header><b>单品 '+(i+1)+(d.candidateCount>1?' / 同图 '+d.candidateCount+' 件':'')+'</b><button class="draft-remove" data-remove-draft="'+i+'" aria-label="移除">×</button></header><div class="draft-fields"><label>名称<input data-draft-field="name" data-draft-index="'+i+'" value="'+esc(d.name)+'"></label><label>品类<select data-draft-field="category" data-draft-index="'+i+'">'+categories.map(x=>'<option '+(x===d.category?'selected':'')+'>'+x+'</option>').join('')+'</select></label><label>季节<select data-draft-field="season" data-draft-index="'+i+'">'+seasons.map(x=>'<option '+(x===d.season?'selected':'')+'>'+x+'</option>').join('')+'</select></label><label>色系<input data-draft-field="color" data-draft-index="'+i+'" value="'+esc(d.color)+'"></label><label>材质<input data-draft-field="material" data-draft-index="'+i+'" value="'+esc(d.material)+'"></label><label>风格<input data-draft-field="style" data-draft-index="'+i+'" value="'+esc(d.style)+'"></label><label>版型<input data-draft-field="shape" data-draft-index="'+i+'" value="'+esc(d.shape)+'"></label></div><small class="draft-status">'+esc(d.reconstructionLabel||'真实基础抠图')+' · 点击图片可继续扫描编辑</small></div></article>';
    }).join('')+'</div><div class="import-footer"><span class="import-count">已选择 '+drafts.filter(d=>d.selected!==false).length+' / '+drafts.length+' 件</span><button class="primary" id="confirmBatchImport">确认加入衣橱</button></div>';
  }
  legacy.renderImportDrafts=render;
  document.addEventListener('change',event=>{const input=event.target.closest?.('[data-smart-select]');if(!input)return;const drafts=legacy.getDrafts(),draft=drafts[+input.dataset.smartSelect];if(draft){draft.selected=input.checked;render()}},true);
  document.addEventListener('click',async event=>{
    const variant=event.target.closest?.('[data-smart-variant]');if(variant){event.preventDefault();event.stopImmediatePropagation();const drafts=legacy.getDrafts(),draft=drafts[+variant.dataset.smartIndex],key=variant.dataset.smartVariant,url=variantUrl(draft,key);if(url){draft.selectedVariant=key;draft.image=url;draft.reconstructionLabel=key==='ai'?'AI 平铺重建':'真实基础抠图';render()}return}
    const ai=event.target.closest?.('[data-smart-ai]');if(ai){event.preventDefault();event.stopImmediatePropagation();const drafts=legacy.getDrafts(),draft=drafts[+ai.dataset.smartAi];ai.disabled=true;ai.textContent='正在本地重建…';try{const garment=await request('/api/garments/'+encodeURIComponent(draft.garmentId)+'/process',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'ai_generate'})});draft.aiUrl=garment.ai_url;draft.aiStatus='ready';draft.selectedVariant='ai';draft.image=garment.ai_url;draft.reconstructionLabel='AI 平铺重建';render();legacy.toast('AI 平铺重建已生成，请对比后确认 ✦')}catch(error){draft.aiStatus='unavailable';legacy.toast(error.message);render()}return}
    const confirm=event.target.closest?.('#confirmBatchImport');if(confirm){const selected=legacy.getDrafts().filter(d=>d.selected!==false);if(!selected.length){event.preventDefault();event.stopImmediatePropagation();legacy.toast('请至少勾选一件要导入的单品');return}legacy.setDrafts(selected)}
  },true);
})();
