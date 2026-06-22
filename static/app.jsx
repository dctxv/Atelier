/* ====== App root — Atelier v2 ====== */
const { useState, useEffect } = React;

const { ChatSurface }       = window.V2Chat;
const { ResearchSurface }   = window.V2Research;
const { MemorySurface }     = window.V2Memory;
const { NotesSurface }      = window.V2Notes;
const { ScratchpadSurface } = window.V2Scratchpad;
const { ProjectsSurface }   = window.V2Projects;
const { DocumentsSurface }  = window;
const { SettingsSurface }   = window;

function Placeholder({ name }) {
  return (
    <div style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',
      justifyContent:'center',gap:12,opacity:.4}}>
      <span style={{fontFamily:'var(--font-d)',fontSize:28,fontStyle:'italic',color:'var(--text)'}}>{name}</span>
      <span style={{fontFamily:'var(--font-m)',fontSize:11,color:'var(--text-3)',
        letterSpacing:'.1em',textTransform:'uppercase'}}>coming soon</span>
    </div>
  );
}

function ls(k,d){try{const v=localStorage.getItem(k);return v===null?d:JSON.parse(v);}catch{return d;}}
function lsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch{}}

function App() {
  const [surface,       setSurface]       = useState(()=>ls('atl_surface','chat'));
  const [theme,         setTheme]         = useState(()=>ls('atl_theme','natural'));
  const [activeProject, setActiveProject] = useState(null); // project the user is chatting inside
  const [chatTarget,    setChatTarget]    = useState(null); // session to open in the main chat after a move
  const [projectsTarget, setProjectsTarget] = useState(null); // {projectId, sessionId} to open after a move
  const [showWelcome, setShowWelcome] = useState(false);
  const [showSetup,   setShowSetup]   = useState(false);
  const [showSearchSetup, setShowSearchSetup] = useState(false);
  const [showWeatherSetup, setShowWeatherSetup] = useState(false);
  const [showStockSetup, setShowStockSetup] = useState(false);
  const [showGames, setShowGames] = useState(false);
  const [settingsSection, setSettingsSection] = useState(null);

  useEffect(()=>lsSet('atl_surface',surface),[surface]);
  useEffect(()=>{
    lsSet('atl_theme',theme);
    document.documentElement.dataset.theme=theme;
  },[theme]);
  useEffect(()=>{document.documentElement.dataset.theme=theme;},[]);

  /* Show welcome modal on first ever load */
  useEffect(()=>{
    if (!localStorage.getItem('atl_welcomed')) setShowWelcome(true);
  },[]);

  function dismissWelcome(){localStorage.setItem('atl_welcomed','1');setShowWelcome(false);}
  function openSetup(){setShowWelcome(false);setShowSetup(true);}
  function openSearchSetup(){setShowSearchSetup(true);}
  function openWeatherSetup(){setShowWeatherSetup(true);}
  function openStockSetup(){setShowStockSetup(true);}
  function openSettings(section){setSettingsSection(section||null);setSurface('settings');}
  function handleSetupSaved(){setShowSetup(false);setSurface('chat');}

  const toggleTheme=()=>setTheme(t=>t==='natural'?'mono':'natural');

  /* W3: quiet proactive memory signal — a subtle dot on the Memory rail when
     there are inferences/conflicts worth a look. Polls slowly; never nags.
     Re-checks when leaving the memory surface (the user just acted on items). */
  const [memBadge, setMemBadge] = useState(0);
  useEffect(()=>{
    let alive = true;
    const check = () => {
      if (document.visibilityState === 'hidden') return;
      fetch('/api/memory/surfacing').then(r=>r.ok?r.json():null)
        .then(d=>{ if (alive && d) setMemBadge(d.total||0); }).catch(()=>{});
    };
    check();
    const id = setInterval(check, 45000);
    return ()=>{ alive = false; clearInterval(id); };
  },[surface]);

  /* A conversation was moved between the main chat and a project. Follow it. */
  function handleMoved(sessionId, toProjectId){
    if (toProjectId){ setProjectsTarget({ projectId: toProjectId, sessionId }); setSurface('projects'); }
    else { setChatTarget(sessionId); setSurface('chat'); }
  }

  const renderSurface=()=>{
    switch(surface){
      case 'chat':      return <ChatSurface onSetup={openSetup} onSearchSetup={openSearchSetup} onWeatherSetup={openWeatherSetup} onStockSetup={openStockSetup} onToggleTheme={toggleTheme} onOpenSettings={openSettings} onNav={setSurface} onPlay={()=>setShowGames(true)} activeProject={activeProject} onExitProject={()=>setActiveProject(null)} onMoved={handleMoved} openSessionId={chatTarget} onConsumeOpen={()=>setChatTarget(null)}/>;
      case 'projects':  return <ProjectsSurface onSetup={openSetup} onSearchSetup={openSearchSetup} onWeatherSetup={openWeatherSetup} onStockSetup={openStockSetup} onToggleTheme={toggleTheme} onOpenSettings={openSettings} onNav={setSurface} onPlay={()=>setShowGames(true)} onMoved={handleMoved} target={projectsTarget} onConsumeTarget={()=>setProjectsTarget(null)}/>;
      case 'research':  return <ResearchSurface/>;
      case 'memory':    return <MemorySurface/>;
      case 'notes':     return <NotesSurface/>;
      case 'scratchpad':return <ScratchpadSurface/>;
      case 'documents': return <DocumentsSurface/>;
      case 'settings':  return <SettingsSurface initialSection={settingsSection}/>;
      default:          return <Placeholder name={surface.charAt(0).toUpperCase()+surface.slice(1)}/>;
    }
  };

  return (
    <div style={{display:'flex',height:'100%',width:'100%',overflow:'hidden'}}>
      <LeftRail active={surface} onNav={setSurface} theme={theme} onTheme={toggleTheme}
        badges={{ memory: memBadge }}/>
      <div style={{flex:1,display:'flex',flexDirection:'column',overflow:'hidden'}}>
        {renderSurface()}
      </div>
      {showWelcome && <WelcomeModal onSetup={openSetup} onClose={dismissWelcome}/>}
      {showSetup   && <SetupModal onClose={()=>setShowSetup(false)} onSaved={handleSetupSaved}/>}
      {showSearchSetup && <SearchSetupModal onClose={()=>setShowSearchSetup(false)} onSaved={()=>setShowSearchSetup(false)}/>}
      {showWeatherSetup && <WeatherSetupModal onClose={()=>setShowWeatherSetup(false)} onSaved={()=>setShowWeatherSetup(false)}/>}
      {showStockSetup && <StockSetupModal onClose={()=>setShowStockSetup(false)} onSaved={()=>setShowStockSetup(false)}/>}
      {showGames && <GamesModal onClose={()=>setShowGames(false)}/>}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
