/* ====== Prescient Memory Surface — Part 1 ====== */
/* Design language: parchment palette, Cormorant italic display,
   Lora prose, IBM Plex Mono 9px/.14em uppercase labels, 1px warm borders,
   no shadows, 10-12px radii, 160ms ease transitions, fadeUp entry.       */
const { useState, useEffect, useCallback, useRef, useMemo } = React;

// ── Tier config ────────────────────────────────────────────────────────────
const TIER_ORDER = { essential: 0, living: 1, prescient: 2 };

const TIER_TABS = {
  essential:  ['fragments'],
  living:     ['overview', 'fragments', 'review', 'goals', 'timelines'],
  prescient:  ['overview', 'fragments', 'review', 'goals', 'timelines', 'inferred'],
};
const TAB_LABELS = {
  overview: 'Overview', fragments: 'Garden', review: 'Review',
  goals: 'Goals', timelines: 'Timelines', inferred: 'Inferred',
};
const TAB_MIN_TIER = {
  overview: 'living', fragments: 'essential', review: 'living',
  goals: 'living', timelines: 'living', inferred: 'prescient',
};

// ── Style helpers ──────────────────────────────────────────────────────────
// Full modality set the extractor emits (factual|opinion|desire|plan|
// self_perception|hypothetical|commitment) plus the engine-internal
// hypothesis/insight. 'hypothetical' is aliased to the hypothesis hue.
const MODALITY_COLORS = {
  factual:         'oklch(50% .03 250)',
  opinion:         'oklch(54% .12 90)',
  desire:          'oklch(52% .12 40)',
  plan:            'oklch(50% .12 200)',
  self_perception: 'oklch(52% .11 330)',
  hypothetical:    'oklch(52% .10 320)',
  commitment:      'oklch(48% .10 280)',
  hypothesis:      'oklch(52% .10 320)',
  insight:         'oklch(50% .12 160)',
};

function monoLabel(text, color, style) {
  return (
    <span style={{
      fontFamily:'var(--font-m)', fontSize:9, letterSpacing:'.12em',
      textTransform:'uppercase', color: color || 'var(--text-3)', ...style,
    }}>{text}</span>
  );
}

function GhostBtn({ onClick, children, style }) {
  return (
    <button onClick={onClick} style={{
      fontFamily:'var(--font-m)', fontSize:10, cursor:'pointer',
      padding:'3px 10px', borderRadius:4, color:'var(--text-2)',
      border:'1px solid var(--border-2)', background:'transparent',
      transition:'all var(--t)', ...style,
    }}>{children}</button>
  );
}

function MonoBadge({ children, color, style }) {
  const c = color || 'var(--accent)';
  return (
    <span style={{
      fontFamily:'var(--font-m)', fontSize:9, letterSpacing:'.10em',
      textTransform:'uppercase', color: c,
      border:`1px solid ${c}`, borderRadius:3, padding:'1px 6px',
      ...style,
    }}>{children}</span>
  );
}

function Card({ children, style }) {
  return (
    <div style={{
      background:'var(--surface)', border:'1px solid var(--border-2)',
      borderRadius:11, padding:'16px 20px', ...style,
    }}>{children}</div>
  );
}

function relTime(ts) {
  if (!ts) return '';
  const diff = (Date.now()/1000) - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff/86400)}d ago`;
  if (diff < 2592000) return `${Math.floor(diff/604800)}w ago`;
  return `${Math.floor(diff/2592000)}mo ago`;
}

function fmtDate(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString('en', { month:'short', year:'numeric' });
}

// ── Toggle ──────────────────────────────────────────────────────────────────
function Toggle({ on, onToggle }) {
  return (
    <div onClick={onToggle} style={{
      width:34, height:19, borderRadius:12, flexShrink:0, cursor:'pointer',
      background: on ? 'var(--accent-bg)' : 'var(--border)',
      border:`1px solid ${on ? 'var(--accent-bd)' : 'var(--border-2)'}`,
      position:'relative', transition:'all var(--t)',
    }}>
      <div style={{
        position:'absolute', top:2, left: on?15:2, width:13, height:13,
        borderRadius:'50%', background: on ? 'var(--accent)' : 'var(--text-3)',
        transition:'left var(--t), background var(--t)',
      }}/>
    </div>
  );
}

// ── Garden view ───────────────────────────────────────────────────────────────
const MODALITY_GLYPH = {
  factual:         '●',
  opinion:         '◈',
  desire:          '◇',
  plan:            '▷',
  self_perception: '◉',
  hypothetical:    '⬡',
  commitment:      '◼',
  hypothesis:      '⬡',
  insight:         '◎',
};

function decayOpacity(createdAt) {
  if (!createdAt) return 1;
  const ageDays = (Date.now() / 1000 - createdAt) / 86400;
  if (ageDays < 7) return 1;
  if (ageDays > 180) return 0.45;
  return 1 - (ageDays - 7) / (180 - 7) * 0.55;
}

function GardenAtomRow({ atom, onClick, selected }) {
  const glyph = MODALITY_GLYPH[atom.modality] || '●';
  const modColor = MODALITY_COLORS[atom.modality] || 'var(--bar)';
  const opacity = decayOpacity(atom.created_at);
  const isInferred = atom.modality === 'insight' || atom.modality === 'hypothesis';
  const isProposed = atom.status === 'proposed';

  return (
    <div onClick={() => onClick(atom)} style={{
      display: 'flex', gap: 10, padding: '9px 0',
      borderBottom: '1px solid var(--rule)', cursor: 'pointer', opacity,
      background: selected ? 'var(--accent-bg)' : 'transparent',
      transition: 'background var(--t)',
    }}>
      <span style={{ fontFamily: 'var(--font-m)', fontSize: 11, color: modColor,
        flexShrink: 0, lineHeight: 1.65, paddingTop: 1 }}>{glyph}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontFamily: 'var(--font-b)', fontSize: 13.5, lineHeight: 1.65,
          color: 'var(--text)', margin: 0 }}>
          {atom.text}
          {isProposed && (
            <span style={{ fontFamily: 'var(--font-m)', fontSize: 9,
              color: 'var(--accent)', marginLeft: 8 }}>(proposed)</span>
          )}
          {isInferred && !isProposed && (
            <span style={{ fontFamily: 'var(--font-m)', fontSize: 9,
              color: MODALITY_COLORS.insight, marginLeft: 8, opacity: 0.7 }}>(inferred)</span>
          )}
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center',
          marginTop: 3 }}>
          {monoLabel(relTime(atom.created_at))}
          {atom.predicate && (
            <span style={{ fontFamily: 'var(--font-m)', fontSize: 9, color: 'var(--text-3)',
              padding: '1px 5px', border: '1px solid var(--border)', borderRadius: 3 }}>
              {atom.predicate}
            </span>
          )}
          {atom.confidence != null && atom.confidence < 0.7 && (
            <span style={{ fontFamily: 'var(--font-m)', fontSize: 9, color: 'var(--text-3)' }}>
              {Math.round(atom.confidence * 100)}%
            </span>
          )}
          {atom.pinned && <span style={{ color: 'var(--accent)', fontSize: 10 }}>📌</span>}
        </div>
      </div>
    </div>
  );
}

function StrandBed({ strand, atoms, selectedId, onAtomClick }) {
  const [open, setOpen] = useState(true);
  const color = strand.color || '#9A8A78';
  const name = strand.label || strand.name || 'Unlabeled';

  return (
    <div style={{ marginBottom: 28 }}>
      <div onClick={() => setOpen(o => !o)} style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
        cursor: 'pointer', borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: color,
          flexShrink: 0, display: 'inline-block' }}/>
        <span style={{ fontFamily: 'var(--font-b)', fontSize: 13, fontStyle: 'italic',
          color: 'var(--text-2)', flex: 1 }}>{name}</span>
        <span style={{ fontFamily: 'var(--font-m)', fontSize: 9,
          color: 'var(--text-3)' }}>{atoms.length}</span>
        <span style={{ color: 'var(--text-3)', fontSize: 10 }}>{open ? '▴' : '▾'}</span>
      </div>
      {open && atoms.map(a => (
        <GardenAtomRow key={a.id} atom={a}
          onClick={onAtomClick} selected={selectedId === a.id}/>
      ))}
    </div>
  );
}

function AtomDetailPanel({ atom, onClose, onUpdate }) {
  const [events, setEvents] = useState([]);
  const [eventsLoaded, setEventsLoaded] = useState(false);
  const [confirming, setConfirming] = useState(null);

  useEffect(() => {
    if (!atom) return;
    setEventsLoaded(false);
    setEvents([]);
    fetch(`/api/memory/${atom.id}/events`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setEvents(d.events || []); setEventsLoaded(true); })
      .catch(() => setEventsLoaded(true));
  }, [atom ? atom.id : null]);

  async function togglePin() {
    await fetch(`/api/memory/${atom.id}/pin`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned: !atom.pinned }),
    });
    if (onUpdate) onUpdate();
  }

  async function retract() {
    await fetch(`/api/memory/${atom.id}/retract`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'user' }),
    });
    setConfirming(null);
    if (onUpdate) onUpdate();
    onClose();
  }

  async function forget() {
    await fetch(`/api/memory/${atom.id}/forget`, { method: 'POST' });
    setConfirming(null);
    if (onUpdate) onUpdate();
    onClose();
  }

  if (!atom) return null;

  const isProposed = atom.status === 'proposed';
  const isInferred = atom.modality === 'insight' || atom.modality === 'hypothesis';
  const fields = [
    ['subject',    atom.subject],
    ['predicate',  atom.predicate],
    ['object',     atom.object],
    ['modality',   atom.modality],
    ['status',     atom.status],
    ['confidence', atom.confidence != null ? `${Math.round(atom.confidence * 100)}%` : null],
    ['added',      relTime(atom.created_at)],
    ['valid from', atom.valid_from ? fmtDate(atom.valid_from) : null],
    ['expires',    atom.valid_until ? fmtDate(atom.valid_until) : null],
  ].filter(([, v]) => v);

  return (
    <div className="fade-up" style={{ width: 320, flexShrink: 0,
      borderLeft: '1px solid var(--border)', background: 'var(--nav-bg)',
      overflowY: 'auto', padding: '20px 22px', display: 'flex',
      flexDirection: 'column', gap: 16 }}>

      <div style={{ display: 'flex', alignItems: 'center',
        justifyContent: 'space-between' }}>
        {monoLabel('Atom')}
        <button onClick={onClose} style={{ cursor: 'pointer' }}>
          <Ico n="close" size={14} color="var(--text-3)"/>
        </button>
      </div>

      <div>
        {isProposed && (
          <div style={{ marginBottom: 8 }}>
            <MonoBadge color="var(--accent)">proposed — not in context</MonoBadge>
          </div>
        )}
        {isInferred && !isProposed && (
          <div style={{ marginBottom: 8 }}>
            <MonoBadge color={MODALITY_COLORS.insight}>(inferred)</MonoBadge>
          </div>
        )}
        <p style={{ fontFamily: 'var(--font-b)', fontSize: 14.5, lineHeight: 1.7,
          color: 'var(--text)' }}>{atom.text}</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {fields.map(([label, value]) => (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between',
            alignItems: 'baseline', gap: 8 }}>
            {monoLabel(label)}
            <span style={{ fontFamily: 'var(--font-m)', fontSize: 10.5,
              color: 'var(--text-2)', textAlign: 'right', flex: 1 }}>{value}</span>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <GhostBtn onClick={togglePin}>{atom.pinned ? 'Unpin' : 'Pin'}</GhostBtn>
        {confirming === 'retract' ? (
          <>
            <GhostBtn onClick={retract}
              style={{ color: 'oklch(52% .15 25)', borderColor: 'oklch(70% .10 25)' }}>
              Confirm retract
            </GhostBtn>
            <GhostBtn onClick={() => setConfirming(null)}>Cancel</GhostBtn>
          </>
        ) : confirming === 'forget' ? (
          <>
            <GhostBtn onClick={forget}
              style={{ color: 'oklch(52% .15 25)', borderColor: 'oklch(70% .10 25)' }}>
              Confirm forget
            </GhostBtn>
            <GhostBtn onClick={() => setConfirming(null)}>Cancel</GhostBtn>
          </>
        ) : (
          <>
            <GhostBtn onClick={() => setConfirming('retract')}>Retract</GhostBtn>
            <GhostBtn onClick={() => setConfirming('forget')}
              style={{ color: 'oklch(52% .15 25)', borderColor: 'oklch(70% .10 25)' }}>
              Forget
            </GhostBtn>
          </>
        )}
      </div>

      {eventsLoaded && events.length > 0 && (
        <div>
          {monoLabel('audit trail', undefined, { display: 'block', marginBottom: 8 })}
          {events.map((e, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between',
              padding: '4px 0', borderBottom: '1px solid var(--rule)' }}>
              <span style={{ fontFamily: 'var(--font-m)', fontSize: 9.5,
                color: 'var(--text-2)' }}>{e.kind}</span>
              <span style={{ fontFamily: 'var(--font-m)', fontSize: 9,
                color: 'var(--text-3)' }}>{relTime(e.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function GardenTab() {
  const [view, setView] = useState('garden');
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [modFilter, setModFilter] = useState('all');
  const [selectedAtom, setSelectedAtom] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    fetch('/api/memory/graph')
      .then(r => r.ok ? r.json() : null)
      .then(d => { setGraphData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  function handleUpdate() { load(); setSelectedAtom(null); }

  if (loading) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center',
      justifyContent: 'center' }}>
      <Pulse size={8}/>
    </div>
  );
  if (!graphData) return null;

  const allStrands = [
    ...(graphData.strands || []).filter(s => s.id !== '_unstranded'),
    {
      id: '_unstranded', name: 'Unsorted', label: 'Unsorted',
      color: '#9A8A78', atoms: graphData.unstranded || [],
    },
  ].filter(s => (s.atoms || []).length > 0);

  const MODALITIES = ['all', 'factual', 'opinion', 'desire', 'plan', 'insight', 'hypothesis'];

  function filterAtoms(atoms) {
    return atoms.filter(a => {
      if (modFilter !== 'all' && a.modality !== modFilter) return false;
      if (query) {
        const q = query.toLowerCase();
        return (a.text || '').toLowerCase().includes(q) ||
               (a.predicate || '').toLowerCase().includes(q);
      }
      return true;
    });
  }

  const allAtoms = allStrands.flatMap(s => s.atoms || []);
  const pinnedFiltered = allAtoms.filter(a => a.pinned && filterAtoms([a]).length > 0);

  return (
    <div style={{ flex: 1, overflow: 'hidden', display: 'flex',
      flexDirection: 'column' }}>

      {/* Sticky control bar */}
      <div style={{ padding: '10px 40px', borderBottom: '1px solid var(--border)',
        background: 'var(--nav-bg)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8,
            padding: '4px 12px', border: '1px solid var(--border-2)', borderRadius: 8,
            background: 'var(--thread-bg)', flex: 1, maxWidth: 360 }}>
            <Ico n="search" size={12} color="var(--text-3)"/>
            <input value={query} onChange={e => setQuery(e.target.value)}
              placeholder="Search memories…"
              style={{ fontFamily: 'var(--font-m)', fontSize: 11,
                color: 'var(--text)', flex: 1 }}/>
          </div>
          {monoLabel(`${allAtoms.length}`, 'var(--text-3)')}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center',
            gap: 0, borderRadius: 8, border: '1px solid var(--border-2)',
            overflow: 'hidden', background: 'var(--thread-bg)' }}>
            {[['garden', '⊞ Garden'], ['constellation', '◈ Map']].map(([v, lbl]) => (
              <button key={v} onClick={() => setView(v)} style={{
                padding: '5px 14px', cursor: 'pointer',
                fontFamily: 'var(--font-m)', fontSize: 10, letterSpacing: '.06em',
                background: view === v ? 'var(--accent-bg)' : 'transparent',
                color: view === v ? 'var(--accent)' : 'var(--text-3)',
                borderRight: v === 'garden' ? '1px solid var(--border-2)' : 'none',
              }}>{lbl}</button>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
          {MODALITIES.map(m => (
            <button key={m} onClick={() => setModFilter(m)} style={{
              fontFamily: 'var(--font-m)', fontSize: 9.5, letterSpacing: '.06em',
              textTransform: 'uppercase', cursor: 'pointer',
              padding: '2px 8px', borderRadius: 4,
              border: modFilter === m ? '1px solid var(--accent-bd)' : '1px solid transparent',
              background: modFilter === m ? 'var(--accent-bg)' : 'transparent',
              color: modFilter === m ? 'var(--accent)' : 'var(--text-3)',
            }}>{m}</button>
          ))}
        </div>
      </div>

      {/* Main area */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
        {view === 'garden' ? (
          <div className="scroll" style={{ flex: 1, background: 'var(--thread-bg)',
            padding: '24px 40px' }}>

            {pinnedFiltered.length > 0 && (
              <div style={{ marginBottom: 32 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8,
                  padding: '4px 0', borderBottom: '1px solid var(--border)',
                  marginBottom: 2 }}>
                  {monoLabel('pinned', 'var(--accent)')}
                </div>
                {pinnedFiltered.map(a => (
                  <GardenAtomRow key={a.id} atom={a}
                    onClick={setSelectedAtom}
                    selected={selectedAtom ? selectedAtom.id === a.id : false}/>
                ))}
              </div>
            )}

            {allStrands.map(s => {
              const filtered = filterAtoms(s.atoms || []);
              if (!filtered.length) return null;
              return (
                <StrandBed key={s.id} strand={s} atoms={filtered}
                  selectedId={selectedAtom ? selectedAtom.id : null}
                  onAtomClick={setSelectedAtom}/>
              );
            })}

            {allAtoms.length === 0 && (
              <p style={{ fontFamily: 'var(--font-m)', fontSize: 12,
                color: 'var(--text-3)', fontStyle: 'italic' }}>
                No memories yet — they build up as you chat.
              </p>
            )}
            {allAtoms.length > 0 &&
              allStrands.every(s => filterAtoms(s.atoms || []).length === 0) && (
              <p style={{ fontFamily: 'var(--font-m)', fontSize: 12,
                color: 'var(--text-3)', fontStyle: 'italic' }}>
                No matches.
              </p>
            )}
          </div>
        ) : (
          <ConstellationView
            strands={allStrands}
            selectedId={selectedAtom ? selectedAtom.id : null}
            onAtomClick={setSelectedAtom}/>
        )}

        {selectedAtom && (
          <AtomDetailPanel
            atom={selectedAtom}
            onClose={() => setSelectedAtom(null)}
            onUpdate={handleUpdate}/>
        )}
      </div>
    </div>
  );
}

// ── Review tab (W6: extraction visibility & steering) ─────────────────────────
function ReviewTab({ questions, onResolve, onChange }) {
  const open = questions.open || [];
  const resolved = questions.resolved || [];
  const [learned, setLearned] = useState([]);
  const [proposed, setProposed] = useState([]);

  const load = useCallback(() => {
    fetch('/api/memory/review').then(r => r.ok ? r.json() : null).then(d => {
      if (d) { setLearned(d.learned || []); setProposed(d.proposed || []); }
    }).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);
  // Refresh the learned/proposed queue whenever the parent re-polls.
  useEffect(() => { load(); }, [questions]);

  async function act(id, action) {
    await fetch(`/api/memory/review/${id}/${action}`, { method:'POST' });
    load();
    if (onChange) onChange();
  }

  async function saveEdit(id, text) {
    await fetch(`/api/memory/${id}`, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ text }),
    });
    load();
    if (onChange) onChange();
  }

  const nothing = open.length === 0 && learned.length === 0 && proposed.length === 0;
  if (nothing) {
    return (
      <div style={{ padding:'56px', textAlign:'center' }}>
        <p style={{ fontFamily:'var(--font-b)', fontSize:15, color:'var(--text-2)', fontStyle:'italic' }}>
          Memory is coherent
        </p>
        <p style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)', marginTop:8 }}>
          Nothing to review — no new learnings, inferences, or conflicts.
        </p>
        {resolved.length > 0 && (
          <p style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)', marginTop:16 }}>
            {resolved.length} previously resolved.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>
      <div style={{ maxWidth:760, margin:'0 auto', padding:'32px 40px' }}>

        {/* Recently learned — stated facts extraction produced */}
        {learned.length > 0 && (
          <section style={{ marginBottom:36 }}>
            <SectionLabel right={`${learned.length}`} style={{ marginBottom:6 }}>
              Recently learned
            </SectionLabel>
            <p style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)',
              marginBottom:16, fontStyle:'italic' }}>
              What I picked up from our conversations. Keep, edit, or reject —
              rejecting tells me not to learn it again.
            </p>
            {learned.map(m => (
              <LearnedCard key={m.id} m={m}
                onAccept={() => act(m.id, 'accept')}
                onReject={() => act(m.id, 'reject')}
                onSave={txt => saveEdit(m.id, txt)}/>
            ))}
          </section>
        )}

        {/* Proposed inferences — shown before believed (Visibility Law) */}
        {proposed.length > 0 && (
          <section style={{ marginBottom:36 }}>
            <SectionLabel right={`${proposed.length}`} style={{ marginBottom:6 }}>
              Proposed inferences
            </SectionLabel>
            <p style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)',
              marginBottom:16, fontStyle:'italic' }}>
              Things I've inferred but not yet acted on. They won't shape my
              answers until you confirm them.
            </p>
            {proposed.map(p => (
              <ProposedCard key={p.id} p={p}
                onConfirm={() => act(p.id, 'accept')}
                onReject={() => act(p.id, 'reject')}/>
            ))}
          </section>
        )}

        {/* To reconcile — conflicts / tensions / gaps */}
        {open.length > 0 && (
          <section>
            <SectionLabel right={`${open.length} open`} style={{ marginBottom:20 }}>
              To reconcile
            </SectionLabel>
            {open.map(q => (
              <QuestionCard key={q.id} q={q} onResolve={onResolve}/>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}

function LearnedCard({ m, onAccept, onReject, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(m.text);
  const color = MODALITY_COLORS[m.modality] || 'var(--text-3)';
  return (
    <Card style={{ marginBottom:12 }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
        {monoLabel(m.modality || 'fact', color)}
        {m.confidence != null && monoLabel(`${Math.round(m.confidence*100)}%`)}
        {monoLabel(relTime(m.timestamp), undefined, { marginLeft:'auto' })}
      </div>
      {editing ? (
        <textarea value={draft} onChange={e => setDraft(e.target.value)} rows={2}
          style={{ width:'100%', fontFamily:'var(--font-b)', fontSize:13.5, color:'var(--text)',
            lineHeight:1.6, background:'var(--thread-bg)', border:'1px solid var(--border-2)',
            borderRadius:6, padding:'8px 10px', marginBottom:12, resize:'vertical' }}/>
      ) : (
        <p style={{ fontFamily:'var(--font-b)', fontSize:13.5, color:'var(--text)',
          lineHeight:1.65, marginBottom:12 }}>{m.text}</p>
      )}
      <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
        {editing ? (
          <>
            <GhostBtn onClick={() => { if (draft.trim()) { onSave(draft.trim()); setEditing(false); } }}
              style={{ color:'var(--accent)', borderColor:'var(--accent-bd)' }}>Save</GhostBtn>
            <GhostBtn onClick={() => { setDraft(m.text); setEditing(false); }}>Cancel</GhostBtn>
          </>
        ) : (
          <>
            <GhostBtn onClick={onAccept}>Keep</GhostBtn>
            <GhostBtn onClick={() => setEditing(true)}>Edit</GhostBtn>
            <GhostBtn onClick={onReject}
              style={{ color:'oklch(52% .15 25)', borderColor:'oklch(70% .10 25)' }}>Reject</GhostBtn>
          </>
        )}
      </div>
    </Card>
  );
}

function ProposedCard({ p, onConfirm, onReject }) {
  const [showProv, setShowProv] = useState(false);
  const prov = p.provenance || [];
  return (
    <Card style={{ marginBottom:12 }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
        {monoLabel(p.inference_kind || 'inferred', MODALITY_COLORS.insight)}
        {p.confidence != null && monoLabel(`${Math.round(p.confidence*100)}%`)}
        {monoLabel('inferred', undefined, { marginLeft:'auto' })}
      </div>
      <p style={{ fontFamily:'var(--font-b)', fontSize:13.5, color:'var(--text)',
        lineHeight:1.65, marginBottom:12 }}>{p.text}</p>
      {prov.length > 0 && (
        <div style={{ marginBottom:12 }}>
          <button onClick={() => setShowProv(v => !v)} style={{ cursor:'pointer' }}>
            {monoLabel(`${showProv ? 'hide' : 'show'} evidence (${prov.length})`,
              'var(--accent-tx)')}
          </button>
          {showProv && (
            <div style={{ marginTop:8 }}>
              {prov.map(s => (
                <div key={s.id} style={{ padding:'6px 10px', marginBottom:5,
                  background:'var(--thread-bg)', borderRadius:6,
                  fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-2)' }}>
                  {s.text}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
        <GhostBtn onClick={onConfirm}
          style={{ color:'var(--accent)', borderColor:'var(--accent-bd)' }}>Confirm</GhostBtn>
        <GhostBtn onClick={onReject}
          style={{ color:'oklch(52% .15 25)', borderColor:'oklch(70% .10 25)' }}>Reject</GhostBtn>
      </div>
    </Card>
  );
}

function QuestionCard({ q, onResolve }) {
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState('');

  const kindLabel = {
    conflict:        'Conflict',
    soft_conflict:   'Possible conflict',
    reversal_check:  'Changed your mind?',
    gap:             'Gap',
    stale_check:     'Still current?',
    goal_check:      'Goal update',
    insight_offer:   'Timeline offer',
  }[q.kind] || q.kind;

  const kindColor = {
    conflict:       'oklch(52% .15 25)',
    soft_conflict:  'oklch(52% .10 40)',
    reversal_check: 'oklch(48% .10 280)',
    gap:            'oklch(50% .10 200)',
    stale_check:    'oklch(48% .08 180)',
    goal_check:     'oklch(50% .10 120)',
    insight_offer:  'var(--accent)',
  }[q.kind] || 'var(--text-3)';

  const isInsightOffer = q.kind === 'insight_offer';

  return (
    <div style={{
      marginBottom:20, padding:'16px 20px',
      border:'1px solid var(--border-2)', borderRadius:10,
      background:'var(--nav-bg)',
    }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
        <MonoBadge color={kindColor}>{kindLabel}</MonoBadge>
        {monoLabel(relTime(q.created_at), undefined, { marginLeft:4 })}
      </div>

      <p style={{ fontFamily:'var(--font-b)', fontSize:13, color:'var(--text)', marginBottom:12 }}>
        {q.prompt_text}
      </p>

      {isInsightOffer && (
        <p style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)',
          marginBottom:12, fontStyle:'italic' }}>
          Note: clustering is word-overlap based — verify the suggested name makes sense.
        </p>
      )}

      {q.atoms && q.atoms.length > 0 && (
        <div style={{ marginBottom:16 }}>
          {q.atoms.map((a, i) => (
            <div key={a.id} style={{
              padding:'8px 12px', marginBottom:6,
              background:'var(--thread-bg)', borderRadius:6,
              display:'flex', alignItems:'center', justifyContent:'space-between', gap:12,
            }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text)', flex:1 }}>
                {a.text}
              </span>
              {q.atoms.length >= 2 && !isInsightOffer && (
                <GhostBtn onClick={() => onResolve(q.id, i===0?'confirm_a':'confirm_b', a.id)}>
                  This one
                </GhostBtn>
              )}
            </div>
          ))}
        </div>
      )}

      {isInsightOffer && renaming && (
        <div style={{ display:'flex', gap:8, marginBottom:12, alignItems:'center' }}>
          <input
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder="Timeline name…"
            style={{ fontFamily:'var(--font-m)', fontSize:12, flex:1,
              padding:'6px 10px', border:'1px solid var(--border-2)', borderRadius:6,
              background:'var(--thread-bg)', color:'var(--text)' }}
          />
          <GhostBtn onClick={() => {
            if (newName.trim()) {
              onResolve(q.id, 'accept_named', null, newName.trim());
              setRenaming(false);
            }
          }}>Accept</GhostBtn>
          <GhostBtn onClick={() => setRenaming(false)}>Cancel</GhostBtn>
        </div>
      )}

      <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
        {!isInsightOffer && q.atoms && q.atoms.length >= 2 && (
          <>
            <GhostBtn onClick={() => onResolve(q.id, 'both_true')}>Both true</GhostBtn>
            <GhostBtn onClick={() => onResolve(q.id, 'neither')}>Neither</GhostBtn>
          </>
        )}
        {isInsightOffer && !renaming && (
          <GhostBtn onClick={() => { setRenaming(true); setNewName(''); }}
            style={{ color:'var(--accent)', borderColor:'var(--accent-bd)' }}>
            Group &amp; name
          </GhostBtn>
        )}
        <GhostBtn onClick={() => onResolve(q.id, 'dismiss')}>
          {isInsightOffer ? 'Not now' : 'Dismiss'}
        </GhostBtn>
      </div>
    </div>
  );
}

// ── Goals tab ───────────────────────────────────────────────────────────────
function GoalsTab({ goals }) {
  if (!goals || goals.length === 0) {
    return (
      <div style={{ padding:'56px', textAlign:'center' }}>
        <p style={{ fontFamily:'var(--font-b)', fontSize:15, color:'var(--text-2)', fontStyle:'italic' }}>
          No goals or aspirations yet
        </p>
        <p style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)', marginTop:8 }}>
          Goals are extracted from phrases like "I want to…" or "I'm planning to…"
        </p>
      </div>
    );
  }

  return (
    <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>
      <div style={{ maxWidth:760, margin:'0 auto', padding:'32px 40px' }}>
        <SectionLabel right={`${goals.length} active`} style={{ marginBottom:20 }}>Goals & Aspirations</SectionLabel>
        {goals.map((g, i) => {
          const color = MODALITY_COLORS[g.modality] || 'var(--text-3)';
          return (
            <div key={g.id||i}>
              <div style={{ padding:'10px 0 12px', display:'flex', gap:16 }}>
                <div style={{ width:1.5, background:color, opacity:.35, borderRadius:1, flexShrink:0 }}/>
                <div style={{ flex:1 }}>
                  <p style={{ fontFamily:'var(--font-b)', fontSize:14.5, lineHeight:1.72,
                    color:'var(--text)', marginBottom:4 }}>{g.text}</p>
                  <div style={{ display:'flex', gap:10 }}>
                    {monoLabel(g.modality || 'goal', color)}
                    <span style={{ fontFamily:'var(--font-m)', fontSize:9.5, color:'var(--text-3)' }}>
                      · {relTime(g.timestamp)}
                    </span>
                  </div>
                </div>
              </div>
              {i < goals.length-1 && <Rule/>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Timelines tab ────────────────────────────────────────────────────────────
function TimelinesTab({ tier }) {
  const [strands, setStrands] = useState([]);
  const [selectedStrand, setSelectedStrand] = useState(null);
  const [strandData, setStrandData] = useState(null);
  const [loadingStrand, setLoadingStrand] = useState(false);
  const [basicTimeline, setBasicTimeline] = useState(null);
  const [filterFrom, setFilterFrom] = useState(0);

  useEffect(() => {
    if (tier === 'prescient') {
      fetch('/api/memory/strands').then(r => r.ok ? r.json() : null).then(d => {
        if (d) setStrands(d.strands || []);
      });
    } else {
      // Living: basic predicate chain list
      fetch('/api/memory/timeline').then(r => r.ok ? r.json() : null).then(d => {
        if (d) setBasicTimeline(d);
      });
    }
  }, [tier]);

  async function loadStrand(id) {
    setSelectedStrand(id);
    setLoadingStrand(true);
    const r = await fetch(`/api/memory/timeline?strand=${id}`);
    const d = await r.json();
    setStrandData(d);
    setFilterFrom(d.span?.from || 0);
    setLoadingStrand(false);
  }

  if (tier === 'living') {
    return (
      <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>
        <div style={{ maxWidth:760, margin:'0 auto', padding:'32px 40px' }}>
          <SectionLabel style={{ marginBottom:20 }}>Timelines</SectionLabel>
          {!basicTimeline ? (
            <Pulse size={8}/>
          ) : (
            Object.entries(basicTimeline.predicates || {}).map(([pred, chain]) => (
              <BasicChain key={pred} predicate={pred} chain={chain}/>
            ))
          )}
        </div>
      </div>
    );
  }

  // Prescient: strand lanes
  return (
    <div style={{ display:'flex', height:'100%', overflow:'hidden' }}>
      {/* Strand sidebar */}
      <div style={{ width:180, borderRight:'1px solid var(--border)', overflowY:'auto',
        background:'var(--nav-bg)', flexShrink:0, padding:'20px 16px' }}>
        {monoLabel('Strands', undefined, { marginBottom:12, display:'block' })}
        {strands.map(s => (
          <button key={s.id} onClick={() => loadStrand(s.id)} style={{
            display:'block', width:'100%', textAlign:'left',
            padding:'8px 10px', borderRadius:6, marginBottom:4, cursor:'pointer',
            background: selectedStrand===s.id ? 'var(--accent-bg)' : 'transparent',
            border: selectedStrand===s.id ? '1px solid var(--accent-bd)' : '1px solid transparent',
          }}>
            <div style={{ fontFamily:'var(--font-m)', fontSize:10,
              letterSpacing:'.08em', textTransform:'uppercase',
              color: selectedStrand===s.id ? 'var(--accent)' : 'var(--text-2)' }}>
              {s.name}
            </div>
            <div style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)', marginTop:2 }}>
              {s.atom_count} fact{s.atom_count!==1?'s':''}
            </div>
          </button>
        ))}
      </div>

      {/* Strand content */}
      <div style={{ flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
        {!selectedStrand ? (
          <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center' }}>
            <p style={{ fontFamily:'var(--font-b)', fontSize:14, color:'var(--text-3)', fontStyle:'italic' }}>
              Select a strand to view its timeline
            </p>
          </div>
        ) : loadingStrand ? (
          <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center' }}>
            <Pulse size={8}/>
          </div>
        ) : strandData ? (
          <StrandLane
            data={strandData}
            filterFrom={filterFrom}
            onFilterChange={setFilterFrom}
          />
        ) : null}
      </div>
    </div>
  );
}

function BasicChain({ predicate, chain }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginBottom:16 }}>
      <button onClick={() => setOpen(o => !o)} style={{
        display:'flex', alignItems:'center', gap:10, width:'100%',
        padding:'8px 0', cursor:'pointer',
      }}>
        {monoLabel(predicate)}
        <span style={{ color:'var(--text-3)', fontSize:10, marginLeft:'auto' }}>
          {chain.length} version{chain.length!==1?'s':''}
        </span>
        <span style={{ color:'var(--text-3)', fontSize:10 }}>{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div style={{ paddingLeft:16, borderLeft:'1.5px solid var(--bar)' }}>
          {chain.map((atom, i) => (
            <div key={atom.id} style={{ padding:'6px 0 8px', borderBottom:'1px solid var(--rule)' }}>
              <p style={{ fontFamily:'var(--font-b)', fontSize:13, color:'var(--text)' }}>
                {atom.text}
              </p>
              <div style={{ display:'flex', gap:8, marginTop:4 }}>
                {monoLabel(fmtDate(atom.valid_from || atom.created_at))}
                {atom.status !== 'active' && (
                  <MonoBadge color="var(--text-3)">{atom.status}</MonoBadge>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StrandLane({ data, filterFrom, onFilterChange }) {
  const chains = data.chains || {};
  const span = data.span || {};
  const spanFrom = span.from || 0;
  const spanTo = span.to || Math.floor(Date.now()/1000);
  const [hovered, setHovered] = useState(null);

  const allAtoms = Object.values(chains).flat();
  const range = spanTo - spanFrom || 1;

  return (
    <div style={{ flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
      {/* Header */}
      <div style={{ padding:'16px 24px', borderBottom:'1px solid var(--border)',
        background:'var(--nav-bg)', display:'flex', alignItems:'center', gap:12 }}>
        <span style={{ fontFamily:'var(--font-d)', fontSize:22, fontStyle:'italic',
          color:'var(--text)' }}>{data.name || data.strand}</span>
        {monoLabel(`${allAtoms.length} facts`, undefined, { marginLeft:'auto' })}
      </div>

      {/* Lanes */}
      <div className="scroll" style={{ flex:1, padding:'24px' }}>
        {Object.entries(chains).map(([key, chain]) => {
          const [subj, pred] = key.split(':');
          const visible = chain.filter(a => {
            const ts = a.valid_from || a.created_at || 0;
            return ts >= filterFrom;
          });
          if (!visible.length) return null;
          return (
            <div key={key} style={{ marginBottom:32 }}>
              {/* Lane label */}
              <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:8 }}>
                {monoLabel(pred || key, undefined, { fontSize:9 })}
                {subj && subj !== 'user' && (
                  <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)' }}>
                    · {subj}
                  </span>
                )}
              </div>
              {/* Chain as vertical list */}
              <div style={{ paddingLeft:12, borderLeft:'1.5px solid var(--bar)' }}>
                {visible.map((atom, i) => (
                  <div key={atom.id} style={{
                    padding:'6px 0 8px',
                    borderBottom: i < visible.length-1 ? '1px solid var(--rule)' : 'none',
                    cursor:'pointer',
                  }} onMouseEnter={() => setHovered(atom.id)}
                     onMouseLeave={() => setHovered(null)}>
                    <div style={{ display:'flex', gap:8, alignItems:'baseline' }}>
                      <p style={{ fontFamily:'var(--font-b)', fontSize:13.5,
                        color: atom.status==='active' ? 'var(--text)' : 'var(--text-3)',
                        flex:1 }}>
                        {atom.text}
                      </p>
                      {monoLabel(fmtDate(atom.valid_from || atom.created_at), undefined,
                        { flexShrink:0 })}
                    </div>
                    {hovered===atom.id && atom.status && atom.status!=='active' && (
                      <MonoBadge color="var(--text-3)" style={{ marginTop:4 }}>
                        {atom.status}
                      </MonoBadge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Date filter scrubber */}
      {spanFrom < spanTo && (
        <div style={{ padding:'12px 24px', borderTop:'1px solid var(--border)',
          background:'var(--nav-bg)', display:'flex', alignItems:'center', gap:12 }}>
          {monoLabel('from')}
          <input
            type="range"
            min={spanFrom} max={spanTo} value={filterFrom}
            onChange={e => onFilterChange(Number(e.target.value))}
            style={{ flex:1, accentColor:'var(--accent)' }}
          />
          <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-2)',
            minWidth:80 }}>
            {new Date(filterFrom*1000).toLocaleDateString('en', {month:'short',year:'numeric'})}
          </span>
          <GhostBtn onClick={() => onFilterChange(spanFrom)}>Reset</GhostBtn>
        </div>
      )}
    </div>
  );
}

// ── Inferred tab (prescient) ─────────────────────────────────────────────────
function InferredTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetch('/api/memory/inferred').then(r => r.ok ? r.json() : null).then(d => {
      setData(d);
      setLoading(false);
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  async function act(id, action) {
    await fetch(`/api/memory/inferred/${id}/${action}`, { method:'POST' });
    load();
  }

  if (loading) return (
    <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center' }}>
      <Pulse size={8}/>
    </div>
  );

  if (!data) return null;

  const { hypotheses=[], inferred_facts=[], scoreboard={} } = data;

  if (!hypotheses.length && !inferred_facts.length) {
    return (
      <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center',
        padding:48 }}>
        <div style={{ textAlign:'center' }}>
          <p style={{ fontFamily:'var(--font-d)', fontSize:20, fontStyle:'italic',
            color:'var(--text-2)', lineHeight:1.6 }}>
            Nothing yet. Hypotheses form weekly, and you'll always see them here before they're believed.
          </p>
          <p style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
            marginTop:24, letterSpacing:'.12em', textTransform:'uppercase' }}>
            INFERRED — SHOWN BEFORE BELIEVED
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>
      <div style={{ maxWidth:800, margin:'0 auto', padding:'32px 40px' }}>

        {/* Open Hypotheses */}
        {hypotheses.length > 0 && (
          <section style={{ marginBottom:40 }}>
            <SectionLabel right={`${hypotheses.length}`} style={{ marginBottom:20 }}>
              Open Hypotheses
            </SectionLabel>
            {hypotheses.map(h => (
              <HypothesisCard key={h.id} h={h}
                onConfirm={() => act(h.id,'confirm')}
                onReject={() => act(h.id,'reject')}
                onWatch={() => act(h.id,'watch')}/>
            ))}
          </section>
        )}

        {/* Inferred Facts */}
        {inferred_facts.length > 0 && (
          <section style={{ marginBottom:40 }}>
            <SectionLabel right={`${inferred_facts.length}`} style={{ marginBottom:20 }}>
              Inferred Facts
            </SectionLabel>
            {inferred_facts.map(f => (
              <InferredFactCard key={f.id} fact={f}
                onConfirm={() => act(f.id,'confirm')}
                onReject={() => act(f.id,'reject')}/>
            ))}
          </section>
        )}

        {/* Scoreboard */}
        {Object.keys(scoreboard).length > 0 && (
          <section style={{ marginBottom:40 }}>
            <SectionLabel style={{ marginBottom:20 }}>Scoreboard</SectionLabel>
            <ScoreboardTable scoreboard={scoreboard}/>
          </section>
        )}

        {/* Epistemic footer */}
        <p style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
          letterSpacing:'.12em', textTransform:'uppercase', textAlign:'center',
          paddingTop:24, borderTop:'1px solid var(--rule)' }}>
          INFERRED — SHOWN BEFORE BELIEVED
        </p>
      </div>
    </div>
  );
}

function HypothesisCard({ h, onConfirm, onReject, onWatch }) {
  const patternColor = {
    extrapolation:           'oklch(52% .10 40)',
    analogy_to_past_decision:'oklch(50% .10 200)',
    goal_implication:        'oklch(48% .10 120)',
    correlation_promotion:   'oklch(50% .10 280)',
  }[h.generation_pattern] || 'var(--text-3)';

  const obs = h.observations || [];
  const verdictGlyph = v => v==='supports' ? '+' : v==='refutes' ? '−' : '·';

  return (
    <Card style={{ marginBottom:16 }}>
      {/* Prediction */}
      <p style={{ fontFamily:'var(--font-b)', fontSize:14, color:'var(--text)',
        marginBottom:10, lineHeight:1.65 }}>
        {h.text}
      </p>

      {/* Meta row */}
      <div style={{ display:'flex', gap:10, flexWrap:'wrap', marginBottom:10 }}>
        {monoLabel(`prior ${Math.round((h.prior||0.5)*100)}%`)}
        <span style={{ color:'var(--text-3)', fontFamily:'var(--font-m)', fontSize:9 }}>·</span>
        {monoLabel(h.generation_pattern || 'extrapolation', patternColor)}
        {h.days_left !== null && h.days_left !== undefined && (
          <>
            <span style={{ color:'var(--text-3)', fontFamily:'var(--font-m)', fontSize:9 }}>·</span>
            {monoLabel(`${h.days_left}d left`, h.days_left < 14 ? 'oklch(52% .15 25)' : 'var(--text-3)')}
          </>
        )}
        {h.domain && (
          <>
            <span style={{ color:'var(--text-3)', fontFamily:'var(--font-m)', fontSize:9 }}>·</span>
            {monoLabel(h.domain)}
          </>
        )}
        {h.watched && (
          <Pulse size={6} style={{ marginLeft:4, alignSelf:'center' }}/>
        )}
      </div>

      {/* Evidence so far */}
      {obs.length > 0 && (
        <div style={{ marginBottom:12, paddingLeft:8,
          borderLeft:'1px solid var(--rule)' }}>
          {obs.slice(-5).map((o, i) => (
            <div key={i} style={{ display:'flex', gap:6, padding:'2px 0',
              borderBottom: i<obs.slice(-5).length-1 ? '1px solid var(--rule)' : 'none' }}>
              <span style={{ fontFamily:'var(--font-m)', fontSize:10,
                color: o.verdict_exp==='supports' ? 'oklch(48% .12 140)' :
                       o.verdict_dis==='supports' ? 'oklch(52% .15 25)' : 'var(--text-3)',
                width:12, flexShrink:0 }}>
                {o.verdict_exp==='supports' ? '+' : o.verdict_dis==='supports' ? '−' : '·'}
              </span>
              <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>
                {fmtDate(o.ts)} — {o.verdict_exp}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div style={{ display:'flex', gap:8 }}>
        <GhostBtn onClick={onConfirm} style={{ color:'oklch(48% .12 140)',
          borderColor:'oklch(48% .12 140)' }}>confirm</GhostBtn>
        <GhostBtn onClick={onReject} style={{ color:'oklch(52% .15 25)',
          borderColor:'oklch(52% .15 25)' }}>reject</GhostBtn>
        <GhostBtn onClick={onWatch}>keep watching</GhostBtn>
      </div>
    </Card>
  );
}

function InferredFactCard({ fact, onConfirm, onReject }) {
  return (
    <Card style={{ marginBottom:12 }}>
      <div style={{ display:'flex', alignItems:'flex-start', gap:10, marginBottom:8 }}>
        <MonoBadge color="var(--accent)">(INFERRED)</MonoBadge>
        <p style={{ fontFamily:'var(--font-b)', fontSize:14, color:'var(--text)',
          flex:1, lineHeight:1.65 }}>{fact.text}</p>
      </div>
      {fact.inferred_from_hypothesis && (
        <p style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)',
          marginBottom:10 }}>
          from hypothesis · confirmed by atom
        </p>
      )}
      {monoLabel(`${Math.round((fact.confidence||0)*100)}% confidence`, undefined, { marginBottom:10, display:'block' })}
      <div style={{ display:'flex', gap:8 }}>
        <GhostBtn onClick={onConfirm} style={{ color:'oklch(48% .12 140)',
          borderColor:'oklch(48% .12 140)' }}>confirm</GhostBtn>
        <GhostBtn onClick={onReject}>retract</GhostBtn>
      </div>
    </Card>
  );
}

function ScoreboardTable({ scoreboard }) {
  const entries = Object.entries(scoreboard);
  return (
    <div>
      {entries.map(([pattern, d]) => (
        <div key={pattern} style={{
          padding:'10px 0', borderBottom:'1px solid var(--rule)',
          opacity: d.suppressed ? 0.6 : 1,
        }}>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <span style={{
              fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-2)',
              flex:1,
              textDecoration: d.suppressed ? 'line-through' : 'none',
            }}>{pattern}</span>
            {monoLabel(`${d.confirmed}c / ${d.refuted}r`)}
            {d.precision !== null && d.precision !== undefined && (
              <span style={{ fontFamily:'var(--font-m)', fontSize:10,
                color: d.precision < 0.4 ? 'oklch(52% .15 25)' : 'oklch(48% .12 140)' }}>
                {Math.round(d.precision*100)}%
              </span>
            )}
          </div>
          {d.suppressed && (
            <p style={{ fontFamily:'var(--font-b)', fontSize:11, fontStyle:'italic',
              color:'var(--text-3)', marginTop:4 }}>
              suppressed — this reasoning move hasn't been reliable for you.
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Active memory panel (W3: quiet proactive surfacing) ───────────────────────
function ActiveMemoryPanel({ onTabSwitch }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);

  const load = useCallback(() => {
    fetch('/api/memory/surfacing').then(r => r.ok ? r.json() : null).then(d => {
      if (d) { setItems(d.items || []); setTotal(d.total || 0); }
    }).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  async function actInference(id, action) {
    await fetch(`/api/memory/review/${id}/${action}`, { method:'POST' });
    load();
  }

  if (!items.length) return null;  // quiet by default — nothing to say, say nothing

  const kindLabel = { contradiction:'Conflict', tension:'Tension' };

  return (
    <div style={{ marginBottom:24, padding:'16px 20px', background:'var(--accent-bg)',
      border:'1px solid var(--accent-bd)', borderRadius:10 }}>
      <div style={{ display:'flex', alignItems:'center', marginBottom:12 }}>
        <SectionLabel>Active memory</SectionLabel>
        {total > items.length && (
          <button onClick={() => onTabSwitch('review')} style={{ marginLeft:'auto', cursor:'pointer' }}>
            {monoLabel(`+${total - items.length} more in Review`, 'var(--accent-tx)')}
          </button>
        )}
      </div>
      {items.map(it => (
        <div key={it.id} style={{ padding:'10px 0', borderBottom:'1px solid var(--rule)' }}>
          <div style={{ display:'flex', alignItems:'baseline', gap:8, marginBottom:6 }}>
            {monoLabel(it.type === 'inference' ? (it.kind || 'inferred') : (kindLabel[it.type] || it.type),
              it.type === 'inference' ? MODALITY_COLORS.insight : 'oklch(52% .15 25)')}
            {it.confidence != null && monoLabel(`${Math.round(it.confidence*100)}%`)}
          </div>
          <p style={{ fontFamily:'var(--font-b)', fontSize:13, color:'var(--text)',
            lineHeight:1.55, marginBottom:8 }}>{it.text}</p>
          {it.type === 'inference' ? (
            <div style={{ display:'flex', gap:8 }}>
              <GhostBtn onClick={() => actInference(it.id, 'accept')}
                style={{ color:'var(--accent)', borderColor:'var(--accent-bd)' }}>Confirm</GhostBtn>
              <GhostBtn onClick={() => actInference(it.id, 'reject')}
                style={{ color:'oklch(52% .15 25)', borderColor:'oklch(70% .10 25)' }}>Reject</GhostBtn>
            </div>
          ) : (
            <GhostBtn onClick={() => onTabSwitch('review')}>Reconcile in Review</GhostBtn>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Overview tab ─────────────────────────────────────────────────────────────
function OverviewTab({ memories, questions, goals, tier, onTabSwitch }) {
  const openQCount = (questions.open || []).length;
  const inferredCount = tier === 'prescient' ? null : null; // loaded lazily
  const [inferredData, setInferredData] = useState(null);

  useEffect(() => {
    if (tier === 'prescient') {
      fetch('/api/memory/inferred').then(r => r.ok?r.json():null).then(setInferredData);
    }
  }, [tier]);

  const openHypCount = inferredData?.hypotheses?.length || 0;

  const totalPrecision = (() => {
    if (!inferredData?.scoreboard) return null;
    const vals = Object.values(inferredData.scoreboard)
      .filter(d => d.precision !== null && d.precision !== undefined);
    if (!vals.length) return null;
    return Math.round((vals.reduce((s,d) => s + d.precision, 0) / vals.length) * 100);
  })();

  const nEntries = Object.values(inferredData?.scoreboard||{})
    .reduce((s,d) => s + d.confirmed + d.refuted, 0);

  return (
    <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>
      <div style={{ maxWidth:900, margin:'0 auto', padding:'32px 40px' }}>

        {/* Header strip */}
        <div style={{ display:'flex', gap:16, flexWrap:'wrap', marginBottom:24,
          padding:'12px 20px', background:'var(--nav-bg)',
          border:'1px solid var(--border)', borderRadius:10 }}>
          {monoLabel(`${memories.length} fragments`)}
          <span style={{ color:'var(--border-2)' }}>·</span>
          {monoLabel(`${memories.filter(m=>m.pinned).length} pinned`)}
          {tier === 'prescient' && totalPrecision !== null && (
            <>
              <span style={{ color:'var(--border-2)' }}>·</span>
              {monoLabel(`inference ${totalPrecision}% (n=${nEntries})`, 'var(--accent)')}
            </>
          )}
        </div>

        {/* Active memory — quiet proactive surfacing (W3) */}
        <ActiveMemoryPanel onTabSwitch={onTabSwitch}/>

        {/* Card grid */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(300px,1fr))',
          gap:16 }}>
          {/* Recent activity */}
          <Card>
            <SectionLabel style={{ marginBottom:12 }}>Recent activity</SectionLabel>
            {memories.slice(0,5).map(m => (
              <div key={m.id} style={{ padding:'5px 0', borderBottom:'1px solid var(--rule)',
                display:'flex', gap:8, alignItems:'baseline' }}>
                <span style={{ fontFamily:'var(--font-b)', fontSize:12, color:'var(--text)',
                  flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                  {m.text}
                </span>
                {monoLabel(relTime(m.timestamp), undefined, { flexShrink:0 })}
              </div>
            ))}
            {memories.length === 0 && (
              <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)',
                fontStyle:'italic' }}>No memory yet.</p>
            )}
          </Card>

          {/* Review */}
          <Card onClick={() => onTabSwitch('review')} style={{ cursor:'pointer' }}>
            <SectionLabel right={openQCount > 0 ? `${openQCount} open` : ''} style={{ marginBottom:12 }}>
              Review
            </SectionLabel>
            {openQCount === 0 ? (
              <p style={{ fontFamily:'var(--font-b)', fontSize:13, color:'var(--text-2)',
                fontStyle:'italic' }}>Memory is coherent.</p>
            ) : (
              (questions.open||[]).slice(0,2).map(q => (
                <div key={q.id} style={{ padding:'6px 0', borderBottom:'1px solid var(--rule)' }}>
                  <p style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-2)' }}>
                    {q.prompt_text.slice(0,80)}{q.prompt_text.length>80?'…':''}
                  </p>
                </div>
              ))
            )}
          </Card>

          {/* Goals */}
          <Card onClick={() => onTabSwitch('goals')} style={{ cursor:'pointer' }}>
            <SectionLabel right={`${goals.length}`} style={{ marginBottom:12 }}>Goals</SectionLabel>
            {goals.slice(0,3).map(g => (
              <div key={g.id} style={{ padding:'6px 0', borderBottom:'1px solid var(--rule)',
                display:'flex', gap:8, alignItems:'baseline' }}>
                <p style={{ fontFamily:'var(--font-b)', fontSize:12, color:'var(--text)',
                  flex:1 }}>{g.text.slice(0,60)}{g.text.length>60?'…':''}</p>
                {monoLabel(relTime(g.timestamp), undefined, { flexShrink:0 })}
              </div>
            ))}
            {goals.length === 0 && (
              <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)',
                fontStyle:'italic' }}>No active goals.</p>
            )}
          </Card>

          {/* Inferred (prescient only) */}
          {tier === 'prescient' && (
            <Card onClick={() => onTabSwitch('inferred')} style={{ cursor:'pointer' }}>
              <SectionLabel right={openHypCount > 0 ? `${openHypCount} open` : ''} style={{ marginBottom:12 }}>
                Inferred knowledge
              </SectionLabel>
              {totalPrecision !== null ? (
                <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-2)' }}>
                  Inference accuracy — <strong style={{ color:'var(--accent)' }}>{totalPrecision}%</strong>
                  {nEntries > 0 ? ` (n=${nEntries})` : ''}
                </p>
              ) : (
                <p style={{ fontFamily:'var(--font-b)', fontSize:13, color:'var(--text-2)',
                  fontStyle:'italic' }}>
                  {openHypCount > 0
                    ? `${openHypCount} hypothesis${openHypCount!==1?'es':''} forming`
                    : 'Hypotheses form weekly.'}
                </p>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Constellation view (hand-rolled SVG, no physics) ─────────────────────────
const GLYPH_MAP = {
  factual:         '●',
  opinion:         '◈',
  desire:          '◇',
  plan:            '▷',
  self_perception: '◉',
  hypothetical:    '⬡',
  commitment:      '◼',
  hypothesis:      '⬡',
  insight:         '◎',
};

function ConstellationView({ strands, selectedId, onAtomClick }) {
  const containerRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [hovered, setHovered] = useState(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver(entries => {
      const e = entries[0].contentRect;
      setSize({ w: e.width, h: e.height });
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  const nodes = useMemo(() => {
    const { w, h } = size;
    const cx = w / 2, cy = h / 2;
    const sCount = strands.length;
    if (!sCount) return [];
    const sRadius = Math.min(w, h) * 0.30;
    const result = [];
    strands.forEach((strand, si) => {
      const sa = (2 * Math.PI * si / sCount) - Math.PI / 2;
      const sx = cx + sRadius * Math.cos(sa);
      const sy = cy + sRadius * Math.sin(sa);
      const atoms = strand.atoms || [];
      const aCount = atoms.length;
      const aRadius = Math.min(72, 20 + Math.sqrt(aCount) * 9);
      atoms.forEach((atom, ai) => {
        const aa = (2 * Math.PI * ai / Math.max(aCount, 1));
        result.push({
          id: atom.id, atom,
          x: sx + aRadius * Math.cos(aa),
          y: sy + aRadius * Math.sin(aa),
          color: strand.color || '#9A8A78',
        });
      });
    });
    return result;
  }, [strands, size]);

  const strandLabels = useMemo(() => {
    const { w, h } = size;
    const cx = w / 2, cy = h / 2;
    const sCount = strands.length;
    if (!sCount) return [];
    const sRadius = Math.min(w, h) * 0.30;
    return strands.map((strand, si) => {
      const sa = (2 * Math.PI * si / sCount) - Math.PI / 2;
      const atoms = strand.atoms || [];
      const aRadius = Math.min(72, 20 + Math.sqrt(atoms.length) * 9) + 20;
      return {
        id: strand.id,
        x: cx + sRadius * Math.cos(sa) + aRadius * Math.cos(sa),
        y: cy + sRadius * Math.sin(sa) + aRadius * Math.sin(sa),
        label: (strand.label || strand.name || '').toUpperCase().slice(0, 16),
        color: strand.color || '#9A8A78',
      };
    });
  }, [strands, size]);

  const hoveredNode = hovered ? nodes.find(n => n.id === hovered) : null;

  return (
    <div ref={containerRef} style={{ flex: 1, position: 'relative',
      overflow: 'hidden', background: 'var(--thread-bg)' }}>
      <svg width={size.w} height={size.h} style={{ display: 'block' }}>
        {strandLabels.map(sl => (
          <text key={sl.id} x={sl.x} y={sl.y}
            textAnchor="middle" dominantBaseline="middle"
            style={{ fontFamily: 'var(--font-m)', fontSize: 9, fill: sl.color,
              letterSpacing: '.10em', pointerEvents: 'none' }}>
            {sl.label}
          </text>
        ))}
        {nodes.map(n => {
          const isSelected = n.id === selectedId;
          const isHovered = n.id === hovered;
          const dimmed = n.atom.confidence != null && n.atom.confidence < 0.4;
          const r = isSelected ? 10 : isHovered ? 9 : 7;
          return (
            <g key={n.id}
              onClick={() => onAtomClick(n.atom)}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: 'pointer' }}>
              <circle cx={n.x} cy={n.y} r={r}
                fill={n.color}
                opacity={dimmed ? 0.3 : isSelected || isHovered ? 0.9 : 0.65}
                stroke={isSelected ? 'var(--accent)' : 'none'}
                strokeWidth={1.5}/>
              <text x={n.x} y={n.y} textAnchor="middle" dominantBaseline="central"
                style={{ fontSize: isSelected ? 9 : 7, fill: 'white',
                  pointerEvents: 'none', userSelect: 'none',
                  fontFamily: 'sans-serif' }}>
                {GLYPH_MAP[n.atom.modality] || '●'}
              </text>
            </g>
          );
        })}
      </svg>

      {hoveredNode && (
        <div style={{
          position: 'absolute',
          left: Math.min(hoveredNode.x + 14, size.w - 290),
          top: Math.max(hoveredNode.y - 10, 4),
          background: 'var(--surface)', border: '1px solid var(--border-2)',
          borderRadius: 6, padding: '6px 10px', maxWidth: 280,
          pointerEvents: 'none', zIndex: 10,
        }}>
          <p style={{ fontFamily: 'var(--font-b)', fontSize: 12, color: 'var(--text)',
            lineHeight: 1.5, margin: 0 }}>{hoveredNode.atom.text}</p>
          {hoveredNode.atom.predicate && (
            <div style={{ marginTop: 4 }}>
              {monoLabel(hoveredNode.atom.predicate)}
            </div>
          )}
        </div>
      )}

      {strands.length === 0 && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center' }}>
          <p style={{ fontFamily: 'var(--font-b)', fontSize: 14, color: 'var(--text-3)',
            fontStyle: 'italic' }}>No memories to map yet.</p>
        </div>
      )}
    </div>
  );
}

// ── Main surface ──────────────────────────────────────────────────────────────
function MemorySurface() {
  const [tab, setTab] = useState('fragments');
  const [memories, setMemories] = useState([]);
  const [questions, setQuestions] = useState({ open:[], resolved:[] });
  const [goals, setGoals] = useState([]);
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reviewBadge, setReviewBadge] = useState(0);
  const [tier, setTier] = useState('living');

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch('/api/memory').then(r=>r.ok?r.json():{memories:[]}).catch(()=>({memories:[]})),
      fetch('/api/skills').then(r=>r.ok?r.json():{skills:[]}).catch(()=>({skills:[]})),
      fetch('/api/memory/questions').then(r=>r.ok?r.json():{open:[],resolved:[]}).catch(()=>({open:[],resolved:[]})),
      fetch('/api/memory/goals').then(r=>r.ok?r.json():{goals:[]}).catch(()=>({goals:[]})),
      fetch('/api/config').then(r=>r.ok?r.json():null).catch(()=>null),
      fetch('/api/memory/review').then(r=>r.ok?r.json():{counts:{}}).catch(()=>({counts:{}})),
    ]).then(([memData, skillData, qData, goalData, cfgData, revData]) => {
      setMemories(memData.memories || memData.memory || []);
      setSkills(skillData.skills || []);
      setQuestions(qData);
      setReviewBadge((qData.open||[]).length + ((revData.counts||{}).total||0));
      setGoals(goalData.goals || []);
      // Tier comes from app_config; the /config endpoint doesn't include it, so
      // try the dedicated settings route if available
      setLoading(false);
    });
    // Load tier from the dedicated endpoint (always returns a safe default; no 404)
    fetch('/api/memory/tier').then(r=>r.ok?r.json():null).then(d => {
      if (d && d.depth) setTier(d.depth);
    }).catch(() => {});
  }, []);

  // Silent background poll — only the three endpoints that change after extraction
  const refreshDynamic = useCallback(() => {
    if (document.visibilityState === 'hidden') return;
    Promise.all([
      fetch('/api/memory').then(r=>r.ok?r.json():{memories:[]}).catch(()=>({memories:[]})),
      fetch('/api/memory/questions').then(r=>r.ok?r.json():{open:[],resolved:[]}).catch(()=>({open:[],resolved:[]})),
      fetch('/api/memory/goals').then(r=>r.ok?r.json():{goals:[]}).catch(()=>({goals:[]})),
      fetch('/api/memory/review').then(r=>r.ok?r.json():{counts:{}}).catch(()=>({counts:{}})),
    ]).then(([memData, qData, goalData, revData]) => {
      setMemories(memData.memories || memData.memory || []);
      setQuestions(qData);
      setReviewBadge((qData.open||[]).length + ((revData.counts||{}).total||0));
      setGoals(goalData.goals || []);
    }).catch(() => {});
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Poll every 6 seconds while the memory surface is mounted
  useEffect(() => {
    const id = setInterval(refreshDynamic, 6000);
    return () => clearInterval(id);
  }, [refreshDynamic]);

  // Snap to a valid tab for the current tier
  useEffect(() => {
    const valid = TIER_TABS[tier] || TIER_TABS.living;
    if (!valid.includes(tab)) {
      setTab(valid[0]);
    }
  }, [tier]);

  async function handleResolve(questionId, choice, atomId, detail) {
    await fetch(`/api/memory/questions/${questionId}/resolve`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({choice, atom_id:atomId, detail}),
    });
    loadData();
  }

  async function toggleSkill(sk) {
    const newStatus = sk.status==='active' ? 'inactive' : 'active';
    setSkills(prev => prev.map(s => s.id===sk.id ? {...s,status:newStatus} : s));
    try { await fetch(`/api/skills/${sk.id}/toggle`, {method:'POST'}); }
    catch { setSkills(prev => prev.map(s => s.id===sk.id ? {...s,status:sk.status} : s)); }
  }

  const currentTierRank = TIER_ORDER[tier] ?? 1;
  const allTabs = ['overview','fragments','review','goals','timelines','inferred','skills'];

  function tabAllowed(t) {
    const minTier = TAB_MIN_TIER[t] || 'essential';
    return currentTierRank >= (TIER_ORDER[minTier] ?? 0);
  }

  if (loading) return (
    <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', opacity:.4 }}>
      <Pulse size={10}/>
    </div>
  );

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', overflow:'hidden' }}
      className="surface-enter">

      {/* Tab bar */}
      <div style={{ height:48, flexShrink:0, background:'var(--nav-bg)',
        borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center',
        justifyContent:'center', padding:'0 20px', gap:0, overflowX:'auto' }}>
        {allTabs.map(t => {
          const allowed = tabAllowed(t);
          const on = tab === t;
          const label = TAB_LABELS[t] || t.charAt(0).toUpperCase()+t.slice(1);
          const badge = t==='review' ? reviewBadge : 0;
          if (!allowed) return null; // hide above-tier tabs entirely
          return (
            <button key={t} onClick={() => setTab(t)} style={{
              padding:'0 14px', margin:'0 2px',
              fontFamily:'var(--font-b)', fontSize:13, fontStyle:'italic',
              textAlign:'center',
              color: on ? 'var(--text)' : 'var(--text-2)',
              borderBottom:`1.5px solid ${on ? 'var(--accent)' : 'transparent'}`,
              paddingBottom:10, marginBottom:-1,
              cursor:'pointer', transition:'color var(--t), border-color var(--t)',
              whiteSpace:'nowrap', flexShrink:0, position:'relative',
            }}>
              {label}
              {badge > 0 && (
                <span style={{
                  position:'absolute', top:4, right:0,
                  width:14, height:14, borderRadius:'50%',
                  background:'var(--accent)', color:'#fff',
                  fontFamily:'var(--font-m)', fontSize:8, fontWeight:700,
                  display:'flex', alignItems:'center', justifyContent:'center',
                }}>{badge>9?'9+':badge}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div style={{ flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
        {tab==='overview' && (
          <OverviewTab
            memories={memories} questions={questions} goals={goals}
            tier={tier} onTabSwitch={setTab}/>
        )}
        {tab==='fragments' && <GardenTab/>}
        {tab==='review' && (
          <ReviewTab questions={questions} onResolve={handleResolve} onChange={loadData}/>
        )}
        {tab==='goals' && <GoalsTab goals={goals}/>}
        {tab==='timelines' && <TimelinesTab tier={tier}/>}
        {tab==='inferred' && <InferredTab/>}
        {tab==='skills' && (
          <SkillsTab skills={skills} onToggle={toggleSkill}/>
        )}
      </div>
    </div>
  );
}

// ── Skills tab ─────────────────────────────────────────────────────────────
function SkillsTab({ skills, onToggle }) {
  return (
    <div className="scroll" style={{ flex:1, background:'var(--thread-bg)' }}>
      <div style={{ maxWidth:760, margin:'0 auto', padding:'32px 40px' }}>
        <SectionLabel
          right={`${skills.filter(s=>s.status==='active'||s.enabled!==false).length} of ${skills.length}`}
          style={{ marginBottom:16 }}>
          Skills
        </SectionLabel>
        {skills.length===0 && (
          <p style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', fontStyle:'italic' }}>
            No skills found.
          </p>
        )}
        {skills.map((sk,i) => {
          const isOn = sk.enabled!==false && sk.status!=='inactive';
          return (
            <div key={sk.id||i}>
              <div style={{ display:'flex', alignItems:'center', gap:16, padding:'12px 0' }}>
                <div style={{ flex:1 }}>
                  <div style={{ display:'flex', alignItems:'baseline', gap:10, marginBottom:3 }}>
                    <span style={{ fontFamily:'var(--font-b)', fontSize:14.5, fontStyle:'italic',
                      color: isOn ? 'var(--text)' : 'var(--text-q)' }}>{sk.name}</span>
                    {sk.category && monoLabel(sk.category, undefined, { marginLeft:4 })}
                  </div>
                  <span style={{ fontFamily:'var(--font-m)', fontSize:10.5, color:'var(--text-3)' }}>
                    {sk.description || sk.when_to_use || ''}
                  </span>
                </div>
                <Toggle on={isOn} onToggle={() => onToggle(sk)}/>
              </div>
              {i<skills.length-1 && <Rule/>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

window.V2Memory = { MemorySurface };
