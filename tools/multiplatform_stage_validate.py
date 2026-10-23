"""Validate the exact Git index snapshot, including artifact and provenance blobs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import subprocess
from PIL import Image
from multiplatform_covers import DEFAULT_OUT, image_url, platform_ids


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=DEFAULT_OUT)
    parser.add_argument('--platform',required=True)
    args=parser.parse_args()
    def git(*arguments):
        return subprocess.check_output(['git','-C',str(args.out),*arguments])
    entries={}
    for entry in git('ls-files','--stage','-z').decode('utf8').split('\0'):
        if entry:
            header,path=entry.split('\t',1)
            mode,oid,stage=header.split()
            assert stage=='0','Unmerged Git index'
            entries[path]=oid
    def staged_json(path):
        return metadata_cache[path] if path in metadata_cache else json.loads(git('show',':'+path))
    metadata_cache={}
    key=args.platform
    index_path=f'platforms/{key}/index.json'
    index_bytes=git('show',':'+index_path)
    index=json.loads(index_bytes)
    catalog=staged_json('catalogs/'+key+'.json')
    source={str(game['id']):game for game in catalog['games']}
    assert catalog['catalog_complete']
    referenced={index_path,'catalogs/'+key+'.json'}
    # One persistent Git process avoids thousands of process launches on Windows.
    metadata_paths=[f'platforms/{key}/{folder}/{gid}{suffix}' for gid in index['games']
      for folder,suffix in [('flat','.source.json'),('3d','.render.json'),('3d/dark','.render.json')]]
    reader=subprocess.Popen(['git','-C',str(args.out),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        for path in metadata_paths:
            assert path in entries,'Dangling staged provenance: '+path
            reader.stdin.write((entries[path]+'\n').encode());reader.stdin.flush()
            header=reader.stdout.readline().decode().split()
            assert len(header)==3 and header[1]=='blob'
            payload=reader.stdout.read(int(header[2]));assert reader.stdout.read(1)==b'\n'
            metadata_cache[path]=json.loads(payload)
        reader.stdin.close();assert reader.wait()==0
    finally:
        if reader.poll() is None: reader.terminate()
    def check(pair):
        gid,game=pair
        assert game['source_url']==image_url(source[gid])
        assert game['igdb_platform_ids']==[pid for pid in platform_ids(key) if pid in source[gid]['platforms']]
        for field in ('path','path_3d','path_3d_dark'):
            path=game[field]
            assert path in entries, 'Dangling staged artifact reference: '+path
            data=(args.out/path).read_bytes()
            assert hashlib.sha256(data).hexdigest()==game['sha256'+field.removeprefix('path')],path
            blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            assert blob==entries[path], 'Working bytes differ from exact staged blob: '+path
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                if field!='path':
                    assert image.size==(840,1080) and image.mode=='RGBA'
            referenced.add(path)
        assert game['sha256_3d']!=game['sha256_3d_dark']
        origin_path=f'platforms/{key}/flat/{gid}.source.json'
        origin=staged_json(origin_path)
        assert origin['source_url']==game['source_url'] and origin['sha256']==game['sha256']
        referenced.add(origin_path)
        for folder,theme in [('3d','light'),('3d/dark','dark')]:
            state_path=f'platforms/{key}/{folder}/{gid}.render.json'
            state=staged_json(state_path)
            assert state=={'renderer':game['renderer'],'source_sha256':game['sha256'],'title':game['name'],'platform':key,'theme':theme}
            referenced.add(state_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(check,index['games'].items()))
    for title,gid in index['titles'].items():
        assert index['title_candidates'][title]==[gid]
    changed=git('diff','--cached','--name-only','-z').decode('utf8').split('\0')
    for path in filter(None,changed):
        assert not path.startswith('covers/'),'Existing combined DS/3DS asset changed'
        if path.startswith('platforms/'):
            assert path in referenced, 'Unreviewed platform file staged: '+path
        assert not path.endswith(('.log','.part','.pyc','.db')) and Path(path).name!='config.py','Private/cache file staged: '+path
    assert not git('diff','--cached','--diff-filter=D','--name-only').strip(),'Unexpected deletion'
    print(json.dumps({'passed':True,'platform':key,'complete_sets':len(index['games']),
      'staged_index_sha256':hashlib.sha256(index_bytes).hexdigest(),'referenced_files':len(referenced),
      'changed_staged_files':len(list(filter(None,changed)))},indent=2))


if __name__=='__main__':
    main()
