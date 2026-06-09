/* ====== Shared setting sections — Atelier ======
 *
 * Three section components that render differently by mode:
 *   mode="wizard"   → step body inside SetupModal (onAdvance moves to next step)
 *   mode="settings" → standalone card inside SettingsSurface (inline save)
 *
 * Contract:
 *   function Section({ mode, config, onConfigChange, onAdvance, ...extras })
 *     config        : latest public_config() object (lifted state)
 *     onConfigChange: () => Promise — re-fetch public_config after a write
 *     onAdvance     : () => void — wizard only; proceed to next step
 */
const { useState, useEffect, useRef } = React;

/* ── Shared sub-components ────────────────────────────────────────────────── */

function SettingsCard({ title, subtitle, children, id }) {
  return (
    <div id={id} style={{
      background:'var(--surface)', border:'1px solid var(--border-2)',
      borderRadius:14, padding:'28px 32px', marginBottom:20,
    }}>
      {title && (
        <div style={{marginBottom:20}}>
          <SectionLabel style={{marginBottom:6}}>{subtitle||''}</SectionLabel>
          <h3 style={{fontFamily:'var(--font-d)',fontSize:22,fontWeight:400,
            fontStyle:'italic',color:'var(--text)',lineHeight:1.2}}>{title}</h3>
        </div>
      )}
      {children}
    </div>
  );
}

function FieldLabel({ children }) {
  return (
    <label style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)',
      letterSpacing:'.1em',textTransform:'uppercase',display:'block',marginBottom:6}}>
      {children}
    </label>
  );
}

function FieldInput({ type='text', value, onChange, onKeyDown, placeholder, style:sx }) {
  return (
    <input type={type} value={value} onChange={onChange} onKeyDown={onKeyDown}
      placeholder={placeholder}
      style={{width:'100%',padding:'10px 12px',fontFamily:'var(--font-m)',fontSize:13,
        color:'var(--text)',background:'var(--thread-bg)',
        border:'1px solid var(--border-2)',borderRadius:8,...(sx||{})}} />
  );
}

function PrimaryBtn({ onClick, disabled, children, style:sx }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding:'12px 0',borderRadius:9,width:'100%',
      background:'var(--send-bg)',border:'1px solid var(--accent-bd)',
      fontFamily:'var(--font-b)',fontSize:14,fontStyle:'italic',
      color:'var(--send-fg)',cursor:disabled?'default':'pointer',
      opacity:disabled?0.7:1,transition:'opacity var(--t)',...(sx||{})}}>
      {children}
    </button>
  );
}

function SecondaryBtn({ onClick, disabled, children, style:sx }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding:'10px 0',borderRadius:9,width:'100%',
      background:'transparent',border:'1px solid var(--border-2)',
      fontFamily:'var(--font-m)',fontSize:11.5,
      color:'var(--text-3)',cursor:'pointer',letterSpacing:'.04em',
      transition:'all var(--t)',...(sx||{})}}>
      {children}
    </button>
  );
}

function StatusDot({ active }) {
  return (
    <span style={{width:7,height:7,borderRadius:'50%',display:'inline-block',flexShrink:0,
      background:active?'var(--accent)':'var(--border-2)',
      transition:'background var(--t)'}} />
  );
}

const PRESETS = [
  { label:'OpenRouter', url:'https://openrouter.ai/api/v1' },
  { label:'OpenAI',     url:'https://api.openai.com/v1'    },
  { label:'Ollama',     url:'http://localhost:11434'        },
  { label:'Anthropic',  url:'https://api.anthropic.com/v1' },
  { label:'LM Studio',  url:'http://localhost:1234'        },
];


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * EndpointSection
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function EndpointSection({ mode, config, onConfigChange, onAdvance }) {
  const [url, setUrl]         = useState('');
  const [apiKey, setApiKey]   = useState('');
  const [name, setName]       = useState('');
  const [probing, setProbing] = useState(false);
  const [probeErr, setProbeErr] = useState('');
  const [showAdd, setShowAdd] = useState(mode === 'wizard');
  const [probeOk, setProbeOk] = useState(false);

  const endpoints = config?.endpoints || [];
  const activeId  = config?.active_endpoint_id;

  async function handleAdd() {
    if (!url.trim()) { setProbeErr('Enter an API endpoint URL.'); return; }
    setProbing(true); setProbeErr(''); setProbeOk(false);
    try {
      // Probe first
      const probeResp = await fetch('/api/models/probe', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ url:url.trim(), api_key:apiKey.trim() }),
      });
      const probeData = await probeResp.json();
      if (!probeData.ok) { setProbeErr(probeData.error||'Could not reach that endpoint.'); return; }
      if (!probeData.models?.length) { setProbeErr('Connected but no models found.'); return; }

      // Add endpoint
      const epResp = await fetch('/api/endpoints', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ url:url.trim(), api_key:apiKey.trim(), name:name||url.trim(), type:'cloud' }),
      }).then(r=>r.json());
      const epId = epResp?.endpoint?.id;

      // Activate it
      if (epId) {
        await fetch(`/api/endpoints/${epId}/activate`, {method:'POST'});
      }
      setProbeOk(true);
      setUrl(''); setApiKey(''); setName('');
      await onConfigChange();
      if (mode === 'wizard' && onAdvance) onAdvance();
      else setShowAdd(false);
    } catch(e) { setProbeErr('Connection failed — check the URL and network.'); }
    finally { setProbing(false); }
  }

  async function handleActivate(epId) {
    await fetch(`/api/endpoints/${epId}/activate`, {method:'POST'});
    await onConfigChange();
  }

  async function handleDelete(epId) {
    await fetch(`/api/endpoints/${epId}`, {method:'DELETE'});
    await onConfigChange();
  }

  async function handleTest(ep) {
    setProbing(true); setProbeErr('');
    try {
      const resp = await fetch('/api/models/probe', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ url:ep.url, api_key:'' }),
      }).then(r=>r.json());
      if (resp.ok) setProbeErr(`✓ Connected — ${resp.models.length} models available`);
      else setProbeErr(resp.error || 'Could not connect');
    } catch { setProbeErr('Connection test failed'); }
    finally { setProbing(false); }
  }

  const addForm = (
    <>
      <div style={{display:'flex',gap:6,flexWrap:'wrap',marginBottom:16}}>
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
        <div>
          <FieldLabel>API base URL</FieldLabel>
          <FieldInput value={url} onChange={e=>setUrl(e.target.value)}
            onKeyDown={e=>e.key==='Enter'&&handleAdd()}
            placeholder="https://openrouter.ai/api/v1" />
        </div>
        <div>
          <FieldLabel>API key (optional)</FieldLabel>
          <FieldInput type="password" value={apiKey} onChange={e=>setApiKey(e.target.value)}
            onKeyDown={e=>e.key==='Enter'&&handleAdd()}
            placeholder="sk-…" />
        </div>
        <div>
          <FieldLabel>Name (optional)</FieldLabel>
          <FieldInput value={name} onChange={e=>setName(e.target.value)}
            onKeyDown={e=>e.key==='Enter'&&handleAdd()}
            placeholder="My endpoint" />
        </div>
      </div>
      {probeErr && <p style={{fontFamily:'var(--font-m)',fontSize:11,
        color:probeErr.startsWith('✓')?'var(--accent-tx)':'var(--text-3)',
        fontStyle:'italic',marginTop:10}}>{probeErr}</p>}
      <PrimaryBtn onClick={handleAdd} disabled={probing} style={{marginTop:16}}>
        {probing?'Connecting…':'Connect & add endpoint →'}
      </PrimaryBtn>
    </>
  );

  const endpointList = endpoints.length > 0 && (
    <div style={{marginBottom:showAdd?16:0}}>
      {endpoints.map(ep => {
        const isActive = ep.id === activeId;
        return (
          <div key={ep.id} style={{
            display:'flex',alignItems:'center',gap:10,padding:'10px 12px',
            borderRadius:8,marginBottom:4,
            background:isActive?'var(--accent-bg)':'transparent',
            border:`1px solid ${isActive?'var(--accent-bd)':'var(--border)'}`,
            transition:'all var(--t)',
          }}>
            <StatusDot active={isActive} />
            <div style={{flex:1,minWidth:0}}>
              <div style={{fontFamily:'var(--font-b)',fontSize:13.5,fontStyle:'italic',
                color:'var(--text)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                {ep.name}
              </div>
              <div style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)',
                overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                {ep.type} · {ep.has_key?'key set':'no key'}
              </div>
            </div>
            <div style={{display:'flex',gap:4,flexShrink:0}}>
              {!isActive && (
                <button onClick={()=>handleActivate(ep.id)} title="Activate"
                  style={{padding:'4px 10px',borderRadius:7,
                    fontFamily:'var(--font-m)',fontSize:9.5,
                    color:'var(--accent-tx)',background:'var(--accent-bg)',
                    border:'1px solid var(--accent-bd)',cursor:'pointer'}}>
                  Use
                </button>
              )}
              <button onClick={()=>handleTest(ep)} title="Test connection" disabled={probing}
                style={{padding:'4px 8px',borderRadius:7,
                  fontFamily:'var(--font-m)',fontSize:9.5,
                  color:'var(--text-3)',border:'1px solid var(--border-2)',cursor:'pointer'}}>
                <Ico n="refresh" size={11} color="currentColor"/>
              </button>
              <button onClick={()=>handleDelete(ep.id)} title="Delete"
                style={{padding:'4px 8px',borderRadius:7,
                  fontFamily:'var(--font-m)',fontSize:9.5,
                  color:'var(--text-3)',border:'1px solid var(--border-2)',cursor:'pointer'}}>
                <Ico n="trash" size={11} color="currentColor"/>
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );

  if (mode === 'wizard') {
    return (
      <>
        {endpointList}
        {addForm}
      </>
    );
  }

  return (
    <SettingsCard title="Endpoints" subtitle="Connections" id="section-endpoints">
      {endpointList}
      {!showAdd ? (
        <button onClick={()=>setShowAdd(true)} style={{
          display:'flex',alignItems:'center',gap:6,padding:'8px 12px',
          fontFamily:'var(--font-m)',fontSize:11,color:'var(--accent-tx)',
          cursor:'pointer',borderRadius:8,border:'1px solid var(--accent-bd)',
          background:'var(--accent-bg)',transition:'all var(--t)',width:'100%',
          justifyContent:'center',marginTop:endpoints.length?8:0}}>
          <Ico n="plus" size={12} color="var(--accent-tx)"/>
          Add endpoint
        </button>
      ) : addForm}
    </SettingsCard>
  );
}


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * ModelSection
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function ModelSection({ mode, config, onConfigChange, onAdvance, subStep }) {
  const [models, setModels]   = useState([]);
  const [filter, setFilter]   = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [err, setErr]         = useState('');
  const prevEndpoint = useRef(config?.active_endpoint_id);

  const activeModel = config?.active_model || '';
  const cheapModel  = config?.cheap_model || '';

  function fetchModels() {
    setLoading(true); setErr('');
    fetch('/api/models').then(r=>r.json())
      .then(d => { setModels(d.models||[]); if(d.error) setErr(d.error); })
      .catch(e => setErr(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => { fetchModels(); }, []);

  // Re-fetch when active endpoint changes
  useEffect(() => {
    if (config?.active_endpoint_id !== prevEndpoint.current) {
      prevEndpoint.current = config?.active_endpoint_id;
      fetchModels();
    }
  }, [config?.active_endpoint_id]);

  async function selectMain(model) {
    setSaving(true);
    await fetch('/api/config', {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ active_model:model }),
    }).catch(()=>{});
    setSaving(false);
    setFilter('');
    await onConfigChange();
    if (mode === 'wizard' && onAdvance) onAdvance();
  }

  async function selectCheap(model) {
    setSaving(true);
    await fetch('/api/config', {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ cheap_model:model }),
    }).catch(()=>{});
    setSaving(false);
    setFilter('');
    await onConfigChange();
    if (mode === 'wizard' && onAdvance) onAdvance();
  }

  async function useSameAsMain() {
    setSaving(true);
    await fetch('/api/config', {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ cheap_model:null }),
    }).catch(()=>{});
    setSaving(false);
    await onConfigChange();
    if (mode === 'wizard' && onAdvance) onAdvance();
  }

  // Inverted-tier warning: simple heuristic based on known cheap model slugs
  function isLikelyCheap(m) {
    const l = (m||'').toLowerCase();
    return /flash|mini|haiku|nano|lite|small|tiny/.test(l);
  }
  function isLikelyExpensive(m) {
    const l = (m||'').toLowerCase();
    return /opus|pro|ultra|large|turbo/.test(l);
  }
  const invertedTier = cheapModel && activeModel &&
    (isLikelyExpensive(cheapModel) && isLikelyCheap(activeModel));

  const filtered = filter
    ? models.filter(m => m.toLowerCase().includes(filter.toLowerCase()))
    : models;

  function modelList(onSelect, currentModel) {
    return (
      <>
        <div style={{display:'flex',alignItems:'center',gap:8,padding:'8px 12px',
          border:'1px solid var(--border-2)',borderRadius:8,
          background:'var(--thread-bg)',marginBottom:12}}>
          <Ico n="search" size={12} color="var(--text-3)"/>
          <input autoFocus value={filter} onChange={e=>setFilter(e.target.value)}
            placeholder="Filter models…"
            style={{flex:1,fontFamily:'var(--font-m)',fontSize:13,color:'var(--text)'}}/>
          {filter && (
            <span style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)'}}>
              {filtered.length}/{models.length}
            </span>
          )}
        </div>
        <div style={{maxHeight:280,overflowY:'auto',marginBottom:12}}>
          {loading && <div style={{padding:18,textAlign:'center'}}><Pulse size={8}/></div>}
          {!loading && filtered.length===0 && (
            <div style={{padding:'14px',fontFamily:'var(--font-m)',fontSize:11,
              color:'var(--text-3)',fontStyle:'italic'}}>
              {err || (models.length===0 ? 'No endpoint configured' : 'No matches')}
            </div>
          )}
          {filtered.map((m,i) => {
            const short = m.split('/').pop().split(':')[0];
            const isCurrent = m === currentModel;
            return (
              <button key={i} onClick={()=>onSelect(m)} disabled={saving}
                style={{width:'100%',textAlign:'left',padding:'10px 12px',
                  display:'flex',justifyContent:'space-between',alignItems:'center',
                  borderBottom:'1px solid var(--border)',cursor:'pointer',
                  background:isCurrent?'var(--accent-bg)':'transparent',
                  borderLeft:`2px solid ${isCurrent?'var(--accent)':'transparent'}`,
                  transition:'background var(--t)'}}
                onMouseEnter={e=>{if(!isCurrent)e.currentTarget.style.background='var(--accent-bg)'}}
                onMouseLeave={e=>{if(!isCurrent)e.currentTarget.style.background='transparent'}}>
                <span style={{fontFamily:'var(--font-b)',fontSize:13.5,
                  fontStyle:'italic',color:'var(--text)',
                  overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:200}}>
                  {short}
                </span>
                <span style={{fontFamily:'var(--font-m)',fontSize:9.5,color:'var(--text-3)',
                  maxWidth:180,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                  {m}
                </span>
              </button>
            );
          })}
        </div>
      </>
    );
  }

  // Wizard mode — render based on subStep
  if (mode === 'wizard') {
    if (subStep === 'fast') {
      return (
        <>
          <p style={{fontFamily:'var(--font-b)',fontSize:13.5,lineHeight:1.7,
            color:'var(--text-q)',marginBottom:16}}>
            Pick a faster, cheaper model for background work — memory extraction,
            categorization, and flashcard generation. This keeps your main model free
            for actual answers. Or use the same model.
          </p>
          {modelList(selectCheap, cheapModel)}
          <SecondaryBtn onClick={useSameAsMain} disabled={saving} style={{marginBottom:8}}>
            Use same model
          </SecondaryBtn>
        </>
      );
    }
    // subStep === 'main' (default)
    return modelList(selectMain, activeModel);
  }

  // Settings mode — both pickers in one card
  const mainShort = activeModel ? activeModel.split('/').pop().split(':')[0] : 'none';
  const cheapShort = cheapModel ? cheapModel.split('/').pop().split(':')[0] : (activeModel ? 'same as main' : 'none');

  return (
    <SettingsCard title="Models" subtitle="AI Models" id="section-models">
      {/* Current selection summary */}
      <div style={{display:'flex',gap:12,marginBottom:16,flexWrap:'wrap'}}>
        <div style={{flex:1,minWidth:140,padding:'10px 14px',borderRadius:8,
          border:'1px solid var(--border-2)',background:'var(--thread-bg)'}}>
          <div style={{fontFamily:'var(--font-m)',fontSize:9,color:'var(--text-3)',
            letterSpacing:'.1em',textTransform:'uppercase',marginBottom:4}}>Main Model</div>
          <div style={{fontFamily:'var(--font-b)',fontSize:14,fontStyle:'italic',
            color:'var(--text)'}}>{mainShort}</div>
        </div>
        <div style={{flex:1,minWidth:140,padding:'10px 14px',borderRadius:8,
          border:'1px solid var(--border-2)',background:'var(--thread-bg)'}}>
          <div style={{fontFamily:'var(--font-m)',fontSize:9,color:'var(--text-3)',
            letterSpacing:'.1em',textTransform:'uppercase',marginBottom:4}}>Fast Model</div>
          <div style={{fontFamily:'var(--font-b)',fontSize:14,fontStyle:'italic',
            color:'var(--text)'}}>{cheapShort}</div>
        </div>
      </div>

      {invertedTier && (
        <div style={{padding:'10px 14px',borderRadius:8,marginBottom:14,
          background:'rgba(200,120,50,.08)',border:'1px solid rgba(200,120,50,.2)'}}>
          <span style={{fontFamily:'var(--font-m)',fontSize:10.5,color:'var(--accent-tx)'}}>
            ⚠ Your fast model appears heavier than your main model — background tasks may cost more than chat.
          </span>
        </div>
      )}

      <SectionLabel style={{marginBottom:10}}>Main model</SectionLabel>
      {modelList(selectMain, activeModel)}

      <div style={{height:1,background:'var(--rule)',margin:'16px 0'}}/>

      <SectionLabel style={{marginBottom:10}}>Fast model (background tasks)</SectionLabel>
      {modelList(selectCheap, cheapModel)}
      <SecondaryBtn onClick={useSameAsMain} disabled={saving}>
        Use same as main model
      </SecondaryBtn>
    </SettingsCard>
  );
}


/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * PersonaSection
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function PersonaSection({ mode, config, onConfigChange, onAdvance }) {
  const defaultPersona = "You are Atelier, a sophisticated AI workspace assistant. " +
    "Provide direct, natural answers. Do not redundantly repeat your conclusions, equations, or exact phrases across paragraphs. " +
    "Use LaTeX formatting like \\( \\) or \\[ \\] for math.";

  const [prompt, setPrompt] = useState(config?.system_prompt || '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved]   = useState(false);

  // Sync when config loads/changes
  useEffect(() => {
    if (config?.system_prompt !== undefined) {
      setPrompt(config.system_prompt || '');
    }
  }, [config?.system_prompt]);

  async function handleSave() {
    setSaving(true); setSaved(false);
    await fetch('/api/config', {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ system_prompt: prompt.trim() || null }),
    }).catch(()=>{});
    setSaving(false); setSaved(true);
    await onConfigChange();
    setTimeout(() => setSaved(false), 2000);
    if (mode === 'wizard' && onAdvance) onAdvance();
  }

  function handleReset() {
    setPrompt(defaultPersona);
  }

  const charCount = prompt.length;
  const isDefault = prompt.trim() === '' || prompt.trim() === defaultPersona;

  if (mode === 'wizard') {
    return (
      <>
        <p style={{fontFamily:'var(--font-b)',fontSize:13.5,lineHeight:1.7,
          color:'var(--text-q)',marginBottom:14}}>
          Customize the AI's persona — or skip to use the default. You can always
          change this later in settings.
        </p>
        <div style={{position:'relative',marginBottom:12}}>
          <textarea value={prompt || defaultPersona}
            onChange={e=>setPrompt(e.target.value)}
            placeholder={defaultPersona}
            rows={5}
            style={{width:'100%',resize:'vertical',padding:'12px 14px',
              fontFamily:'var(--font-b)',fontSize:13.5,lineHeight:1.65,
              color:'var(--text)',background:'var(--thread-bg)',
              border:'1px solid var(--border-2)',borderRadius:8,
              minHeight:100}} />
          <span style={{position:'absolute',bottom:8,right:10,
            fontFamily:'var(--font-m)',fontSize:9,color:'var(--text-3)'}}>
            {charCount} chars
          </span>
        </div>
        <div style={{display:'flex',gap:10}}>
          <PrimaryBtn onClick={handleSave} disabled={saving} style={{flex:1}}>
            {saving?'Saving…':'Save persona'}
          </PrimaryBtn>
          <SecondaryBtn onClick={()=>{ if (onAdvance) onAdvance(); }} style={{flex:1}}>
            Skip — use default
          </SecondaryBtn>
        </div>
      </>
    );
  }

  return (
    <SettingsCard title="System Prompt" subtitle="Persona" id="section-persona">
      <div style={{position:'relative',marginBottom:12}}>
        <textarea value={prompt || ''}
          onChange={e=>setPrompt(e.target.value)}
          placeholder={defaultPersona}
          rows={6}
          style={{width:'100%',resize:'vertical',padding:'12px 14px',
            fontFamily:'var(--font-b)',fontSize:13.5,lineHeight:1.65,
            color:'var(--text)',background:'var(--thread-bg)',
            border:'1px solid var(--border-2)',borderRadius:8,
            minHeight:120}} />
        <span style={{position:'absolute',bottom:8,right:10,
          fontFamily:'var(--font-m)',fontSize:9,color:'var(--text-3)'}}>
          {charCount} chars
        </span>
      </div>
      {!isDefault && (
        <button onClick={handleReset} style={{
          fontFamily:'var(--font-m)',fontSize:10,color:'var(--text-3)',
          cursor:'pointer',marginBottom:12}}>
          Reset to default
        </button>
      )}
      <PrimaryBtn onClick={handleSave} disabled={saving}>
        {saved?'Saved ✓':saving?'Saving…':'Save system prompt'}
      </PrimaryBtn>
    </SettingsCard>
  );
}

/* ── Register globally ────────────────────────────────────────────────────── */
window.AtelierSections = { EndpointSection, ModelSection, PersonaSection, SettingsCard };
