"""Private durable object storage; local files are used only in SQLite mode."""
import json,os,uuid
from urllib.parse import quote
import httpx
from . import storage as db

BUCKET=(os.getenv('SUPABASE_STORAGE_BUCKET') or '').strip() or 'housescope'
MAX_FILE=25*1024*1024
_client=httpx.Client(timeout=45)

def request(method,path,**kwargs):
    allow_missing=kwargs.pop('allow_missing',False)
    secret=os.getenv('SUPABASE_SECRET_KEY','')
    headers={'apikey':secret,'Authorization':'Bearer '+secret,**kwargs.pop('headers',{})}
    try:
        response=_client.request(method,os.environ['SUPABASE_URL'].rstrip('/')+'/storage/v1/'+path,
                               headers=headers,timeout=45,**kwargs)
        if allow_missing and response.status_code in (400,404): return response
        if response.status_code>=400:
            try: failure=response.json()
            except ValueError: failure={}
            # Only map known errors to fixed messages. Never expose upstream payloads,
            # credentials, signed tokens, or internal object paths to the browser.
            message=str(failure.get('message','')).casefold()
            if 'bucket not found' in message:
                raise db.StorageNotConfigured('Supabase Storage bucket not found. Set SUPABASE_STORAGE_BUCKET=housescope and ensure SUPABASE_URL points to the project provisioned with scripts/setup_supabase.py.')
            if any(reason in message for reason in ['invalid jwt','invalid api key','signature verification failed','invalid signature']):
                raise db.StorageNotConfigured('Supabase Storage rejected the server key. Check SUPABASE_SECRET_KEY belongs to the SUPABASE_URL project; use a server secret or service-role key.')
            raise db.StorageNotConfigured('Supabase Storage request failed (HTTP '+str(response.status_code)+'). Check the server secret and private bucket setup.')
        return response
    except httpx.HTTPError:
        raise db.StorageNotConfigured('Supabase Storage is unavailable. Retry after checking connectivity.') from None

def object_path(path): return quote(BUCKET+'/'+str(path.relative_to(db.DATA)),safe='/')

def write(path,content,kind='application/json'):
    if db.cloud():
        request('POST','object/'+object_path(path),content=content,headers={'Content-Type':kind,'x-upsert':'true'})
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(content);temp.replace(path)

def read(path):
    if db.cloud(): return request('GET','object/authenticated/'+object_path(path)).content
    return path.read_bytes()

def exists(path):
    if not db.cloud(): return path.exists()
    return request('HEAD','object/'+object_path(path),allow_missing=True).is_success

def write_json(path,value): write(path,json.dumps(value).encode())
def read_json(path): return json.loads(read(path))

def signed_download(path):
    data=request('POST','object/sign/'+object_path(path),json={'expiresIn':60}).json()
    return os.environ['SUPABASE_URL'].rstrip('/')+'/storage/v1'+data['signedURL']

def signed_upload(key):
    data=request('POST','object/upload/sign/'+quote(BUCKET+'/'+key,safe='/'),json={}).json()
    return os.environ['SUPABASE_URL'].rstrip('/')+'/storage/v1'+data['url']
