(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const panel = $('archive-workspace');
  const message = $('archive-message');
  const results = $('archive-results');
  const fields = $('archive-search-form');
  let session = new URLSearchParams(location.search).get('session');
  let offset = 0;
  let shown = [];
  let total = 0;
  const request = async (url, data) => {
    const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json','X-BookHarbor-Action':'archive-explorer'},body:JSON.stringify(data)});
    const json = await response.json();
    if (!response.ok) throw new Error(json.error || json.detail || `HTTP ${response.status}`);
    return json;
  };
  const get = async url => {const response = await fetch(url); const json = await response.json(); if (!response.ok) throw new Error(json.error || json.detail || `HTTP ${response.status}`); return json;};
  const tell = text => {message.textContent=text;};
  const elm = (tag, cls, value) => {const node=document.createElement(tag); if(cls)node.className=cls;if(value!==undefined)node.textContent=String(value);return node;};
  const button = (label, fn) => {const b=elm('button','small',label);b.type='button';b.addEventListener('click',fn);return b;};
  async function refreshStats() {const data=await get('/api/archive/stats');$('indexed-total').textContent=data.indexed;$('verified-total').textContent=data.public_verified;$('session-total').textContent=data.sessions;}
  async function refreshSession() {
    if (!session) return;
    const state = await get('/api/archive/session?session='+encodeURIComponent(session));
    panel.hidden=false;
    $('archive-counter').textContent=state.discovered.toLocaleString()+' records indexed in this session';
    $('archive-pages').textContent=state.page_count+' page(s) fetched'+(state.finished?' · complete/limit reached':' · more available');
    $('archive-next-btn').disabled=Boolean(state.finished);
    await refreshIndex(); await refreshStats();
  }
  async function refreshIndex() {
    if (!session) return;
    const params = new URLSearchParams({session,offset:String(offset),limit:'50',q:$('archive-local-query').value,access:$('archive-access-filter').value});
    const d=await get('/api/archive/items?'+params);
    total=d.total;shown=d.items;results.replaceChildren();
    for (const b of shown) {
      const card=elm('article','archive-item');
      const select=elm('input');select.type='checkbox';select.className='archive-choice';select.dataset.id=b.id;select.value=b.selection_token;select.setAttribute('aria-label','Select '+b.title);
      const head=elm('div','archive-item-head');head.append(select,elm('strong','',b.title));
      const meta=elm('div','archive-item-meta',b.author+' · '+(b.year||'undated')+' · '+(b.language||'language unknown'));
      const avail=elm('span','archive-status','Availability: '+b.availability);
      const actions=elm('div','archive-actions');
      actions.append(button('Inspect open files',async()=>{
        tell('Checking '+b.title+'…');
        try {const data=await request('/api/archive/inspect',{id:b.id});
          avail.textContent='Availability: '+data.availability;
          actions.querySelectorAll('.archive-download-file').forEach(node=>node.remove());
          for(const offer of data.options){const x=button('↓ '+offer.fmt,async()=>{try{const response=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:offer.token})}); const out=await response.json(); if(!response.ok)throw Error(out.error);tell(out.reused?'Already queued/completed job #'+out.job_id:'Queued job #'+out.job_id);}catch(err){tell(err.message);}});x.classList.add('archive-download-file');actions.append(x);}
          tell(data.options.length?data.options.length+' public file format(s) found':data.message);
          await refreshStats();
        }catch(err){tell(err.message);}
      }));
      const link=elm('a','small link','Open Archive record');link.href=b.page;link.target='_blank';link.rel='noopener noreferrer';actions.append(link);
      card.append(head,meta,avail,actions);results.append(card);
    }
    $('archive-list-range').textContent=(total?(offset+1):0)+'–'+Math.min(offset+shown.length,total)+' of '+total+' matching indexed titles';
    $('archive-prev-list-btn').disabled=offset===0;
    $('archive-next-list-btn').disabled=offset+shown.length>=total;
  }
  fields.addEventListener('submit',async event=>{
    event.preventDefault();$('archive-search-btn').disabled=true;tell('Connecting to Internet Archive…');
    try{const data=Object.fromEntries(new FormData(fields).entries());const state=await request('/api/archive/start',data);session=state.id;offset=0;
      history.replaceState(null,'','/archive?session='+encodeURIComponent(session));await refreshSession();tell('First page indexed. Continue explicitly to collect more metadata.');
    }catch(err){panel.hidden=false;tell(err.message);}finally{$('archive-search-btn').disabled=false;}
  });
  $('archive-next-btn').addEventListener('click',async()=>{
    const b=$('archive-next-btn');b.disabled=true;tell('Indexing one more page…');
    try{const state=await request('/api/archive/next',{session});await refreshSession();tell(state.finished?'Indexing finished for this session.':'Indexed next 100 or fewer records.');}
    catch(err){tell(err.message);}finally{if(session)await refreshSession().catch(()=>{});}
  });
  $('archive-filter-btn').addEventListener('click',async()=>{offset=0;try{await refreshIndex()}catch(err){tell(err.message)}});
  $('archive-prev-list-btn').addEventListener('click',()=>{offset=Math.max(0,offset-50);refreshIndex().catch(err=>tell(err.message));});
  $('archive-next-list-btn').addEventListener('click',()=>{offset+=50;refreshIndex().catch(err=>tell(err.message));});
  $('archive-verify-btn').addEventListener('click',async()=>{
    const ids=Array.from(document.querySelectorAll('.archive-choice:checked')).map(x=>x.dataset.id);
    if(!ids.length||ids.length>5){tell('Choose 1 to 5 titles to check public availability.');return;}
    const b=$('archive-verify-btn');b.disabled=true;tell('Checking file metadata…');
    try{const d=await request('/api/archive/verify-selected',{ids});tell(d.results.map(x=>x.id+': '+x.status).join(' · '));await refreshIndex();await refreshStats();}
    catch(err){tell(err.message);}finally{b.disabled=false;}
  });
  $('archive-download-btn').addEventListener('click',async()=>{
    const tokens=Array.from(document.querySelectorAll('.archive-choice:checked')).map(x=>x.value);
    if(!tokens.length||tokens.length>10){tell('Select 1–10 titles. Only publicly accessible files will be queued.');return;}
    const b=$('archive-download-btn');b.disabled=true;tell('Checking selected items for public file formats…');
    try{const response=await fetch('/api/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tokens,preference:$('archive-format-pref').value})});const data=await response.json();if(!response.ok)throw Error(data.error);tell(data.queued.length+' queued, '+data.skipped.length+' skipped. See My Library.');}
    catch(err){tell(err.message);}finally{b.disabled=false;}
  });
  if(session){refreshSession().catch(err=>{panel.hidden=false;tell('Saved session unavailable: '+err.message);});}
})();
