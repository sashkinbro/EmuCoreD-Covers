"""Native-resolution alpha WebP comparison using an actual IGDB source scan."""
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from multiplatform_covers import DEFAULT_OUT, generic_render, atomic_json

out=DEFAULT_OUT
samples=[('gb',1129),('gba',49542),('snes',259651)]
results=[]
for key,gid in samples:
    catalog=json.loads((out/'catalogs'/(key+'.json')).read_text(encoding='utf8'))
    game=next(g for g in catalog['games'] if g['id']==gid)
    with Image.open(out/'platforms'/key/'flat'/(str(gid)+'.jpg')) as source:
        reference=generic_render(source,game['name'],key,'light')
    png=io.BytesIO(); reference.save(png,'PNG')
    comparisons=[]
    decoded={}
    for quality in (92,90,88):
        encoded=io.BytesIO(); reference.save(encoded,'WEBP',quality=quality,method=4)
        encoded.seek(0)
        restored=Image.open(encoded).convert('RGBA')
        decoded[quality]=restored
        errors=[]
        for backdrop in ('white','#181a1e'):
            a=Image.new('RGBA',reference.size,backdrop); a.alpha_composite(reference)
            b=Image.new('RGBA',reference.size,backdrop); b.alpha_composite(restored)
            mse=np.mean((np.asarray(a.convert('RGB'),dtype=np.float64)-np.asarray(b.convert('RGB'),dtype=np.float64))**2)
            errors.append(round(10*np.log10(255**2/max(mse,1e-20)),3))
        comparisons.append({'quality':quality,'bytes':len(encoded.getvalue()),'psnr_light_dark_db':errors,
          'alpha_exact':bool(np.array_equal(np.asarray(reference.getchannel('A')),np.asarray(restored.getchannel('A'))))})
    results.append({'platform':key,'igdb_id':gid,'name':game['name'],'lossless_png_bytes':len(png.getvalue()),'webp':comparisons,'selected_quality':92})
    # 1:1 crop retains exact edge/spine/text pixels for a meaningful visual review.
    crop=(30,80,600,800)
    sheet=Image.new('RGB',(1140,750),'#ddd')
    draw=ImageDraw.Draw(sheet)
    for col,(label,art) in enumerate([('Lossless rendered reference',reference),('Alpha WebP quality 92 (selected)',decoded[92])]):
        bg=Image.new('RGBA',art.size,'white'); bg.alpha_composite(art)
        sheet.paste(bg.crop(crop).convert('RGB'),(570*col,30))
        draw.text((570*col+10,8),label,fill='black')
    sheet.save(out/'reports'/('quality-native-'+key+'.png'))
atomic_json(out/'reports'/'quality-comparison.json',results)
print(json.dumps(results,indent=2))
