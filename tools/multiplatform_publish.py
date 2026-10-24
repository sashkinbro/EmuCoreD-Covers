"""Publish already-validated, coherent platform batches without rewriting history.

Run scope and validate first. Each platform is staged, checked against its frozen
validation digest, independently committed, and pushed before the next starts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from multiplatform_covers import DEFAULT_OUT, atomic_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platforms',nargs='+')
    parser.add_argument('--out',type=Path,default=DEFAULT_OUT)
    parser.add_argument('--common-paths',nargs='+',default=[])
    args=parser.parse_args()
    out=args.out.resolve()
    def git(*arguments,check=True):
        return subprocess.run(['git','-C',str(out),*arguments],capture_output=True,check=check)
    assert git('branch','--show-current').stdout.strip()==b'main'
    assert not git('diff','--cached','--name-only').stdout.strip(),'Git index must start clean'
    verification=json.loads((out/'reports/validation.json').read_text(encoding='utf8'))
    assert verification['passed']
    def identity(field):
        result=git('config','--get','user.'+field,check=False)
        if result.returncode:
            result=subprocess.run(['git','-C',str(out.parent),'config','--get','user.'+field],capture_output=True,check=True)
        return result.stdout.decode().strip()
    author=['-c','user.name='+identity('name'),'-c','user.email='+identity('email')]
    names={'nds':'Nintendo DS and DSi','n3ds':'Nintendo 3DS and New Nintendo 3DS','gamecube':'GameCube','wii':'Wii',
      'gba':'Game Boy Advance','gb':'Game Boy','gbc':'Game Boy Color','nes':'NES and Famicom','snes':'SNES and Super Famicom'}
    report=out/'reports/publication.json'
    history=json.loads(report.read_text(encoding='utf8')) if report.exists() else {'batches':[]}
    for key in args.platforms:
        relative=f'platforms/{key}/index.json'
        index_bytes=(out/relative).read_bytes()
        expected=verification['index_sha256'][key]
        assert hashlib.sha256(index_bytes).hexdigest()==expected,'Manifest changed since validation: '+key
        ready=len(json.loads(index_bytes)['games'])
        head=git('show','HEAD:'+relative,check=False)
        if head.returncode or hashlib.sha256(head.stdout).hexdigest()!=expected:
            print('Staging',key,ready,'complete sets',flush=True)
            git('add','--pathspec-from-file=reports/'+key+'-release-paths.txt')
            if args.common_paths:
                git('add','--',*args.common_paths)
            result=subprocess.run([sys.executable,str(out/'tools/multiplatform_stage_validate.py'),'--out',str(out),'--platform',key],capture_output=True,check=True)
            (out/'reports'/('staged-'+key+'-validation.log')).write_bytes(result.stdout+result.stderr)
            staged=git('show',':'+relative).stdout
            assert hashlib.sha256(staged).hexdigest()==expected
            whitespace=git('diff','--cached','--check',check=False)
            (out/'reports'/('staged-'+key+'-whitespace.log')).write_bytes(whitespace.stdout+whitespace.stderr)
            assert whitespace.returncode==0,'Whitespace check failed; see local log'
            commit=git(*author,'commit','-m','Add complete IGDB '+names[key]+' cover catalog')
            (out/'reports'/(key+'-commit.log')).write_bytes(commit.stdout+commit.stderr)
        print('Pushing',key,ready,'complete sets',flush=True)
        pushed=git('-c','pack.threads=4','push','origin','main',check=False)
        (out/'reports'/(key+'-push.log')).write_bytes(pushed.stdout+pushed.stderr)
        assert pushed.returncode==0,'Push failed; commit preserved, see local log: '+key
        commit=git('rev-parse','HEAD').stdout.decode().strip()
        remote=git('ls-remote','origin','refs/heads/main').stdout.decode().split()[0]
        assert remote==commit,'Remote main differs from published commit'
        history['batches'].append({'platform':key,'complete_sets':ready,'commit':commit,'index_sha256':expected})
        atomic_json(report,history)
        print('Published',key,ready,commit[:12],flush=True)


if __name__=='__main__':
    main()
