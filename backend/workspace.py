"""Anonymous browser workspaces authenticated by the server-side frontend gateway."""
import hashlib,hmac,os,time
from contextvars import ContextVar
from . import storage as db
owner=ContextVar('workspace',default='local')

def verify(token):
    try:
        identity,expires,signature=token.split('.')
        if len(identity)!=32 or any(c not in '0123456789abcdef' for c in identity) or int(expires)<time.time():return None
        key=os.getenv('HOUSESCOPE_SESSION_SECRET') or os.environ['SUPABASE_SECRET_KEY']
        expected=hmac.new(key.encode(),('housescope:'+identity+'.'+expires).encode(),hashlib.sha256).hexdigest()
        return identity if hmac.compare_digest(signature,expected) else None
    except (ValueError,KeyError):return None
