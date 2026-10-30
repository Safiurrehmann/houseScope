import json
import pytest
from pydantic import ValidationError
from backend import budget,storage as db

PLAN={'tasks':[{'id':'electric','category':'electrical_evaluation','title':'Electrical evaluation','priority':'Safety'},
               {'id':'drain','category':'drainage','title':'Drainage correction','priority':'Planned'}]}

def test_quantity_adjustment_contingency_and_partial_scope():
    draft=budget.Draft(local_factor=1.2,contingency_percent=10,fees_allowance=50,covered_scopes=['electric'],
                       lines=[budget.Line(id='e',task_id='electric',rate_id='electrical_visit',quantity=1,quantity_basis='quoted')])
    result=budget.calculate(draft,PLAN)
    assert result['totals']['low']==182 and result['totals']['high']==314
    assert result['totals']['planning_midpoint']==248
    assert result['complete_scopes']==1 and result['is_partial']
    assert result['missing_scopes']==['drain']

def test_unknown_material_only_and_stale_items_never_cover_plan():
    draft=budget.Draft(covered_scopes=['drain'],lines=[
        budget.Line(id='material',task_id='drain',rate_id='downspout_extension_material',quantity=2),
        budget.Line(id='missing',task_id='electric',rate_id='gfci_replacement',quantity=None),
        budget.Line(id='obsolete',task_id='removed',rate_id='electrical_visit',quantity=100)])
    result=budget.calculate(draft,PLAN)
    assert result['totals']['base_low']==10 and result['totals']['base_high']==40
    assert result['complete_scopes']==0 and len(result['stale_items'])==1
    assert result['scopes'][1]['reason']=='Materials only; installation missing'
    assert result['rows'][1]['low'] is None
    with pytest.raises(ValidationError):
        budget.Draft(lines=[budget.Line(id='one',task_id='electric',rate_id='electrical_visit',quantity=1),budget.Line(id='two',task_id='electric',rate_id='electrical_visit',quantity=1)])
    with pytest.raises(ValidationError):budget.Line(id='bad',task_id='electric',custom_low=100,custom_high=50)

def test_custom_quote_revision_snapshot_and_export(tmp_path,monkeypatch):
    from backend.main import app,register_pdf
    from fastapi.testclient import TestClient
    import pymupdf
    monkeypatch.setattr(db,'DATA',tmp_path);monkeypatch.setattr(db,'DB',tmp_path/'budget.sqlite');db.initialize()
    pdf=pymupdf.open();pdf.new_page().insert_text((50,50),'Test inspection report, no defects identified.');content=pdf.tobytes();pdf.close()
    rid=register_pdf(content,'test.pdf')['id']
    # Unknown scope is intentionally excluded by the HTTP export's current empty plan.
    draft=budget.Draft(lines=[budget.Line(id='quote',task_id='electric',rate_id='custom',quantity=1,quantity_basis='quoted',
                                         description='Electrical repair quote',custom_low=500,custom_high=750,custom_source='Local contractor quote dated 2026-10-30')])
    saved=budget.save(rid,budget.SaveBudget(expected_revision=0,draft=draft),PLAN)
    assert saved['revision']==1 and saved['estimate']['totals']['low']==575
    with pytest.raises(ValueError,match='another view'):budget.save(rid,budget.SaveBudget(expected_revision=0,draft=draft),PLAN)
    with db.connection() as con:
        snapshot=json.loads(con.execute('SELECT snapshot FROM budget_versions').fetchone()[0])
        assert snapshot['totals']['high']==862.5
    with TestClient(app) as client:
        exported=client.get(f'/api/reports/{rid}/budget/export')
        assert exported.status_code==200 and exported.json()['revision']==1
        assert exported.json()['estimate']['has_estimate'] is False
