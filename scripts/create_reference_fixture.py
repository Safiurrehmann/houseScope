"""Curated labels from reading the public Kentucky report. No model calls."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.document import normalize, extract_document
root=Path(__file__).resolve().parents[1]
pdf=root/'fixtures/peirson-kentucky-sample.pdf'
doc=extract_document(pdf)
# Explicit annotation choices, not an extraction algorithm. Text anchors are checked against the source.
labels=[
('3.1.1',9,'Seal siding penetrations','Caulk/seal any areas of home'),
('4.1.1',10,'Roof covering debris','Debris noted on the roof covering'),
('4.2.1',10,'Gutter debris','Clean the debris from the gutters'),
('4.2.2',11,'Downspouts discharge near foundation','Downspouts were observed discharging too close'),
('5.3.1',13,'Mystery switches','Mystery switches were noted throughout the home'),
('5.4.1',14,'Missing receptacle cover plates','Replace the missing cover plate'),
('5.4.2',14,'Loose receptacles','Loose receptacles were noted in the home'),
('5.4.3',15,'Open ground receptacles','Receptacles in multiple rooms have an open ground'),
('5.4.4',15,'Laundry GFCI absent','not GFCI protected'),
('5.4.5',16,'Open neutral receptacle','open neutral condition'),
('5.4.6',16,'Floor receptacle grounding opening obstructed','obstructs the grounding prong opening'),
('5.5.1',17,'Missing or inoperable bulbs','Replace all missing/inoperable bulbs'),
('5.6.1',17,'Additional smoke detectors','SMOKE DETECTOR(S) - ADD'),
('6.1.1',20,'Weak attic ladder','Ladder to the attic is weak'),
('6.2.1',20,'Insufficient attic insulation','Six inches or less of insulation'),
('11.2.1',30,'Dirty HVAC air filters','Replace the dirty air filter(s)'),
('14.1.1',35,'Inoperable fireplace','The fireplace would not light'),
('15.2.1',38,'Missing cabinet hardware','Install the missing handle(s)/pull(s)'),
('15.3.1',38,'Loose kitchen faucet','securing the loose faucet'),
('20.1.1',44,'Missing stair handrail','A handrail was not present'),
('20.2.1',44,'Loose porch railing','One or more railings were loose'),
('21.1.1',46,'Regrade soils away from foundation','Pitch slope of soils away from foundation'),
('23.1.1',50,'Missing crawlspace vapor barrier','Install the missing vapor barrier'),
('23.1.2',50,'Crawlspace moisture intrusion','Signs of moisture intrusion'),
]
entries=[]
for ref,page,title,anchor in labels:
 assert normalize(anchor) in normalize(doc['pages'][page-1]['text']), (ref,anchor)
 entries.append({'reference':ref,'detail_pages':[page]+([18] if ref=='5.6.1' else []),'title':title,'anchor':anchor})
fixture={'id':'kentucky-v1','version':1,'document_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
 'source_url':'https://peirsoninspections.com/sample-report','annotation_method':'Agent-curated from direct inspection of the PDF; not independently human-audited.',
 'scope':'24 defect/maintenance observations. Summary has 25 entries including a dryer limitation. No claim that inspector severity is a ground-truth repair priority.',
 'excluded':[{'reference':'18.1.1','page':42,'reason':'Dryer absent and components untested: inspection limitation, not confirmed equipment failure.'}],
 'negative_pages':[4,5,6,7,8,12], 'findings':entries}
(root/'fixtures/annotations/kentucky-v1.json').write_text(json.dumps(fixture,indent=2))
print('Validated 24 annotation anchors against the exact 56-page source PDF.')
