"""SQLite/Postgres persistence with transactional review and spending reservations."""
import json,os,sqlite3,time,threading
from contextlib import contextmanager
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.getenv('HOUSESCOPE_DATA_DIR',str(ROOT/'data')))
DB=DATA/'housescope.sqlite'

class StorageNotConfigured(RuntimeError):
    pass

def cloud():
    return os.getenv('HOUSESCOPE_STORAGE', 'supabase' if os.getenv('VERCEL') else 'sqlite') == 'supabase'

class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)

class Cursor:
    def __init__(self, cursor, returned=False):
        self.cursor=cursor; self.rowcount=cursor.rowcount
        self.lastrowid=cursor.fetchone()['id'] if returned else None
    def fetchone(self):
        row=self.cursor.fetchone(); return Row(row) if row else None
    def fetchall(self): return [Row(r) for r in self.cursor.fetchall()]
    def __iter__(self): return iter(self.fetchall())

class Postgres:
    def __init__(self, con): self.con=con
    def execute(self, sql, params=()):
        if sql.strip().upper()=='BEGIN IMMEDIATE':
            return Cursor(self.con.execute('SELECT pg_advisory_xact_lock(746812903)'))
        returned=sql.lstrip().upper().startswith(tuple('INSERT INTO '+t.upper()+'(' for t in ['usage','stages','reviews','budget_versions']))
        sql=sql.replace('?', '%s')
        if returned: sql+=' RETURNING id'
        return Cursor(self.con.execute(sql,params),returned)

_pool=None
_pool_lock=threading.Lock()

def postgres_pool():
    global _pool
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row
    with _pool_lock:
        if _pool is None:
            _pool=ConnectionPool(os.environ['DATABASE_URL'],min_size=0,max_size=3,timeout=12,
                kwargs={'connect_timeout':10,'sslmode':'verify-full','sslrootcert':str(ROOT/'backend/supabase-ca.crt'),
                        'prepare_threshold':None,'row_factory':dict_row},open=True)
    return _pool

@contextmanager
def postgres_connection():
    import psycopg
    from psycopg_pool import PoolTimeout
    try:
        with postgres_pool().connection() as con:
            with con.transaction():
                con.execute('SET LOCAL search_path TO housescope')
                con.execute("SET LOCAL statement_timeout = '25s'")
                yield Postgres(con)
    except (PoolTimeout,psycopg.OperationalError,psycopg.errors.UndefinedTable,psycopg.errors.InvalidSchemaName,psycopg.errors.QueryCanceled):
        raise StorageNotConfigured('Supabase database is unavailable or not provisioned. Check the pooler DATABASE_URL and run scripts/setup_supabase.py.') from None

def storage_configured():
    # No ephemeral fallback: losing this ledger would also reset spending limits.
    return all(os.getenv(k) for k in ['DATABASE_URL','SUPABASE_URL','SUPABASE_SECRET_KEY']) if cloud() else not os.getenv('VERCEL')

@contextmanager
def connection():
    if not storage_configured():
        raise StorageNotConfigured('Durable backend storage is not configured. Vercel Services routing does not persist local SQLite, uploads or the spending ledger. Configure a durable storage adapter before enabling analysis; /tmp is not a production solution.')
    if cloud():
        with postgres_connection() as con: yield con
        return
    DATA.mkdir(parents=True,exist_ok=True)
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
    if not storage_configured():
        return
    if cloud(): return # Provision explicitly with scripts/setup_supabase.py, never on cold starts.
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
    with connection() as con:
        columns={r['name'] for r in con.execute('PRAGMA table_info(reports)')}
        for name,typ in [('owner',"TEXT DEFAULT 'local'"),('document_hash','TEXT'),('lease_until','REAL DEFAULT 0')]:
            if name not in columns: con.execute('ALTER TABLE reports ADD COLUMN '+name+' '+typ)


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
