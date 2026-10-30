import json
from pathlib import Path
from types import SimpleNamespace
import pymupdf
import pytest
from fastapi.testclient import TestClient
from backend.document import extract_document
from backend.engine import consolidate,apply_reviews,build_plan
from backend.evaluation import evaluate
from backend.models import Review,Extraction
from backend import storage as db

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DATA',tmp_path)
    monkeypatch.setattr(db,'DB',tmp_path/'test.sqlite')
    db.initialize()
    return tmp_path

@pytest.fixture
def document(tmp_path):
    doc=pymupdf.open()
    doc.new_page().insert_text((50,60),'SUMMARY\n5.4.5 Receptacles: Open neutral condition\n')
    doc.new_page().insert_text((50,60),'5.4.5 Receptacles Condition\nOPEN NEUTRAL\nAn electrical receptacle tested positive for an open neutral condition.\nImmediate Deficiency\n')
    path=tmp_path/'inspection.pdf';doc.save(path);doc.close()
    return path,extract_document(path)

def observation(**kwargs):
    base=dict(system='Electrical',location='Kitchen',title='Open neutral receptacle',description='A receptacle tested open neutral.',page=2,
              evidence='An electrical receptacle tested positive for an open neutral condition.',report_reference='5.4.5',kind='observed_defect',
              inspector_recommendation='Electrician evaluation',inspector_severity='Immediate Deficiency')
    return {**base,**kwargs}

def test_geometry_reference_merge_and_policy(document):
    _,doc=document
    rows=consolidate([observation(page=1,evidence='5.4.5 Receptacles: Open neutral condition'),observation()],doc)
    assert len(rows)==1 and len(rows[0]['sources'])==2
    assert all(s['geometry_matched'] for s in rows[0]['sources'])
    assert rows[0]['priority']=='Safety' and rows[0]['priority_rule']=='electric.open_neutral'
    assert rows[0]['merge_reasons']==['validated_report_reference']
    assert rows[0]['sources'][1]['source_severity']=='Immediate Deficiency'
    # False reference declarations must not bind the observation to another defect.
    wrong=consolidate([observation(report_reference='9.9.9')],doc)[0]
    assert not wrong['eligible'] and 'reference_mismatch' in wrong['flags']

def test_unsupported_and_limitation_gate(document):
    _,doc=document
    rows=consolidate([observation(evidence='The roof is collapsing and must be replaced.'),observation(kind='limitation')],doc)
    assert all(not r['eligible'] for r in rows)
    assert build_plan(rows)['totals']['priced_scopes']==0

def test_shared_scope_dependencies_and_rejection(document):
    _,doc=document
    # Independent source observations share one diagnostic scope, not multiple visit prices.
    a=consolidate([observation()],doc)[0]
    b={**a,'id':'second-electric','sources':list(a['sources'])}
    p=build_plan([a,b]);assert p['totals']['low']==150 and len(p['tasks'])==1
    moisture={**a,'id':'moisture','repair_category':'moisture_investigation','priority':'Urgent'}
    drainage={**a,'id':'drainage','repair_category':'drainage','priority':'Planned'}
    tasks=build_plan([moisture,drainage])
    order=[t['id'] for t in tasks['tasks']]
    assert order.index('scope-moisture_investigation')<order.index('scope-moisture-correction')
    assert order.index('scope-drainage')<order.index('scope-moisture-correction')
    assert tasks['relationships'][0]['confirmed'] is False
    reviewed=apply_reviews([a],{a['id']:{'revision':1,'decision':'rejected','changes':{},'note':'Duplicate'}})
    assert not build_plan(reviewed)['tasks'] and a['eligible'] # baseline immutable

def test_evaluation_reports_duplicates_and_misses(document):
    _,doc=document
    a=consolidate([observation()],doc)[0]
    fixture={'id':'test','annotation_method':'test fixture','scope':'test','excluded':[],
             'findings':[{'reference':'5.4.5','title':'Open neutral','detail_pages':[2],'anchor':'open neutral condition'},
                         {'reference':'4.2.2','title':'Drainage','detail_pages':[1],'anchor':'downspout'}]}
    result=evaluate([a,{**a,'id':'unmerged-duplicate'}],fixture,True)
    assert result['precision']==0.5 and result['recall']==0.5
    assert result['false_positives']==1 and result['false_negatives']==1
    assert result['detail_citation_accuracy']==1
    assert evaluate([],fixture,False)['state']=='not_run'

def test_budget_and_revision_concurrency(isolated):
    db.reserve('report',0.04,0.05,'gpt-6-luna')
    with pytest.raises(ValueError,match='budget'):db.reserve('report',0.02,0.05,'gpt-6-luna')
    db.save_review('report','finding',Review(expected_revision=0,decision='accepted',title='Corrected title'))
    with pytest.raises(ValueError,match='another view'):db.save_review('report','finding',Review(expected_revision=0,decision='rejected'))
    db.save_review('report','finding',Review(expected_revision=1,decision='pending',note='Keep correction'))
    assert db.reviews_for('report')['finding']['changes']['title']=='Corrected title'

def test_api_review_and_highlight_contract(isolated,document):
    from backend.main import app,register_pdf
    path,_=document
    report=register_pdf(path.read_bytes(),'test.pdf');rid=report['id']
    with db.connection() as con:
        con.execute('INSERT INTO extractions VALUES(?,?,?,?)',(rid,json.dumps([observation()]),'pipeline-2.0','offline_test'))
        con.execute("UPDATE reports SET state='complete' WHERE id=?",(rid,))
    with TestClient(app) as client:
        row=client.get(f'/api/reports/{rid}/status').json()
        f=row['result'][0];source=f['sources'][0]
        image=client.get(f'/api/reports/{rid}/pages/2?source_id={source["id"]}')
        assert image.status_code==200 and image.content.startswith(b'\x89PNG')
        url=f'/api/reports/{rid}/findings/{f["id"]}/review'
        saved=client.patch(url,json={'expected_revision':0,'decision':'rejected','note':'Review test'})
        assert saved.status_code==200 and not saved.json()['plan']['tasks']
        assert client.patch(url,json={'expected_revision':0,'decision':'accepted'}).status_code==409
        assert 'Review: rejected' in client.get(f'/api/reports/{rid}/export').text
        assert len(client.get(f'/api/reports/{rid}/annotations/export').json()['history'])==1

def test_pipeline_checkpoints_resume_without_rebilling_cached_sections(isolated,document,monkeypatch):
    from backend import pipeline
    from backend.main import register_pdf
    path,doc=document
    rid=register_pdf(path.read_bytes(),'test.pdf')['id']
    batches=[[{'page':1,'text':'summary'}],[{'page':2,'text':'detail'}]]
    monkeypatch.setattr(pipeline,'chunks',lambda _:iter(batches))
    calls=[]
    def fake_parse(**kwargs):
        calls.append(kwargs['input'])
        if len(calls)==2:raise RuntimeError('Simulated connection failure')
        return SimpleNamespace(status='completed',output_parsed=Extraction.model_validate({'findings':[observation()]}),usage=SimpleNamespace(input_tokens=100,output_tokens=100))
    monkeypatch.setattr(pipeline,'OpenAI',lambda **kwargs:SimpleNamespace(responses=SimpleNamespace(parse=fake_parse)))
    pipeline.analyze(rid)
    assert db.get_report(rid)['state']=='failed'
    pipeline.analyze(rid)
    assert db.get_report(rid)['state']=='complete'
    assert len(calls)==3 # first section loaded from cache, never called a second time
    with db.connection() as con:
        assert con.execute('SELECT COUNT(*) FROM usage').fetchone()[0]==3
        assert con.execute("SELECT COUNT(*) FROM usage WHERE actual IS NULL").fetchone()[0]==1
        assert '1 cache hits' in con.execute("SELECT detail FROM stages WHERE name='extract' ORDER BY id DESC LIMIT 1").fetchone()[0]

def test_continuation_binding_and_preventative_priority(tmp_path):
    from backend.document import source_record
    from backend.rules import policy
    pdf=pymupdf.open()
    pdf.new_page().insert_text((50,60),'5.6.1 Smoke Detectors Condition\nSMOKE DETECTORS - ADD\nGeneral Maintenance')
    pdf.new_page().insert_text((50,60),'Recommend additional smoke detectors be installed in the bedrooms.\nRecommendation\nContact an electrician.')
    path=tmp_path/'continuation.pdf';pdf.save(path);pdf.close()
    doc=extract_document(path)
    f=observation(page=2,evidence='Recommend additional smoke detectors be installed in the bedrooms.',report_reference='5.6.1')
    source=source_record(f,doc)
    assert source['reference']=='5.6.1' and source['continuation_of']==1
    assert source['geometry_matched'] and not source['reference_conflict']
    prevention={'title':'Seal penetrations','kind':'observed_defect','evidence_verified':True,
                'sources':[{'quote':'Caulk penetrations to prevent moisture intrusion.','section':'CAULK PENETRATIONS',
                            'quote_matched':True,'source_severity':'General Maintenance','reference_conflict':False}]}
    assert policy(prevention)['priority']=='Planned'
