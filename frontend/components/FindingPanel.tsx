'use client';
import {useEffect,useState} from 'react';
import {ArrowUpRight,Check,GitMerge,LoaderCircle,X} from 'lucide-react';
import {api} from '../lib/api';
import type {Finding,History,Report} from '../lib/types';

export default function FindingPanel({finding:f,report,onClose,onSaved}:{finding:Finding;report:Report;onClose:()=>void;onSaved:(r:Report)=>void}){
  const [sourceIndex,setSourceIndex]=useState(0),[history,setHistory]=useState<History[]>([]),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const [form,setForm]=useState({title:f.title,description:f.description,location:f.location,priority:f.priority,kind:f.kind,note:f.review.note});
  const source=f.sources[sourceIndex]||f.sources[0];
  useEffect(()=>{const listener=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',listener);return()=>window.removeEventListener('keydown',listener)},[onClose]);
  useEffect(()=>{api<History[]>(`/reports/${report.id}/reviews`).then(h=>setHistory(h.filter(x=>(x as History&{finding:string}).finding===f.id))).catch(()=>{})},[f.id,f.review.revision,report.id]);
  async function save(decision:string){
    setSaving(true);setError('');
    const changes:Record<string,string>={};
    for(const k of ['title','description','location','priority','kind'] as const){if(form[k]!==f[k])changes[k]=form[k]}
    try{const next=await api<Report>(`/reports/${report.id}/findings/${f.id}/review`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:f.review.revision,decision,note:form.note,...changes})});onSaved(next)}catch(e){setError((e as Error).message)}finally{setSaving(false)}
  }
  return <div className="modal-backdrop" onClick={onClose}><section className="modal wide" role="dialog" aria-modal="true" aria-label="Review finding and evidence" onClick={e=>e.stopPropagation()}>
    <div className="modal-head"><div><span className="eyebrow">EVIDENCE WORKBENCH · {f.report_reference||f.id}</span><h2>{f.title}</h2></div><button autoFocus aria-label="Close finding" className="icon-button" onClick={onClose}><X/></button></div>
    <div className="modal-grid"><div className="modal-copy">
      <div className="finding-title"><span className={`badge ${f.priority.toLowerCase()}`}>{f.priority} · {f.priority_rule==='human_override'?'human':'policy'}</span><span className={`badge review-${f.review.decision}`}>{f.review.decision} · revision {f.review.revision}</span></div>
      <p>{f.description}</p><div className="provenance-row"><span>Observation / Luna</span><span>Priority / Python rules</span><span>Approval / Human</span></div>
      <h4>Source passages · {f.sources.length}</h4><div className="source-switch">{f.sources.map((s,i)=><button className={i===sourceIndex?'selected':''} key={s.id} onClick={()=>setSourceIndex(i)}>Page {s.page} <span>{s.role}</span></button>)}</div>
      <blockquote>{source.quote}</blockquote><p className="small muted">{source.quote_matched?'Quote matched':'Quote NOT matched'} · {source.geometry_matched?`${source.boxes.length} highlighted text lines`:'No highlight coordinates'} · Ref {source.reference||'not bound'}{source.continuation_of?` · continuation inferred from page ${source.continuation_of}`:''}</p>
      <h4>Support gates</h4><div className="gate-list">{[{label:'Source quotation exists',ok:f.evidence_verified},{label:'Coordinates located',ok:f.sources.some(s=>s.geometry_matched)},{label:'Mechanical support gates passed',ok:f.support_status==='text_supported'},{label:'Human reviewed meaning and scope',ok:f.review.decision==='accepted'}].map(g=><div key={g.label}><span className={g.ok?'gate-pass':'gate-wait'}>{g.ok?<Check size={12}/>:<span>!</span>}</span>{g.label}</div>)}</div>
      {f.flags.length>0&&<div className="flag-list">{f.flags.map(flag=><span key={flag}>{flag.replaceAll('_',' ')}</span>)}</div>}
      <p className="small muted">Mechanical gates are not a semantic correctness guarantee. Accept only after reading the passage and source page.</p>
      <h4>Consolidation & provenance</h4><p><GitMerge size={13}/> {f.variants.length} extracted observations → 1 finding. {f.merge_reasons.length?Array.from(new Set(f.merge_reasons)).join(', '):'No automatic merge.'}</p>
      {f.related_candidates.length>0&&<p className="small muted">{f.related_candidates.length} potentially similar findings remain separate. Review and reject duplicates manually if appropriate.</p>}
      <details><summary>Inspect original extracted variants</summary><pre className="json-view">{JSON.stringify(f.variants,null,2)}</pre></details>
      <h4>Why this priority?</h4><p>{f.priority_reason}</p><code className="rule-code">{f.rule_version} / {f.priority_rule}</code>
      <h4>Inspector recommendation</h4><p>{f.inspector_recommendation||'Not supplied'}</p><p className="small muted">Source severity: {f.inspector_severity||'Not located in the cited observation'}</p>
      <div className="review-form"><h4>Review & correct</h4><label>Title<input value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/></label><label>Location<input value={form.location} onChange={e=>setForm({...form,location:e.target.value})}/></label><label>Interpretation<textarea rows={3} value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></label><label>Observation type<select value={form.kind} onChange={e=>setForm({...form,kind:e.target.value})}><option value="observed_defect">Observed defect / maintenance finding</option><option value="limitation">Inspection limitation</option><option value="informational">Information only</option></select></label><label>Priority override<select value={form.priority} onChange={e=>setForm({...form,priority:e.target.value})}>{['Safety','Urgent','Planned','Cosmetic'].map(p=><option key={p}>{p}</option>)}</select></label><label>Review note<textarea rows={2} placeholder="Why did you accept, reject or correct this finding?" value={form.note} onChange={e=>setForm({...form,note:e.target.value})}/></label>
      {error&&<div role="alert" className="alert">{error}</div>}
      <div className="review-actions"><button className="primary" disabled={saving||!f.evidence_verified} onClick={()=>save('accepted')}>{saving?<LoaderCircle size={13} className="spin"/>:<Check size={13}/>}Accept</button><button className="secondary" disabled={saving} onClick={()=>save('rejected')}>Reject</button><button className="secondary" disabled={saving} onClick={()=>save('pending')}>Save for review</button></div><p className="small muted">Every save appends an audit revision. Original observations and source quotes are preserved. Rejected findings leave the repair plan.</p></div>
      {history.length>0&&<details className="audit"><summary>Review history · {history.length} revisions</summary>{history.slice().reverse().map(h=><div key={h.revision}><strong>v{h.revision} · {h.decision}</strong><small>{new Date(h.created*1000).toLocaleString()}</small><p>{h.note||'No note supplied'}</p><code>{JSON.stringify(h.changes)}</code></div>)}</details>}
    </div><div className="page-preview"><a href={`/api/reports/${report.id}/pdf#page=${source.page}`} target="_blank" rel="noreferrer">Original PDF · page {source.page} <ArrowUpRight size={14}/></a><img key={source.id} src={`/api/reports/${report.id}/pages/${source.page}?source_id=${source.id}`} alt={`Original page ${source.page}, highlighted source quotation`}/><p className="small muted">Highlights are derived from PDF word coordinates. The original file is unchanged.</p></div></div>
  </section></div>
}
