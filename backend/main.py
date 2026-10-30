"""Local API for document intelligence, review, evaluation and trace exports."""
import hashlib,json,os,time
from contextlib import asynccontextmanager
from pathlib import Path
import pymupdf
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
from fastapi import BackgroundTasks,FastAPI,File,HTTPException,UploadFile
from fastapi.responses import FileResponse,Response
from . import storage as db
from .document import VERSION as DOCUMENT_VERSION
from .engine import VERSION,apply_reviews,build_plan
from .evaluation import evaluate,reference_for
from .models import Review
from . import budget
from .pipeline import BUDGET,MODEL,analyze,document_for,load_baseline,reprocess

db.initialize()
@asynccontextmanager
async def lifespan(app):
    with db.connection() as con:
        con.execute("UPDATE reports SET state='failed',error='Server restarted. Resume to use completed extraction checkpoints.' WHERE state='processing'")
        con.execute("UPDATE runs SET state='interrupted',ended=? WHERE state='running'",(time.time(),))
        con.execute("UPDATE stages SET state='interrupted',ended=? WHERE state='running'",(time.time(),))
    yield
app=FastAPI(title='HouseScope · Evidence pipeline',lifespan=lifespan)

def get_report(report_id):
    row=db.get_report(report_id)
    if not row:raise HTTPException(404,'Report not found')
    return row

def effective(report_id):
    return apply_reviews(load_baseline(report_id),db.reviews_for(report_id))

@app.get('/api/health')
def health():
    with db.connection() as con:
        spent=con.execute('SELECT COALESCE(SUM(actual),0) FROM usage').fetchone()[0]
        committed=con.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM usage').fetchone()[0]
    return {'ready':bool(os.getenv('OPENAI_API_KEY')),'model':MODEL,'budget':BUDGET,'spent':spent,
            'committed':committed,'remaining':max(0,BUDGET-committed),'pipeline_version':VERSION}

@app.get('/api/reports')
def reports():
    with db.connection() as con:return [dict(r) for r in con.execute('SELECT id,name,state,created FROM reports ORDER BY created DESC')]

def register_pdf(content,name):
    if len(content)>25*1024*1024:raise HTTPException(413,'Maximum file size is 25 MB')
    if not content.startswith(b'%PDF-'):raise HTTPException(400,'Please upload a valid PDF')
    report_id=hashlib.sha256(content).hexdigest()
    try:
        with pymupdf.open(stream=content,filetype='pdf') as doc:
            if doc.needs_pass or not 1<=len(doc)<=150:raise ValueError('Use an unlocked PDF with 1–150 pages')
    except Exception as exc:raise HTTPException(400,str(exc) if isinstance(exc,ValueError) else 'The PDF could not be opened')
    path=db.DATA/(report_id+'.pdf')
    if not path.exists():path.write_bytes(content)
    with db.connection() as con:
        con.execute('INSERT OR IGNORE INTO reports(id,name,pages,state,progress,created) VALUES(?,?,?,?,?,?)',
                    (report_id,Path(name).name,'[]','uploaded','Document indexed; ready for extraction',time.time()))
    document_for(report_id)
    return status(report_id)

@app.post('/api/reports')
async def upload(file:UploadFile=File(...)):
    return register_pdf(await file.read(25*1024*1024+1),file.filename or 'Inspection.pdf')

@app.post('/api/samples/kentucky')
def sample():
    path=db.ROOT/'fixtures/peirson-kentucky-sample.pdf'
    if not path.exists():raise HTTPException(404,'Download the Kentucky sample listed in fixtures/SOURCES.md first.')
    return register_pdf(path.read_bytes(),'Kentucky · Public inspection sample.pdf')

@app.post('/api/reports/{report_id}/analyze')
def start(report_id:str,background:BackgroundTasks):
    row=get_report(report_id)
    if row['state'] in ['complete','processing']:return status(report_id)
    if not os.getenv('OPENAI_API_KEY'):raise HTTPException(400,'Add OPENAI_API_KEY to the root .env and restart the backend.')
    with db.connection() as con:
        changed=con.execute("UPDATE reports SET state='processing',error=NULL,progress='Preparing staged analysis' WHERE id=? AND state NOT IN ('processing','complete')",(report_id,)).rowcount
    if changed:background.add_task(analyze,report_id)
    return status(report_id)

@app.post('/api/reports/{report_id}/reprocess')
def replay(report_id:str):
    row=get_report(report_id)
    if row['state']!='complete':raise HTTPException(409,'Complete extraction before replaying local policies.')
    try:reprocess(report_id)
    except ValueError as exc:raise HTTPException(400,str(exc))
    return status(report_id)

@app.get('/api/reports/{report_id}/status')
def status(report_id:str):
    row=get_report(report_id);document=document_for(report_id)
    row.pop('pages');row['result']=effective(report_id)
    row['page_count']=len(document['pages']);row['ocr_pages']=document['stats']['sparse_pages']
    row['document_stats']=document['stats'];row['pipeline_version']=VERSION
    row['plan']=build_plan(row['result'])
    with db.connection() as con:
        row['usage']=[dict(r) for r in con.execute('SELECT model,input_tokens,output_tokens,actual,reserved,state FROM usage WHERE report=?',(report_id,))]
        extraction=con.execute('SELECT origin,version FROM extractions WHERE report=?',(report_id,)).fetchone()
        row['extraction_origin']=dict(extraction) if extraction else None
        run=con.execute('SELECT * FROM runs WHERE report=? ORDER BY started DESC LIMIT 1',(report_id,)).fetchone()
        row['run']=dict(run) if run else None
        row['stages']=[dict(r) for r in con.execute('SELECT * FROM stages WHERE run=? ORDER BY id',(run['id'],))] if run else []
    row['evaluation']=evaluate(load_baseline(report_id),reference_for(report_id),row['state']=='complete')
    row['review_counts']={s:sum(f['review']['decision']==s for f in row['result']) for s in ['pending','accepted','rejected']}
    return row

@app.get('/api/reports/{report_id}/findings')
def findings(report_id:str):
    get_report(report_id);return effective(report_id)

@app.get('/api/reports/{report_id}/renovation-plan')
def renovation(report_id:str):return build_plan(findings(report_id))

@app.get('/api/reports/{report_id}/budget')
def get_budget(report_id:str):
    get_report(report_id)
    return budget.budget_data(report_id,build_plan(effective(report_id)))

@app.post('/api/reports/{report_id}/budget/preview')
def preview_budget(report_id:str,body:budget.Draft):
    get_report(report_id)
    try:return budget.calculate(body,build_plan(effective(report_id)))
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.put('/api/reports/{report_id}/budget')
def save_budget(report_id:str,body:budget.SaveBudget):
    get_report(report_id)
    try:return budget.save(report_id,body,build_plan(effective(report_id)))
    except ValueError as exc:raise HTTPException(409 if 'another view' in str(exc) else 422,str(exc))

@app.get('/api/reports/{report_id}/budget/history')
def budget_history(report_id:str):
    get_report(report_id)
    with db.connection() as con:
        rows=con.execute('SELECT revision,catalog_version,created,snapshot FROM budget_versions WHERE report=? ORDER BY revision DESC LIMIT 50',(report_id,)).fetchall()
    return [{**dict(row),'snapshot':json.loads(row['snapshot'])} for row in rows]

@app.get('/api/reports/{report_id}/budget/export')
def export_budget(report_id:str):
    get_report(report_id)
    data=budget.budget_data(report_id,build_plan(effective(report_id)))
    return Response(json.dumps(data,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="repair-budget.json"'})

@app.get('/api/reports/{report_id}/document')
def document_structure(report_id:str):
    get_report(report_id);doc=document_for(report_id)
    return {'version':doc['version'],'stats':doc['stats'],'pages':[{'page':p['page'],'role':p['role'],
              'needs_ocr':p['needs_ocr'],'blocks':len(p['blocks']),'references':[o['reference'] for o in p['observations']]} for p in doc['pages']],
            'observations':doc['observations']}

@app.get('/api/reports/{report_id}/pages/{page}/layout')
def page_layout(report_id:str,page:int):
    get_report(report_id);doc=document_for(report_id)
    if not 1<=page<=len(doc['pages']):raise HTTPException(404,'Page not found')
    return doc['pages'][page-1]

@app.get('/api/reports/{report_id}/pages/{page}')
def page_image(report_id:str,page:int,source_id:str=''):
    get_report(report_id)
    with pymupdf.open(db.DATA/(report_id+'.pdf')) as doc:
        if not 1<=page<=len(doc):raise HTTPException(404,'Page not found')
        p=doc[page-1]
        if source_id:
            sources=[s for f in load_baseline(report_id) for s in f['sources'] if s['id']==source_id and s['page']==page]
            if not sources:raise HTTPException(404,'Evidence source not found on this page')
            for box in sources[0]['boxes']:
                annot=p.add_highlight_annot(pymupdf.Rect(box));annot.set_colors(stroke=(0.92,0.75,0.15));annot.set_opacity(0.4);annot.update()
        return Response(p.get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).tobytes('png'),media_type='image/png')

@app.get('/api/reports/{report_id}/pdf')
def pdf(report_id:str):
    get_report(report_id);return FileResponse(db.DATA/(report_id+'.pdf'),media_type='application/pdf')

@app.patch('/api/reports/{report_id}/findings/{finding_id}/review')
def review(report_id:str,finding_id:str,body:Review):
    row=get_report(report_id)
    if row['state']!='complete':raise HTTPException(409,'Finish analysis before reviewing findings.')
    found=next((f for f in effective(report_id) if f['id']==finding_id),None)
    if not found:raise HTTPException(404,'Finding not found')
    if body.decision=='accepted' and not found['evidence_verified']:raise HTTPException(422,'Cannot accept a finding without a matching source quotation.')
    try:db.save_review(report_id,finding_id,body)
    except ValueError as exc:raise HTTPException(409,str(exc))
    return status(report_id)

@app.get('/api/reports/{report_id}/reviews')
def review_history(report_id:str):
    get_report(report_id)
    with db.connection() as con:
        return [{**dict(r),'changes':json.loads(r['changes'])} for r in con.execute('SELECT * FROM reviews WHERE report=? ORDER BY id',(report_id,))]

@app.get('/api/reports/{report_id}/evaluation')
def evaluation(report_id:str):
    row=get_report(report_id)
    return evaluate(load_baseline(report_id),reference_for(report_id),row['state']=='complete')

@app.get('/api/reports/{report_id}/reference')
def reference(report_id:str):
    get_report(report_id);fixture=reference_for(report_id)
    if not fixture:raise HTTPException(404,'No reference dataset for this exact document')
    return fixture

@app.get('/api/reports/{report_id}/annotations/export')
def annotations(report_id:str):
    row=get_report(report_id)
    payload={'report_sha256':report_id,'report':row['name'],'purpose':'Human review training/evaluation candidates. Not independent ground truth.',
             'findings':[{'id':f['id'],'sources':f['sources'],'original':f.get('original'),
                          'effective':{k:f[k] for k in ['title','description','location','priority','kind']},'review':f['review']} for f in effective(report_id)],
             'history':review_history(report_id)}
    return Response(json.dumps(payload,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="review-annotations.json"'})

@app.get('/api/reports/{report_id}/export')
def export(report_id:str,format:str='markdown'):
    r=status(report_id)
    r['repair_budget']=budget.budget_data(report_id,r['plan'])
    if format=='json':
        return Response(json.dumps(r,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="assessment-evidence.json"'})
    lines=['# HouseScope evidence assessment',r['name'],'',f'Pipeline: {VERSION}',
           'Priorities are rule-based suggestions. Scenarios are illustrative, not quotes. Rejected findings are excluded from planning.',
           f"Sparse/OCR pages: {r['ocr_pages']}",'']
    for f in r['result']:
        lines.extend([f"## {f['title']} — {f['priority']}",f"Review: {f['review']['decision']} · Revision {f['review']['revision']}",
                      f['description'],f"Priority policy: {f['priority_rule']} ({f.get('rule_version','')})",f"Flags: {', '.join(f['flags']) or 'none'}"])
        for s in f['sources']:lines.append(f"- PDF page {s['page']} / ref {s['reference'] or 'unavailable'}: {s['quote']} [matched={s['quote_matched']}, coordinates={s['geometry_matched']}]")
        lines.extend(['Inspector recommendation: '+f['inspector_recommendation'],'Buyer question: '+f['buyer_question'],'Review note: '+f['review']['note'],''])
    lines.extend(['## Shared repair scopes',''])
    for task in r['plan']['tasks']:
        lines.extend([f"### {task['title']}",task['action'],f"Depends on: {', '.join(task['depends_on']) or 'none'}",
                      f"Missing information: {', '.join(task['missing_information'])}"])

    estimate=r['repair_budget']['estimate'];settings=r['repair_budget']['draft']
    lines.extend(['','## Preliminary repair budget',f"Budget revision: {r['repair_budget']['revision']} · Catalog: {estimate['catalog_version']}",
                  f"Location label: {settings['location']} · User local factor: {settings['local_factor']} · Contingency: {settings['contingency_percent']}%",
                  f"Coverage: {estimate['complete_scopes']}/{estimate['total_scopes']} scopes marked covered. Partial: {estimate['is_partial']}."])
    if estimate['has_estimate']:
        t=estimate['totals'];lines.append(f"Selected-work budget: ${t['low']:,.2f}–${t['high']:,.2f}; arithmetic planning midpoint ${t['planning_midpoint']:,.2f}.")
    for item in estimate['rows']:
        lines.append(f"- {item['title']}: quantity {item['quantity']}, basis {item['quantity_basis']}; range {item['low']}–{item['high']} before adjustments. {item['custom_source'] if item['source_type']=='user_entered' else item['reference']['url'] if item['reference'] else 'No rate selected'}")
    lines.extend(['Method: '+estimate['method'],'Excluded: '+ '; '.join(estimate['exclusions'])])
    lines.extend(['','## Evaluation',json.dumps(r['evaluation'],indent=2)])
    return Response('\n'.join(lines),media_type='text/markdown',headers={'Content-Disposition':'attachment; filename="housescope-assessment.md"'})
