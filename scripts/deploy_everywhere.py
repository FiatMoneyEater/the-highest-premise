#!/usr/bin/env python3
"""Publish the complete Edition 2.0 and verify each destination separately."""
import hashlib,json,os,re,shutil,subprocess,tempfile,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from release_files import public_files,require_books,redact,TMP
ROOT=Path(__file__).resolve().parent.parent
GH_REPO=HF_REPO='FiatMoneyEater/the-highest-premise'
BASE='https://fiatmoneyeater.github.io/the-highest-premise/'
IA_ITEM='the-highest-premise-open-book-package'
INDEXNOW_KEY='20372d4b9f8e4c1a8b7d6e5f4a3b2c1d'
BUNDLE=ROOT/'dist/The_Highest_Premise_v2_Open_Book_Package.zip'
REPORT={k:False for k in ['github_push','pages_configured','github_release','huggingface','internet_archive','pages_live','indexnow']}

def run_cmd(cmd,cwd=None,check=False):
    print('[EXEC] '+' '.join(map(str,cmd)),flush=True)
    env=os.environ.copy();env['GIT_TERMINAL_PROMPT']='0';env['GCM_INTERACTIVE']='never'
    res=subprocess.run(list(map(str,cmd)),cwd=cwd,text=True,encoding='utf-8',errors='replace',capture_output=True,env=env)
    for value in [res.stdout,res.stderr]:
        if value.strip():print(redact(value.strip()),flush=True)
    if check and res.returncode:raise RuntimeError(f'Command failed ({res.returncode}): {cmd[0]} {cmd[1]}')
    return res

def copy_public(stage,hf=False):
    for item in public_files():
        rel=item.relative_to(ROOT)
        if hf and '.github' in rel.parts:continue
        dest=stage/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(item,dest)
    if hf:shutil.copyfile(ROOT/'DATASET_CARD.md',stage/'README.md')

def deploy_github():
    gh=shutil.which('gh')
    if not gh:raise RuntimeError('GitHub CLI is unavailable')
    auth=subprocess.run([gh,'api','user'],capture_output=True,text=True,encoding='utf-8')
    if auth.returncode:raise RuntimeError('GitHub login required')
    account=json.loads(auth.stdout)
    if account.get('login','').lower()!='fiatmoneyeater':raise RuntimeError('Unexpected GitHub account')
    with tempfile.TemporaryDirectory(dir=TMP) as temp:
        stage=Path(temp)/'repo'
        run_cmd(['git','clone','--branch','main','--single-branch',f'https://github.com/{GH_REPO}.git',stage],check=True)
        run_cmd(['git','config','--local','credential.helper',''],cwd=stage,check=True)
        run_cmd(['git','config','--local','--add','credential.helper','!'+gh.replace('\\','/')+' auth git-credential'],cwd=stage,check=True)
        run_cmd(['git','config','--local','user.name','Jo aus Österreich (FiatMoneyEater)'],cwd=stage,check=True)
        run_cmd(['git','config','--local','user.email',f"{account['id']}+{account['login']}@users.noreply.github.com"],cwd=stage,check=True)
        pages=subprocess.run([gh,'api',f'repos/{GH_REPO}/pages'],capture_output=True,text=True,encoding='utf-8')
        old_type=json.loads(pages.stdout).get('build_type') if pages.returncode==0 else None
        if old_type!='workflow':
            run_cmd([gh,'api','-X','PUT' if pages.returncode==0 else 'POST',f'repos/{GH_REPO}/pages','-f','build_type=workflow'],cwd=stage,check=True)
        REPORT['pages_configured']=True
        for name in ['Die_oberste_Praemisse.pdf','The_Highest_Premise.pdf']:
            if (stage/name).is_file():
                (stage/'archive_v1').mkdir(exist_ok=True);shutil.copyfile(stage/name,stage/'archive_v1'/name)
        copy_public(stage)
        run_cmd(['git','add','-A'],cwd=stage,check=True)
        changed=run_cmd(['git','status','--porcelain'],cwd=stage,check=True).stdout.strip()
        if changed:
            run_cmd(['git','commit','-m','Release Edition 2.0: complete DE/EN books, reading pages, specification and datasets'],cwd=stage,check=True)
            run_cmd(['git','push','origin','HEAD:main'],cwd=stage,check=True)
        else:run_cmd([gh,'workflow','run','publish_and_index.yml','--repo',GH_REPO,'--ref','main'],cwd=stage,check=True)
        REPORT['github_push']=True
        REPORT['github_commit']=run_cmd(['git','rev-parse','HEAD'],cwd=stage,check=True).stdout.strip()
        exists=subprocess.run([gh,'release','view','v2.0.0','--repo',GH_REPO],capture_output=True).returncode==0
        if exists:run_cmd([gh,'release','upload','v2.0.0',BUNDLE,'--repo',GH_REPO,'--clobber'],cwd=stage,check=True)
        else:run_cmd([gh,'release','create','v2.0.0',BUNDLE,'--repo',GH_REPO,'--target','main','--title','Edition 2.0 – Die oberste Prämisse / The Highest Premise','--notes','Complete Edition 2.0 (DE/EN), HTML, PDF, constitutional specification v2, benchmark and documented restraint corpus. CC BY 4.0.'],cwd=stage,check=True)
        REPORT['github_release']=True
        return True

def deploy_huggingface():
    from huggingface_hub import HfApi
    api=HfApi()
    if api.whoami().get('name','').lower()!='fiatmoneyeater':raise RuntimeError('Hugging Face login for FiatMoneyEater required')
    with tempfile.TemporaryDirectory(dir=TMP) as temp:
        copy_public(Path(temp),hf=True)
        info=api.upload_folder(folder_path=temp,repo_id=HF_REPO,repo_type='dataset',commit_message='Release Edition 2.0: complete bilingual books, specification and datasets')
        REPORT['huggingface_commit']=str(info.oid)
    REPORT['huggingface']=True
    return True

def deploy_internet_archive():
    import internetarchive
    session=internetarchive.get_session()
    if not getattr(session,'access_key',None) or not getattr(session,'secret_key',None):
        print('[PENDING] Internet Archive login required. Ready package: '+str(BUNDLE),flush=True)
        return False
    files=[BUNDLE]
    for folder in ['books','spec','evals','datasets']:files.extend(sorted(p for p in (ROOT/folder).rglob('*') if p.is_file()))
    # Preserve directory names in the remote item.
    mapping={p.relative_to(ROOT).as_posix():str(p) for p in files}
    item=session.get_item(IA_ITEM)
    responses=item.upload(mapping,metadata={'creator':'Jo aus Österreich (FiatMoneyEater)','licenseurl':'https://creativecommons.org/licenses/by/4.0/'},retries=2,verbose=False)
    REPORT['internet_archive']=bool(responses) and all(r.status_code in [200,201] for r in responses)
    return REPORT['internet_archive']

def pages_live():
    for name in ['index.html','robots.txt','llms.txt','sitemap.xml','read/de/full.html','read/en/full.html']:
        req=urllib.request.Request(BASE+('' if name=='index.html' else name),headers={'User-Agent':'HighestPremiseReleaseVerifier/2.0'})
        try:
            with urllib.request.urlopen(req,timeout=20) as response:
                if response.status!=200 or response.read()!=(ROOT/name).read_bytes():return False
        except Exception:return False
    return True

def ping_indexnow():
    if not pages_live():
        print('[PENDING] Edition 2.0 Pages deployment is not yet verified; IndexNow is deferred.',flush=True)
        return False
    REPORT['pages_live']=True
    urls=re.findall(r'<loc>(.*?)</loc>',(ROOT/'sitemap.xml').read_text(encoding='utf-8'))
    payload={'host':'fiatmoneyeater.github.io','key':INDEXNOW_KEY,'keyLocation':BASE+INDEXNOW_KEY+'.txt','urlList':urls}
    req=urllib.request.Request('https://api.indexnow.org/indexnow',data=json.dumps(payload).encode('utf-8'),headers={'Content-Type':'application/json; charset=utf-8'},method='POST')
    with urllib.request.urlopen(req,timeout=30) as response:
        REPORT['indexnow_http']=response.status;REPORT['indexnow']=response.status in [200,202]
        print(f'IndexNow accepted {len(urls)} URLs: HTTP {response.status}. Acceptance does not prove indexing.',flush=True)
    return REPORT['indexnow']

def main():
    require_books(built=True)
    for label,fn in [('GitHub',deploy_github),('Hugging Face',deploy_huggingface),('Internet Archive',deploy_internet_archive)]:
        print('\n=== '+label+' ===',flush=True)
        try:fn()
        except Exception as exc:
            REPORT[label+'_error']=redact(exc);print('[PENDING] '+redact(exc),flush=True)
    if REPORT['github_push']:
        for attempt in range(7):
            if pages_live():break
            if attempt<6:time.sleep(10)
        try:ping_indexnow()
        except Exception as exc:REPORT['indexnow_error']=redact(exc);print('[PENDING] IndexNow: '+redact(exc),flush=True)
    REPORT['checked_at']=datetime.now(timezone.utc).isoformat()
    (ROOT/'.build-local/deployment-status.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\n'+json.dumps(REPORT,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
