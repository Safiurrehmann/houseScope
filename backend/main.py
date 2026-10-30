"""Local API for document intelligence, review, evaluation and trace exports."""
import hashlib,json,os,time,uuid
from contextlib import asynccontextmanager
from pathlib import Path
import pymupdf
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
from fastapi import BackgroundTasks,FastAPI,File,HTTPException,UploadFile
from fastapi.responses import FileResponse,Response,JSONResponse,RedirectResponse
from pydantic import BaseModel,Field
from . import artifacts,workspace
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
    if not db.storage_configured() or db.cloud():
        yield
        return
    with db.connection() as con:
        con.execute("UPDATE reports SET state='failed',error='Server restarted. Resume to use completed extraction checkpoints.' WHERE state='processing'")
        con.execute("UPDATE runs SET state='interrupted',ended=? WHERE state='running'",(time.time(),))
        con.execute("UPDATE stages SET state='interrupted',ended=? WHERE state='running'",(time.time(),))
    yield
app=FastAPI(title='HouseScope · Evidence pipeline',lifespan=lifespan)

@app.middleware('http')
async def workspace_scope(request,call_next):
    identity='local'
    if db.cloud():
        identity=workspace.verify(request.headers.get('x-housescope-workspace',''))
        if not identity:return JSONResponse(status_code=401,content={'detail':'Open HouseScope through its frontend to establish a workspace.'})
    token=workspace.owner.set(identity)
    try:return await call_next(request)
    finally:workspace.owner.reset(token)

@app.exception_handler(db.StorageNotConfigured)
async def storage_unavailable(request, exc):
    return JSONResponse(status_code=503,content={'detail':str(exc)})

def get_report(report_id):
    row=db.get_report(report_id)
    if not row or row['owner']!=workspace.owner.get():raise HTTPException(404,'Report not found')
    return row

def effective(report_id):
    return apply_reviews(load_baseline(report_id),db.reviews_for(report_id))

@app.get('/api/health')
def health():
    with db.connection() as con:
        spent=con.execute('SELECT COALESCE(SUM(actual),0) FROM usage').fetchone()[0]
        committed=con.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM usage').fetchone()[0]
    return {'ready':bool(os.getenv('OPENAI_API_KEY')),'model':MODEL,'budget':BUDGET,'spent':spent,
            'committed':committed,'remaining':max(0,BUDGET-committed),'pipeline_version':VERSION,'direct_uploads':db.cloud(),'request_driven':db.cloud()}

@app.get('/api/reports')
def reports():
    with db.connection() as con:return [dict(r) for r in con.execute('SELECT id,name,state,created FROM reports WHERE owner=? ORDER BY created DESC',(workspace.owner.get(),))]

def register_pdf(content,name):
    if len(content)>25*1024*1024:raise HTTPException(413,'Maximum file size is 25 MB')
    if not content.startswith(b'%PDF-'):raise HTTPException(400,'Please upload a valid PDF')
    document_hash=hashlib.sha256(content).hexdigest()
    report_id=hashlib.sha256((workspace.owner.get()+':'+document_hash).encode()).hexdigest() if db.cloud() else document_hash
    try:
        with pymupdf.open(stream=content,filetype='pdf') as doc:
            if doc.needs_pass or not 1<=len(doc)<=150:raise ValueError('Use an unlocked PDF with 1–150 pages')
    except Exception as exc:raise HTTPException(400,str(exc) if isinstance(exc,ValueError) else 'The PDF could not be opened')
    path=db.DATA/(report_id+'.pdf')
    if not artifacts.exists(path):artifacts.write(path,content,'application/pdf')
    with db.connection() as con:
        con.execute('INSERT INTO reports(id,name,pages,state,progress,created,owner,document_hash) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING',
                    (report_id,Path(name).name,'[]','uploaded','Document indexed; ready for extraction',time.time(),workspace.owner.get(),document_hash))
    document_for(report_id)
    return status(report_id)

@app.post('/api/reports')
async def upload(file:UploadFile=File(...)):
    return register_pdf(await file.read(25*1024*1024+1),file.filename or 'Inspection.pdf')

@app.post('/api/samples/kentucky')
def sample():
    path=db.ROOT/'fixtures/peirson-kentucky-sample.pdf'
    if path.exists():content=path.read_bytes()
    else:
        import httpx
        try:
            parts=[];size=0
            with httpx.stream('GET','https://peirsoninspections.com/sample-inspection-report.pdf',timeout=40,follow_redirects=True) as response:
                response.raise_for_status()
                for part in response.iter_bytes():
                    size+=len(part)
                    if size>artifacts.MAX_FILE:raise ValueError('Sample too large')
                    parts.append(part)
            content=b''.join(parts)
            if hashlib.sha256(content).hexdigest()!='4dbfa8ffba743e3e410dec9846f64d1dbb81f4ee9bcbc973c555391aff64c40c':raise ValueError('Sample changed')
        except Exception:raise HTTPException(502,'Public sample unavailable or changed. Upload your own inspection PDF.') from None
    return register_pdf(content,'Kentucky · Public inspection sample.pdf')

@app.post('/api/reports/{report_id}/analyze')
def start(report_id:str,background:BackgroundTasks):
    row=get_report(report_id)
    if row['state']=='complete':return status(report_id)
    if row['state']=='processing' and (not db.cloud() or row['lease_until']>time.time()):return status(report_id)
    if not os.getenv('OPENAI_API_KEY'):raise HTTPException(400,'Add OPENAI_API_KEY to the root .env and restart the backend.')
    with db.connection() as con:
        if db.cloud():
            con.execute('BEGIN IMMEDIATE')
            con.execute("UPDATE reports SET state='failed',lease_until=0 WHERE id=? AND state='processing' AND lease_until<?",(report_id,time.time()))
        changed=con.execute("UPDATE reports SET state='processing',error=NULL,progress='Preparing staged analysis' WHERE id=? AND state NOT IN ('processing','complete')",(report_id,)).rowcount
    if changed and not db.cloud():background.add_task(analyze,report_id)
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
    with pymupdf.open(stream=artifacts.read(db.DATA/(report_id+'.pdf')),filetype='pdf') as doc:
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
    get_report(report_id)
    path=db.DATA/(report_id+'.pdf')
    if db.cloud():return RedirectResponse(artifacts.signed_download(path),status_code=307)
    return FileResponse(path,media_type='application/pdf')

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


@app.post('/api/reports/{report_id}/advance')
def advance(report_id:str):
    row=get_report(report_id)
    if not db.cloud() or row['state']!='processing':return status(report_id)
    now=time.time()
    with db.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT state,lease_until FROM reports WHERE id=?',(report_id,)).fetchone()
        if row['state']!='processing':pass
        elif row['lease_until']>now:pass
        elif row['lease_until']:
            con.execute("UPDATE reports SET state='failed',error='A section was interrupted. Resume explicitly; its spending reservation is retained.',lease_until=0 WHERE id=?",(report_id,))
        else:
            con.execute('UPDATE reports SET lease_until=? WHERE id=?',(now+360,report_id))
            row=None
    if row is not None:return status(report_id)
    try:analyze(report_id,max_calls=1)
    finally:db.update(report_id,lease_until=0)
    return status(report_id)

class UploadTicket(BaseModel):
    name:str=Field(min_length=1,max_length=255)
    size:int=Field(gt=0,le=25*1024*1024)

class ImportTicket(BaseModel):
    ticket:str=Field(pattern=r'^[0-9a-f]{32}$')

@app.post('/api/uploads')
def create_upload(body:UploadTicket):
    if not db.cloud():raise HTTPException(400,'Use multipart upload in local mode.')
    ticket=uuid.uuid4().hex;key='incoming/'+workspace.owner.get()+'/'+ticket+'.pdf'
    url=artifacts.signed_upload(key)
    with db.connection() as con:
        con.execute('INSERT INTO upload_tickets(id,owner,path,name,created) VALUES(?,?,?,?,?)',
                    (ticket,workspace.owner.get(),key,Path(body.name).name,time.time()))
    return {'ticket':ticket,'url':url}

@app.post('/api/reports/import')
def import_upload(body:ImportTicket):
    if not db.cloud():raise HTTPException(400,'Use multipart upload in local mode.')
    with db.connection() as con:
        ticket=con.execute('SELECT * FROM upload_tickets WHERE id=? AND owner=?',(body.ticket,workspace.owner.get())).fetchone()
    if not ticket:raise HTTPException(404,'Upload ticket not found')
    if ticket['report']:return status(ticket['report'])
    if ticket['created']<time.time()-3600:raise HTTPException(410,'Upload expired. Select the PDF again.')
    result=register_pdf(artifacts.read(db.DATA/ticket['path']),ticket['name'])
    with db.connection() as con:con.execute('UPDATE upload_tickets SET report=? WHERE id=?',(result['id'],body.ticket))
    return result
