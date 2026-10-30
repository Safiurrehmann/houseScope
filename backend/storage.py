"""SQLite persistence, append-only review history, and per-request budget reservations."""
import json,os,sqlite3,time
from contextlib import contextmanager
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.getenv('HOUSESCOPE_DATA_DIR',str(ROOT/'data')))
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'housescope.sqlite'

@contextmanager
def connection():
    con=sqlite3.connect(DB,timeout=30);con.row_factory=sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def initialize():
    with connection() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,name TEXT,pages TEXT,state TEXT,progress TEXT,result TEXT,error TEXT,created REAL,elapsed REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS usage(id INTEGER PRIMARY KEY,report TEXT,model TEXT,reserved REAL,actual REAL,input_tokens INTEGER,output_tokens INTEGER,state TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS documents(report TEXT PRIMARY KEY,version TEXT,artifact TEXT);
        CREATE TABLE IF NOT EXISTS extractions(report TEXT PRIMARY KEY,payload TEXT,version TEXT,origin TEXT);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,report TEXT,version TEXT,state TEXT,started REAL,ended REAL);
        CREATE TABLE IF NOT EXISTS stages(id INTEGER PRIMARY KEY,run TEXT,name TEXT,state TEXT,detail TEXT,started REAL,ended REAL);
        CREATE TABLE IF NOT EXISTS budget_versions(id INTEGER PRIMARY KEY,report TEXT,revision INTEGER,payload TEXT,snapshot TEXT,catalog_version TEXT,created REAL,UNIQUE(report,revision));
        CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,report TEXT,finding TEXT,revision INTEGER,decision TEXT,note TEXT,changes TEXT,created REAL,UNIQUE(report,finding,revision));
        ''')

def get_report(report_id):
    with connection() as con:row=con.execute('SELECT * FROM reports WHERE id=?',(report_id,)).fetchone()
    return dict(row) if row else None

def update(report_id,**values):
    with connection() as con:con.execute('UPDATE reports SET '+','.join(k+'=?' for k in values)+' WHERE id=?',[*values.values(),report_id])

def reviews_for(report_id):
    with connection() as con:rows=con.execute('SELECT * FROM reviews WHERE report=? ORDER BY revision,id',(report_id,)).fetchall()
    latest={}
    for row in rows:
        r=dict(row);r['changes']=json.loads(r['changes']);latest[r['finding']]=r
    return latest

def reserve(report_id,amount,budget,model):
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        total=con.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM usage').fetchone()[0]
        if total+amount>budget:raise ValueError('Project API budget reached. No further request was sent.')
        return con.execute('INSERT INTO usage(report,model,reserved,state,created) VALUES(?,?,?,?,?)',(report_id,model,amount,'reserved',time.time())).lastrowid

def save_review(report_id,finding_id,review):
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        old=con.execute('SELECT MAX(revision) FROM reviews WHERE report=? AND finding=?',(report_id,finding_id)).fetchone()[0] or 0
        if old!=review.expected_revision:raise ValueError('Review changed in another view. Reload the report before saving.')
        previous=con.execute('SELECT changes FROM reviews WHERE report=? AND finding=? ORDER BY revision DESC LIMIT 1',(report_id,finding_id)).fetchone()
        changes=json.loads(previous['changes']) if previous else {}
        changes.update({k:getattr(review,k) for k in ['title','description','location','priority','kind'] if getattr(review,k) is not None})
        con.execute('INSERT INTO reviews(report,finding,revision,decision,note,changes,created) VALUES(?,?,?,?,?,?,?)',
                    (report_id,finding_id,old+1,review.decision,review.note,json.dumps(changes),time.time()))
