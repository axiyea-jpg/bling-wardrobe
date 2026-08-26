(function () {
  'use strict';

  const SCHEMA_KEY = 'bling-wardrobe-schema-v3';
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
    if (localStorage.getItem(SCHEMA_KEY) === '3') return;
    LEGACY_KEYS.forEach(key => localStorage.removeItem(key));
    localStorage.removeItem(OUTFIT_KEY);
    localStorage.setItem(SCHEMA_KEY, '3');
    document.documentElement.style.removeProperty('--items-img');
  }

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
        const error = Error('云端衣橱尚未部署，当前不会保存或伪造任何图片');
        error.code = 'cloud_not_configured';
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
        const error = Error(detail.message || '云端衣橱暂时不可用');
        error.code = detail.code || 'api_error';
        throw error;
      }
      return body;
    },
    async listGarments() {
      const result = await this.request('/api/garments?status=approved&limit=200');
      return (result.items || []).map(normalizeGarment);
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
      thumbnailUrl:row.thumbnail_url || '', modeledPreviewUrl:row.modeled_preview_url || ''
    };
  }

  const state = {
    garments: [], loading: false, category: null, search: '', selected: new Set(), manage: false,
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
    const filtered = state.garments.filter(g => (!state.category || g.category === state.category) && (!search || [g.name,g.category,g.color,g.material,g.style,g.fit,...g.tags].join(' ').toLowerCase().includes(search)));
    page.innerHTML = '<div class="title wardrobe-title"><div><p class="eyebrow">MY WARDROBE</p><h1>我的衣橱</h1></div><span class="count">'+state.garments.length+' 件</span></div>'+
      '<div class="search wardrobe-search">⌕<input data-v3-search placeholder="搜索名称、分类或标签" value="'+esc(state.search)+'"></div>'+
      '<div class="v3-wardrobe-actions"><button data-v3-import>＋ 批量导入</button>'+(state.category?'<button data-v3-back>‹ 全部分类</button>':'')+'</div>'+
      (state.loading ? '<div class="v3-empty">正在读取私有云端衣橱…</div>' : !state.category ? categoryMarkup() : garmentGrid(filtered));
  }

  function categoryMarkup() {
    return '<div class="category-overview"><div class="category-head"><div><b>按类别浏览</b><small>选择一类，再查看里面的单品</small></div></div><div class="category-grid">'+CATEGORIES.map(category => {
      const count = state.garments.filter(g => g.category === category).length;
      return '<button class="category-card" data-v3-category="'+esc(category)+'"><span class="cat-icon cat-icon-'+CATEGORY_ICONS[category]+'" aria-hidden="true"></span><span><b>'+esc(category)+'</b><small>'+count+' 件单品</small></span><em>›</em></button>';
    }).join('')+'</div></div>';
  }

  function garmentGrid(rows) {
    if (!rows.length) return '<div class="v3-empty">这个分类还没有单品<br><button data-v3-import>从相册导入</button></div>';
    return '<div class="grid v3-garment-grid">'+rows.map(g => '<article class="item" data-garment-id="'+esc(g.id)+'"><button class="item-main" data-v3-garment="'+esc(g.id)+'"><div class="itempic">'+imageMarkup(g,'v3-thumb')+'</div><b>'+esc(g.name)+'</b><div class="auto-tags">'+[g.color,g.material,g.fit].filter(Boolean).slice(0,3).map(t=>'<em>'+esc(t)+'</em>').join('')+'</div></button><div class="item-actions"><button data-v3-garment="'+esc(g.id)+'">查看编辑</button><button class="danger" data-v3-delete="'+esc(g.id)+'">移除</button></div></article>').join('')+'</div>';
  }

  function openImport() {
    const body = q('#modalBody');
    body.innerHTML = '<h2>\u6dfb\u52a0\u5230\u8863\u6a71</h2><p class="import-intro">\u9009\u62e9\u4f60\u4e60\u60ef\u7684\u5bfc\u5165\u65b9\u5f0f\uff0c\u5bfc\u5165\u540e\u4ecd\u53ef\u7f16\u8f91\u56fe\u7247\u548c\u6807\u7b7e\u3002</p><div class="v3-import-sources"><label class="v3-import-source"><input data-v3-file-input type="file" accept="image/*" multiple hidden><span class="v3-import-icon">\u25a3</span><b>\u4ece\u76f8\u518c\u4e0a\u4f20</b><small>\u53ef\u4e00\u6b21\u9009\u62e9\u591a\u5f20\u7167\u7247</small></label><button class="v3-import-source" data-v3-link-panel><span class="v3-import-icon">\u2197</span><b>\u590d\u5236\u5546\u54c1\u9875\u94fe\u63a5</b><small>\u652f\u6301\u5546\u54c1\u9875\u6216\u56fe\u7247\u94fe\u63a5</small></button><label class="v3-import-source"><input data-v3-camera-input type="file" accept="image/*" capture="environment" hidden><span class="v3-import-icon">\u25c9</span><b>\u76f4\u63a5\u62cd\u7167</b><small>\u6253\u5f00\u76f8\u673a\u62cd\u6444\u5355\u4ef6\u8863\u7269</small></label></div><div data-v3-import-progress></div>';
    q('#modal').classList.add('show');
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
        let source = urls[i];
        let response = await fetch(source, {mode:'cors'});
        if (!response.ok) throw Error('\u65e0\u6cd5\u8bfb\u53d6\u8be5\u94fe\u63a5');
        let type = response.headers.get('content-type') || '';
        if (type.includes('text/html')) {
          const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
          const image = doc.querySelector('meta[property="og:image"]')?.content || doc.querySelector('meta[name="twitter:image"]')?.content;
          if (!image) throw Error('\u8be5\u5546\u54c1\u9875\u672a\u627e\u5230\u53ef\u5bfc\u5165\u7684\u5546\u54c1\u56fe');
          source = new URL(image, source).href;
          response = await fetch(source, {mode:'cors'});
          if (!response.ok) throw Error('\u5546\u54c1\u56fe\u8bfb\u53d6\u5931\u8d25');
          type = response.headers.get('content-type') || 'image/jpeg';
        }
        if (!type.startsWith('image/')) throw Error('\u94fe\u63a5\u4e0d\u662f\u53ef\u7528\u7684\u56fe\u7247');
        const blob = await response.blob();
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
      host.innerHTML = '<p class="v3-progress">正在建立上传任务…</p>';
      const job = await api.createImport(list);
      for (let i = 0; i < list.length; i++) {
        if (job.uploads[i].duplicate) continue;
        host.innerHTML = '<p class="v3-progress">正在上传 '+(i+1)+' / '+list.length+'：'+esc(list[i].name)+'</p><progress max="'+list.length+'" value="'+(i+1)+'"></progress>';
        await api.uploadFile(job.uploads[i], list[i]);
      }
      await api.completeImport(job.id);
      const result = await waitJob(job.id, host, '正在识别、抠图并生成上身图');
      await showImportReview(result.garments || []);
    } catch (error) {
      host.innerHTML = '<p class="v3-error">'+esc(error.message)+'</p>';
    }
  }

  async function waitJob(id, host, label) {
    for (let attempt = 0; attempt < 180; attempt++) {
      const job = await api.getJob(id);
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
    try { await api.approve(id); button.textContent = '已确认'; await refreshGarments(); }
    catch (error) { button.disabled = false; button.textContent = '重试'; toast(error.message); }
  }

  async function refreshGarments() {
    state.loading = true; renderWardrobe();
    try { state.garments = dedupeById(await api.listGarments()); }
    catch (error) { state.garments = []; if (error.code !== 'cloud_not_configured') toast(error.message); }
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
      if (target.dataset.v3Category) { state.category=target.dataset.v3Category; renderWardrobe(); return; }
      if (target.hasAttribute('data-v3-back')) { state.category=null; renderWardrobe(); return; }
      if (target.dataset.v3Delete) { event.preventDefault(); if(confirm('确定移除这件衣服吗？')){try{await api.remove(target.dataset.v3Delete);await refreshGarments()}catch(e){toast(e.message)}} return; }
      if (target.dataset.v3Garment) { const g=getGarment(target.dataset.v3Garment); if(g){q('#modalBody').innerHTML='<h2>'+esc(g.name)+'</h2><div class="v3-detail-image">'+imageMarkup(g,'v3-detail-img')+'</div><p>'+[g.category,g.season,g.color,g.material,g.style,g.fit].map(esc).join(' · ')+'</p><button class="primary" data-v3-wear="'+esc(g.id)+'">加入当前穿搭</button>';q('#modal').classList.add('show')} return; }
      if (target.dataset.v3Wear || target.dataset.v3Pick) { const g=getGarment(target.dataset.v3Wear||target.dataset.v3Pick);if(g){q('#modal').classList.remove('show');equip(g)}return; }
      if (target.dataset.v3Layer) { openPicker(target.dataset.v3Layer); return; }
      if (target.hasAttribute('data-v3-reset')) { state.outfit={top:null,outerwear:null,bottom:null,dress:null,shoes:null,bag:null,accessory:[],headscarf:null};state.activeImage='';state.saveOutfit();renderDressing('manual');return; }
      if (target.hasAttribute('data-v3-generate')) { generateTryOn(selectedIds());return; }
      if (target.dataset.v3Approve) { approveGarment(target.dataset.v3Approve,target);return; }
      if (target.hasAttribute('data-v3-approve-all')) { for(const button of qa('[data-v3-approve]'))if(!button.disabled)await approveGarment(button.dataset.v3Approve,button);return; }
      if (target.hasAttribute('data-v3-ai-generate')) { generateLooks();return; }
      if (target.dataset.stylemode) { event.preventDefault();event.stopImmediatePropagation();renderDressing(target.dataset.stylemode); }
    }, true);
    document.addEventListener('change', event => { if (event.target.matches('[data-v3-file-input],[data-v3-camera-input]')) importFiles(event.target.files); }, true);
    document.addEventListener('input', event => { if(event.target.matches('[data-v3-search]')){state.search=event.target.value;renderWardrobe();q('[data-v3-search]')?.focus()} }, true);
  }

  async function init() {
    migrate(); state.loadOutfit(); bindEvents();
    document.body.classList.add('wardrobe-v3');
    const profileNote = q('#profile .profile small');
    if (profileNote) profileNote.textContent = '衣橱照片加密保存在私有云端';
    renderWardrobe(); renderDressing('manual');
    if (config.apiBase && window.BlingGeneration?.config) {
      try {
        const identity = await auth.get();
        window.BlingGeneration.config.set(config.apiBase, identity.idToken || '');
      } catch (_) {}
    }
    await refreshGarments();
  }

  window.BlingWardrobeV3 = {state, api, refresh:refreshGarments, equip};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true}); else init();
})();
