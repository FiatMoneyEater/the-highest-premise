from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parent.parent
LOCAL=ROOT/'.build-local'
TMP=LOCAL/'tmp'
TMP.mkdir(parents=True,exist_ok=True)
PUBLIC_DIRS={'books','spec','evals','datasets','chapters','read','scripts','.github'}
PUBLIC_FILES={'index.html','LICENSE.txt','DATASET_CARD.md','metadata.json','robots.txt','llms.txt','dataset.jsonl','sitemap.xml','CITATION.cff','.zenodo.json','.nojekyll','.gitignore','DEPLOY_ALL.ps1','README.md'}
EXCLUDED={'.git','.build-local','.venv','__pycache__'}
def public_files():
    candidates=[]
    for p in ROOT.iterdir():
        if p.is_file()and(p.name in PUBLIC_FILES or re.fullmatch(r'google[^/]*[.]html',p.name)or re.fullmatch(r'[0-9a-f]{32}[.]txt',p.name)or p.name in{'Die_oberste_Praemisse.md','The_Highest_Premise.md'}):candidates.append(p)
    for name in sorted(PUBLIC_DIRS):
        directory=ROOT/name
        if directory.is_dir():candidates.extend(p for p in directory.rglob('*')if p.is_file())
    for p in sorted(candidates):
        rel=p.relative_to(ROOT)
        if set(rel.parts)&EXCLUDED:continue
        if not p.resolve().is_relative_to(ROOT.resolve()):raise RuntimeError('Public file escapes workspace')
        yield p


def require_books(built=False):
    for name in ['Die_oberste_Praemisse_v2_DE.md','The_Highest_Premise_v2_EN.md']:
        p=ROOT/'books'/name
        if not p.is_file()or p.stat().st_size<=10240:raise FileNotFoundError('Missing final Edition 2.0 source (>10 KB): '+str(p))
        p.read_bytes().decode('utf-8')
    baseline_path=LOCAL/'source-integrity.json'
    metadata=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
    baseline=json.loads(baseline_path.read_text(encoding='utf-8')) if baseline_path.is_file() else {'files':metadata['source_sha256']}
    for name,digest in metadata.get('source_sha256',{}).items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Source checksum mismatch: '+name)
    for name,digest in baseline['files'].items():
        if name.startswith('spec/')and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Supplied specification changed: '+name)
    if built:
        for name in ['llms.txt','dataset.jsonl','sitemap.xml','read/de/index.html','read/en/index.html','read/de/full.html','read/en/full.html','dist/The_Highest_Premise_v2_Open_Book_Package.zip']:
            if not(ROOT/name).is_file():raise FileNotFoundError('Missing build output: '+name)

def redact(value):
    value=re.sub(r'(?:ghp_|github_pat_|hf_)[A-Za-z0-9_]{12,}','[REDACTED]',str(value))
    return re.sub(r'(?i)((?:bearer|password|token|secret)\s*[:=]\s*)[^\s]+',r'\1[REDACTED]',value)
