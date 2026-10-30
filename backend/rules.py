"""Versioned, inspectable policies operating on cited source text, never model prices."""
import re
from .document import normalize
VERSION='priority-2.1'
PRIORITIES=['Safety','Urgent','Planned','Cosmetic']
SAFETY=[('electric.open_neutral',r'open neutral'),('electric.open_ground',r'open ground'),('electric.loose',r'loose receptacle'),
        ('electric.gfci',r'(not gfci|no gfci|gfci.*(missing|absent)|gfci - laundry)'),
        ('electric.cover',r'(cover plate.*missing|missing cover plate|grounding.*obstruct|arcing|exposed wir)'),
        ('fall.rail',r'(handrail.*(not present|missing)|railing.*(missing|loose)|loose railing|fall hazard)'),
        ('fall.ladder',r'(ladder.*(weak|unsafe)|weak ladder)'),('fire.detector',r'(smoke detector.*(add|insufficient|missing)|additional smoke detectors)'),
        ('hazard.explicit',r'(safety hazard|shock hazard|risk of fire)')]
LIMITATION=re.compile(r'(unable to test|not (?:operated|tested|inspected)|could not be (?:tested|verified)|no dryer was installed)',re.I)
BOILERPLATE=re.compile(r'(unless otherwise noted|regular maintenance/inspections are always recommended)',re.I)

def source_text(f):
    return normalize(' '.join(s['quote']+' '+s.get('section','') for s in f['sources'] if s['quote_matched']))

def policy(f):
    text=source_text(f)
    evidence=' '.join(s['quote'] for s in f['sources'] if s['quote_matched'])
    flags=[]
    if not f['evidence_verified']:flags.append('unmatched_evidence')
    if f.get('kind')!='observed_defect' or LIMITATION.search(evidence):flags.append('limitation_or_information')
    if BOILERPLATE.search(evidence):flags.append('boilerplate_requires_review')
    if any(s['reference_conflict'] for s in f['sources']):flags.append('reference_mismatch')
    # A conservative contradiction gate, not a claim of semantic verification.
    if re.search(r'\b(no (?:signs|evidence) of|not observed|no defects)\b',normalize(evidence)):
        flags.append('negated_observation')
    title_terms=set(re.findall(r'[a-z]{4,}',normalize(f['title']))) - {'condition','observed','noted','with','from','report','issue','issues','the','this'}
    supported_terms=title_terms & set(re.findall(r'[a-z]{4,}',text))
    if title_terms and len(supported_terms)/len(title_terms)<0.25:flags.append('weak_lexical_support')
    severities=sorted({s['source_severity'] for s in f['sources'] if s['source_severity']})
    if len(severities)>1:flags.append('conflicting_source_severity')
    priority='Planned';rule='default.planned';reason='No explicit urgent or safety rule matched the cited source.'
    if f['evidence_verified']:
        for rule_id,pattern in SAFETY:
            if re.search(pattern,text):
                priority,rule,reason='Safety',rule_id,'Cited source matched the safety policy: '+rule_id
                break
        else:
            if 'Immediate Deficiency' in severities or re.search(r'(active leak|active water|signs of moisture intrusion|moisture intrusion (?:observed|noted|present)|would not light)',text):
                priority,rule,reason='Urgent','damage_or_reported_immediate','Inspector immediate deficiency or a nonfunctional / moisture condition requires prompt evaluation.'
            elif re.search(r'(cosmetic|missing handle|missing.*pull|cabinet.*hardware)',text):
                priority,rule,reason='Cosmetic','finish.hardware','Cited finding concerns minor finish or cabinet hardware.'
    category='specialist_review'
    for name,pattern in [('electrical_evaluation',r'(receptacle|electrical|switch|smoke detector)'),
                         ('drainage',r'(down.?spout|re-grading|grading -|gutter)'),
                         ('moisture_investigation',r'(moisture|vapor barrier|water intrusion)'),
                         ('handrail',r'(handrail|railing)'),('roof_repair',r'(roof covering|shingle)'),
                         ('hvac_service',r'(air filter|hvac|air handler)'),('plumbing_repair',r'(faucet|plumbing|pipe leak)')]:
        if re.search(pattern,text):category=name;break
    eligible=not any(x in flags for x in ['unmatched_evidence','limitation_or_information','boilerplate_requires_review','negated_observation','reference_mismatch','weak_lexical_support','conflicting_source_severity'])
    return {'priority':priority,'priority_reason':reason,'priority_rule':rule,'rule_version':VERSION,
            'repair_category':category,'flags':flags,'support_status':'text_supported' if eligible else 'needs_review',
            'eligible':eligible,'inspector_severity':' / '.join(severities),
            'buyer_question':f"What evaluation or repair has been completed for {f['title'].lower()}, and can you provide the scope, date and supporting documentation?"}
