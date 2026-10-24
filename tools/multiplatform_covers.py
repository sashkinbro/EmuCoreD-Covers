#!/usr/bin/env python3
"""Resumable, platform-scoped IGDB catalog/artifact pipeline. No secrets are persisted.

Run catalog, assets, validate separately. Existing DS/3DS renderers supply the
approved case geometry; other consoles use the same geometry with honest labels.
Original IGDB bytes are preserved; region-specific artwork is never inferred.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import hashlib
from functools import lru_cache
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sqlite3
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')

PLATFORMS = {'nds': (20, 'Nintendo DS'), 'n3ds': (37, 'Nintendo 3DS'),
 'gamecube': (21, 'Nintendo GameCube'), 'wii': (5, 'Nintendo Wii'),
 'gba': (24, 'Game Boy Advance'), 'gb': (33, 'Game Boy'),
 'gbc': (22, 'Game Boy Color'), 'nes': (18, 'Nintendo Entertainment System'),
 'snes': (19, 'Super Nintendo Entertainment System')}
def platform_ids(key):
    return {'nds':(20,159),'n3ds':(37,137),'nes':(18,99),'snes':(19,58)}.get(key,(PLATFORMS[key][0],))
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT if (ROOT / 'index.min.json').exists() else ROOT / 'covers'

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    os.replace(tmp, path)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

@lru_cache(maxsize=8)
def legacy_profiles(out):
    path=Path(out)/'reports'/'legacy-case-profiles.json'
    return json.loads(path.read_text(encoding='utf8')).get('profiles',{}) if path.exists() else {}

def eligible_legacy(out,key,game):
    if key not in ('nds','n3ds'):
        return False
    profile=legacy_profiles(str(out.resolve())).get(str(game['id']),{})
    if profile.get('renderer')!=key:
        return False
    for field,folder in [('sha256_3d','3d'),('sha256_3d_dark','3d/dark')]:
        path=out/'covers'/folder/(str(game['id'])+'.webp')
        if not path.exists() or digest(path)!=profile.get(field):
            return False
    return True

def actual_flat(out,key,gid):
    path=out/'platforms'/key/'flat'/(str(gid)+'.jpg')
    metadata=path.with_suffix('.source.json')
    if metadata.exists():
        record=json.loads(metadata.read_text(encoding='utf8'))
        if record.get('local_path')=='covers/'+str(gid)+'.jpg':
            return out/record['local_path']
    return path

def renderer_version(key,source):
    if key in ('nds','n3ds'):
        return 'existing_ds_3ds_v2'
    with Image.open(source) as image:
        return 'source_aspect_wide_spine_v4' if image.width/image.height>4 else 'source_aspect_geometry_v3'

def audit_legacy(args):
    import numpy as np
    from render_nds_covers_3d import render_nds_3d
    from render_n3ds_covers_3d import render_n3ds_3d
    crop=(50,35,110,150)
    white=Image.new('RGB',(800,1110),'white')
    templates={(key,theme):np.asarray(renderer(white,'','',theme=theme).crop(crop).convert('RGB'),dtype=float)
      for key,renderer in [('nds',render_nds_3d),('n3ds',render_n3ds_3d)] for theme in ('light','dark')}
    ids=set()
    for key in ('nds','n3ds'):
        data=json.loads((args.out/'catalogs'/(key+'.json')).read_text(encoding='utf8'))
        ids.update(str(g['id']) for g in data['games'] if image_url(g))
    def inspect(gid):
        profile={}; guesses=[]
        try:
            for theme,folder,field in [('light','3d','sha256_3d'),('dark','3d/dark','sha256_3d_dark')]:
                path=args.out/'covers'/folder/(gid+'.webp')
                with Image.open(path) as image:
                    assert image.size==(840,1080) and image.mode=='RGBA'
                    pixels=np.asarray(image.crop(crop).convert('RGB'),dtype=float)
                distances={key:float(np.mean((pixels-templates[(key,theme)])**2)) for key in ('nds','n3ds')}
                ordered=sorted(distances,key=distances.get)
                guesses.append(ordered[0] if distances[ordered[0]]<3000 and distances[ordered[0]]<.65*distances[ordered[1]] else 'unknown')
                profile[field]=digest(path)
                profile['signature_mse_'+theme]=distances
            profile['renderer']=guesses[0] if guesses[0]==guesses[1] else 'unknown'
            return gid,profile
        except (OSError,AssertionError):
            return gid,None
    profiles={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for gid,profile in pool.map(inspect,sorted(ids,key=int)):
            if profile:
                profiles[gid]=profile
    counts={key:sum(p['renderer']==key for p in profiles.values()) for key in ('nds','n3ds','unknown')}
    atomic_json(args.out/'reports'/'legacy-case-profiles.json',{'method':'fixed top-spine pixel signature against existing DS/3DS renderers, both light and dark; uncertain profiles are not reused','counts':counts,'profiles':profiles})
    print(json.dumps(counts),flush=True)

def deduplicate_legacy(args):
    removed=0; saved=0; reused_sources=0; reused_sets=0
    previous_path=args.out/'reports'/'legacy-reuse.json'
    previous=json.loads(previous_path.read_text(encoding='utf8')) if previous_path.exists() else {}
    for key in ('nds','n3ds'):
        catalog=json.loads((args.out/'catalogs'/(key+'.json')).read_text(encoding='utf8'))
        managed=(args.out/'platforms'/key).resolve()
        for game in catalog['games']:
            gid=str(game['id']); source=args.out/'covers'/(gid+'.jpg')
            metadata=managed/'flat'/(gid+'.source.json')
            if not metadata.exists() or not source.exists():
                continue
            record=json.loads(metadata.read_text(encoding='utf8'))
            if record['source_url']!=image_url(game) or digest(source)!=record['sha256']:
                continue
            record['local_path']='covers/'+gid+'.jpg'
            atomic_json(metadata,record)
            reused_sources+=1
            candidates=[managed/'flat'/(gid+'.jpg')]
            if eligible_legacy(args.out,key,game):
                reused_sets+=1
                candidates.extend(managed/folder/(gid+'.webp') for folder in ('3d','3d/dark'))
            for path in candidates:
                resolved=path.resolve()
                assert resolved.is_relative_to(managed), 'Refusing to remove a file outside its managed platform'
                if path.exists():
                    saved+=path.stat().st_size
                    path.unlink()
                    removed+=1
    atomic_json(args.out/'reports'/'legacy-reuse.json',{'reused_sources':reused_sources,'reused_complete_sets':reused_sets,'duplicate_files_removed':removed,'duplicate_bytes_removed':saved,
      'cumulative_duplicate_files_removed':previous.get('cumulative_duplicate_files_removed',previous.get('duplicate_files_removed',0))+removed,
      'cumulative_duplicate_bytes_removed':previous.get('cumulative_duplicate_bytes_removed',previous.get('duplicate_bytes_removed',0))+saved,'original_combined_assets_modified':0})
    indexes(args)
    print('Removed',removed,'generated duplicates;',saved,'bytes; original assets remain unchanged.',flush=True)

def normalize(title):
    title = title.replace('+', ' plus ')
    title = ''.join(c for c in unicodedata.normalize('NFKD', title).casefold() if not unicodedata.combining(c))
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in title).split())

class Client:
    def __init__(self, config):
        spec = importlib.util.spec_from_file_location('private_igdb_config', config)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.cid = module.TWITCH_CLIENT_ID
        payload = urllib.parse.urlencode({'client_id': self.cid, 'client_secret': module.TWITCH_CLIENT_SECRET, 'grant_type': 'client_credentials'}).encode()
        with urllib.request.urlopen(urllib.request.Request('https://id.twitch.tv/oauth2/token', data=payload), timeout=30) as response:
            self.token = json.load(response)['access_token']

    def post(self, endpoint, query):
        for attempt in range(6):
            request = urllib.request.Request('https://api.igdb.com/v4/' + endpoint, data=query.encode(), headers={'Client-ID': self.cid, 'Authorization': 'Bearer ' + self.token, 'Content-Type': 'text/plain'})
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    result = json.load(response)
                time.sleep(.28)
                return result
            except Exception:
                if attempt == 5:
                    raise RuntimeError('IGDB request failed: ' + endpoint) from None
                time.sleep(min(2 ** attempt, 15))

def catalog(args):
    client = Client(args.config)
    # One page per platform in each round keeps all platforms progressing.
    states = {}
    for key in args.platforms:
        path = args.out / 'catalogs' / (key + '.json')
        states[key] = json.loads(path.read_text(encoding='utf8')) if path.exists() and not args.refresh else {
          'schema_version': 1, 'platform': key, 'igdb_platform_id': PLATFORMS[key][0], 'igdb_platform_ids':list(platform_ids(key)),
          'platform_name': PLATFORMS[key][1], 'source': 'https://api.igdb.com/v4/games',
          'catalog_complete': False, 'last_id': 0, 'games': []}
    while any(not state['catalog_complete'] for state in states.values()):
        for key, state in states.items():
            if state['catalog_complete']:
                continue
            pid = ','.join(map(str,platform_ids(key)))
            fields = 'id,name,slug,url,platforms,game_type,parent_game,alternative_names.name,alternative_names.comment,cover.id,cover.image_id,cover.url,release_dates.id,release_dates.platform,release_dates.release_region.region,release_dates.date,version_parent,version_title,updated_at'
            query = f'fields {fields}; where platforms = ({pid}) & id > {state["last_id"]}; sort id asc; limit 500;'
            rows = client.post('games', query)
            state['games'].extend(rows)
            if rows:
                state['last_id'] = rows[-1]['id']
            state['catalog_complete'] = len(rows) < 500
            state['retrieved_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            state['query'] = query
            atomic_json(args.out / 'catalogs' / (key + '.json'), state)
            print(key, len(state['games']), 'complete' if state['catalog_complete'] else 'checkpoint', flush=True)

def image_url(game):
    image = game.get('cover', {}).get('image_id')
    return f'https://images.igdb.com/igdb/image/upload/t_1080p/{image}.jpg' if image else None

def ensure_flat(task):
    game, path = task
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        origin=path.with_suffix('.source.json')
        if origin.exists():
            try:
                metadata=json.loads(origin.read_text(encoding='utf8'))
                cached=path
                if metadata.get('local_path')=='covers/'+str(game['id'])+'.jpg':
                    cached=path.parents[3]/metadata['local_path']
                with Image.open(cached) as im:
                    im.verify()
                if metadata['source_url']==image_url(game) and metadata['sha256']==digest(cached):
                    return game['id'], True
            except Exception:
                pass
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(image_url(game), headers={'User-Agent': 'EmuCoreD-Covers/1'}), timeout=35) as response:
                    data = response.read()
                tmp = path.with_suffix('.jpg.part')
                tmp.write_bytes(data)
                with Image.open(tmp) as im:
                    im.verify()
                os.replace(tmp, path)
                atomic_json(origin,{'source':'IGDB','source_url':image_url(game),'image_id':game['cover']['image_id'],'sha256':digest(path)})
                return game['id'], True
            except Exception:
                time.sleep(.5 * (attempt + 1))
    except Exception:
        pass
    return game['id'], False

def generic_render(art, title, platform, theme):
    from render_nds_covers_3d import CANVAS_SIZE, warp
    light = theme == 'light'
    background = (246,248,252,255) if light else (18,20,24,255)
    text = (25,28,35,255) if light else (240,243,248,255)
    # Adapt the physical case to the source scan, including square GBA and wide
    # SNES boxes. Keep the entire source visible and leave padding on the OUTPUT
    # canvas rather than inside a falsely tall box front.
    ratio=art.width/max(1,art.height)
    face_h=min(1110,max(1,round(800/ratio)))
    face_w=min(800,max(1,round(face_h*ratio)))
    physical_h=round(face_h*1220/1110)
    skew=round(55*face_w/800)
    left=235; right=left+face_w; top=round((1500-physical_h)/2)-30; bottom=top+physical_h
    front_corners=[(left,top),(right,top+skew),(right,bottom-skew),(left,bottom)]
    spine_corners=[(left-105,top+35),(left,top),(left,bottom),(left-105,bottom-35)]
    canvas = Image.new('RGBA', CANVAS_SIZE)
    shadow = Image.new('RGBA', CANVAS_SIZE)
    ImageDraw.Draw(shadow).polygon([(left-120,bottom-50),(left,bottom+5),(right+5,bottom-skew+5),(right+40,bottom+60),(left+15,bottom+105),(left-140,bottom+35)], fill=(0,0,0,125 if light else 165))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(32)))
    ImageDraw.Draw(canvas).polygon([(left-110,top+30),(left,top-5),(right+5,top+skew-5),(right+5,bottom-skew+5),(left,bottom+5),(left-110,bottom-30)], fill=background)
    face=art.convert('RGBA').resize((face_w,face_h),Image.Resampling.LANCZOS)
    canvas.alpha_composite(warp(face, front_corners))
    spine = Image.new('RGBA', (105,physical_h), background)
    draw = ImageDraw.Draw(spine)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 31)
        small = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 17)
    except OSError:
        font = small = ImageFont.load_default()
    title_width = max(1, int(draw.textlength(title,font=font)) + 30)
    label = Image.new('RGBA', (title_width,105))
    ImageDraw.Draw(label).text((15,28), title, font=font, fill=text)
    bbox = label.getbbox()
    if bbox:
        # Panorama scans need proportional header/footer reserves; a fixed250px
        # reserve leaves only11px and Pillow rounds the title width to zero.
        max_title_h=max(1,physical_h-(150 if ratio>4 else 250))
        label=label.crop(bbox).rotate(90,expand=True)
        scale=min(70/label.width,max_title_h/label.height)
        if ratio>4:
            label=label.resize((max(1,round(label.width*scale)),max(1,round(label.height*scale))),Image.Resampling.LANCZOS)
        else:
            label=ImageOps.contain(label,(70,max_title_h),Image.Resampling.LANCZOS)
        spine.alpha_composite(label, ((105-label.width)//2,(physical_h-label.height)//2))
    header={'gamecube':['NINTENDO','GAMECUBE'],'wii':['Nintendo','Wii'],'gba':['GAME BOY','ADVANCE'],
      'gb':['GAME BOY'],'gbc':['GAME BOY','COLOR'],'nes':['NINTENDO','NES'],'snes':['SUPER','NINTENDO']}[platform]
    for i, word in enumerate(header):
        word_image = Image.new('RGBA',(max(1,int(draw.textlength(word,font=small))+2),24))
        ImageDraw.Draw(word_image).text((0,0),word,font=small,fill=text)
        word_image = ImageOps.contain(word_image,(91,24),Image.Resampling.LANCZOS)
        spine.alpha_composite(word_image,((105-word_image.width)//2,20+i*25))
    draw.text((12,physical_h-60), platform.upper(), font=small, fill=text)
    canvas.alpha_composite(warp(spine, spine_corners))
    draw = ImageDraw.Draw(canvas)
    draw.line([(left,top),(left,bottom)], fill=(255,255,255,230) if light else (150,155,165,220), width=3)
    draw.line([(left-105,top+35),(left,top),(right,top+skew)], fill=(255,255,255,230) if light else (165,170,180,210), width=3)
    bbox = canvas.getchannel('A').point(lambda p:255 if p>5 else 0).getbbox()
    crop=canvas.crop((max(0,bbox[0]-12),max(0,bbox[1]-12),min(1200,bbox[2]+12),min(1500,bbox[3]+12)))
    fitted=ImageOps.contain(crop,(840,1080),Image.Resampling.LANCZOS)
    output=Image.new('RGBA',(840,1080))
    output.alpha_composite(fitted,((840-fitted.width)//2,(1080-fitted.height)//2))
    return output

def render(task):
    key, game, out = task
    gid = str(game['id'])
    base = out / 'platforms' / key
    flat = actual_flat(out,key,gid)
    try:
        legacy_flat=out/'covers'/(gid+'.jpg')
        reuse_legacy=eligible_legacy(out,key,game) and legacy_flat.exists() and digest(legacy_flat)==digest(flat)
        with Image.open(flat) as art:
            for theme, folder in [('light','3d'),('dark','3d/dark')]:
                path = base / folder / (gid+'.webp')
                render_state=path.with_suffix('.render.json')
                version=renderer_version(key,flat)
                signature={'renderer':version,'source_sha256':digest(flat),'title':game['name'],'platform':key,'theme':theme}
                legacy=out/'covers'/folder/(gid+'.webp')
                if reuse_legacy:
                    path=legacy
                if path.exists() and render_state.exists():
                    try:
                        if json.loads(render_state.read_text(encoding='utf8'))==signature:
                            with Image.open(path) as existing:
                                existing.verify()
                            continue
                    except (OSError,ValueError):
                        pass
                path.parent.mkdir(parents=True, exist_ok=True)
                if reuse_legacy and legacy.exists():
                    with Image.open(legacy) as old:
                        valid=old.size==(840,1080) and old.mode=='RGBA'
                        old.verify()
                    if valid:
                        if legacy!=path:
                            shutil.copy2(legacy,path)
                        atomic_json(render_state,signature)
                        continue
                if key == 'nds':
                    from render_nds_covers_3d import render_nds_3d
                    result = render_nds_3d(art, game['name'], '', theme=theme)
                elif key == 'n3ds':
                    from render_n3ds_covers_3d import render_n3ds_3d
                    result = render_n3ds_3d(art, game['name'], '', theme=theme)
                else:
                    result = generic_render(art, game['name'], key, theme)
                tmp = path.with_suffix('.webp.part')
                result.save(tmp, 'WEBP', quality=92, method=4)
                os.replace(tmp,path)
                atomic_json(render_state,signature)
        return key,gid,None
    except Exception as error:
        return key,gid,str(error)

def assets(args):
    tasks = []
    seed_report = seed_matches(args)
    seed_ids = defaultdict(set)
    for entry in seed_report:
        if len(entry['candidates']) == 1:
            candidate = entry['candidates'][0]
            seed_ids[candidate['platform']].add(candidate['igdb_id'])
    for key in args.platforms:
        data = json.loads((args.out/'catalogs'/(key+'.json')).read_text(encoding='utf8'))
        games = [g for g in data['games'] if image_url(g)]
        if args.limit:
            # Stable sample spread throughout the full catalog; no seed-only bias.
            games = games[:args.limit] + [g for g in games[args.limit:] if g['id'] in seed_ids[key]]
        tasks.extend((key,g,args.out) for g in games)
    # Round robin console batches instead of finishing one console first.
    tasks.sort(key=lambda t:(t[1]['id'],t[0]))
    ready = []
    download_failures=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(ensure_flat,(g,args.out/'platforms'/key/'flat'/(str(g['id'])+'.jpg'))):(key,g,out) for key,g,out in tasks}
        for i,future in enumerate(as_completed(futures),1):
            _,ok = future.result()
            if ok:
                ready.append(futures[future])
            else:
                key,game,_=futures[future]
                download_failures.append({'platform':key,'igdb_id':game['id'],'source_url':image_url(game),'reason':'download_or_image_verification_failed'})
            if i%100==0 or i==len(futures):
                print('download',i,'/',len(futures),'valid',len(ready),flush=True)
    atomic_json(args.out/'reports'/'download-failures.json',download_failures)
    if args.download_only:
        print('Download-only checkpoint complete:',len(ready),'valid source images.',flush=True)
        return
    errors=[]
    with ProcessPoolExecutor(max_workers=args.render_workers) as pool:
        for i,result in enumerate(pool.map(render,ready,chunksize=1),1):
            if result[2]:
                errors.append(result)
            if i%25==0 or i==len(ready):
                print('render',i,'/',len(ready),'errors',len(errors),flush=True)
            if i%250==0:
                atomic_json(args.out/'reports'/'progress.json',{'phase':'render','completed':i,'total':len(ready),'errors':len(errors),'updated_at':time.time()})
            if args.checkpoint_every and i%args.checkpoint_every==0:
                indexes(args)
    atomic_json(args.out/'reports'/'render-errors.json',errors)
    indexes(args)
    atomic_json(args.out/'reports'/'progress.json',{'phase':'complete' if not errors else 'complete_with_errors','completed':len(ready),'total':len(ready),'errors':len(errors),'updated_at':time.time()})

def seed_matches(args):
    """Filename identity is retained; only unambiguous exact canonical/alias matches map."""
    source = args.seeds
    result=[]
    if not source or not source.exists():
        return result
    names=defaultdict(set)
    for key in PLATFORMS:
        catalog_path=args.out/'catalogs'/(key+'.json')
        if not catalog_path.exists():
            continue
        data=json.loads(catalog_path.read_text(encoding='utf8'))
        for game in data['games']:
            for title in [game['name']]+[a['name'] for a in game.get('alternative_names',[])]:
                names[(key,normalize(title))].add(game['id'])
    ext_platforms={'.nds':['nds'],'.3ds':['n3ds'],'.cia':['n3ds'],'.gb':['gb'],'.gbc':['gbc'],'.gba':['gba'],'.nes':['nes'],'.sfc':['snes'],'.smc':['snes'],'.rvz':['gamecube','wii'],'.iso':['gamecube','wii']}
    for path in sorted(source.iterdir()):
        keys=ext_platforms.get(path.suffix.lower(),[])
        if not keys or not path.is_file():
            continue
        tags=re.findall(r'\(([^)]*)\)|\[([^]]*)\]',path.stem)
        title=re.sub(r'\([^)]*\)|\[[^]]*\]',' ',path.stem).strip()
        title=re.sub(r'^(.*), (The|A|An)$',r'\2 \1',title)
        title=re.sub(r'^([^,]+), (The|A|An)(\s+-\s+.*)$',r'\2 \1\3',title)
        candidates=[{'platform':key,'igdb_id':gid} for key in keys for gid in sorted(names.get((key,normalize(title)),set()))]
        result.append({'filename':path.name,'size':path.stat().st_size,'title':title,'identity_tags':[a or b for a,b in tags],
          'candidates':candidates,'match':'exact_title_or_alias' if len(candidates)==1 else 'ambiguous' if candidates else 'unmatched',
          'region_revision_policy':'Filename tags retained verbatim; mapping does not assert a region-specific artwork or revision.'})
    atomic_json(args.out/'reports'/'seed-matches.json',result)
    return result

def indexes(args):
    old=json.loads((args.out/'index.min.json').read_text(encoding='utf8')) if (args.out/'index.min.json').exists() else {}
    summary_path=args.out/'reports'/'summary.json'
    summary=json.loads(summary_path.read_text(encoding='utf8')) if summary_path.exists() else {}
    for key in args.platforms:
        catalog=json.loads((args.out/'catalogs'/(key+'.json')).read_text(encoding='utf8'))
        games={}; titles=defaultdict(set); missing=[]
        for game in catalog['games']:
            gid=str(game['id']); base='platforms/'+key+'/'
            paths={'path':base+'flat/'+gid+'.jpg','path_3d':base+'3d/'+gid+'.webp','path_3d_dark':base+'3d/dark/'+gid+'.webp'}
            source_path=actual_flat(args.out,key,gid)
            if not source_path.exists():
                missing.append({'igdb_id':game['id'],'name':game['name'],'reason':'no_igdb_cover' if not image_url(game) else 'assets_pending'})
                continue
            renderer=renderer_version(key,source_path)
            if key in ('nds','n3ds'):
                old_flat=args.out/'covers'/(gid+'.jpg')
                if source_path.exists() and old_flat.exists() and digest(source_path)==digest(old_flat):
                    paths['path']='covers/'+gid+'.jpg'
                    if eligible_legacy(args.out,key,game):
                        paths['path_3d']='covers/3d/'+gid+'.webp'
                        paths['path_3d_dark']='covers/3d/dark/'+gid+'.webp'
            complete=all((args.out/path).exists() for path in paths.values())
            if complete:
                try:
                    origin=json.loads((args.out/base/'flat'/(gid+'.source.json')).read_text(encoding='utf8'))
                    complete=origin['source_url']==image_url(game) and origin['sha256']==digest(args.out/paths['path'])
                    for field,theme in [('path_3d','light'),('path_3d_dark','dark')]:
                        state_folder='3d' if theme=='light' else '3d/dark'
                        state=json.loads((args.out/base/state_folder/(gid+'.render.json')).read_text(encoding='utf8'))
                        complete=complete and state=={'renderer':renderer,'source_sha256':origin['sha256'],'title':game['name'],'platform':key,'theme':theme}
                except (OSError,ValueError,KeyError):
                    complete=False
            if not complete:
                missing.append({'igdb_id':game['id'],'name':game['name'],'reason':'no_igdb_cover' if not image_url(game) else 'assets_pending'})
                continue
            actual_ids=[pid for pid in platform_ids(key) if pid in game['platforms']]
            record={'igdb_id':game['id'],'igdb_platform_id':actual_ids[0],'igdb_platform_ids':actual_ids,'name':game['name'],**paths,
             'source':'IGDB','source_url':image_url(game),'igdb_url':game.get('url'), 'cover_id':game['cover'].get('id'), 'image_id':game['cover']['image_id'],
             'artwork_region':'unspecified_by_igdb', 'releases':[r for r in game.get('release_dates',[]) if r.get('platform') in platform_ids(key)],
             'version_parent':game.get('version_parent'),'version_title':game.get('version_title'),
             'renderer':renderer}
            for field,path in paths.items():
                record['sha256'+field.removeprefix('path')]=digest(args.out/path)
            games[gid]=record
            for title in [game['name']]+[a['name'] for a in game.get('alternative_names',[])]:
                titles[normalize(title)].add(gid)
        serials={}
        if key in ('nds','n3ds'):
            for serial,value in old.get('serials',{}).items():
                match=re.search(r'(\d+)(?:\.jpg)?$',str(value))
                gid=match.group(1) if match else str(value)
                is3ds=serial.upper().startswith(('CTR','KTR')) or (bool(re.fullmatch(r'[0-9A-Fa-f]{16}',serial)) and serial.startswith('0004'))
                if gid in games and (key=='n3ds')==is3ds:
                    serials[serial]=gid
        # Arrays preserve collisions; singleton map is safe for clients without candidate support.
        candidates={t:sorted(ids,key=int) for t,ids in sorted(titles.items())}
        index={'version':3,'platform':key,'igdb_platform_id':PLATFORMS[key][0],'igdb_platform_ids':list(platform_ids(key)), 'catalog_complete':catalog['catalog_complete'],
          'total_games':len(games),'games':games,'titles':{t:ids[0] for t,ids in candidates.items() if len(ids)==1},
          'title_candidates':candidates,'serials':serials, 'serial_provenance':'existing DS/3DS index; scoped by exact IGDB platform membership' if serials else 'No verified platform serial source ingested'}
        atomic_json(args.out/'platforms'/key/'index.json',index)
        atomic_json(args.out/'reports'/(key+'-missing.json'),missing)
        summary[key]={'catalog_games':len(catalog['games']),'igdb_cover_available':sum(bool(image_url(g)) for g in catalog['games']),
          'complete_assets':len(games),'missing_igdb_cover':sum(not image_url(g) for g in catalog['games']),
          'assets_pending':sum(bool(image_url(g)) for g in catalog['games'])-len(games),'serials':len(serials),'title_collisions':sum(len(ids)>1 for ids in candidates.values())}
    atomic_json(args.out/'reports'/'summary.json',summary)
    print(json.dumps(summary,indent=2),flush=True)

def validate(args):
    count=0
    counts={}
    index_digests={}
    for key in args.platforms:
        index_bytes=(args.out/'platforms'/key/'index.json').read_bytes()
        index=json.loads(index_bytes)
        index_digests[key]=hashlib.sha256(index_bytes).hexdigest()
        catalog=json.loads((args.out/'catalogs'/(key+'.json')).read_text(encoding='utf8'))
        membership={str(g['id']):g for g in catalog['games']}
        assert catalog['catalog_complete'], 'Catalog pagination is not complete'
        assert len(membership)==len(catalog['games']), 'Duplicate IGDB ID in source catalog'
        assert index['igdb_platform_id']==PLATFORMS[key][0]
        def verify_record(pair):
            gid,game=pair
            assert any(pid in membership[gid]['platforms'] for pid in platform_ids(key))
            assert game['igdb_platform_ids']==[pid for pid in platform_ids(key) if pid in membership[gid]['platforms']]
            assert game['igdb_platform_id'] in game['igdb_platform_ids']
            assert game['source_url']==image_url(membership[gid])
            for field in ('path','path_3d','path_3d_dark'):
                assert game[field].startswith('platforms/'+key+'/') or (key in ('nds','n3ds') and game[field] in ('covers/'+gid+'.jpg','covers/3d/'+gid+'.webp','covers/3d/dark/'+gid+'.webp'))
                path=args.out/game[field]
                assert digest(path)==game['sha256'+field.removeprefix('path')]
                with Image.open(path) as image:
                    image.load()
                    assert min(image.size)>0
                    if field!='path':
                        assert image.size==(840,1080) and image.mode=='RGBA'
            assert game['sha256_3d']!=game['sha256_3d_dark']
        with ThreadPoolExecutor(max_workers=args.validation_workers) as pool:
            list(pool.map(verify_record,index['games'].items()))
        count+=len(index['games'])
        counts[key]=len(index['games'])
        for title,gid in index['titles'].items():
            assert index['title_candidates'][title]==[gid]
        assert all(str(gid) in index['games'] for gid in index['serials'].values())
    assert normalize('Final Fantasy ++')!=normalize('Final Fantasy')
    assert normalize('Super Mario Bros. 3+')!=normalize('Super Mario Bros. 3')
    report='validation-'+args.platforms[0]+'.json' if len(args.platforms)==1 else 'validation.json'
    atomic_json(args.out/'reports'/report,{'passed':True,'total_complete_sets':count,'platform_counts':counts,'index_sha256':index_digests,'validated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'checks':['full_image_decode','sha256','original_igdb_source','exact_platform_membership','complete_catalog_pagination','transparent_840x1080_variants','distinct_light_dark','ambiguous_title_safety']})
    print('Verified',count,'platform-scoped cover sets (flat/light/dark), provenance, digests, membership and ambiguity handling.',flush=True)

def contact_sheet(args):
    rows=[]
    for key in args.platforms:
        index=json.loads((args.out/'platforms'/key/'index.json').read_text(encoding='utf8'))
        seed=json.loads((args.out/'reports'/'seed-matches.json').read_text(encoding='utf8')) if (args.out/'reports'/'seed-matches.json').exists() else []
        preferred=[str(c['igdb_id']) for s in seed for c in s['candidates'] if c['platform']==key and str(c['igdb_id']) in index['games']]
        gid=preferred[0] if preferred else next(iter(index['games']))
        rows.append((key,index['games'][gid]))
    sheet=Image.new('RGB',(1050,len(rows)*260),(38,40,46))
    draw=ImageDraw.Draw(sheet)
    try:
        font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',17)
    except OSError:
        font=ImageFont.load_default()
    for row,(key,game) in enumerate(rows):
        y=row*260
        draw.text((12,y+10),f'{key} | IGDB {game["igdb_id"]} | {game["name"]}',font=font,fill='white')
        for col,field in enumerate(('path','path_3d','path_3d_dark')):
            bg=(245,245,245) if col==1 else (24,26,30)
            canvas=Image.new('RGBA',(320,215),bg+(255,))
            with Image.open(args.out/game[field]) as art:
                art=ImageOps.contain(art.convert('RGBA'),(310,205),Image.Resampling.LANCZOS)
                canvas.alpha_composite(art,((320-art.width)//2,(215-art.height)//2))
            sheet.paste(canvas.convert('RGB'),(col*350+12,y+38))
    path=args.out/'reports'/'contact-sheet.jpg'
    sheet.save(path,quality=91)
    print(path)

def release_scope(args):
    tracked=set(subprocess.check_output(['git','-C',str(args.out),'ls-files','-z']).decode('utf8').split('\0'))
    summary={}
    for key in args.platforms:
        index_path=args.out/'platforms'/key/'index.json'
        index=json.loads(index_path.read_text(encoding='utf8'))
        paths={'platforms/'+key+'/index.json','catalogs/'+key+'.json'}
        for gid,game in index['games'].items():
            paths.update(game[field] for field in ('path','path_3d','path_3d_dark'))
            base='platforms/'+key+'/'
            paths.update([base+'flat/'+gid+'.source.json',base+'3d/'+gid+'.render.json',base+'3d/dark/'+gid+'.render.json'])
        paths={p for p in paths if (args.out/p).exists()}
        new=paths-tracked
        summary[key]={'complete_sets':len(index['games']),'index_sha256':digest(index_path),'referenced_files':len(paths),'new_files':len(new),
          'new_bytes':sum((args.out/p).stat().st_size for p in new),'all_referenced_bytes':sum((args.out/p).stat().st_size for p in paths)}
        target=args.out/'reports'/(key+'-release-paths.txt')
        target.write_text('\n'.join(sorted(paths))+'\n',encoding='utf8')
    atomic_json(args.out/'reports'/'release-scope.json',summary)
    print(json.dumps(summary,indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['catalog','assets','index','validate','contact-sheet','scope','audit-legacy','deduplicate-legacy','seeds'])
    parser.add_argument('--out',type=Path,default=DEFAULT_OUT)
    parser.add_argument('--config',type=Path,default=ROOT/'IGDB'/'config.py')
    parser.add_argument('--seeds',type=Path,default=Path('E:/nINtENDO'))
    parser.add_argument('--platforms',nargs='+',choices=PLATFORMS,default=list(PLATFORMS))
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--workers',type=int,default=16)
    parser.add_argument('--render-workers',type=int,default=4)
    parser.add_argument('--validation-workers',type=int,default=4)
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--download-only',action='store_true')
    parser.add_argument('--checkpoint-every',type=int,default=1000)
    args=parser.parse_args()
    {'catalog':catalog,'assets':assets,'index':indexes,'validate':validate,'contact-sheet':contact_sheet,'scope':release_scope,'audit-legacy':audit_legacy,'deduplicate-legacy':deduplicate_legacy,'seeds':seed_matches}[args.command](args)

if __name__=='__main__':
    main()
