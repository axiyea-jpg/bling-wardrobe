(function () {
  'use strict';

  const SCHEMA_KEY = 'bling-wardrobe-schema-v4';
  const OUTFIT_KEY = 'bling-outfit-v3';
  const AUTH_KEY = 'bling-anonymous-auth-v1';
  const BODY_MODEL_KEY = 'bling-body-model-id-v2';
  const LEGACY_KEYS = [
    'bling-items', 'bling-seasons', 'bling-item-meta', 'bling-current-outfit-v1',
    'bling-current-outfit-v2', 'bling-tryon-cache-v1', 'bling-tryon-cache-v2',
    'bling-thumb-cache', 'bling-image-cache', 'bling-item-image-cache',
    'bling-item-thumbnail-cache', 'bling-wardrobe-thumbnail-repair-v1',
    'bling-wardrobe-thumbnail-repair-v2', 'bling-wardrobe-clean-reset-v1'
  ];
  const CATEGORIES = ['\u4e0a\u8863', '\u5916\u5957', '\u88e4\u5b50', '\u88d9\u5b50', '\u978b', '\u5305', '\u914d\u9970', '\u5934\u5dfe'];
  const SEASONS = ['全部','春','夏','秋','冬','春夏','秋冬','四季'];
  const CATEGORY_ICONS = {
    '\u4e0a\u8863':'top', '\u5916\u5957':'outer', '\u88e4\u5b50':'pants', '\u88d9\u5b50':'skirt',
    '\u978b':'shoes', '\u5305':'bag', '\u914d\u9970':'accessory', '\u5934\u5dfe':'scarf'
  };
  const LAYERS = [
    ['top', '上衣', ['上衣']], ['outerwear', '外套', ['外套']],
    ['bottom', '下装', ['裤子', '裙子']], ['dress', '连衣裙', ['连衣裙']],
    ['shoes', '鞋', ['鞋']], ['bag', '包', ['包']],
    ['accessory', '配饰', ['配饰']], ['headscarf', '头巾', ['头巾']]
  ];
  const q = (s, root = document) => root.querySelector(s);
  const qa = (s, root = document) => [...root.querySelectorAll(s)];
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  function migrate() {
    if (localStorage.getItem(SCHEMA_KEY) === '4') return [];
    let legacy=[];try{const rows=JSON.parse(localStorage.getItem('bling-items')||'[]'),imagePrefix='data:'+'image/',frequencies={};rows.forEach(row=>{if(typeof row?.[3]==='string'&&row[3].startsWith(imagePrefix))frequencies[row[3]]=(frequencies[row[3]]||0)+1});legacy=rows.filter(row=>row?.[2]==='imported'&&typeof row?.[3]==='string'&&row[3].startsWith(imagePrefix)&&frequencies[row[3]]===1).map((row,index)=>({name:(row[0]||'迁移单品')+'.jpg',data:row[3],index}))}catch(_){}
    LEGACY_KEYS.forEach(key => localStorage.removeItem(key));
    localStorage.removeItem(OUTFIT_KEY);
    localStorage.setItem(SCHEMA_KEY, '4');
    document.documentElement.style.removeProperty('--items-img');
    return legacy;
  }

  function legacyFile(row){const parts=row.data.split(','),mime=(parts[0].match(/data:([^;]+)/)||[])[1]||'image/jpeg',bytes=atob(parts[1]||''),data=new Uint8Array(bytes.length);for(let i=0;i<bytes.length;i++)data[i]=bytes.charCodeAt(i);return new File([data],row.name,{type:mime})}

  function toast(message) {
    const el = q('#toast');
    if (!el) return;
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(window.__wardrobeV3Toast);
    window.__wardrobeV3Toast = setTimeout(() => el.classList.remove('show'), 2200);
  }

  const config = {
    get apiBase() {
      return String(window.BLING_API_BASE || q('meta[name="bling-api-base"]')?.content || '').replace(/\/$/, '');
    },
    get firebase() { return window.BLING_FIREBASE_CONFIG || null; }
  };

  const auth = {
    value: null,
    async get() {
      if (this.value?.idToken && this.value?.expiresAt > Date.now() + 60000) return this.value;
      try { this.value = JSON.parse(localStorage.getItem(AUTH_KEY) || 'null'); } catch (_) {}
      const fb = config.firebase;
      if (!fb?.apiKey) return this.value || {idToken: ''};
      if (this.value?.refreshToken && this.value?.expiresAt > Date.now() + 60000) return this.value;
      if (this.value?.refreshToken) {
        const response = await fetch('https://securetoken.googleapis.com/v1/token?key=' + encodeURIComponent(fb.apiKey), {
          method: 'POST', headers: {'Content-Type':'application/x-www-form-urlencoded'},
          body: new URLSearchParams({grant_type:'refresh_token', refresh_token:this.value.refreshToken})
        });
        if (response.ok) {
          const row = await response.json();
          this.value = {idToken:row.id_token, refreshToken:row.refresh_token, uid:row.user_id, expiresAt:Date.now() + (+row.expires_in * 1000)};
          localStorage.setItem(AUTH_KEY, JSON.stringify(this.value));
          return this.value;
        }
      }
      const response = await fetch('https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=' + encodeURIComponent(fb.apiKey), {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({returnSecureToken:true})
      });
      if (!response.ok) throw Error('无法建立私有衣橱身份');
      const row = await response.json();
      this.value = {idToken:row.idToken, refreshToken:row.refreshToken, uid:row.localId, expiresAt:Date.now() + (+row.expiresIn * 1000)};
      localStorage.setItem(AUTH_KEY, JSON.stringify(this.value));
      return this.value;
    }
  };

  const api = {
    async request(path, options = {}) {
      if (!config.apiBase) {
        const error = Error('本地衣橱服务未启动，请双击“启动布灵本地版.bat”后再试');
        error.code = 'local_service_not_configured';
        throw error;
      }
      const identity = await auth.get();
      const headers = new Headers(options.headers || {});
      if (identity.idToken) headers.set('Authorization', 'Bearer ' + identity.idToken);
      if (options.json !== undefined) {
        headers.set('Content-Type', 'application/json');
        options.body = JSON.stringify(options.json);
      }
      const response = await fetch(config.apiBase + path, {...options, headers});
      let body = null;
      try { body = await response.json(); } catch (_) {}
      if (!response.ok) {
        const detail = body?.detail || body || {};
        const error = Error(detail.message || '本地衣橱服务未连接，请保持启动窗口开启');
        error.code = detail.code || 'api_error';
        throw error;
      }
      return body;
    },
    async listGarments() {
      const result = await this.request('/api/garments?status=approved&limit=200');
      return (result.items || []).map(normalizeGarment);
    },
    status() { return this.request('/api/system/status'); },
    importUrl(url) { return this.request('/api/import/url', {method:'POST', json:{url}}); },
    importPhotos(files) {
      const form = new FormData();
      files.forEach(file => form.append('files', file, file.name));
      return this.request('/api/import/photos', {method:'POST', body:form});
    },
    async createImport(files) {
      const manifests = [];
      for (const file of files) {
        const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
        manifests.push({name:file.name, content_type:file.type || 'image/jpeg', size:file.size, sha256:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('')});
      }
      return this.request('/api/import/jobs', {method:'POST', json:{files:manifests, body_model_id:localStorage.getItem(BODY_MODEL_KEY) || null}});
    },
    async uploadFile(upload, file) {
      const headers = new Headers(upload.headers || {'Content-Type':file.type || 'application/octet-stream'});
      const response = await fetch(upload.upload_url, {method:upload.method || 'PUT', headers, body:file});
      if (!response.ok) throw Error('图片上传失败：' + file.name);
    },
    completeImport(id) { return this.request('/api/import/jobs/' + encodeURIComponent(id) + '/complete', {method:'POST'}); },
    getJob(id) { return this.request('/api/jobs/' + encodeURIComponent(id)); },
    approve(id) { return this.request('/api/garments/' + encodeURIComponent(id) + '/approve', {method:'POST'}); },
    patch(id, values) { return this.request('/api/garments/' + encodeURIComponent(id), {method:'PATCH', json:values}); },
    crop(id, values) { return this.request('/api/garments/' + encodeURIComponent(id) + '/crop', {method:'POST', json:values}); },
    reanalyze(id) { return this.request('/api/garments/' + encodeURIComponent(id) + '/reanalyze', {method:'POST'}); },
    process(id, mode) { return this.request('/api/garments/' + encodeURIComponent(id) + '/process', {method:'POST', json:{mode}}); },
    remove(id) { return this.request('/api/garments/' + encodeURIComponent(id), {method:'DELETE'}); },
    tryOn(garmentIds, quality = 'draft') {
      return this.request('/api/tryon/jobs', {method:'POST', json:{model_mode:'digital', body_model_id:localStorage.getItem(BODY_MODEL_KEY) || '', garment_ids:[...new Set(garmentIds)], scene:'日常通勤', quality}});
    }
  };

  function normalizeGarment(row) {
    const category = row.category === '\u8fde\u8863\u88d9' ? '\u88d9\u5b50' : (row.category || '\u4e0a\u8863');
    return {
      id:String(row.id), name:row.name || '未命名单品', category,
      season:row.season || '四季', color:row.color || '待识别', material:row.material || '待识别',
      style:row.style || '日常', fit:row.fit || '常规版型', tags:Array.isArray(row.tags) ? row.tags : [],
      status:row.status || 'processing', originalUrl:row.original_url || '', cutoutUrl:row.cutout_url || '',
      whiteBgUrl:row.white_bg_url || '', thumbnailUrl:row.thumbnail_url || '', modeledPreviewUrl:row.modeled_preview_url || '',
      lockedFields:row.locked_fields || [], confidence:row.confidence || {}
    };
  }

  const state = {
    garments: [], loading: false, category: null, season: '全部', page: 1, pageSize: 8, search: '', selected: new Set(), manage: false, serviceStatus: null,
    outfit: {top:null, outerwear:null, bottom:null, dress:null, shoes:null, bag:null, accessory:[], headscarf:null},
    activeImage: '', tryonTimer: null, tryonGeneration: 0,
    loadOutfit() {
      try { this.outfit = {...this.outfit, ...JSON.parse(localStorage.getItem(OUTFIT_KEY) || '{}')}; } catch (_) {}
      this.outfit.accessory = [...new Set(Array.isArray(this.outfit.accessory) ? this.outfit.accessory : [])];
    },
    saveOutfit() { localStorage.setItem(OUTFIT_KEY, JSON.stringify(this.outfit)); }
  };

  function imageMarkup(garment, className = '') {
    const src = garment?.thumbnailUrl || garment?.cutoutUrl || '';
    return src ? '<img class="'+className+'" src="'+esc(src)+'" alt="'+esc(garment.name)+'" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),{className:\'v3-missing\',textContent:\'需要补图\'}))">' : '<span class="v3-missing">图片处理中</span>';
  }

  function navigate(id, mode) {
    qa('.page').forEach(page => page.classList.toggle('active', page.id === id));
    qa('.nav [data-go]').forEach(button => button.classList.toggle('on', button.dataset.go === id));
    q('#overlay')?.classList.remove('show');
    q('.screen').scrollTop = 0;
    if (id === 'wardrobe') renderWardrobe();
    if (id === 'style') renderDressing(mode || 'manual');
  }

  function renderWardrobe() {
    const page = q('#wardrobe');
    if (!page) return;
    const search = state.search.toLowerCase();
    const filtered = state.garments.filter(g => (!state.category || g.category === state.category) && (state.season==='全部'||g.season===state.season) && (!search || [g.name,g.category,g.color,g.material,g.style,g.fit,...g.tags].join(' ').toLowerCase().includes(search)));
    const pages=Math.max(1,Math.ceil(filtered.length/state.pageSize));state.page=Math.min(state.page,pages);const shown=filtered.slice((state.page-1)*state.pageSize,state.page*state.pageSize);
    page.innerHTML = '<div class="title wardrobe-title"><div><p class="eyebrow">MY WARDROBE</p><h1>我的衣橱</h1></div><span class="count">'+state.garments.length+' 件</span></div>'+ 
      '<div class="search wardrobe-search">⌕<input data-v3-search placeholder="搜索名称、分类或标签" value="'+esc(state.search)+'"></div>'+ 
      (state.category?'<div class="detail-toolbar"><button data-v3-back>‹ 全部分类</button><b>'+esc(state.category)+'</b><label>季节 <select data-v3-season>'+SEASONS.map(s=>'<option '+(s===state.season?'selected':'')+'>'+s+'</option>').join('')+'</select></label></div><div class="compact-actions"><button data-v3-import>＋ 导入单品</button><button data-v3-manage>☑ 批量整理</button><label>每页 <select data-v3-page-size>'+[4,8,12,20].map(n=>'<option '+(n===state.pageSize?'selected':'')+'>'+n+'</option>').join('')+'</select></label></div>'+(state.manage?'<div class="bulkbar"><button data-v3-select-page>全选本页</button><span>已选 '+state.selected.size+' 件</span><button class="danger" data-v3-delete-selected>删除</button><button data-v3-manage>完成</button></div>':''):'')+
      (state.loading ? '<div class="v3-empty">正在读取本地衣橱…</div>' : !state.category ? categoryMarkup() : garmentGrid(shown)+pagerMarkup(pages));
  }

  function shownGarmentIds() {
    const search = state.search.toLowerCase();
    return state.garments
      .filter(g => (!state.category || g.category === state.category) &&
        (state.season === '全部' || g.season === state.season) &&
        (!search || [g.name,g.category,g.color,g.material,g.style,g.fit,...g.tags].join(' ').toLowerCase().includes(search)))
      .slice((state.page - 1) * state.pageSize, state.page * state.pageSize)
      .map(g => g.id);
  }

  function categoryMarkup() {
    return '<div class="category-overview"><div class="category-head"><div><b>按类别浏览</b><small>选择一类，再查看里面的单品</small></div><button class="compact-import" data-v3-import>＋ 导入</button></div><div class="category-grid">'+CATEGORIES.map(category => {
      const count = state.garments.filter(g => g.category === category).length;
      return '<button class="category-card" data-v3-category="'+esc(category)+'"><span class="cat-icon cat-icon-'+CATEGORY_ICONS[category]+'" aria-hidden="true"></span><span><b>'+esc(category)+'</b><small>'+count+' 件单品</small></span><em>›</em></button>';
    }).join('')+'</div></div>';
  }

  function garmentGrid(rows) {
    if (!rows.length) return '<div class="v3-empty">这个分类还没有单品<br><button data-v3-import>从相册导入</button></div>';
    return '<div class="grid v3-garment-grid">'+rows.map(g => '<article class="item '+(state.selected.has(g.id)?'selected':'')+'" data-garment-id="'+esc(g.id)+'">'+(state.manage?'<button class="item-check" data-v3-select="'+esc(g.id)+'">'+(state.selected.has(g.id)?'✓':'')+'</button>':'')+'<button class="item-main" data-v3-garment="'+esc(g.id)+'"><div class="itempic">'+imageMarkup(g,'v3-thumb')+'</div><b>'+esc(g.name)+'</b><div class="auto-tags">'+[g.color,g.material,g.fit].filter(Boolean).slice(0,3).map(t=>'<em>'+esc(t)+'</em>').join('')+'</div></button><div class="item-actions"><button data-v3-garment="'+esc(g.id)+'">查看编辑</button><button class="danger" data-v3-delete="'+esc(g.id)+'">移除</button></div></article>').join('')+'</div>';
  }

  function pagerMarkup(pages){if(pages<=1)return '';return '<div class="v3-pager">'+Array.from({length:pages},(_,i)=>'<button class="'+(state.page===i+1?'on':'')+'" data-v3-page="'+(i+1)+'">'+(i+1)+'</button>').join('')+'</div>'}

  function openImport() {
    const body = q('#modalBody');
    body.innerHTML = '<h2>\u6dfb\u52a0\u5230\u8863\u6a71</h2><p class="import-intro">\u9009\u62e9\u4f60\u4e60\u60ef\u7684\u5bfc\u5165\u65b9\u5f0f\uff0c\u5bfc\u5165\u540e\u4ecd\u53ef\u7f16\u8f91\u56fe\u7247\u548c\u6807\u7b7e\u3002</p><div class="v3-import-sources"><label class="v3-import-source"><input data-v3-file-input type="file" accept="image/*" multiple hidden><span class="v3-import-icon">\u25a3</span><b>\u4ece\u76f8\u518c\u4e0a\u4f20</b><small>\u53ef\u4e00\u6b21\u9009\u62e9\u591a\u5f20\u7167\u7247</small></label><button class="v3-import-source" data-v3-link-panel><span class="v3-import-icon">\u2197</span><b>\u590d\u5236\u5546\u54c1\u9875\u94fe\u63a5</b><small>\u652f\u6301\u5546\u54c1\u9875\u6216\u56fe\u7247\u94fe\u63a5</small></button><label class="v3-import-source"><input data-v3-camera-input type="file" accept="image/*" capture="environment" hidden><span class="v3-import-icon">\u25c9</span><b>\u76f4\u63a5\u62cd\u7167</b><small>\u6253\u5f00\u76f8\u673a\u62cd\u6444\u5355\u4ef6\u8863\u7269</small></label></div><div class="v3-progress" data-v3-local-state>\u6b63\u5728\u68c0\u67e5\u672c\u5730\u8863\u6a71\u670d\u52a1\u2026</div><div data-v3-import-progress></div>';
    q('#modal').classList.add('show');
    api.status().then(()=>{const el=q('[data-v3-local-state]');if(el){el.textContent='● \u672c\u5730\u8863\u6a71\u670d\u52a1\u5df2\u8fde\u63a5\uff0c\u53ef\u4ee5\u4e0a\u4f20\u3001\u62a0\u56fe\u5e76\u4fdd\u5b58';el.classList.add('connected')}}).catch(error=>{const el=q('[data-v3-local-state]');if(el){el.className='v3-error';el.textContent=error.message}});
  }

  function openLinkImport() {
    const body = q('#modalBody');
    body.innerHTML = '<h2>\u4ece\u5546\u54c1\u9875\u94fe\u63a5\u5bfc\u5165</h2><p class="import-intro">\u6bcf\u884c\u7c98\u8d34\u4e00\u4e2a\u5546\u54c1\u9875\u6216\u56fe\u7247\u94fe\u63a5\u3002</p><textarea class="v3-link-input" data-v3-link-input placeholder="https://..."></textarea><div class="v3-link-actions"><button data-v3-import-menu>\u8fd4\u56de</button><button class="primary" data-v3-link-submit>\u5f00\u59cb\u5bfc\u5165</button></div><div data-v3-import-progress></div>';
  }

  async function importLinks(value) {
    const urls = [...new Set(String(value || '').split(/[\n\r,\uff0c]+/).map(x => x.trim()).filter(x => /^https?:\/\//i.test(x)))];
    const host = q('[data-v3-import-progress]');
    if (!urls.length) { if (host) host.innerHTML = '<p class="v3-error">\u8bf7\u7c98\u8d34\u6709\u6548\u7684\u5546\u54c1\u9875\u6216\u56fe\u7247\u94fe\u63a5\u3002</p>'; return; }
    try {
      const files = [];
      for (let i = 0; i < urls.length; i++) {
        if (host) host.innerHTML = '<p class="v3-progress">\u6b63\u5728\u8bfb\u53d6\u94fe\u63a5 '+(i+1)+' / '+urls.length+'</p>';
        const candidate=(await api.importUrl(urls[i])).candidate;const source=candidate.images?.[0];if(!source)throw Error('商品页没有可用主图');
        const response=await fetch(source);if(!response.ok)throw Error('商品主图读取失败，请使用网页助手或相册上传');const blob=await response.blob();
        files.push(new File([blob], 'product-'+(i+1)+'.'+(blob.type.split('/')[1] || 'jpg'), {type:blob.type || 'image/jpeg'}));
      }
      await importFiles(files);
    } catch (error) {
      if (host) host.innerHTML = '<p class="v3-error">'+esc(error.message)+'<br><small>\u5982\u5546\u5bb6\u7f51\u7ad9\u7981\u6b62\u8bfb\u53d6\uff0c\u53ef\u4fdd\u5b58\u5546\u54c1\u56fe\u540e\u4ece\u76f8\u518c\u4e0a\u4f20\u3002</small></p>';
    }
  }

  async function importFiles(files) {
    const list = [...files].filter(file => file.type.startsWith('image/'));
    if (!list.length) return;
    const host = q('[data-v3-import-progress]');
    try {
      host.innerHTML = '<p class="v3-progress">正在上传 '+list.length+' 张照片到本地衣橱…</p><progress></progress>';
      const job = await api.importPhotos(list);
      const result = await waitJob(job.id, host, '正在识别、抠图并生成上身图');
      await showImportReview(result.garments || []);
    } catch (error) {
      host.innerHTML = '<p class="v3-error">'+esc(error.message)+'</p>';
    }
  }

  async function waitJob(id, host, label) {
    let transientErrors = 0;
    for (let attempt = 0; attempt < 180; attempt++) {
      let job;
      try { job = await api.getJob(id); transientErrors = 0; }
      catch (error) {
        transientErrors++;
        if (transientErrors >= 6) throw error;
        if (host) host.innerHTML = '<p class="v3-progress">本地任务仍在处理，正在重新连接（'+transientErrors+'/5）…</p>';
        await sleep(900);
        continue;
      }
      if (host) host.innerHTML = '<p class="v3-progress">'+esc(label)+' · '+(job.progress || 0)+'%</p><progress max="100" value="'+(job.progress || 0)+'"></progress>';
      if (job.status === 'ready' || job.status === 'review') return job.result || {};
      if (job.status === 'failed') throw Error(job.error?.message || '处理失败');
      await sleep(1200);
    }
    throw Error('处理时间较长，请稍后回到衣橱查看');
  }

  async function showImportReview(rows) {
    const body = q('#modalBody');
    const garments = rows.map(normalizeGarment);
    body.innerHTML = '<h2>确认导入结果</h2><p class="import-intro">确认后才会进入正式衣橱。</p><div class="v3-review-list">'+garments.map(g=>'<article><div>'+imageMarkup(g,'v3-review-img')+'</div><span><b>'+esc(g.name)+'</b><small>'+[g.category,g.color,g.material,g.fit].map(esc).join(' · ')+'</small></span><button data-v3-approve="'+esc(g.id)+'">确认</button></article>').join('')+'</div><button class="primary" data-v3-approve-all>全部确认</button>';
  }

  async function approveGarment(id, button) {
    button.disabled = true; button.textContent = '处理中…';
    try { const approved=normalizeGarment(await api.approve(id));button.textContent = '已确认';state.category=approved.category;state.season='全部';state.page=1;await refreshGarments();q('#modal')?.classList.remove('show');navigate('wardrobe');setTimeout(()=>q('[data-garment-id="'+CSS.escape(id)+'"]')?.scrollIntoView({behavior:'smooth',block:'center'}),80); }
    catch (error) { button.disabled = false; button.textContent = '重试'; toast(error.message); }
  }

  async function refreshGarments() {
    state.loading = true; renderWardrobe();
    try { state.garments = dedupeById(await api.listGarments());state.serviceStatus=await api.status(); }
    catch (error) { state.garments = []; if (error.code !== 'local_service_not_configured') toast(error.message); }
    finally { state.loading = false; renderWardrobe(); }
  }

  function dedupeById(rows) {
    const map = new Map();
    rows.forEach(row => { if (row?.id) map.set(row.id, row); });
    return [...map.values()];
  }

  function getGarment(id) { return state.garments.find(g => g.id === id) || null; }
  function selectedIds() {
    const o = state.outfit;
    return [...new Set([o.top,o.outerwear,o.bottom,o.dress,o.shoes,o.bag,...(o.accessory||[]),o.headscarf].filter(Boolean))];
  }
  function layerFor(g) {
    if (g.category === '上衣') return 'top'; if (g.category === '外套') return 'outerwear';
    if (g.category === '裤子' || g.category === '裙子') return 'bottom'; if (g.category === '连衣裙') return 'dress';
    if (g.category === '鞋') return 'shoes'; if (g.category === '包') return 'bag';
    if (g.category === '头巾') return 'headscarf'; return 'accessory';
  }

  function equip(g) {
    const layer = layerFor(g);
    if (layer === 'accessory') state.outfit.accessory = [g.id];
    else state.outfit[layer] = g.id;
    if (layer === 'dress') { state.outfit.top = null; state.outfit.bottom = null; }
    if (layer === 'top' || layer === 'bottom') state.outfit.dress = null;
    state.saveOutfit();
    if (selectedIds().length === 1 && g.modeledPreviewUrl) state.activeImage = g.modeledPreviewUrl;
    renderDressing('manual');
    scheduleTryOn();
  }

  function renderDressing(mode = 'manual') {
    const manual = q('#manual'), ai = q('#ai');
    if (!manual || !ai) return;
    manual.hidden = mode !== 'manual'; ai.hidden = mode !== 'ai';
    qa('[data-stylemode]').forEach(b => b.classList.toggle('on', b.dataset.stylemode === mode));
    if (mode === 'ai') return renderAiPanel();
    const ids = selectedIds(), selected = ids.map(getGarment).filter(Boolean);
    manual.innerHTML = '<div class="dressing-shell"><div class="v3-model-stage">'+(state.activeImage?'<img class="v3-tryon-image" src="'+esc(state.activeImage)+'" alt="真实 AI 上身效果">':'<img class="v3-base-model" src="assets/bling-avatar-base-v3.png?v=e25ca681" alt="数字衣模">')+'<div class="v3-stage-status" data-v3-stage-status>'+(selected.length?'已选择 '+selected.length+' 件，正在准备真实上身效果':'从下方分类选择衣服')+'</div></div><div class="outfit-summary">'+selected.map(g=>'<span>'+esc(g.name)+'</span>').join('')+'</div><div class="category-dock">'+LAYERS.map(([layer,label])=>{const value=layer==='accessory'?state.outfit.accessory[0]:state.outfit[layer],g=getGarment(value);return '<button class="outfit-slot '+(g?'on':'')+'" data-v3-layer="'+layer+'"><b>'+label+'</b><small>'+(g?esc(g.name):'选择单品')+'</small></button>'}).join('')+'</div><div class="outfit-actions"><button data-v3-reset>重新搭配</button><button data-v3-generate '+(!ids.length?'disabled':'')+'>立即重新生成</button></div></div>';
  }

  function openPicker(layer) {
    const entry = LAYERS.find(x => x[0] === layer), categories = entry?.[2] || [];
    const rows = dedupeById(state.garments.filter(g => categories.includes(g.category)));
    const selected = layer === 'accessory' ? state.outfit.accessory[0] : state.outfit[layer];
    q('#modalBody').innerHTML = '<h2>选择'+esc(entry?.[1] || '单品')+'</h2><div class="garment-picker">'+(rows.length?rows.map(g=>'<button class="garment-pick '+(selected===g.id?'on':'')+'" data-v3-pick="'+esc(g.id)+'"><span class="pick-img">'+imageMarkup(g,'v3-picker-img')+'</span><span><b>'+esc(g.name)+'</b><small>'+[g.color,g.material,g.fit].map(esc).join(' · ')+'</small></span><em>›</em></button>').join(''):'<p class="v3-empty">这个分类还没有可用单品</p>')+'</div>';
    q('#modal').classList.add('show');
  }

  function openGarmentEditor(g){
    q('#modalBody').innerHTML='<h2>编辑单品信息</h2><div class="v3-editor-preview">'+imageMarkup(g,'v3-detail-img')+'</div><div class="v3-preview-tabs"><a href="'+esc(g.originalUrl)+'" target="_blank">原图</a>'+(g.cutoutUrl?'<a href="'+esc(g.cutoutUrl)+'" target="_blank">透明图</a>':'')+(g.whiteBgUrl?'<a href="'+esc(g.whiteBgUrl)+'" target="_blank">白底图</a>':'')+'</div><div class="v3-edit-grid"><label>名称<input data-edit-name value="'+esc(g.name)+'"></label><label>分类<select data-edit-category>'+CATEGORIES.map(v=>'<option '+(v===g.category?'selected':'')+'>'+v+'</option>').join('')+'</select></label><label>季节<select data-edit-season>'+SEASONS.slice(1).map(v=>'<option '+(v===g.season?'selected':'')+'>'+v+'</option>').join('')+'</select></label><label>色系<input data-edit-color value="'+esc(g.color)+'"></label><label>材质<input data-edit-material value="'+esc(g.material)+'"></label><label>风格<input data-edit-style value="'+esc(g.style)+'"></label><label>版型<input data-edit-fit value="'+esc(g.fit)+'"></label></div><details class="v3-crop"><summary>裁剪与旋转</summary><div><label>X<input type="range" min="0" max=".8" step=".01" value="0" data-crop-x></label><label>Y<input type="range" min="0" max=".8" step=".01" value="0" data-crop-y></label><label>宽<input type="range" min=".2" max="1" step=".01" value="1" data-crop-width></label><label>高<input type="range" min=".2" max="1" step=".01" value="1" data-crop-height></label><label>旋转<input type="range" min="-30" max="30" step="1" value="0" data-crop-rotation></label></div><button data-v3-crop="'+esc(g.id)+'">应用并重新抠图</button></details><div class="v3-ai-option"><button data-v3-ai-rebuild="'+esc(g.id)+'">AI 统一重建（需兼容 GPU）</button><small>AI 图会明确标注，不覆盖原图与基础抠图。</small></div><div class="v3-editor-actions"><button data-v3-reanalyze="'+esc(g.id)+'">重新识别</button><button class="primary" data-v3-save="'+esc(g.id)+'">保存修改</button></div>';
    q('#modal').classList.add('show');
  }

  function scheduleTryOn() {
    clearTimeout(state.tryonTimer);
    const ids = selectedIds();
    if (!ids.length) return;
    state.tryonTimer = setTimeout(() => generateTryOn(ids), 800);
  }

  async function generateTryOn(ids) {
    const generation = ++state.tryonGeneration;
    const status = q('[data-v3-stage-status]');
    if (status) status.textContent = '布灵正在生成完整上身效果…';
    try {
      const job = await api.tryOn(ids);
      const result = await waitJob(job.id, null, '正在生成');
      if (generation !== state.tryonGeneration) return;
      if (!result.image_url) throw Error('生成结果缺少图片');
      state.activeImage = result.image_url;
      renderDressing('manual');
      q('[data-v3-stage-status]').textContent = result.cache_hit ? '已读取上身缓存' : '真实上身效果已生成';
    } catch (error) {
      if (generation !== state.tryonGeneration) return;
      const current = q('[data-v3-stage-status]');
      if (current) { current.textContent = error.message; current.classList.add('error'); }
    }
  }

  function renderAiPanel() {
    const ai = q('#ai');
    ai.innerHTML = '<div class="panel"><h3>交给布灵</h3><p>从真实衣橱生成三套完整上身 Look，不再拼贴单品缩略图。</p></div><button class="primary" data-v3-ai-generate>生成三套 Look ✦</button><div class="v3-ai-results" data-v3-ai-results></div>';
  }

  async function generateLooks() {
    const host = q('[data-v3-ai-results]');
    const tops = state.garments.filter(g=>['上衣','连衣裙'].includes(g.category));
    const bottoms = state.garments.filter(g=>['裤子','裙子'].includes(g.category));
    if (!tops.length || (!bottoms.length && !tops.some(g=>g.category==='连衣裙'))) return toast('衣橱中的上装和下装还不足以生成 Look');
    host.innerHTML = '<p class="v3-progress">正在生成三套真实上身 Look…</p>';
    const results = [];
    for (let i=0;i<3;i++) {
      const top=tops[i%tops.length], ids=[top.id];
      if(top.category!=='连衣裙'&&bottoms.length)ids.push(bottoms[i%bottoms.length].id);
      try {const job=await api.tryOn(ids);results.push(await waitJob(job.id,null,'生成 Look'))} catch(error){results.push({error:error.message})}
    }
    host.innerHTML = results.map((r,i)=>r.image_url?'<article><img src="'+esc(r.image_url)+'" alt="LOOK 0'+(i+1)+'"><b>LOOK 0'+(i+1)+'</b></article>':'<article class="v3-error">LOOK 0'+(i+1)+'：'+esc(r.error)+'</article>').join('');
  }

  function bindEvents() {
    document.addEventListener('click', async event => {
      const target = event.target.closest('button,label');
      if (!target) return;
      const go = target.closest('[data-go]');
      if (go) { event.preventDefault(); event.stopImmediatePropagation(); navigate(go.dataset.go, go.dataset.mode); return; }
      if (target.closest('[data-modal="add"],[data-modal="import"],[data-v3-import]')) { event.preventDefault(); event.stopImmediatePropagation(); openImport(); return; }
      if (target.hasAttribute('data-v3-link-panel')) { openLinkImport(); return; }
      if (target.hasAttribute('data-v3-import-menu')) { openImport(); return; }
      if (target.hasAttribute('data-v3-link-submit')) { importLinks(q('[data-v3-link-input]')?.value || ''); return; }
      if (target.dataset.v3Category) { state.category=target.dataset.v3Category;state.season='全部';state.page=1; renderWardrobe(); return; }
      if (target.hasAttribute('data-v3-back')) { state.category=null; renderWardrobe(); return; }
      if(target.hasAttribute('data-v3-manage')){state.manage=!state.manage;state.selected.clear();renderWardrobe();return}
      if(target.hasAttribute('data-v3-select-page')){shownGarmentIds().forEach(id=>state.selected.add(id));renderWardrobe();return}
      if(target.hasAttribute('data-v3-delete-selected')){if(!state.selected.size)return;if(confirm('确定移除已选择的 '+state.selected.size+' 件衣服吗？')){for(const id of [...state.selected])await api.remove(id);state.selected.clear();await refreshGarments()}return}
      if(target.dataset.v3Select){state.selected.has(target.dataset.v3Select)?state.selected.delete(target.dataset.v3Select):state.selected.add(target.dataset.v3Select);renderWardrobe();return}
      if(target.dataset.v3Page){state.page=+target.dataset.v3Page;renderWardrobe();return}
      if (target.dataset.v3Delete) { event.preventDefault(); if(confirm('确定移除这件衣服吗？')){try{await api.remove(target.dataset.v3Delete);await refreshGarments()}catch(e){toast(e.message)}} return; }
      if (target.dataset.v3Garment) { const g=getGarment(target.dataset.v3Garment); if(g)openGarmentEditor(g); return; }
      if (target.dataset.v3Wear || target.dataset.v3Pick) { const g=getGarment(target.dataset.v3Wear||target.dataset.v3Pick);if(g){q('#modal').classList.remove('show');equip(g)}return; }
      if (target.dataset.v3Layer) { openPicker(target.dataset.v3Layer); return; }
      if (target.hasAttribute('data-v3-reset')) { state.outfit={top:null,outerwear:null,bottom:null,dress:null,shoes:null,bag:null,accessory:[],headscarf:null};state.activeImage='';state.saveOutfit();renderDressing('manual');return; }
      if (target.hasAttribute('data-v3-generate')) { generateTryOn(selectedIds());return; }
      if (target.dataset.v3Approve) { approveGarment(target.dataset.v3Approve,target);return; }
      if (target.hasAttribute('data-v3-approve-all')) { for(const button of qa('[data-v3-approve]'))if(!button.disabled)await approveGarment(button.dataset.v3Approve,button);return; }
      if (target.hasAttribute('data-v3-ai-generate')) { generateLooks();return; }
      if(target.dataset.v3Save){const id=target.dataset.v3Save;try{await api.patch(id,{name:q('[data-edit-name]').value,category:q('[data-edit-category]').value,season:q('[data-edit-season]').value,color:q('[data-edit-color]').value,material:q('[data-edit-material]').value,style:q('[data-edit-style]').value,fit:q('[data-edit-fit]').value});q('#modal').classList.remove('show');await refreshGarments();toast('已保存')}catch(e){toast(e.message)}return}
      if(target.dataset.v3Reanalyze){try{const g=normalizeGarment(await api.reanalyze(target.dataset.v3Reanalyze));openGarmentEditor(g);toast('已重新识别未锁定字段')}catch(e){toast(e.message)}return}
      if(target.dataset.v3Crop){try{const v=s=>+q(s).value;const g=normalizeGarment(await api.crop(target.dataset.v3Crop,{x:v('[data-crop-x]'),y:v('[data-crop-y]'),width:v('[data-crop-width]'),height:v('[data-crop-height]'),rotation:v('[data-crop-rotation]')}));openGarmentEditor(g);toast('已重新裁剪并抠图')}catch(e){toast(e.message)}return}
      if(target.dataset.v3AiRebuild){target.disabled=true;try{await api.process(target.dataset.v3AiRebuild,'ai_generate');toast('AI 重建完成');await refreshGarments()}catch(e){toast(e.message)}finally{target.disabled=false}return}
      if (target.dataset.stylemode) { event.preventDefault();event.stopImmediatePropagation();renderDressing(target.dataset.stylemode); }
    }, true);
    document.addEventListener('change', event => { if (event.target.matches('[data-v3-file-input],[data-v3-camera-input]')) importFiles(event.target.files);if(event.target.matches('[data-v3-season]')){state.season=event.target.value;state.page=1;renderWardrobe()}if(event.target.matches('[data-v3-page-size]')){state.pageSize=+event.target.value;state.page=1;renderWardrobe()} }, true);
    document.addEventListener('input', event => { if(event.target.matches('[data-v3-search]')){state.search=event.target.value;renderWardrobe();q('[data-v3-search]')?.focus()} }, true);
  }

  async function init() {
    const legacy=migrate(); state.loadOutfit(); bindEvents();
    document.body.classList.add('wardrobe-v3');
    const profileNote = q('#profile .profile small');
    if (profileNote) profileNote.textContent = '衣橱照片仅保存在这台设备';
    renderWardrobe(); renderDressing('manual');
    if (config.apiBase && window.BlingGeneration?.config) {
      try {
        const identity = await auth.get();
        window.BlingGeneration.config.set(config.apiBase, identity.idToken || '');
      } catch (_) {}
    }
    await refreshGarments();
    if(legacy.length&&state.serviceStatus?.ok){openImport();toast('发现 '+legacy.length+' 件真实旧照片，正在迁移');await importFiles(legacy.map(legacyFile))}
  }

  window.BlingWardrobeV3 = {state, api, refresh:refreshGarments, equip};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true}); else init();
})();
