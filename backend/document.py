"""Local PDF layout extraction and auditable quotation-to-coordinate mapping."""
import hashlib
import re
import unicodedata
import pymupdf

VERSION = 'layout-v2.1'
REF = re.compile(r'(?m)^(\d+\.\d+\.\d+)\s+([^\n]+)')

def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).replace('\u00ad', '')).strip().casefold()

def extract_document(path):
    pages = []
    observations = []
    with pymupdf.open(path) as doc:
        if doc.needs_pass or not 1 <= len(doc) <= 150:
            raise ValueError('Use an unlocked PDF with 1–150 pages')
        for index, page in enumerate(doc):
            text = page.get_text()
            blocks = []
            for b in page.get_text('dict')['blocks']:
                if b['type'] != 0:
                    continue
                lines = []
                for line in b['lines']:
                    value = ''.join(s['text'] for s in line['spans'])
                    lines.append({'text': value, 'bbox': list(line['bbox']),
                                  'font_size': round(max((s['size'] for s in line['spans']), default=0),1)})
                blocks.append({'id': f'p{index+1}-b{len(blocks)+1}', 'bbox':list(b['bbox']),
                               'text':'\n'.join(l['text'] for l in lines), 'lines':lines})
            is_summary = bool(re.search(r'(?im)^SUMMARY\s*$',text))
            matches = list(REF.finditer(text))
            page_obs = []
            for n, match in enumerate(matches):
                body = text[match.start():matches[n+1].start() if n+1<len(matches) else len(text)]
                # Repeated report footer is not part of a finding.
                body = re.split(r'\nPeirson Construction and Remodeling\n',body)[0]
                title = match.group(2) if is_summary else '\n'.join(body.splitlines()[1:4])
                obs = {'reference':match.group(1),'page':index+1,'role':'summary' if is_summary else 'detail',
                       'heading':title,'text':body,'severity':next((s for s in ['Immediate Deficiency','General Maintenance','General Comment'] if s in body),'')}
                observations.append(obs)
                page_obs.append(obs)
            # Conservative continuation adapter: bind an unnumbered following page
            # only when its opening recommendation shares at least two subject terms
            # with the last numbered detail observation. Preserve that inference.
            if not page_obs and not is_summary and observations:
                previous=next((o for o in reversed(observations) if o['role']=='detail'),None)
                leading=text.splitlines()[0] if text.splitlines() else ''
                def subject_terms(value):
                    tokens=re.findall(r'[a-z]{4,}',normalize(value).replace('(s)','s'))
                    stop={'recommend','recommendation','general','maintenance','condition','qualified','contact','professional','report','construction','remodeling','deficiency'}
                    return {t.rstrip('s') for t in tokens if t not in stop}
                if previous and previous['page']==index and re.match(r'^(Recommend|Recommendation|[a-z])',leading) and not re.search(r'(?m)^\d+: ',text):
                    overlap=subject_terms(previous['heading']) & subject_terms(' '.join(text.splitlines()[:3]))
                    if len(overlap)>=2:
                        body=re.split(r'\nPeirson Construction and Remodeling\n',text)[0]
                        continuation={'reference':previous['reference'],'page':index+1,'role':'detail','heading':previous['heading'],
                                      'text':body,'severity':'','continuation_of':previous['page'],
                                      'binding_terms':sorted(overlap)}
                        page_obs.append(continuation);observations.append(continuation)
            words = [{'text':w[4], 'bbox':list(w[:4]), 'line':[w[5],w[6]]} for w in page.get_text('words')]
            pages.append({'page':index+1, 'text':text, 'needs_ocr':len(text.strip())<60,
                          'width':page.rect.width,'height':page.rect.height,'blocks':blocks,'words':words,
                          'role':'summary' if is_summary else 'content','observations':page_obs})
    return {'version':VERSION,'pages':pages,'observations':observations,
            'stats':{'pages':len(pages),'blocks':sum(len(p['blocks']) for p in pages),
                     'indexed_observations':len(observations),
                     'detail_references':len({o['reference'] for o in observations if o['role']=='detail'}),
                     'sparse_pages':[p['page'] for p in pages if p['needs_ocr']]}}

def locate_evidence(page, quote):
    needle = normalize(quote)
    matched = len(needle)>=12 and needle in normalize(page['text'])
    boxes=[]
    if matched and page.get('words'):
        # Track word offsets in a normalized stream; retain physical PDF coordinates.
        stream, spans = '', []
        for word in page['words']:
            value=normalize(word['text'])
            start=len(stream)
            stream+=value+' '
            spans.append((start,start+len(value),word))
        start=stream.find(needle)
        if start>=0:
            end=start+len(needle)
            lines={}
            for a,b,word in spans:
                if b>start and a<end:
                    key=tuple(word['line'])
                    box=word['bbox']
                    if key not in lines:lines[key]=list(box)
                    else:
                        old=lines[key];lines[key]=[min(old[0],box[0]),min(old[1],box[1]),max(old[2],box[2]),max(old[3],box[3])]
            boxes=list(lines.values())
    return {'quote_matched':matched,'boxes':boxes,'geometry_matched':bool(boxes)}

def source_record(finding, document):
    page_no=finding['page']
    page=document['pages'][page_no-1] if 1<=page_no<=len(document['pages']) else None
    location=locate_evidence(page,finding['evidence']) if page else {'quote_matched':False,'boxes':[],'geometry_matched':False}
    candidates=[o for o in document['observations'] if o['page']==page_no and normalize(finding['evidence']) in normalize(o['text'])]
    # Trust an inspection reference only if the quoted passage belongs to it.
    reference=candidates[0]['reference'] if len(candidates)==1 else ''
    declared=finding.get('report_reference','')
    reference_conflict=bool(declared and declared!=reference)
    identity=hashlib.sha256(f"{page_no}:{normalize(finding['evidence'])}".encode()).hexdigest()[:16]
    return {'id':identity,'page':page_no,'quote':finding['evidence'],**location,
            'reference':reference,'declared_reference':declared,'reference_conflict':reference_conflict,
            'role':page.get('role','content') if page else 'unknown',
            'source_severity':candidates[0]['severity'] if len(candidates)==1 else '',
            'section':candidates[0]['heading'] if len(candidates)==1 else '',
            'reference_binding':'continuation_subject_overlap' if len(candidates)==1 and candidates[0].get('continuation_of') else 'printed_reference' if reference else 'unbound',
            'continuation_of':candidates[0].get('continuation_of') if len(candidates)==1 else None}
