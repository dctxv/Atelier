/* ====== App root — The Atelier v2 ====== */
const { useState, useEffect } = React;

const { ChatSurface }     = window.V2Chat;
const { ResearchSurface } = window.V2Research;
const { MemorySurface }   = window.V2Memory;
const { NotesSurface }    = window.V2Notes;

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
  const [surface,     setSurface]     = useState(()=>ls('atl_surface','chat'));
  const [theme,       setTheme]       = useState(()=>ls('atl_theme','natural'));
  const [showWelcome, setShowWelcome] = useState(false);
  const [showSetup,   setShowSetup]   = useState(false);
  const [showSearchSetup, setShowSearchSetup] = useState(false);
  const [showWeatherSetup, setShowWeatherSetup] = useState(false);
  const [showStockSetup, setShowStockSetup] = useState(false);

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
  function handleSetupSaved(){setShowSetup(false);setSurface('chat');}

  const toggleTheme=()=>setTheme(t=>t==='natural'?'mono':'natural');

  const renderSurface=()=>{
    switch(surface){
      case 'chat':     return <ChatSurface onSetup={openSetup} onSearchSetup={openSearchSetup} onWeatherSetup={openWeatherSetup} onStockSetup={openStockSetup} onToggleTheme={toggleTheme}/>;
      case 'research': return <ResearchSurface/>;
      case 'memory':   return <MemorySurface/>;
      case 'notes':    return <NotesSurface/>;
      default:         return <Placeholder name={surface.charAt(0).toUpperCase()+surface.slice(1)}/>;
    }
  };

  return (
    <div style={{display:'flex',height:'100%',width:'100%',overflow:'hidden'}}>
      <LeftRail active={surface} onNav={setSurface} theme={theme} onTheme={toggleTheme}/>
      <div style={{flex:1,display:'flex',flexDirection:'column',overflow:'hidden'}}>
        {renderSurface()}
      </div>
      {showWelcome && <WelcomeModal onSetup={openSetup} onClose={dismissWelcome}/>}
      {showSetup   && <SetupModal onClose={()=>setShowSetup(false)} onSaved={handleSetupSaved}/>}
      {showSearchSetup && <SearchSetupModal onClose={()=>setShowSearchSetup(false)} onSaved={()=>setShowSearchSetup(false)}/>}
      {showWeatherSetup && <WeatherSetupModal onClose={()=>setShowWeatherSetup(false)} onSaved={()=>setShowWeatherSetup(false)}/>}
      {showStockSetup && <StockSetupModal onClose={()=>setShowStockSetup(false)} onSaved={()=>setShowStockSetup(false)}/>}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
