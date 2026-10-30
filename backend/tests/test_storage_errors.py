import importlib
import httpx
import pytest
from backend import artifacts,storage

def test_blank_bucket_uses_provisioned_default(monkeypatch):
    try:
        with monkeypatch.context() as env:
            env.setenv('SUPABASE_STORAGE_BUCKET','  ')
            importlib.reload(artifacts)
            assert artifacts.BUCKET=='housescope'
    finally:
        importlib.reload(artifacts)

def test_missing_bucket_error_is_actionable_without_exposing_upstream_data(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL','https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SECRET_KEY','test-only-secret')
    def respond(request):
        return httpx.Response(400,json={'statusCode':'404','error':'InvalidRequest','message':'Bucket not found','untrusted':'test-only-secret'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(artifacts,'_client',client)
        with pytest.raises(storage.StorageNotConfigured) as caught:
            artifacts.signed_upload('incoming/test.pdf')
    assert 'SUPABASE_STORAGE_BUCKET=housescope' in str(caught.value)
    assert 'test-only-secret' not in str(caught.value)
