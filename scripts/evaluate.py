"""Offline layout/annotation validation or score an existing saved extraction. Never calls OpenAI."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
from backend import storage as db
from backend.document import extract_document,locate_evidence
from backend.evaluation import reference_for,evaluate
from backend.pipeline import load_baseline

parser=argparse.ArgumentParser()
parser.add_argument('--pdf',type=Path,required=True)
parser.add_argument('--check-reference',action='store_true')
parser.add_argument('--output',type=Path)
args=parser.parse_args()
rid=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
fixture=reference_for(rid)
if args.check_reference:
    if not fixture:parser.error('No annotation fixture matches this exact PDF hash.')
    doc=extract_document(args.pdf)
    checks=[]
    for label in fixture['findings']:
        page=doc['pages'][label['detail_pages'][0]-1]
        located=locate_evidence(page,label['anchor'])
        checks.append({'reference':label['reference'],'page':page['page'],
                       'quote_matched':located['quote_matched'],'geometry_matched':located['geometry_matched']})
    result={'mode':'offline_reference_integrity','model_quality_measured':False,'document_stats':doc['stats'],
            'annotation_anchors':len(checks),'matched_anchors':sum(c['quote_matched'] for c in checks),
            'located_anchors':sum(c['geometry_matched'] for c in checks),'checks':checks}
else:
    db.initialize();row=db.get_report(rid)
    result=evaluate(load_baseline(rid) if row else [],fixture,completed=bool(row and row['state']=='complete'))
if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
