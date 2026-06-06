/* ====== Welcome & Setup modals — The Atelier backend ====== */
const { useState } = React;

function Backdrop({ children }) {
  return (
    <div style={{position:'fixed',inset:0,zIndex:200,background:'rgba(0,0,0,.45)',
      display:'flex',alignItems:'center',justifyContent:'center'}}>
      {children}
    </div>
  );
}

function ModalCard({ children, width=480 }) {
  return (
    <div style={{width,maxWidth:'calc(100vw - 32px)',
      background:'var(--surface)',border:'1px solid var(--border-2)',
      borderRadius:14,padding:'36px 40px',
      boxShadow:'0 24px 64px rgba(0,0,0,.28)'}}>
      {children}
    </div>
  );
}

function WelcomeModal({ onSetup, onClose }) {
  return (
    <Backdrop>
      <ModalCard width={440}>
        <div style={{display:'flex',justifyContent:'center',marginBottom:28}}>
          <div style={{width:48,height:48,borderRadius:12,background:'var(--accent-bg)',
            border:'1px solid var(--accent-bd)',display:'grid',placeItems:'center'}}>
            <span style={{fontFamily:'var(--font-d)',fontSize:30,fontWeight:500,
              color:'var(--accent-tx)',lineHeight:1}}>A</span>
          </div>
        </div>
        <h1 style={{fontFamily:'var(--font-d)',fontSize:32,fontWeight:400,
          color:'var(--text)',textAlign:'center',lineHeight:1.1,marginBottom:12}}>
          Welcome to The Atelier
        </h1>
        <p style={{fontFamily:'var(--font-b)',fontSize:14.5,lineHeight:1.75,
          color:'var(--text-q)',textAlign:'center',marginBottom:32}}>
          Your personal AI workspace. Connect any model you already have access to —
          OpenRouter, Ollama, OpenAI, or any OpenAI-compatible endpoint.
        </p>
        <div style={{height:1,background:'var(--rule)',marginBottom:28}}/>
        <div style={{display:'flex',flexDirection:'column',gap:10}}>
          <button onClick={onSetup} style={{padding:'12px 0',borderRadius:9,
            background:'var(--send-bg)',border:'1px solid var(--accent-bd)',
            fontFamily:'var(--font-b)',fontSize:14,fontStyle:'italic',
            color:'var(--send-fg)',cursor:'pointer'}}>
            Set up a model
          </button>
          <button onClick={onClose} style={{padding:'10px 0',borderRadius:9,
            background:'transparent',border:'1px solid var(--border-2)',
            fontFamily:'var(--font-m)',fontSize:11.5,
            color:'var(--text-3)',cursor:'pointer',letterSpacing:'.04em'}}>
            Skip for now — I'll type /setup later
          </button>
        </div>
      </ModalCard>
    </Backdrop>
  );
}

function SetupModal({ onClose, onSaved }) {
  const [step,      setStep]     = useState(1);
  const [url,       setUrl]      = useState('');
  const [apiKey,    setApiKey]   = useState('');
  const [name,      setName]     = useState('');
  const [probing,   setProbing]  = useState(false);
  const [probeErr,  setProbeErr] = useState('');
  const [models,    setModels]   = useState([]);
  const [filter,    setFilter]   = useState('');
  const [saving,    setSaving]   = useState(false);

  const PRESETS = [
    { label:'OpenRouter', url:'https://openrouter.ai/api/v1' },
    { label:'OpenAI',     url:'https://api.openai.com/v1'    },
    { label:'Ollama',     url:'http://localhost:11434'        },
    { label:'Anthropic',  url:'https://api.anthropic.com/v1' },
    { label:'LM Studio',  url:'http://localhost:1234'        },
  ];

  async function handleProbe() {
    if (!url.trim()) { setProbeErr('Enter an API endpoint URL.'); return; }
    setProbing(true); setProbeErr('');
    try {
      const resp = await fetch('/api/models/probe', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ url:url.trim(), api_key:apiKey.trim() }),
      });
      const d = await resp.json();
      if (!d.ok) { setProbeErr(d.error||'Could not reach that endpoint.'); return; }
      if (!d.models?.length) { setProbeErr('Connected but no models found.'); return; }
      setModels(d.models);
      setStep(2);
    } catch(e) { setProbeErr('Connection failed — check the URL and network.'); }
    finally { setProbing(false); }
  }

  async function handleSaveModel(model) {
    setSaving(true);
    // Add the endpoint
    const epResp = await fetch('/api/endpoints', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ url:url.trim(), api_key:apiKey.trim(), name:name||url.trim(), type:'cloud' }),
    }).then(r=>r.json()).catch(()=>null);

    const epId = epResp?.endpoint?.id;

    // Activate it + set model
    if (epId) {
      await fetch(`/api/endpoints/${epId}/activate`, {method:'POST'}).catch(()=>{});
    }
    await fetch('/api/config', {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ active_model:model }),
    }).catch(()=>{});

    setSaving(false);
    setStep(3);
    setTimeout(() => { if (onSaved) onSaved(); onClose(); }, 1400);
  }

  const filtered = filter ? models.filter(m=>m.toLowerCase().includes(filter.toLowerCase())) : models;

  return (
    <Backdrop>
      <ModalCard width={500}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:28}}>
          <div>
            <SectionLabel style={{marginBottom:6}}>
              {step===1?'Add API Endpoint':step===2?'Select Default Model':'Ready'}
            </SectionLabel>
            <h2 style={{fontFamily:'var(--font-d)',fontSize:26,fontWeight:400,
              fontStyle:'italic',color:'var(--text)',lineHeight:1.1}}>
              {step===1?'Connect your AI':step===2?`${models.length} models available`:'All set.'}
            </h2>
          </div>
          <button onClick={onClose} style={{color:'var(--text-3)',padding:4}}>
            <Ico n="close" size={16} color="currentColor"/>
          </button>
        </div>

        {step===1 && (
          <>
            <div style={{display:'flex',gap:6,flexWrap:'wrap',marginBottom:20}}>
              {PRESETS.map(p => (
                <button key={p.label} onClick={()=>setUrl(p.url)}
                  style={{padding:'4px 10px',borderRadius:8,cursor:'pointer',
                    fontFamily:'var(--font-m)',fontSize:10.5,
                    color:url===p.url?'var(--accent-tx)':'var(--text-3)',
                    background:url===p.url?'var(--accent-bg)':'transparent',
                    border:`1px solid ${url===p.url?'var(--accent-bd)':'var(--border-2)'}`,
                    transition:'all var(--t)'}}>
                  {p.label}
                </button>
              ))}
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:12}}>
              {[
                {label:'API base URL',      val:url,    set:setUrl,    ph:'https://openrouter.ai/api/v1', type:'text'},
                {label:'API key (optional)',val:apiKey, set:setApiKey, ph:'sk-…',                        type:'password'},
                {label:'Name (optional)',   val:name,   set:setName,   ph:'My endpoint',                 type:'text'},
              ].map(({label,val,set,ph,type}) => (
                <div key={label}>
                  <label style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)',
                    letterSpacing:'.1em',textTransform:'uppercase',display:'block',marginBottom:6}}>
                    {label}
                  </label>
                  <input type={type} value={val} onChange={e=>set(e.target.value)}
                    onKeyDown={e=>e.key==='Enter'&&handleProbe()} placeholder={ph}
                    style={{width:'100%',padding:'10px 12px',fontFamily:'var(--font-m)',fontSize:13,
                      color:'var(--text)',background:'var(--thread-bg)',
                      border:'1px solid var(--border-2)',borderRadius:8}}/>
                </div>
              ))}
            </div>
            {probeErr && <p style={{fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',
              fontStyle:'italic',marginTop:10}}>{probeErr}</p>}
            <button onClick={handleProbe} disabled={probing} style={{
              width:'100%',marginTop:20,padding:'12px 0',borderRadius:9,
              background:'var(--send-bg)',border:'1px solid var(--accent-bd)',
              fontFamily:'var(--font-b)',fontSize:14,fontStyle:'italic',
              color:'var(--send-fg)',cursor:probing?'default':'pointer',opacity:probing?0.7:1}}>
              {probing?'Connecting…':'Connect & fetch models →'}
            </button>
          </>
        )}

        {step===2 && (
          <>
            <div style={{display:'flex',alignItems:'center',gap:8,padding:'8px 12px',
              border:'1px solid var(--border-2)',borderRadius:8,
              background:'var(--thread-bg)',marginBottom:12}}>
              <Ico n="search" size={12} color="var(--text-3)"/>
              <input autoFocus value={filter} onChange={e=>setFilter(e.target.value)}
                placeholder="Filter models…"
                style={{flex:1,fontFamily:'var(--font-m)',fontSize:13,color:'var(--text)'}}/>
            </div>
            <div style={{maxHeight:280,overflowY:'auto',marginBottom:16}}>
              {filtered.map((m,i) => {
                const short = m.split('/').pop().split(':')[0];
                return (
                  <button key={i} onClick={()=>handleSaveModel(m)} disabled={saving}
                    style={{width:'100%',textAlign:'left',padding:'10px 12px',
                      display:'flex',justifyContent:'space-between',alignItems:'baseline',
                      borderBottom:'1px solid var(--border)',cursor:'pointer',
                      background:'transparent',transition:'background var(--t)'}}
                    onMouseEnter={e=>e.currentTarget.style.background='var(--accent-bg)'}
                    onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                    <span style={{fontFamily:'var(--font-b)',fontSize:13.5,
                      fontStyle:'italic',color:'var(--text)'}}>{short}</span>
                    <span style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)',
                      maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{m}</span>
                  </button>
                );
              })}
            </div>
            <button onClick={()=>setStep(1)} style={{fontFamily:'var(--font-m)',fontSize:11,
              color:'var(--text-3)',cursor:'pointer',letterSpacing:'.04em'}}>← Back</button>
          </>
        )}

        {step===3 && (
          <div style={{textAlign:'center',padding:'24px 0'}}>
            <div style={{width:40,height:40,borderRadius:'50%',
              background:'var(--accent-bg)',border:'1px solid var(--accent-bd)',
              display:'grid',placeItems:'center',margin:'0 auto 16px'}}>
              <Ico n="check" size={18} color="var(--accent-tx)"/>
            </div>
            <p style={{fontFamily:'var(--font-d)',fontSize:20,fontStyle:'italic',color:'var(--text)'}}>
              Model saved. Ready to chat.
            </p>
          </div>
        )}
      </ModalCard>
    </Backdrop>
  );
}

function SearchSetupModal({ onClose, onSaved }) {
  const [providers, setProviders] = useState([]);
  const [tavily, setTavily] = useState('');
  const [brave,  setBrave]  = useState('');
  const [saving, setSaving] = useState(false);
  const [done,   setDone]   = useState(false);

  const load = () => fetch('/api/search/providers').then(r=>r.json())
    .then(d=>setProviders(d.providers||[])).catch(()=>{});
  React.useEffect(() => { load(); }, []);

  async function handleSave() {
    setSaving(true);
    await fetch('/api/search/keys', {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ ...(tavily.trim()?{tavily:tavily.trim()}:{}),
                            ...(brave.trim()?{brave:brave.trim()}:{}) }),
    }).catch(()=>{});
    setSaving(false); setDone(true);
    await load();
    setTimeout(() => { if (onSaved) onSaved(); }, 900);
  }

  const dot = (ok) => ({width:7,height:7,borderRadius:'50%',display:'inline-block',
    background: ok?'var(--accent)':'var(--border-2)'});

  return (
    <Backdrop>
      <ModalCard width={500}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:28}}>
          <div>
            <SectionLabel style={{marginBottom:6}}>Web Search</SectionLabel>
            <h2 style={{fontFamily:'var(--font-d)',fontSize:26,fontWeight:400,
              fontStyle:'italic',color:'var(--text)',lineHeight:1.1}}>Connect search</h2>
          </div>
          <button onClick={onClose} style={{color:'var(--text-3)',padding:4}}>
            <Ico n="close" size={16} color="currentColor"/>
          </button>
        </div>

        <p style={{fontFamily:'var(--font-b)',fontSize:13.5,lineHeight:1.7,
          color:'var(--text-q)',marginBottom:20}}>
          Add a provider key for fast, fresh, real-time results — or continue
          keyless (DuckDuckGo, best-effort). <strong>Tavily</strong> is recommended:
          free 1,000 searches/month, news + dates in one call.
        </p>

        <div style={{display:'flex',flexDirection:'column',gap:12,marginBottom:16}}>
          {[
            {label:'Tavily API key (recommended)', val:tavily, set:setTavily, ph:'tvly-…'},
            {label:'Brave Search API key (optional)', val:brave, set:setBrave, ph:'BSA…'},
          ].map(({label,val,set,ph}) => (
            <div key={label}>
              <label style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)',
                letterSpacing:'.1em',textTransform:'uppercase',display:'block',marginBottom:6}}>
                {label}
              </label>
              <input type="password" value={val} onChange={e=>set(e.target.value)}
                onKeyDown={e=>e.key==='Enter'&&handleSave()} placeholder={ph}
                style={{width:'100%',padding:'10px 12px',fontFamily:'var(--font-m)',fontSize:13,
                  color:'var(--text)',background:'var(--thread-bg)',
                  border:'1px solid var(--border-2)',borderRadius:8}}/>
            </div>
          ))}
        </div>

        {providers.length>0 && (
          <div style={{border:'1px solid var(--border)',borderRadius:8,padding:'10px 12px',marginBottom:18}}>
            {providers.map(p => (
              <div key={p.name} style={{display:'flex',alignItems:'center',gap:8,padding:'3px 0'}}>
                <span style={dot(p.available)}/>
                <span style={{fontFamily:'var(--font-m)',fontSize:11,color:'var(--text)',
                  textTransform:'capitalize',flex:1}}>{p.name}</span>
                <span style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)'}}>
                  {p.has_key ? 'key set' : (p.cost_per_call===0 ? 'free' : 'no key')}
                  {p.remaining!=null ? ` · ${p.remaining} left` : ''}
                </span>
              </div>
            ))}
          </div>
        )}

        <div style={{display:'flex',gap:10}}>
          <button onClick={handleSave} disabled={saving} style={{
            flex:1,padding:'12px 0',borderRadius:9,
            background:'var(--send-bg)',border:'1px solid var(--accent-bd)',
            fontFamily:'var(--font-b)',fontSize:14,fontStyle:'italic',
            color:'var(--send-fg)',cursor:saving?'default':'pointer',opacity:saving?0.7:1}}>
            {done?'Saved ✓':saving?'Saving…':'Save keys'}
          </button>
          <button onClick={onClose} style={{padding:'12px 20px',borderRadius:9,
            background:'transparent',border:'1px solid var(--border-2)',
            fontFamily:'var(--font-m)',fontSize:11.5,color:'var(--text-3)',
            cursor:'pointer',letterSpacing:'.04em'}}>
            Continue keyless
          </button>
        </div>
      </ModalCard>
    </Backdrop>
  );
}

function WeatherSetupModal({ onClose, onSaved }) {
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSave() {
    setSaving(true);
    await fetch('/api/weather/keys', {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ openweathermap:key.trim() }),
    }).catch(()=>{});
    setSaving(false); setDone(true);
    setTimeout(() => { if (onSaved) onSaved(); }, 900);
  }

  return (
    <Backdrop>
      <ModalCard width={500}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:28}}>
          <div>
            <SectionLabel style={{marginBottom:6}}>Weather API</SectionLabel>
            <h2 style={{fontFamily:'var(--font-d)',fontSize:26,fontWeight:400,fontStyle:'italic',color:'var(--text)',lineHeight:1.1}}>Connect Weather</h2>
          </div>
          <button onClick={onClose} style={{color:'var(--text-3)',padding:4}}><Ico n="close" size={16} color="currentColor"/></button>
        </div>
        <p style={{fontFamily:'var(--font-b)',fontSize:13.5,lineHeight:1.7,color:'var(--text-q)',marginBottom:20}}>Add an OpenWeatherMap API key to enable live weather context in chat.</p>
        <div style={{marginBottom:24}}>
          <label style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)',letterSpacing:'.1em',textTransform:'uppercase',display:'block',marginBottom:6}}>OpenWeatherMap API Key</label>
          <input type="password" value={key} onChange={e=>setKey(e.target.value)} onKeyDown={e=>e.key==='Enter'&&handleSave()} placeholder="API Key…" style={{width:'100%',padding:'10px 12px',fontFamily:'var(--font-m)',fontSize:13,color:'var(--text)',background:'var(--thread-bg)',border:'1px solid var(--border-2)',borderRadius:8}}/>
        </div>
        <div style={{display:'flex',gap:10}}>
          <button onClick={handleSave} disabled={saving} style={{flex:1,padding:'12px 0',borderRadius:9,background:'var(--send-bg)',border:'1px solid var(--accent-bd)',fontFamily:'var(--font-b)',fontSize:14,fontStyle:'italic',color:'var(--send-fg)',cursor:saving?'default':'pointer',opacity:saving?0.7:1}}>{done?'Saved ✓':saving?'Saving…':'Save key'}</button>
          <button onClick={onClose} style={{padding:'12px 20px',borderRadius:9,background:'transparent',border:'1px solid var(--border-2)',fontFamily:'var(--font-m)',fontSize:11.5,color:'var(--text-3)',cursor:'pointer',letterSpacing:'.04em'}}>Close</button>
        </div>
      </ModalCard>
    </Backdrop>
  );
}

function StockSetupModal({ onClose, onSaved }) {
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSave() {
    setSaving(true);
    await fetch('/api/stock/keys', {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ finnhub:key.trim() }),
    }).catch(()=>{});
    setSaving(false); setDone(true);
    setTimeout(() => { if (onSaved) onSaved(); }, 900);
  }

  return (
    <Backdrop>
      <ModalCard width={500}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:28}}>
          <div>
            <SectionLabel style={{marginBottom:6}}>Stock API</SectionLabel>
            <h2 style={{fontFamily:'var(--font-d)',fontSize:26,fontWeight:400,fontStyle:'italic',color:'var(--text)',lineHeight:1.1}}>Connect Stocks</h2>
          </div>
          <button onClick={onClose} style={{color:'var(--text-3)',padding:4}}><Ico n="close" size={16} color="currentColor"/></button>
        </div>
        <p style={{fontFamily:'var(--font-b)',fontSize:13.5,lineHeight:1.7,color:'var(--text-q)',marginBottom:20}}>Add a Finnhub API key to enable live, real-time stock quotes in chat.</p>
        <div style={{marginBottom:24}}>
          <label style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)',letterSpacing:'.1em',textTransform:'uppercase',display:'block',marginBottom:6}}>Finnhub API Key</label>
          <input type="password" value={key} onChange={e=>setKey(e.target.value)} onKeyDown={e=>e.key==='Enter'&&handleSave()} placeholder="API Key…" style={{width:'100%',padding:'10px 12px',fontFamily:'var(--font-m)',fontSize:13,color:'var(--text)',background:'var(--thread-bg)',border:'1px solid var(--border-2)',borderRadius:8}}/>
        </div>
        <div style={{display:'flex',gap:10}}>
          <button onClick={handleSave} disabled={saving} style={{flex:1,padding:'12px 0',borderRadius:9,background:'var(--send-bg)',border:'1px solid var(--accent-bd)',fontFamily:'var(--font-b)',fontSize:14,fontStyle:'italic',color:'var(--send-fg)',cursor:saving?'default':'pointer',opacity:saving?0.7:1}}>{done?'Saved ✓':saving?'Saving…':'Save key'}</button>
          <button onClick={onClose} style={{padding:'12px 20px',borderRadius:9,background:'transparent',border:'1px solid var(--border-2)',fontFamily:'var(--font-m)',fontSize:11.5,color:'var(--text-3)',cursor:'pointer',letterSpacing:'.04em'}}>Close</button>
        </div>
      </ModalCard>
    </Backdrop>
  );
}

Object.assign(window, { WelcomeModal, SetupModal, SearchSetupModal, WeatherSetupModal, StockSetupModal });
