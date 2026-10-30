"""Evidence resolution, conservative consolidation, review overlay and repair dependency graph."""
import hashlib
import re
from difflib import SequenceMatcher
from .document import normalize, source_record
from .rules import policy, PRIORITIES

VERSION='pipeline-2.1'

def ground(items, document):
    resolved=[]
    for item in items:
        raw=item.model_dump() if hasattr(item,'model_dump') else dict(item)
        resolved.append({'observation':raw,'source':source_record(raw,document)})
    return resolved

def consolidate(items, document=None):
    records=[]
    resolved=ground(items,document) if document is not None else items
    for item in resolved:
        raw=item['observation']
        source=item['source']
        ref=source['reference'] if not source['reference_conflict'] else ''
        target=None;method=None
        for record in records:
            if source['quote_matched'] and ref and ref==record['report_reference']:
                target,method=record,'validated_report_reference';break
            if source['quote_matched'] and any(s['quote_matched'] and normalize(s['quote'])==normalize(source['quote']) and s['page']==source['page'] for s in record['sources']):
                if raw['system']==record['system'] and normalize(raw['location'])==normalize(record['location']):
                    target,method=record,'same_passage_and_location';break
        if target:
            if source['id'] not in [s['id'] for s in target['sources']]:target['sources'].append(source)
            target['variants'].append(raw)
            target['merge_reasons'].append(method)
            # Detail observations take precedence over summary wording, without discarding either.
            if source['role']!='summary' and target['sources'][0]['role']=='summary':
                for key in ['title','description','location','system','page','evidence','inspector_recommendation','kind']:
                    target[key]=raw[key]
            continue
        key='ref:'+ref if ref else f"{raw['system']}:{raw['location']}:{source['id']}"
        records.append({**raw,'id':'f-'+hashlib.sha256(key.encode()).hexdigest()[:14],
                        'report_reference':ref,'sources':[source],'variants':[raw],'merge_reasons':[],
                        'provenance':{'observation':'Luna extraction','evidence':'Local PDF text + word coordinates',
                                      'priority':'Versioned Python policy','scope':'Deterministic trade grouping',
                                      'review':'Pending human review'}})
    for f in records:
        f['evidence_verified']=any(s['quote_matched'] for s in f['sources'])
        f.update(policy(f))
        f['review']={'revision':0,'decision':'pending','note':'','changes':{}}
        f['review_required']=True
        f['cost']=None # Costs belong to shared scopes, never individual duplicated findings.
        f['review_note']='Quotation matching and lexical checks are mechanical. Semantic support still requires human review.'
        f['related_candidates']=[]
        if len({v.get('kind') for v in f['variants']})>1:
            f['flags'].append('conflicting_observation_kind');f['eligible']=False
        normalized_descriptions=[normalize(v['description']) for v in f['variants']]
        if any(re.search(r'\b(no (?:signs|evidence) of|not observed)\b',v) for v in normalized_descriptions) and not all(re.search(r'\b(no (?:signs|evidence) of|not observed)\b',v) for v in normalized_descriptions):
            f['flags'].append('conflicting_interpretations');f['eligible']=False
        if not f['eligible']:f['support_status']='needs_review'
    # Fuzzy matches are suggestions only. Do not silently collapse similar defects.
    for i,a in enumerate(records):
        for b in records[i+1:]:
            if a['system']==b['system'] and normalize(a['location'])==normalize(b['location']):
                similarity=SequenceMatcher(None,normalize(a['title']),normalize(b['title'])).ratio()
                if similarity>=0.72:
                    a['related_candidates'].append(b['id']);b['related_candidates'].append(a['id'])
    return records

def apply_reviews(records, reviews):
    import copy
    output=copy.deepcopy(records)
    for f in output:
        review=reviews.get(f['id'])
        if not review:continue
        f['review']=review
        f['original']={k:f[k] for k in ['title','description','location','priority','kind']}
        for key,value in review['changes'].items():
            if key in ['title','description','location','priority','kind'] and value is not None:f[key]=value
        f['review_required']=review['decision']=='pending'
        if review['decision']=='accepted':
            # Humans can resolve semantic uncertainty, but cannot create missing source evidence.
            f['eligible']=f['evidence_verified'] and f.get('kind')=='observed_defect'
            f['provenance']['review']='Human accepted / corrected'
        elif review['decision']=='rejected':
            f['eligible']=False;f['provenance']['review']='Human rejected'
        if review['changes'].get('priority'):
            f['priority_reason']='Human priority override. '+review['note']
            f['priority_rule']='human_override'
    return output

# These are demonstrative shared-scope assumptions; they are deliberately not contractor estimates.
SCENARIOS={
    'electrical_evaluation':(150,450,'One shared electrician diagnostic visit; all repairs and replacements excluded.'),
    'drainage':(500,3000,'One combined localized drainage scenario; measurements and actual correction scope unverified.'),
    'handrail':(150,800,'One coordinated railing scope; quantities, dimensions and number of locations unverified.'),
    'roof_repair':(500,2500,'One localized roof-work scenario; inspection may instead require cleaning only. Confirm scope.'),
    'hvac_service':(150,600,'One coordinated HVAC service visit; replacements excluded.'),
    'plumbing_repair':(200,1000,'One combined minor accessible plumbing scope; hidden damage excluded.')}

def build_plan(findings):
    usable=[f for f in findings if f['eligible'] and f['review']['decision']!='rejected']
    groups={}
    for f in usable:groups.setdefault(f['repair_category'],[]).append(f)
    tasks=[]
    for category,items in groups.items():
        # Never infer a roof repair price from a debris-only observation.
        scenario=SCENARIOS.get(category)
        if category=='roof_repair' and all('debris' in normalize(f['evidence']) for f in items):scenario=None
        label={'electrical_evaluation':'Electrical safety evaluation','drainage':'Combined roof-runoff and site-drainage scope',
               'moisture_investigation':'Investigate crawlspace / moisture conditions','handrail':'Railing and stair safety scope',
               'roof_repair':'Roof condition and maintenance scope','hvac_service':'HVAC service scope',
               'plumbing_repair':'Plumbing scope','specialist_review':'Specialist scope definition'}[category]
        task={'id':'scope-'+category,'category':category,'title':label,'finding_ids':[f['id'] for f in items],
              'priority':min((f['priority'] for f in items),key=PRIORITIES.index),'depends_on':[],
              'status':'needs_scope','quantity':None,'source':'Python shared-scope policy v2',
              'action':'Obtain a professional evaluation and one coordinated quote for the linked findings.',
              'missing_information':['Confirmed quantities / dimensions','Cause and extent','Access and concealed damage','Contractor pricing'],
              'scenario':({'low':scenario[0],'high':scenario[1],'assumptions':scenario[2],
                           'source':'HouseScope illustrative development assumptions v2','date':'2026-10-30',
                           'region':'No regional adjustment'} if scenario else None)}
        tasks.append(task)
    relationships=[]
    moisture=next((t for t in tasks if t['category']=='moisture_investigation'),None)
    drainage=next((t for t in tasks if t['category']=='drainage'),None)
    if moisture:
        remediation={'id':'scope-moisture-correction','category':'moisture_correction','title':'Define and correct the confirmed moisture source',
                     'finding_ids':moisture['finding_ids'],'priority':moisture['priority'],
                     'depends_on':[moisture['id']]+([drainage['id']] if drainage else []),'status':'blocked_by_evaluation',
                     'quantity':None,'scenario':None,'source':'Python dependency rule moisture.before_restoration',
                     'action':'Proceed only after the specialist confirms the cause; linked drainage work is a planning prerequisite, not a diagnosed cause.',
                     'missing_information':['Confirmed source','Remediation specification','Moisture verification criteria']}
        tasks.append(remediation)
        if drainage:
            relationships.append({'from':drainage['id'],'to':moisture['id'],'type':'possible_related_scope',
                                  'confirmed':False,'reason':'Drainage and moisture observations coexist. A professional must confirm any causal connection.',
                                  'evidence_finding_ids':list(dict.fromkeys(drainage['finding_ids']+moisture['finding_ids']))})
        finishes=[f for f in usable if f['system']=='Interior' and re.search(r'(floor|wall|paint|finish)',normalize(f['evidence']))]
        if finishes:
            tasks.append({'id':'scope-finish-restoration','category':'finishes','title':'Restore affected finishes after cause resolution',
                          'finding_ids':[f['id'] for f in finishes],'priority':'Planned','depends_on':['scope-moisture-correction'],
                          'status':'blocked_by_evaluation','quantity':None,'scenario':None,'source':'Python dependency rule moisture.before_restoration',
                          'action':'Confirm whether finish damage is related before scheduling restoration.','missing_information':['Cause linkage','Dryness verification','Restoration dimensions']})
    # Stable topological order; priorities break ties only after prerequisites are satisfied.
    ordered=[];remaining=list(tasks)
    while remaining:
        ready=[t for t in remaining if set(t['depends_on'])<={o['id'] for o in ordered}]
        if not ready:raise ValueError('Repair dependency cycle detected')
        ready.sort(key=lambda t:(PRIORITIES.index(t['priority']),t['id']))
        task=ready[0];ordered.append(task);remaining.remove(task)
    scenarios=[t['scenario'] for t in tasks if t['scenario']]
    return {'tasks':ordered,'relationships':relationships,'totals':{'low':sum(s['low'] for s in scenarios),
            'high':sum(s['high'] for s in scenarios),'priced_scopes':len(scenarios),'unpriced_scopes':len(tasks)-len(scenarios)},
            'excluded_findings':[f['id'] for f in findings if f not in usable],
            'method':'Count each shared trade scope once. No per-finding price summation. Scope overlap within and between trades still requires professional review.'}
