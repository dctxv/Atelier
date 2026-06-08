/* ====== v2 Chat surface — The Atelier backend ====== */
const { useState, useRef, useEffect } = React;

/* ── Session persistence (localStorage) ── */
function loadSessions() {
  try { return JSON.parse(localStorage.getItem('atl_sessions') || '[]'); } catch { return []; }
}
function saveSessions(sessions) {
  try { localStorage.setItem('atl_sessions', JSON.stringify(sessions.slice(0,50))); } catch {}
}
function newSession(model) {
  return { id: crypto.randomUUID(), name:'New chat', messages:[], model:model||null, createdAt:Date.now() };
}

/* ── Model picker dropdown ── */
function ModelPickerDropdown({ current, onSelect, onClose }) {
  const [models, setModels]   = useState([]);
  const [query,  setQuery]    = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState('');
  const ref = useRef(null);

  useEffect(() => {
    fetch('/api/models')
      .then(r => r.json())
      .then(d => { setModels(d.models||[]); if(d.error) setErr(d.error); })
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const fn = e => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener('mousedown', fn);
    return () => document.removeEventListener('mousedown', fn);
  }, []);

  const filtered = query ? models.filter(m => m.toLowerCase().includes(query.toLowerCase())) : models;

  return (
    <div ref={ref} style={{
      position:'absolute', bottom:'calc(100% + 8px)', left:0,
      width:320, background:'var(--surface)', border:'1px solid var(--border-2)',
      borderRadius:10, zIndex:100, overflow:'hidden',
      boxShadow:'0 8px 32px rgba(0,0,0,.2)',
    }}>
      <div style={{ padding:'9px 12px', borderBottom:'1px solid var(--border)', display:'flex', gap:8 }}>
        <Ico n="search" size={11} color="var(--text-3)"/>
        <input autoFocus value={query} onChange={e=>setQuery(e.target.value)}
          placeholder="Search models…"
          style={{ flex:1, fontFamily:'var(--font-m)', fontSize:12, color:'var(--text)' }}/>
      </div>
      <div style={{ maxHeight:260, overflowY:'auto' }}>
        {loading && <div style={{padding:'18px',textAlign:'center'}}><Pulse size={8}/></div>}
        {!loading && filtered.length===0 && (
          <div style={{padding:'14px 14px',fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',fontStyle:'italic'}}>
            {err || (models.length===0 ? 'No endpoint configured — use /setup' : 'No matches')}
          </div>
        )}
        {filtered.map((m,i) => {
          const on = m===current;
          return (
            <button key={i} onClick={() => onSelect(m)}
              style={{ width:'100%',textAlign:'left',padding:'9px 14px',
                display:'flex',justifyContent:'space-between',alignItems:'center',
                background:on?'var(--accent-bg)':'transparent',
                borderLeft:`2px solid ${on?'var(--accent)':'transparent'}`,
                cursor:'pointer',transition:'background var(--t)',
                borderBottom:'1px solid var(--border)',
              }}>
              <span style={{fontFamily:'var(--font-b)',fontSize:13,fontStyle:'italic',
                color:on?'var(--text)':'var(--text-q)',
                overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:180}}>{m}</span>
              <span style={{fontFamily:'var(--font-m)',fontSize:9,color:'var(--text-3)',
                overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:120,flexShrink:0}}>
                {m.includes('/')?m.split('/')[0]:''}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Command palette ── */
function CommandPalette({ commands, activeIndex, onHover, onRun }) {
  return (
    <div style={{
      position:'absolute', bottom:'calc(100% + 8px)', left:0,
      width:340, background:'var(--surface)', border:'1px solid var(--border-2)',
      borderRadius:10, zIndex:100, overflow:'hidden',
      boxShadow:'0 8px 32px rgba(0,0,0,.2)',
    }}>
      {commands.map((cmd, i) => {
        const active = i === activeIndex;
        return (
          <button key={cmd.id}
            onMouseEnter={() => onHover(i)}
            onClick={() => onRun(cmd)}
            style={{
              width:'100%', textAlign:'left',
              padding:'9px 14px',
              display:'flex', alignItems:'center', gap:8,
              background: active ? 'var(--accent-bg)' : 'transparent',
              borderLeft: `2px solid ${active ? 'var(--accent)' : 'transparent'}`,
              borderBottom: '1px solid var(--border)',
              cursor:'pointer', transition:'background var(--t)',
            }}>
            <Ico n={cmd.icon} size={13} color={active ? 'var(--accent-tx)' : 'var(--text-3)'}/>
            <span style={{
              fontFamily:'var(--font-b)', fontSize:13, fontStyle:'italic',
              color: active ? 'var(--text)' : 'var(--text-q)',
              flex:1,
            }}>{cmd.label}</span>
            {cmd.hint && (
              <span style={{fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)'}}>{cmd.hint}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function ChatSurface({ onSetup, onSearchSetup, onWeatherSetup, onStockSetup, onToggleTheme, onOpenSettings }) {
  const [sessions,   setSessions]   = useState(() => loadSessions());
  const [activeId,   setActiveId]   = useState(() => { const s=loadSessions(); return s.length?s[0].id:null; });
  const [streaming,  setStreaming]   = useState(false);
  const [streamBuf,  setStreamBuf]  = useState('');
  const [streamSearch, setStreamSearch] = useState(null);
  const [streamClock,  setStreamClock]  = useState(null);
  const [streamDocs,   setStreamDocs]   = useState(null);
  const [thinking,   setThinking]   = useState(false);
  const [composer,   setComposer]   = useState('');
  const [config,     setConfig]     = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [webSearch,  setWebSearch]  = useState(() => {
    try { return localStorage.getItem('atl_websearch') === '1'; } catch { return false; }
  });
  const [error,      setError]      = useState('');
  const [paletteIndex,     setPaletteIndex]     = useState(0);
  const [paletteDismissed, setPaletteDismissed] = useState(false);

  useEffect(() => { try { localStorage.setItem('atl_websearch', webSearch?'1':'0'); } catch {} }, [webSearch]);
  const threadRef = useRef(null);
  const abortRef  = useRef(null);

  /* Load backend config (active model) */
  useEffect(() => {
    fetch('/api/config').then(r=>r.json()).then(setConfig).catch(()=>{});
  }, []);

  /* Init session if none */
  useEffect(() => {
    if (sessions.length === 0) {
      const s = newSession(config?.active_model||null);
      setSessions([s]);
      setActiveId(s.id);
    }
  }, []);

  useEffect(() => { saveSessions(sessions); }, [sessions]);

  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [activeId, sessions, streamBuf]);

  const session = sessions.find(s=>s.id===activeId) || sessions[0] || null;

  function selectSession(id) { if (!streaming) setActiveId(id); }

  function newSessionAction() {
    const s = newSession(config?.active_model||null);
    setSessions(prev => [s, ...prev]);
    setActiveId(s.id);
  }

  function deleteSession(id) {
    setSessions(prev => {
      const next = prev.filter(s=>s.id!==id);
      if (activeId===id) {
        const first = next[0];
        if (first) setActiveId(first.id);
        else {
          const s = newSession(config?.active_model||null);
          setActiveId(s.id);
          return [s];
        }
      }
      return next.length ? next : (() => { const s=newSession(config?.active_model||null); setActiveId(s.id); return [s]; })();
    });
  }

  async function handleModelSelect(model) {
    setPickerOpen(false);
    setConfig(prev => ({...prev, active_model:model}));
    await fetch('/api/config', { method:'PATCH', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({active_model:model}) }).catch(()=>{});
    setSessions(prev => prev.map(s => s.id===activeId ? {...s, model} : s));
  }

  const COMMANDS = [
    { id:'new',     label:'New conversation',                   hint:'',               icon:'plus',   keywords:['new','chat','session'],                              run:() => newSessionAction() },
    { id:'model',   label:'Switch model',                       hint:'',               icon:'chat',   keywords:['model','switch','pick'],                             run:() => setPickerOpen(true) },
    { id:'web',     label:`Web search: ${webSearch?'on':'off'}`,hint:'toggle',         icon:'globe',  keywords:['web','search','toggle'],                             run:() => setWebSearch(v => !v) },
    { id:'theme',   label:'Toggle theme',                       hint:'',               icon: (document.documentElement.dataset.theme==='mono'?'sun':'moon'), keywords:['theme','dark','light','mono'], run:() => onToggleTheme && onToggleTheme() },
    { id:'setup',   label:'Set up model / endpoint',            hint:'/setup',         icon:'plus',   keywords:['setup','model','endpoint','api','connect'],          run:() => onSetup && onSetup() },
    { id:'search',  label:'Configure web search',               hint:'/setup search',  icon:'globe',  keywords:['setup','search','tavily','brave','provider'],        run:() => onSearchSetup && onSearchSetup() },
    { id:'weather', label:'Configure weather API',              hint:'/setup weather', icon:'globe',  keywords:['setup','weather','openweathermap'],                  run:() => onWeatherSetup && onWeatherSetup() },
    { id:'stock',   label:'Configure stock API',                hint:'/setup stock',   icon:'globe',  keywords:['setup','stock','finnhub','quote'],                   run:() => onStockSetup && onStockSetup() },
    { id:'settings', label:'Open settings',                       hint:'',               icon:'gear',   keywords:['settings','preferences','config','options'],         run:() => onOpenSettings && onOpenSettings() },
    { id:'setmodel', label:'Set main model',                      hint:'',               icon:'gear',   keywords:['model','main','primary','default'],                  run:() => onOpenSettings && onOpenSettings('models') },
    { id:'setfast',  label:'Set fast model',                      hint:'',               icon:'gear',   keywords:['fast','cheap','background','quick'],                 run:() => onOpenSettings && onOpenSettings('models') },
    { id:'persona',  label:'Set system prompt',                   hint:'',               icon:'gear',   keywords:['system','prompt','persona','personality'],           run:() => onOpenSettings && onOpenSettings('persona') },
  ];

  const paletteQuery = composer.startsWith('/') ? composer.slice(1).toLowerCase().trim() : null;
  const filteredCommands = paletteQuery === null ? [] :
    COMMANDS.filter(c => !paletteQuery ||
      c.label.toLowerCase().includes(paletteQuery) ||
      c.keywords.some(k => k.includes(paletteQuery)));
  const paletteOpen = paletteQuery !== null && !paletteDismissed && filteredCommands.length > 0;

  function runCommand(cmd) {
    setComposer('');
    setPaletteDismissed(false);
    setPaletteIndex(0);
    cmd.run();
  }

  async function handleSend() {
    const text = composer.trim();
    if (!text || streaming) return;

    const model = session?.model || config?.active_model;
    if (!model) { setError('No model selected — use /setup or pick one below.'); return; }

    setComposer(''); setError('');

    const userMsg = { role:'user', content:text };
    const updatedMsgs = [...(session?.messages||[]), userMsg];
    const sessionName = session?.name === 'New chat' ? text.slice(0,50) : session?.name;

    setSessions(prev => prev.map(s => s.id===activeId
      ? {...s, messages:updatedMsgs, name:sessionName} : s));

    setStreaming(true); setStreamBuf(''); setStreamSearch(null); setStreamClock(null); setStreamDocs(null); setThinking(true);

    const controller = new AbortController();
    abortRef.current = controller;
    let searchTrace = null;
    let clockData = null;

    try {
      const resp = await fetch('/api/chat/stream', {
        method:'POST', signal:controller.signal,
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ model, messages:updatedMsgs, web_search: webSearch }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf='', accumulated='';

      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        buf += decoder.decode(value, {stream:true});
        const lines = buf.split('\n');
        buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw==='[DONE]') break;
          try {
            const evt = JSON.parse(raw);
            if (evt.error) { setError(String(evt.error)); break; }
            if (evt.atelier_clock)  { clockData = evt.atelier_clock; setStreamClock(clockData); setThinking(false); continue; }
            if (evt.atelier_search) { searchTrace = evt.atelier_search; setStreamSearch(searchTrace); continue; }
            if (evt.atelier_docs)   { setStreamDocs(evt.atelier_docs); continue; }
            const delta = evt.choices?.[0]?.delta?.content;
            if (delta) { setThinking(false); accumulated+=delta; setStreamBuf(accumulated); }
          } catch(_) {}
        }
      }

      const aiMsg = { role:'assistant', content:accumulated, model, search:searchTrace, clock:clockData };
      setSessions(prev => prev.map(s => s.id===activeId
        ? {...s, messages:[...updatedMsgs, aiMsg]} : s));
      setStreamBuf(''); setStreamSearch(null); setStreamClock(null); setStreamDocs(null); setThinking(false);
    } catch(e) {
      if (e.name!=='AbortError') setError('Stream failed — check your model connection.');
    } finally {
      setStreaming(false); setThinking(false); setStreamClock(null); abortRef.current = null;
    }
  }

  function handleKeyDown(e) {
    if (paletteOpen) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setPaletteIndex(i => Math.min(i+1, filteredCommands.length-1)); return; }
      if (e.key === 'ArrowUp')   { e.preventDefault(); setPaletteIndex(i => Math.max(i-1, 0)); return; }
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runCommand(filteredCommands[paletteIndex]); return; }
      if (e.key === 'Escape')    { e.preventDefault(); setPaletteDismissed(true); return; }
    }
    if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  /* Build rendered message list */
  const msgs = session?.messages || [];
  const renderedMsgs = [];
  for (let i=0; i<msgs.length; i++) {
    const msg = msgs[i];
    if (msg.role==='user') {
      if (i>0 && msgs[i-1].role==='assistant') renderedMsgs.push({type:'divider',key:`d${i}`});
      renderedMsgs.push({type:'user',key:`u${i}`,text:msg.content});
    } else if (msg.role==='assistant') {
      renderedMsgs.push({type:'ai',key:`a${i}`,text:msg.content,model:msg.model,search:msg.search,clock:msg.clock,isLast:i===msgs.length-1&&!streaming});
    }
  }
  const activeModel = session?.model || config?.active_model || '';
  const modelShort = activeModel.split('/').pop().split(':')[0] || '';
  const noModel = !activeModel;
  const tabs = sessions.map(s => ({id:s.id, label:s.name||'Untitled'}));

  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%',overflow:'hidden'}} className="surface-enter">

      {/* Scrollable tab bar */}
      <ChatTabBar
        tabs={tabs}
        active={activeId}
        onSelect={selectSession}
        onDelete={deleteSession}
        onNew={newSessionAction}
      />

      {/* Thread */}
      <div ref={threadRef} className="scroll" style={{
        flex:1, background:'var(--thread-bg)', padding:'32px 0',
        display:'flex', flexDirection:'column', gap:28,
      }}>
        {msgs.length===0 && !streaming && (
          <EmptyState icon="chat"
            title={noModel?'Welcome':'New conversation'}
            subtitle={noModel?'type /setup to add a model':'send a message to begin'}/>
        )}
        {renderedMsgs.map(item => {
          if (item.type==='divider') return (
            <div key={item.key} style={{maxWidth:680,width:'100%',margin:'0 auto',padding:'0 60px'}}>
              <TurnDots/>
            </div>
          );
          if (item.type==='user') return (
            <div key={item.key} style={{maxWidth:680,width:'100%',margin:'0 auto',padding:'0 60px'}}>
              <UserQuery text={item.text}/>
            </div>
          );
          if (item.type==='ai') return (
            <div key={item.key} style={{maxWidth:680,width:'100%',margin:'0 auto',padding:'0 60px'}}>
              {item.clock  && <ClockCard data={item.clock}/>}
              {item.search && <WebSearchTrace trace={item.search}/>}
              {item.text && <AiBlock text={item.text} model={item.model} isLast={item.isLast}/>}
            </div>
          );
          return null;
        })}
        {streaming && (
          <div style={{maxWidth:680,width:'100%',margin:'0 auto',padding:'0 60px'}}>
            {streamClock  && <ClockCard data={streamClock}/>}
            {streamSearch && <WebSearchTrace trace={streamSearch} searching={thinking}/>}
            {streamDocs && streamDocs.length > 0 && (
              <div style={{marginBottom:12,display:'flex',flexWrap:'wrap',gap:6}}>
                {streamDocs.map(fn => (
                  <span key={fn} style={{fontFamily:'var(--font-m)',fontSize:10.5,
                    padding:'3px 10px',borderRadius:20,letterSpacing:'.03em',
                    background:'var(--surface)',border:'1px solid var(--border-2)',
                    color:'var(--text-3)'}}>
                    📄 {fn}
                  </span>
                ))}
              </div>
            )}
            {thinking && !streamSearch && (
              <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:18}}>
                <ModelBadge model={activeModel}/>
                <span style={{color:'var(--text-3)',fontSize:10}}>—</span>
                <span style={{fontFamily:'var(--font-d)',fontSize:12.5,fontStyle:'italic',color:'var(--text-3)'}}>
                  The Atelier
                </span>
              </div>
            )}
            {thinking && !streamSearch && (
              <div style={{display:'flex',gap:20}}>
                <div style={{width:1.5,background:'var(--bar)',borderRadius:1,flexShrink:0}}/>
                <span style={{fontFamily:'var(--font-d)',fontSize:21,fontStyle:'italic',
                  color:'var(--text-3)',animation:'blink-thinking 1.1s ease-in-out infinite'}}>
                  Thinking…
                </span>
              </div>
            )}
            {streamBuf && (
              <AiBlock text={streamBuf} model={activeModel} streaming={true}/>
            )}
          </div>
        )}
        {error && (
          <div style={{maxWidth:680,width:'100%',margin:'0 auto',padding:'0 60px'}}>
            <p style={{fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',fontStyle:'italic'}}>{error}</p>
          </div>
        )}
      </div>

      {/* Composer */}
      <div style={{flexShrink:0,background:'var(--thread-bg)',borderTop:'1px solid var(--border-2)'}}>
        <div style={{maxWidth:680,width:'100%',margin:'0 auto',padding:'14px 60px 18px',position:'relative'}}>
          {paletteOpen && (
            <CommandPalette
              commands={filteredCommands}
              activeIndex={paletteIndex}
              onHover={setPaletteIndex}
              onRun={runCommand}
            />
          )}
          <textarea className="ph"
            placeholder={noModel?'Type /setup to configure a model…':'Continue the conversation…'}
            rows={2} value={composer}
            onChange={e=>{ setComposer(e.target.value); setPaletteDismissed(false); setPaletteIndex(0); }}
            onKeyDown={handleKeyDown}
            disabled={streaming}
            style={{width:'100%',resize:'none',fontFamily:'var(--font-b)',fontSize:15,
              lineHeight:1.65,color:'var(--text)',opacity:streaming?0.5:1}}/>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',
            paddingTop:8,borderTop:'1px solid var(--border)'}}>

            {/* Left controls: model picker + web search toggle */}
            <div style={{display:'flex',alignItems:'center',gap:7}}>
              {/* Model pill — clickable picker */}
              <div style={{position:'relative'}}>
                <button onClick={() => setPickerOpen(o=>!o)} style={{
                  display:'flex',alignItems:'center',gap:5,padding:'3px 10px',
                  border:`1px solid ${pickerOpen?'var(--accent-bd)':'var(--border-2)'}`,
                  borderRadius:10,
                  background:pickerOpen?'var(--accent-bg)':'transparent',
                  cursor:'pointer',transition:'all var(--t)',
                }}>
                  <span style={{fontFamily:'var(--font-m)',fontSize:9.5,
                    color:noModel?'var(--text-3)':'var(--accent-tx)'}}>
                    {noModel?'◇ no model':`◆ ${modelShort}`}
                  </span>
                  <Ico n="chevron" size={9} color="var(--text-3)"
                    style={{transform:pickerOpen?'rotate(180deg)':'none',transition:'transform var(--t)'}}/>
                </button>
                {pickerOpen && (
                  <ModelPickerDropdown
                    current={activeModel}
                    onSelect={handleModelSelect}
                    onClose={()=>setPickerOpen(false)}
                  />
                )}
              </div>

              {/* Web search toggle */}
              <button onClick={()=>setWebSearch(v=>!v)}
                onDoubleClick={()=>onSearchSetup&&onSearchSetup()}
                title={webSearch?'Web search on — double-click to configure providers'
                                :'Web search off — double-click to configure providers'}
                style={{
                  display:'flex',alignItems:'center',gap:5,padding:'3px 10px',
                  border:`1px solid ${webSearch?'var(--accent-bd)':'var(--border-2)'}`,
                  borderRadius:10,
                  background:webSearch?'var(--accent-bg)':'transparent',
                  cursor:'pointer',transition:'all var(--t)',
                }}>
                <Ico n="globe" size={11} color={webSearch?'var(--accent-tx)':'var(--text-3)'}/>
                <span style={{fontFamily:'var(--font-m)',fontSize:9.5,
                  color:webSearch?'var(--accent-tx)':'var(--text-3)'}}>Web</span>
              </button>
            </div>

            {/* Send / Stop */}
            {streaming ? (
              <button onClick={()=>abortRef.current?.abort()} style={{
                width:30,height:30,borderRadius:15,background:'var(--accent-bg)',
                border:'1px solid var(--accent-bd)',display:'grid',placeItems:'center',cursor:'pointer'}}>
                <span style={{width:8,height:8,background:'var(--accent)',borderRadius:2,display:'block'}}/>
              </button>
            ) : (
              <button onClick={handleSend} style={{
                width:30,height:30,borderRadius:15,background:'var(--send-bg)',
                border:'1px solid var(--accent-bd)',display:'grid',placeItems:'center',cursor:'pointer'}}>
                <Ico n="send" size={12} color="var(--send-fg)"/>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

window.V2Chat = { ChatSurface };
