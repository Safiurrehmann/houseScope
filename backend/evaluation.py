"""One-to-one benchmark alignment with explicit dataset identity and transparent errors."""
import json,re
from pathlib import Path
from .document import normalize

FIXTURES=Path(__file__).resolve().parents[1]/'fixtures/annotations'

def reference_for(report_id):
    for path in FIXTURES.glob('*.json'):
        fixture=json.loads(path.read_text())
        if fixture['document_sha256']==report_id:return fixture
    return None

def evaluate(findings, fixture, completed=False):
    if not fixture:return {'state':'unavailable','reason':'No independently labeled fixture is registered for this document hash.'}
    base={'dataset':fixture['id'],'annotation_method':fixture['annotation_method'],'scope':fixture['scope'],
          'expected':len(fixture['findings']),'excluded':fixture['excluded'],
          'limitations':'Reference matching measures extraction coverage; detail-page quote localization is mechanical. Neither establishes semantic correctness. The labels have not been independently human-audited.'}
    if not completed:return {**base,'state':'not_run','reason':'Run extraction first. No model quality metrics have been measured.'}
    predictions=[f for f in findings if f.get('kind')=='observed_defect']
    pairs=[]
    used=set()
    for gold in fixture['findings']:
        candidates=[]
        for i,f in enumerate(predictions):
            if i in used:continue
            # Prefer a source-validated reference. Fallback requires detail-page evidence
            # that actually overlaps the manually selected source anchor.
            by_ref=any(s['quote_matched'] and not s['reference_conflict'] and s['reference']==gold['reference'] for s in f['sources'])
            anchor=normalize(gold['anchor'])
            by_anchor=any(s['quote_matched'] and s['page'] in gold['detail_pages'] and (anchor in normalize(s['quote']) or normalize(s['quote']) in anchor) for s in f['sources'])
            if by_ref or by_anchor:candidates.append((i,f,2 if by_ref else 1))
        if candidates:
            i,f,score=max(candidates,key=lambda c:c[2]);used.add(i)
            localized=any(s['quote_matched'] and s['geometry_matched'] and s['page'] in gold['detail_pages'] for s in f['sources'])
            pairs.append({'reference':gold['reference'],'finding_id':f['id'],'title':gold['title'],
                          'detail_citation_correct':localized,'match_method':'validated_reference' if score==2 else 'source_anchor'})
    matched={p['reference'] for p in pairs}
    tp=len(pairs);fp=len(predictions)-tp;fn=len(fixture['findings'])-tp
    return {**base,'state':'measured','precision':tp/len(predictions) if predictions else None,
            'recall':tp/len(fixture['findings']) if fixture['findings'] else 0,
            'detail_citation_accuracy':sum(p['detail_citation_correct'] for p in pairs)/tp if tp else None,
            'true_positives':tp,'false_positives':fp,'false_negatives':fn,'matches':pairs,
            'missed':[g for g in fixture['findings'] if g['reference'] not in matched],
            'unmatched_predictions':[{'id':f['id'],'title':f['title'],'flags':f['flags']} for i,f in enumerate(predictions) if i not in used],
            'unsupported_safety_findings':[f['id'] for f in predictions if f['priority']=='Safety' and not f['eligible']]}
