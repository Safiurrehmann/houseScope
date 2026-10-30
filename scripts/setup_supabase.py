"""Idempotent provisioning. Reads ignored .env; never prints credentials."""
import os,sys,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
import psycopg
from backend import artifacts,storage as db

def main():
    required=['DATABASE_URL','SUPABASE_URL','SUPABASE_SECRET_KEY']
    if any(not os.getenv(k) for k in required):raise ValueError('Fill DATABASE_URL, SUPABASE_URL and SUPABASE_SECRET_KEY in .env first.')
    with psycopg.connect(os.environ['DATABASE_URL'],connect_timeout=10,sslmode='verify-full',sslrootcert=str(db.ROOT/'backend/supabase-ca.crt'),prepare_threshold=None) as con:
        con.execute('SELECT pg_advisory_xact_lock(746812903)')
        con.execute((db.ROOT/'supabase/migrations/001_housescope.sql').read_text(),prepare=False)
        # Preserve the project-wide $5 limit when moving from the existing local demo.
        if db.DB.exists():
            with sqlite3.connect(db.DB) as local:
                spent=local.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM usage').fetchone()[0]
            con.execute("INSERT INTO usage(id,report,model,reserved,actual,state,created) VALUES(-1,'local-budget-carryover','historical',%s,%s,'completed',0) ON CONFLICT(id) DO UPDATE SET actual=GREATEST(usage.actual,excluded.actual),reserved=GREATEST(usage.reserved,excluded.reserved)",(spent,spent))
    buckets=artifacts.request('GET','bucket').json()
    if not any(b['id']==artifacts.BUCKET for b in buckets):
        artifacts.request('POST','bucket',json={'id':artifacts.BUCKET,'name':artifacts.BUCKET,'public':False,'file_size_limit':artifacts.MAX_FILE,'allowed_mime_types':['application/pdf','application/json']})
    else:
        artifacts.request('PUT','bucket/'+artifacts.BUCKET,json={'public':False,'file_size_limit':artifacts.MAX_FILE,'allowed_mime_types':['application/pdf','application/json']})
    print('Supabase private schema and storage bucket ready. Local spending carryover preserved; no model calls made.')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Setup failed ('+type(exc).__name__+'). Check the pooler DATABASE_URL and server secret. Credentials were not displayed.',file=sys.stderr)
        sys.exit(1)
