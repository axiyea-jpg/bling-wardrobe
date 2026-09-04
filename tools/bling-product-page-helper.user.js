// ==UserScript==
// @name         布灵布灵商品页助手
// @namespace    bling-wardrobe-local
// @version      1.0.0
// @description  将用户当前可见商品页信息发送到本机布灵衣橱
// @match        https://item.taobao.com/*
// @match        https://*.pinduoduo.com/*
// @match        https://www.xiaohongshu.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

(function () {
  'use strict';
  const button = document.createElement('button');
  button.textContent = '导入布灵衣橱';
  Object.assign(button.style, {position:'fixed',right:'18px',bottom:'88px',zIndex:2147483647,border:'0',borderRadius:'18px',padding:'12px 18px',background:'#ad607b',color:'#fff',boxShadow:'0 6px 20px #7d405855',cursor:'pointer'});
  button.addEventListener('click', () => {
    const visible = element => { const box=element.getBoundingClientRect();return box.width>80&&box.height>80&&getComputedStyle(element).visibility!=='hidden'; };
    const images = [...document.images].filter(visible).map(image => image.currentSrc || image.src).filter(url => /^https?:/i.test(url));
    const payload = JSON.stringify({url:location.href,title:(document.querySelector('h1')?.textContent||document.title).trim(),images:[...new Set(images)].slice(0,12),description:(document.querySelector('meta[name="description"]')?.content||'').slice(0,2000),variants:[]});
    GM_xmlhttpRequest({method:'POST',url:'http://127.0.0.1:8765/api/import/page-capture',headers:{'Content-Type':'application/json'},data:payload,onload:response=>{button.textContent=response.status<300?'已发送到布灵 ✓':'发送失败，请启动本地版';},onerror:()=>{button.textContent='本地服务未启动';}});
  });
  document.body.appendChild(button);
})();
