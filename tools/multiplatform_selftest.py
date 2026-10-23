"""Offline behavioral checks for identity, cache repair and source-aspect geometry."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import multiplatform_covers as pipeline


class PipelineTests(unittest.TestCase):
    def test_distinct_hack_titles_survive_normalization(self):
        self.assertNotEqual(pipeline.normalize('Final Fantasy ++'),pipeline.normalize('Final Fantasy'))
        self.assertNotEqual(pipeline.normalize('Super Mario Bros. 3+'),pipeline.normalize('Super Mario Bros. 3'))
        self.assertEqual(pipeline.normalize('Pokémon: Red'),pipeline.normalize('Pokemon - Red'))

    def test_changed_igdb_source_and_corrupt_cache_are_refetched(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.jpg'
            game={'id':1,'cover':{'image_id':'co_first'}}
            encoded=io.BytesIO()
            Image.new('RGB',(64,80),'red').save(encoded,'JPEG')
            payload=encoded.getvalue()
            with patch.object(pipeline.urllib.request,'urlopen',side_effect=lambda *a,**kw:io.BytesIO(payload)) as fetch:
                self.assertTrue(pipeline.ensure_flat((game,path))[1])
                self.assertEqual(fetch.call_count,1)
                self.assertTrue(pipeline.ensure_flat((game,path))[1])
                self.assertEqual(fetch.call_count,1,'Valid checkpoint must resume without network')
                game['cover']['image_id']='co_second'
                self.assertTrue(pipeline.ensure_flat((game,path))[1])
                self.assertEqual(fetch.call_count,2,'Changed image ID must invalidate cache')
                path.write_bytes(b'corrupt')
                self.assertTrue(pipeline.ensure_flat((game,path))[1])
                self.assertEqual(fetch.call_count,3,'Corrupt source must be repaired')

    def test_physical_box_aspect_changes_on_fixed_transparent_canvas(self):
        boxes=[]
        for size in ((600,900),(800,800),(1200,600)):
            output=pipeline.generic_render(Image.new('RGB',size,'red'),'Aspect QA','gba','light')
            self.assertEqual(output.size,(840,1080))
            self.assertEqual(output.mode,'RGBA')
            x1,y1,x2,y2=output.getchannel('A').point(lambda p:255 if p>10 else 0).getbbox()
            boxes.append((x2-x1)/(y2-y1))
        self.assertLess(boxes[0],.85)
        self.assertTrue(.9<boxes[1]<1.15)
        self.assertGreater(boxes[2],1.6,'Landscape source must produce a landscape physical case')


if __name__=='__main__':
    unittest.main()
