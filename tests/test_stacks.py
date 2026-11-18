import copy
import unittest
from adapter import build_pair
from compact import normalize
from generation.core import sample_config, sample_horizontal_stack
from test_adapter import fixture
from workflow.validation import audit_visible_order

class StackTests(unittest.TestCase):
    def test_horizontal_sampler_has_absolute_segments_and_exact_cumulative_boundaries(self):
        for seed in (0, 7, 101, 20261109):
            c=sample_config('barh_stack',seed,{'series_count':3,'category_count':4})
            self.assertEqual(c['stack_mode'],'absolute')
            self.assertIn('bar_height',c)
            for j in range(4):
                total=0
                for i in range(3):
                    self.assertAlmostEqual(c['bottoms'][i][j],total)
                    total+=c['matrix'][i][j]
            with self.assertRaises(ValueError):
                sample_config('barh_stack',seed,{'stack_mode':'percent'})

    def test_both_stack_directions_and_reversed_axes_preserve_source_segments(self):
        for kind in ('barv_stack','barh_stack'):
            for reverse in (False,True):
                c=fixture(kind);c.update(labels=['A','B','C'],matrix=[[2,3,4],[5,6,7]],bottoms=[[0,0,0],[2,3,4]],xerr=None,yerr=None,show_error=False)
                axis='x' if kind.startswith('barh') else 'y'
                c['_render_axes']={axis+'_inverted':reverse}
                full,gt,source=build_pair(kind,c)
                mids=[(r['value_lower']+r['value_upper'])/2 for r in source['rows']]
                for offset in range(0,len(mids),2):
                    self.assertEqual(mids[offset:offset+2],sorted(mids[offset:offset+2],reverse=reverse))
                self.assertEqual(normalize(gt),gt)
                self.assertEqual(sorted(r['value'] for r in source['rows']),[2,3,4,5,6,7])

    def test_independent_geometry_audit_uses_bottom_to_top_and_left_to_right(self):
        rows=[{'row_id':'a'},{'row_id':'b'}]
        for kind,anchors in [('barv_stack',[(10,30),(10,10)]),('barh_stack',[(10,10),(30,10)])]:
            primary=[{'datum':r,'anchor':a} for r,a in zip(rows,anchors)]
            self.assertEqual(audit_visible_order(kind,rows,primary),[])
            self.assertTrue(audit_visible_order(kind,list(reversed(rows)),primary))
