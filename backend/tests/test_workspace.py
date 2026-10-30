"""Gateway proofs must be signed, unexpired and scoped to one browser identity."""
import hashlib,hmac,time
from backend import workspace

def test_workspace_proof_rejects_tampering_expiry_and_key_rotation(monkeypatch):
    monkeypatch.setenv('HOUSESCOPE_SESSION_SECRET','test-only-key')
    identity='a'*32
    def token(expires,key='test-only-key'):
        value=identity+'.'+str(expires)
        return value+'.'+hmac.new(key.encode(),('housescope:'+value).encode(),hashlib.sha256).hexdigest()
    valid=token(int(time.time())+60)
    assert workspace.verify(valid)==identity
    assert workspace.verify(valid.replace(identity,'b'*32)) is None
    assert workspace.verify(token(int(time.time())-1)) is None
    assert workspace.verify(token(int(time.time())+60,'different-key')) is None
    assert workspace.verify('malformed') is None
