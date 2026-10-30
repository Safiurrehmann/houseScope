"""Source-based quantity takeoff and user-entered quotes; no model-generated dollar amounts."""
import json,time
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from typing import List,Literal,Optional
from pydantic import BaseModel,ConfigDict,Field,model_validator
from . import storage as db

CATALOG=json.loads((Path(__file__).parent/'cost_catalog.json').read_text())
RATES={r['id']:r for r in CATALOG['rates']}

def decimal(value):return Decimal(str(value))
def currency(value):return float(decimal(value).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))

class Line(BaseModel):
    model_config=ConfigDict(allow_inf_nan=False)
    id:str=Field(min_length=1,max_length=100)
    task_id:str=Field(min_length=1,max_length=100)
    rate_id:str=Field(default='',max_length=80)
    quantity:Optional[float]=Field(default=None,gt=0,le=1_000_000)
    quantity_basis:Literal['assumed','measured','quoted']='assumed'
    description:str=Field(default='',max_length=300)
    custom_low:Optional[float]=Field(default=None,ge=0,le=10_000_000)
    custom_high:Optional[float]=Field(default=None,ge=0,le=10_000_000)
    custom_source:str=Field(default='',max_length=1000)
    note:str=Field(default='',max_length=1500)
    @model_validator(mode='after')
    def valid_range(self):
        if self.custom_low is not None and self.custom_high is not None and self.custom_low>self.custom_high:
            raise ValueError('Low rate cannot exceed high rate.')
        return self

class Draft(BaseModel):
    model_config=ConfigDict(allow_inf_nan=False)
    location:str=Field(default='US national baseline',max_length=150)
    local_factor:float=Field(default=1,ge=0.5,le=3)
    contingency_percent:float=Field(default=15,ge=0,le=50)
    fees_allowance:float=Field(default=0,ge=0,le=1_000_000)
    covered_scopes:List[str]=Field(default_factory=list,max_length=150)
    lines:List[Line]=Field(default_factory=list,max_length=200)
    @model_validator(mode='after')
    def unique_items(self):
        ids=[r.id for r in self.lines]
        if len(ids)!=len(set(ids)):raise ValueError('Budget line IDs must be unique.')
        keys=[(r.task_id,r.rate_id) for r in self.lines if r.rate_id and r.rate_id!='custom']
        if len(keys)!=len(set(keys)):raise ValueError('Use one row per reference work item in a scope; increase its quantity instead of adding duplicate rows.')
        return self

class SaveBudget(BaseModel):
    expected_revision:int=Field(ge=0)
    draft:Draft

def default_draft(plan):
    lines=[]
    for task in plan['tasks']:
        selected={'electrical_evaluation':'electrical_visit','roof_repair':'roof_cleaning','drainage':'gutter_cleaning'}.get(task['category'])
        if selected:
            lines.append(Line(id='suggested-'+task['id'],task_id=task['id'],rate_id=selected,quantity=1,
                              note='Suggested one-project/visit assumption. Confirm work type and quantity; this may cover only part of the scope.'))
    return Draft(lines=lines)

def calculate(draft,plan):
    tasks={t['id']:t for t in plan['tasks']};rows=[];stale=[];warnings=[]
    total_low=Decimal(0);total_high=Decimal(0)
    for item in draft.lines:
        if item.task_id not in tasks:
            stale.append(item.model_dump());continue
        rate=RATES.get(item.rate_id)
        if item.rate_id not in ['', 'custom'] and not rate:raise ValueError('Unknown cost reference: '+item.rate_id)
        if rate and tasks[item.task_id]['category'] not in rate['categories']:raise ValueError('Selected reference does not match this repair scope.')
        custom=item.rate_id=='custom'
        low=item.custom_low if custom else rate['low'] if rate else None
        high=item.custom_high if custom else rate['high'] if rate else None
        incomplete=[]
        if not rate and not custom:incomplete.append('Select a reference or custom rate')
        if item.quantity is None:incomplete.append('Enter quantity')
        if custom and (low is None or high is None):incomplete.append('Enter low and high custom unit rates')
        if custom and not item.description.strip():incomplete.append('Describe the custom work')
        if custom and not item.custom_source.strip():incomplete.append('Record the quote or pricing assumption source')
        if rate and rate['unit']!='sq ft' and item.quantity is not None and not float(item.quantity).is_integer():
            raise ValueError('Use a whole number of '+rate['unit']+' units.')
        row={**item.model_dump(),'title':item.description.strip() or (rate['title'] if rate else 'Unspecified work'),
             'unit':rate['unit'] if rate else 'unit','unit_low':low,'unit_high':high,'reference':rate,
             'source_type':'user_entered' if custom else 'published_reference','coverage':rate['coverage'] if rate else 'user_defined',
             'incomplete':incomplete,'low':None,'high':None}
        if not incomplete:
            row['low']=currency(decimal(item.quantity)*decimal(low));row['high']=currency(decimal(item.quantity)*decimal(high))
            total_low+=decimal(row['low']);total_high+=decimal(row['high'])
            if item.quantity_basis=='assumed':warnings.append('Assumed quantity: '+row['title'])
            if rate and rate['coverage']=='materials_only':warnings.append('Installation labor is missing from '+row['title'])
        rows.append(row)
    scope_rows=[]
    for task in plan['tasks']:
        selected=[r for r in rows if r['task_id']==task['id']]
        priced=[r for r in selected if not r['incomplete']]
        confirmed=task['id'] in draft.covered_scopes
        materials_only=bool(priced) and all(r['coverage']=='materials_only' for r in priced)
        complete=bool(priced) and all(not r['incomplete'] for r in selected) and confirmed and not materials_only
        scope_rows.append({'id':task['id'],'title':task['title'],'priority':task['priority'],'marked_covered':confirmed,
                           'complete':complete,'priced_lines':len(priced),'total_lines':len(selected),
                           'low':currency(sum(decimal(r['low']) for r in priced)) if priced else None,
                           'high':currency(sum(decimal(r['high']) for r in priced)) if priced else None,
                           'reason':'Covered by your stated scope assumption' if complete else 'Materials only; installation missing' if materials_only else 'No complete priced work items' if not priced else 'Confirm that the selected items cover the full scope' if not confirmed else 'Some selected rows still need inputs'})
        if any(r['rate_id']=='electrical_visit' for r in priced) and any(r['rate_id']=='gfci_replacement' for r in priced):
            warnings.append('Electrician service-call and installed-outlet rates may overlap. Confirm whether the diagnostic fee is credited before adding both.')
    if draft.local_factor!=1 and any(r['source_type']=='user_entered' and not r['incomplete'] for r in rows):
        warnings.append('Your local factor also scales custom quotes. Use 1.00 if those rates already reflect local pricing.')
    if stale:warnings.append(f'{len(stale)} saved items belong to scopes no longer in the plan and are excluded from totals.')
    adjusted_low=currency(total_low*decimal(draft.local_factor));adjusted_high=currency(total_high*decimal(draft.local_factor))
    contingency_low=currency(decimal(adjusted_low)*decimal(draft.contingency_percent)/100)
    contingency_high=currency(decimal(adjusted_high)*decimal(draft.contingency_percent)/100)
    low=currency(decimal(adjusted_low)+decimal(contingency_low)+decimal(draft.fees_allowance))
    high=currency(decimal(adjusted_high)+decimal(contingency_high)+decimal(draft.fees_allowance))
    has_estimate=any(not r['incomplete'] for r in rows)
    missing=[s for s in scope_rows if not s['complete']]
    return {'catalog_version':CATALOG['version'],'checked_at':CATALOG['checked_at'],'rows':rows,'scopes':scope_rows,'stale_items':stale,
            'has_estimate':has_estimate,'is_partial':bool(missing),'complete_scopes':len(scope_rows)-len(missing),
            'total_scopes':len(scope_rows),'missing_scopes':[s['id'] for s in missing],
            'totals':{'base_low':currency(total_low),'base_high':currency(total_high),'adjusted_low':adjusted_low,'adjusted_high':adjusted_high,
                      'contingency_low':contingency_low,'contingency_high':contingency_high,'fees_allowance':draft.fees_allowance,
                      'low':low,'high':high,'planning_midpoint':currency((decimal(low)+decimal(high))/2)},
            'by_priority':[{'priority':p,'low':currency(sum(decimal(s['low'] or 0) for s in scope_rows if s['priority']==p)),
                            'high':currency(sum(decimal(s['high'] or 0) for s in scope_rows if s['priority']==p))} for p in ['Safety','Urgent','Planned','Cosmetic']],
            'warnings':list(dict.fromkeys(warnings)),
            'method':'Sum quantity × unit range once per selected work item; apply your local factor, then contingency, then the separate fee allowance. No automatic visit fee, tax, markup or bundling discount is added. Midpoint is arithmetic, not a statistical expected cost.',
            'exclusions':['Unpriced or incomplete scope','Concealed damage and scope changes','Taxes, permits and disposal unless covered by your allowance','Unselected work and actual contractor minimums not stated in the selected reference']}

def latest(report_id):
    with db.connection() as con:row=con.execute('SELECT * FROM budget_versions WHERE report=? ORDER BY revision DESC LIMIT 1',(report_id,)).fetchone()
    return dict(row) if row else None

def budget_data(report_id,plan):
    saved=latest(report_id)
    draft=Draft.model_validate_json(saved['payload']) if saved else default_draft(plan)
    return {'revision':saved['revision'] if saved else 0,'updated':saved['created'] if saved else None,
            'catalog':CATALOG,'draft':draft.model_dump(),'estimate':calculate(draft,plan)}

def save(report_id,body,plan):
    calculated=calculate(body.draft,plan)
    with db.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        current=con.execute('SELECT MAX(revision) FROM budget_versions WHERE report=?',(report_id,)).fetchone()[0] or 0
        if body.expected_revision!=current:raise ValueError('Budget changed in another view. Reload it before saving.')
        # Snapshot rates and outputs so a later catalog update does not rewrite historical estimates.
        con.execute('INSERT INTO budget_versions(report,revision,payload,snapshot,catalog_version,created) VALUES(?,?,?,?,?,?)',
                    (report_id,current+1,body.draft.model_dump_json(),json.dumps(calculated),CATALOG['version'],time.time()))
    return budget_data(report_id,plan)
