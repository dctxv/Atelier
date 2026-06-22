/* ====== Prescient Memory Surface — Part 1 ====== */
/* Design language: parchment palette, Cormorant italic display,
   Lora prose, IBM Plex Mono 9px/.14em uppercase labels, 1px warm borders,
   no shadows, 10-12px radii, 160ms ease transitions, fadeUp entry.       */
const { useState, useEffect, useCallback, useRef } = React;

// ── Tier config ────────────────────────────────────────────────────────────
const TIER_ORDER = { essential: 0, living: 1, prescient: 2 };

const TIER_TABS = {
  essential:  ['fragments'],
  living:     ['overview', 'fragments', 'graph', 'review', 'goals', 'timelines'],
  prescient:  ['overview', 'fragments', 'graph', 'review', 'goals', 'timelines', 'inferred'],
};
const TAB_LABELS = {
  overview: 'Overview', fragments: 'Memory', graph: 'Graph', review: 'Review',
  goals: 'Goals', timelines: 'Timelines', inferred: 'Inferred',
};
const TAB_MIN_TIER = {
  overview: 'living', fragments: 'essential', graph: 'living', review: 'living',
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

// ── Fragments tab ───────────────────────────────────────────────────────────
function FragmentsTab({ memories }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [includeFaded, setIncludeFaded] = useState(false);

  const CATEGORIES = ['all','functional','multi_valued','comparative','experiential','attribute'];

  const filtered = memories.filter(m => {
    if (!includeFaded && m.confidence !== null && m.confidence !== undefined && m.confidence < 0.4)
      return false;
    if (filter !== 'all' && m.predicate_category !== filter) return false;
    if (query) {
      const q = query.toLowerCase();
      if (!(m.text||'').toLowerCase().includes(q) &&
          !(m.subject||'').toLowerCase().includes(q) &&
          !(m.predicate||'').toLowerCase().includes(q)) return false;
    }
    return true;
  });

  // Group by subject
  const bySubject = {};
  filtered.forEach(m => {
    const s = m.subject || '_legacy';
    if (!bySubject[s]) bySubject[s] = [];
    bySubject[s].push(m);
  });

  const pinnedCount = memories.filter(m => m.pinned).length;
  const fadedCount = memories.filter(m =>
    m.confidence !== null && m.confidence !== undefined && m.confidence < 0.4).length;

  return (
    <div style={{ flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
      {/* Header strip */}
      <div style={{ padding:'12px 40px 0', borderBottom:'1px solid var(--border)',
        background:'var(--nav-bg)', flexShrink:0 }}>
        <div style={{ display:'flex', alignItems:'center', gap:16, marginBottom:12 }}>
          {monoLabel(`${memories.length} fragments`, 'var(--text-3)')}
          <span style={{ color:'var(--border-2)' }}>·</span>
          {monoLabel(`${pinnedCount} pinned`, 'var(--text-3)')}
          {fadedCount > 0 && <>
            <span style={{ color:'var(--border-2)' }}>·</span>
            {monoLabel(`${fadedCount} faded`, 'var(--text-3)')}
          </>}
          <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:8,
            padding:'3px 10px', border:'1px solid var(--border-2)', borderRadius:8,
            background:'var(--thread-bg)' }}>
            <Ico n="search" size={12} color="var(--text-3)"/>
            <input value={query} onChange={e=>setQuery(e.target.value)}
              placeholder="Search…"
              style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text)', width:120 }}/>
          </div>
        </div>
        {/* Filter pills */}
        <div style={{ display:'flex', gap:6, alignItems:'center', paddingBottom:10 }}>
          {CATEGORIES.map(c => (
            <button key={c} onClick={() => setFilter(c)} style={{
              fontFamily:'var(--font-m)', fontSize:10,
              color: filter===c ? 'var(--accent)' : 'var(--text-3)',
              fontWeight: filter===c ? 600 : 400,
              cursor:'pointer', padding:'2px 8px',
              border: filter===c ? '1px solid var(--accent-bd)' : '1px solid transparent',
              borderRadius:4, background: filter===c ? 'var(--accent-bg)' : 'transparent',
            }}>{c}</button>
          ))}
          <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:6 }}>
            {monoLabel('faded', 'var(--text-3)')}
            <Toggle on={includeFaded} onToggle={() => setIncludeFaded(v => !v)}/>
          </div>
        </div>
      </div>

      <div className="scroll" style={{ flex:1, background:'var(--thread-bg)', padding:'24px 40px' }}>
        {filtered.length === 0 && (
          <p style={{ fontFamily:'var(--font-m)', fontSize:12, color:'var(--text-3)', fontStyle:'italic' }}>
            {memories.length === 0 ? 'No memories yet — they build up as you chat.' : 'No matches.'}
          </p>
        )}

        {Object.entries(bySubject).map(([subj, atoms]) => (
          <SubjectBed key={subj} subject={subj} atoms={atoms}/>
        ))}
      </div>
    </div>
  );
}

function SubjectBed({ subject, atoms }) {
  const [expanded, setExpanded] = useState(false);
  const PREVIEW = 6;
  const shown = expanded ? atoms : atoms.slice(0, PREVIEW);

  const subjectLabel = subject === '_legacy' ? 'Other' : subject.toUpperCase();

  return (
    <div style={{ marginBottom:24 }}>
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10, cursor:'pointer' }}
           onClick={() => setExpanded(e => !e)}>
        <div style={{ width:1.5, height:16, background:'var(--bar)', borderRadius:1 }}/>
        {monoLabel(subjectLabel)}
        <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)', marginLeft:'auto' }}>
          {atoms.length}
        </span>
        <span style={{ color:'var(--text-3)', fontSize:10 }}>{expanded ? '▴' : '▾'}</span>
      </div>

      {shown.map((m, i) => (
        <AtomRow key={m.id||i} atom={m}/>
      ))}

      {!expanded && atoms.length > PREVIEW && (
        <button onClick={() => setExpanded(true)} style={{
          fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)', cursor:'pointer',
          padding:'4px 0', marginTop:4,
        }}>▸ show all {atoms.length}</button>
      )}
    </div>
  );
}

function AtomRow({ atom: m }) {
  const faded = (m.confidence !== null && m.confidence !== undefined && m.confidence < 0.4);
  const col = MODALITY_COLORS[m.modality] || 'var(--bar)';
  const isInferred = m.modality === 'insight';

  return (
    <div style={{
      display:'flex', gap:12, padding:'8px 0',
      borderBottom:'1px solid var(--rule)',
      opacity: faded ? 0.5 : 1,
    }}>
      <div style={{ width:1.5, background:col, borderRadius:1, flexShrink:0, alignSelf:'stretch' }}/>
      <div style={{ flex:1, minWidth:0 }}>
        <p style={{ fontFamily:'var(--font-b)', fontSize:14, lineHeight:1.65,
          color:'var(--text)', marginBottom:4 }}>
          {m.text}
          {isInferred && <span style={{ fontFamily:'var(--font-m)', fontSize:9,
            color:'var(--accent)', marginLeft:8, opacity:.7 }}>(inferred)</span>}
        </p>
        <div style={{ display:'flex', gap:8, flexWrap:'wrap', alignItems:'center' }}>
          {monoLabel(relTime(m.timestamp))}
          {m.predicate && (
            <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)',
              padding:'1px 5px', border:'1px solid var(--border)', borderRadius:3 }}>
              {m.predicate}
            </span>
          )}
          {m.modality && m.modality !== 'factual' && (
            <span style={{ fontFamily:'var(--font-m)', fontSize:9,
              color: MODALITY_COLORS[m.modality] || 'var(--text-3)',
              padding:'1px 5px', border:`1px solid ${MODALITY_COLORS[m.modality] || 'var(--border)'}`,
              borderRadius:3 }}>
              {m.modality}
            </span>
          )}
          {m.confidence !== null && m.confidence !== undefined && m.confidence < 0.7 && (
            <span style={{ fontFamily:'var(--font-m)', fontSize:9, color:'var(--text-3)' }}>
              {Math.round(m.confidence * 100)}%
            </span>
          )}
          {m.pinned && <span style={{ color:'var(--accent)', fontSize:11 }}>📌</span>}
        </div>
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

// ── Graph tab — "Constellation Map" ──────────────────────────────────────────
/* Palette-correct strand colours: desaturated earth tones that sit with the
   parchment / mono palettes rather than the saturated primaries of the original
   proposal. Node SHAPE encodes the real modality enum; SIZE encodes salience;
   border/opacity encode confidence. fcose runs once per view — no continuous
   physics. */
const STRAND_COLORS = {
  career:        '#6E7E8A',  // slate
  places:        '#7C8A6E',  // sage
  relationships: '#A8756B',  // clay
  projects:      '#8A7A5A',  // brass
  health:        '#9A6B6B',  // muted rose-brown
  creative:      '#7E6E8A',  // muted violet
  _unstranded:   '#9A8A78',  // taupe
};
const MODALITY_SHAPE = {
  factual:         'ellipse',
  opinion:         'diamond',
  desire:          'triangle',
  plan:            'round-rectangle',
  self_perception: 'star',
  hypothetical:    'hexagon',
  commitment:      'rectangle',
  hypothesis:      'hexagon',
  insight:         'pentagon',
};
const SHAPE_GLYPH = {
  ellipse:'●', triangle:'▲', 'round-rectangle':'▮', diamond:'◆',
  hexagon:'⬡', star:'★', rectangle:'▬', pentagon:'⬠',
};

let _fcoseRegistered = false;
function ensureFcose() {
  if (_fcoseRegistered) return true;
  if (window.cytoscape && window.cytoscapeFcose) {
    try { window.cytoscape.use(window.cytoscapeFcose); _fcoseRegistered = true; }
    catch (e) { /* already registered */ _fcoseRegistered = true; }
  }
  return _fcoseRegistered;
}

function buildElements(data, selStrand, accent) {
  const strands = [
    ...data.strands,
    { id:'_unstranded', name:'Misc', atoms: data.unstranded || [] },
  ].filter(s => (s.atoms || []).length > 0);

  const els = [];
  if (!selStrand) {
    strands.forEach(s => {
      const count = s.atoms.length;
      els.push({ data:{
        id:'s_'+s.id, kind:'strand', sid:s.id, label:s.name,
        color: STRAND_COLORS[s.id] || STRAND_COLORS._unstranded,
        size: 46 + Math.sqrt(count) * 14,
      }});
    });
    return els;
  }

  const s = strands.find(x => x.id === selStrand);
  if (!s) return els;
  const color = STRAND_COLORS[s.id] || STRAND_COLORS._unstranded;
  els.push({ data:{ id:'s_'+s.id, kind:'center', sid:s.id, label:s.name, color, size:44 }});
  s.atoms.forEach(a => {
    const sal  = (a.salience == null ? 1 : a.salience);
    const conf = (a.confidence == null ? 1 : a.confidence);
    els.push({ data:{
      id: a.id, kind:'atom', atom: a, color,
      shape: MODALITY_SHAPE[a.modality] || 'ellipse',
      size: 14 + Math.min(sal, 5) * 5,
      op: 0.30 + conf * 0.55,
      bw: a.pinned ? 2.5 : 1,
      bc: a.pinned ? accent : color,
      short: (a.text || '').slice(0, 22),
    }});
    els.push({ data:{ id:'e_'+a.id, source:'s_'+s.id, target:a.id, op: 0.12 + conf * 0.4 }});
  });
  return els;
}

function GraphTab() {
  const [data, setData] = useState(null);
  const [libReady, setLibReady] = useState(typeof window !== 'undefined' && !!window.cytoscape);
  const [libFailed, setLibFailed] = useState(false);
  const [selectedStrand, setSelectedStrand] = useState(null);
  const [selectedAtom, setSelectedAtom] = useState(null);
  const [omniOpen, setOmniOpen] = useState(false);
  const [omniQuery, setOmniQuery] = useState('');

  const cyEl = useRef(null);
  const cyRef = useRef(null);
  const pendingFocus = useRef(null);
  const omniInput = useRef(null);

  // Load graph payload
  useEffect(() => {
    fetch('/api/memory/graph').then(r => r.ok ? r.json() : null)
      .then(d => setData(d || { strands:[], unstranded:[] }))
      .catch(() => setData({ strands:[], unstranded:[] }));
  }, []);

  // Wait for the deferred Cytoscape CDN script
  useEffect(() => {
    if (window.cytoscape) { setLibReady(true); return; }
    let n = 0;
    const id = setInterval(() => {
      if (window.cytoscape) { setLibReady(true); clearInterval(id); }
      else if (++n > 50) { setLibFailed(true); clearInterval(id); }
    }, 200);
    return () => clearInterval(id);
  }, []);

  // Flat atom index for the omnibar (atom + its strand id)
  const atomIndex = (() => {
    if (!data) return [];
    const out = [];
    const seen = new Set();
    const push = (a, sid, sname) => {
      if (seen.has(a.id)) return;
      seen.add(a.id);
      out.push({ atom:a, strandId:sid, strandName:sname });
    };
    (data.strands || []).forEach(s => (s.atoms||[]).forEach(a => push(a, s.id, s.name)));
    (data.unstranded || []).forEach(a => push(a, '_unstranded', 'Misc'));
    return out;
  })();

  const omniResults = omniQuery.trim()
    ? atomIndex.filter(({ atom }) => {
        const q = omniQuery.toLowerCase();
        return (atom.text||'').toLowerCase().includes(q)
            || (atom.subject||'').toLowerCase().includes(q)
            || (atom.predicate||'').toLowerCase().includes(q);
      }).slice(0, 8)
    : [];

  function focusAtom(atomId) {
    const cy = cyRef.current;
    if (!cy) return;
    const node = cy.getElementById(atomId);
    if (!node || node.empty()) return;
    cy.animate({ center:{ eles:node }, zoom:1.6 }, { duration:480 });
    node.addClass('pulse');
    setTimeout(() => { if (node) node.removeClass('pulse'); }, 2400);
    setSelectedAtom(node.data('atom'));
  }

  function teleport(entry) {
    setOmniOpen(false);
    setOmniQuery('');
    if (selectedStrand === entry.strandId) {
      focusAtom(entry.atom.id);
    } else {
      pendingFocus.current = entry.atom.id;
      setSelectedStrand(entry.strandId);
    }
  }

  // Create the Cytoscape instance once
  useEffect(() => {
    if (!libReady || !data || !cyEl.current || cyRef.current) return;
    ensureFcose();
    const cs = getComputedStyle(document.documentElement);
    const v = k => cs.getPropertyValue(k).trim();
    const cText = v('--text'), cText3 = v('--text-3'), cAccent = v('--accent');

    const cy = window.cytoscape({
      container: cyEl.current,
      elements: [],
      minZoom: 0.2, maxZoom: 3, wheelSensitivity: 0.2,
      style: [
        { selector:'node[kind="strand"]', style:{
          'background-color':'data(color)', 'background-opacity':0.16,
          'border-width':1.5, 'border-color':'data(color)',
          'label':'data(label)', 'color':cText,
          'font-family':'IBM Plex Mono, monospace', 'font-size':10,
          'text-transform':'uppercase', 'text-valign':'center', 'text-halign':'center',
          'width':'data(size)', 'height':'data(size)', 'shape':'ellipse',
        }},
        { selector:'node[kind="center"]', style:{
          'background-color':'data(color)', 'background-opacity':0.26,
          'border-width':1.5, 'border-color':'data(color)',
          'label':'data(label)', 'color':cText,
          'font-family':'IBM Plex Mono, monospace', 'font-size':10,
          'text-transform':'uppercase', 'text-valign':'center', 'text-halign':'center',
          'width':'data(size)', 'height':'data(size)', 'shape':'ellipse',
        }},
        { selector:'node[kind="atom"]', style:{
          'background-color':'data(color)', 'background-opacity':'data(op)',
          'border-width':'data(bw)', 'border-color':'data(bc)', 'shape':'data(shape)',
          'width':'data(size)', 'height':'data(size)',
          'label':'data(short)', 'color':cText3,
          'font-family':'Lora, serif', 'font-size':7,
          'text-valign':'bottom', 'text-margin-y':3,
          'text-max-width':84, 'text-wrap':'ellipsis', 'text-overflow-wrap':'anywhere',
        }},
        { selector:'edge', style:{
          'width':1, 'line-color':cText3, 'opacity':'data(op)', 'curve-style':'bezier',
        }},
        { selector:'.pulse', style:{ 'border-width':4, 'border-color':cAccent }},
      ],
    });
    cyRef.current = cy;

    cy.on('tap', 'node', evt => {
      const n = evt.target;
      const k = n.data('kind');
      if (k === 'strand')      { setSelectedAtom(null); setSelectedStrand(n.data('sid')); }
      else if (k === 'center') { setSelectedAtom(null); setSelectedStrand(null); }
      else if (k === 'atom')   { setSelectedAtom(n.data('atom')); }
    });
    cy.on('tap', evt => { if (evt.target === cy) setSelectedAtom(null); });

    return () => { cy.destroy(); cyRef.current = null; };
  }, [libReady, data]);

  // Rebuild elements + run layout once whenever the view changes
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !data) return;
    const cs = getComputedStyle(document.documentElement);
    const accent = cs.getPropertyValue('--accent').trim();
    cy.elements().remove();
    cy.add(buildElements(data, selectedStrand, accent));
    const layout = cy.layout({
      name: ensureFcose() ? 'fcose' : 'cose',
      animate: true, animationDuration: 480, randomize: true,
      fit: true, padding: 48, nodeRepulsion: 6500, idealEdgeLength: 90,
      numIter: 1000,
    });
    layout.one('layoutstop', () => {
      if (pendingFocus.current) {
        const fid = pendingFocus.current;
        pendingFocus.current = null;
        focusAtom(fid);
      }
    });
    layout.run();
  }, [data, selectedStrand]);

  // Cmd/Ctrl+K omnibar
  useEffect(() => {
    const h = e => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setOmniOpen(o => !o);
      } else if (e.key === 'Escape') {
        setOmniOpen(false);
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  useEffect(() => { if (omniOpen && omniInput.current) omniInput.current.focus(); }, [omniOpen]);

  const selStrandName = (() => {
    if (!selectedStrand || !data) return null;
    if (selectedStrand === '_unstranded') return 'Misc';
    const s = (data.strands || []).find(x => x.id === selectedStrand);
    return s ? s.name : selectedStrand;
  })();

  if (!data) return (
    <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center' }}>
      <Pulse size={8}/>
    </div>
  );

  const totalAtoms = (data.strands||[]).reduce((n,s)=>n+(s.atoms||[]).length,0)
    + (data.unstranded||[]).length;

  if (totalAtoms === 0) return (
    <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', padding:48 }}>
      <p style={{ fontFamily:'var(--font-b)', fontSize:15, color:'var(--text-2)', fontStyle:'italic' }}>
        Nothing to map yet — the constellation forms as memories build up.
      </p>
    </div>
  );

  return (
    <div style={{ flex:1, display:'flex', overflow:'hidden', position:'relative',
      background:'var(--thread-bg)' }}>

      {/* Canvas column */}
      <div style={{ flex:1, position:'relative', overflow:'hidden' }}>

        {/* Breadcrumb / omnibar trigger */}
        <div style={{ position:'absolute', top:14, left:0, right:0, zIndex:5,
          display:'flex', alignItems:'center', justifyContent:'center', gap:12,
          pointerEvents:'none' }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, pointerEvents:'auto',
            padding:'5px 12px', borderRadius:8, background:'var(--nav-bg)',
            border:'1px solid var(--border-2)' }}>
            <button onClick={() => { setSelectedStrand(null); setSelectedAtom(null); }}
              style={{ fontFamily:'var(--font-m)', fontSize:10, letterSpacing:'.10em',
                textTransform:'uppercase',
                color: selectedStrand ? 'var(--text-3)' : 'var(--accent)', cursor:'pointer' }}>
              Strands
            </button>
            {selStrandName && <>
              <span style={{ color:'var(--text-3)', fontSize:10 }}>›</span>
              <span style={{ fontFamily:'var(--font-m)', fontSize:10, letterSpacing:'.10em',
                textTransform:'uppercase', color:'var(--accent)' }}>{selStrandName}</span>
            </>}
          </div>
          <button onClick={() => setOmniOpen(true)} style={{ pointerEvents:'auto',
            display:'flex', alignItems:'center', gap:8, padding:'5px 12px', borderRadius:8,
            background:'var(--nav-bg)', border:'1px solid var(--border-2)', cursor:'pointer' }}>
            <Ico n="search" size={12} color="var(--text-3)"/>
            <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-3)' }}>
              Search · ⌘K
            </span>
          </button>
        </div>

        {/* Cytoscape mount */}
        {libFailed ? (
          <div style={{ height:'100%', display:'flex', alignItems:'center', justifyContent:'center',
            padding:48 }}>
            <p style={{ fontFamily:'var(--font-b)', fontSize:14, color:'var(--text-3)',
              fontStyle:'italic', textAlign:'center', maxWidth:340 }}>
              Graph library couldn't load (offline?). The Memory and Timelines tabs
              show the same data without it.
            </p>
          </div>
        ) : !libReady ? (
          <div style={{ height:'100%', display:'flex', alignItems:'center', justifyContent:'center' }}>
            <Pulse size={8}/>
          </div>
        ) : (
          <div ref={cyEl} style={{ position:'absolute', inset:0 }}/>
        )}

        {/* Modality legend */}
        <div style={{ position:'absolute', bottom:14, left:14, zIndex:5,
          padding:'8px 12px', borderRadius:8, background:'var(--nav-bg)',
          border:'1px solid var(--border)', display:'flex', flexWrap:'wrap', gap:'4px 12px',
          maxWidth:300 }}>
          {Object.entries(MODALITY_SHAPE).map(([mod, shape]) => (
            <span key={mod} style={{ display:'flex', alignItems:'center', gap:5,
              fontFamily:'var(--font-m)', fontSize:8.5, letterSpacing:'.08em',
              textTransform:'uppercase', color:'var(--text-3)' }}>
              <span style={{ color:'var(--text-2)' }}>{SHAPE_GLYPH[shape]}</span>{mod}
            </span>
          ))}
        </div>
      </div>

      {/* Side panel */}
      {selectedAtom && (
        <div className="fade-up" style={{ width:320, flexShrink:0, borderLeft:'1px solid var(--border)',
          background:'var(--nav-bg)', overflowY:'auto', padding:'20px 22px' }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
            marginBottom:16 }}>
            {monoLabel('Atom')}
            <button onClick={() => setSelectedAtom(null)} style={{ cursor:'pointer' }}>
              <Ico n="close" size={14} color="var(--text-3)"/>
            </button>
          </div>
          <p style={{ fontFamily:'var(--font-b)', fontSize:15, lineHeight:1.7,
            color:'var(--text)', marginBottom:16 }}>{selectedAtom.text}</p>
          <div style={{ display:'flex', flexWrap:'wrap', gap:8, marginBottom:16 }}>
            {selectedAtom.subject && selectedAtom.subject !== 'user' && (
              <MonoBadge color="var(--text-3)">{selectedAtom.subject}</MonoBadge>
            )}
            {selectedAtom.predicate && (
              <MonoBadge color="var(--text-3)">{selectedAtom.predicate}</MonoBadge>
            )}
            {selectedAtom.modality && (
              <MonoBadge color={MODALITY_COLORS[selectedAtom.modality] || 'var(--accent)'}>
                {selectedAtom.modality}
              </MonoBadge>
            )}
            {selectedAtom.pinned && <MonoBadge color="var(--accent)">pinned</MonoBadge>}
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {selectedAtom.confidence != null && (
              <div style={{ display:'flex', justifyContent:'space-between' }}>
                {monoLabel('confidence')}
                <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-2)' }}>
                  {Math.round(selectedAtom.confidence * 100)}%
                </span>
              </div>
            )}
            {selectedAtom.salience != null && (
              <div style={{ display:'flex', justifyContent:'space-between' }}>
                {monoLabel('salience')}
                <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-2)' }}>
                  {selectedAtom.salience.toFixed ? selectedAtom.salience.toFixed(1) : selectedAtom.salience}
                </span>
              </div>
            )}
            <div style={{ display:'flex', justifyContent:'space-between' }}>
              {monoLabel('added')}
              <span style={{ fontFamily:'var(--font-m)', fontSize:10, color:'var(--text-2)' }}>
                {relTime(selectedAtom.created_at)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Omnibar overlay */}
      {omniOpen && (
        <div onClick={() => setOmniOpen(false)} style={{ position:'absolute', inset:0, zIndex:20,
          background:'rgba(0,0,0,.18)', display:'flex', justifyContent:'center',
          paddingTop:'12vh' }}>
          <div onClick={e => e.stopPropagation()} style={{ width:'min(560px,86%)', height:'fit-content',
            background:'var(--surface)', border:'1px solid var(--border-2)', borderRadius:12,
            overflow:'hidden' }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, padding:'14px 18px',
              borderBottom:'1px solid var(--border)' }}>
              <Ico n="search" size={15} color="var(--text-3)"/>
              <input ref={omniInput} value={omniQuery} onChange={e => setOmniQuery(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && omniResults[0]) teleport(omniResults[0]); }}
                placeholder="Jump to a memory…"
                style={{ flex:1, fontFamily:'var(--font-b)', fontSize:15, color:'var(--text)' }}/>
            </div>
            {omniResults.length > 0 && (
              <div style={{ maxHeight:'40vh', overflowY:'auto' }}>
                {omniResults.map(entry => (
                  <button key={entry.atom.id} onClick={() => teleport(entry)} style={{
                    display:'flex', alignItems:'center', gap:10, width:'100%', textAlign:'left',
                    padding:'10px 18px', borderBottom:'1px solid var(--rule)', cursor:'pointer' }}>
                    <span style={{ color: STRAND_COLORS[entry.strandId] || STRAND_COLORS._unstranded,
                      fontSize:10 }}>●</span>
                    <span style={{ flex:1, fontFamily:'var(--font-b)', fontSize:13, color:'var(--text)',
                      overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                      {entry.atom.text}
                    </span>
                    {monoLabel(entry.strandName, undefined, { flexShrink:0 })}
                  </button>
                ))}
              </div>
            )}
            {omniQuery.trim() && omniResults.length === 0 && (
              <p style={{ fontFamily:'var(--font-m)', fontSize:11, color:'var(--text-3)',
                padding:'14px 18px', fontStyle:'italic' }}>No matches.</p>
            )}
          </div>
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
  const allTabs = ['overview','fragments','graph','review','goals','timelines','inferred','skills'];

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
        {tab==='fragments' && <FragmentsTab memories={memories}/>}
        {tab==='graph' && <GraphTab/>}
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
