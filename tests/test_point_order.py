import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generation.vsr_runtime import parameter_namespace
from generation.vsr_text import numeric_ticks
from ordering import needs_path_order, visual_rows
from adapter import build_geometry_pair
from compact import normalize
from test_adapter import fixture


class PointOrderTests(unittest.TestCase):
    def test_inverse_x_survives_projection(self):
        cfg=fixture('line_n');cfg['xlim']=[4,0]
        full=build_geometry_pair('line_n',cfg)[0]
        target=normalize(full)
        self.assertTrue(target['encoding']['x']['scale']['reverse'])
        self.assertEqual(normalize(target),target)

    def test_discrete_retreat_keeps_axis_domain_separate_from_path(self):
        for repeated in (False,True):
            cfg=fixture('line_n');cfg.update(x_mode='categorical',x_labels=['A','A' if repeated else 'B','C'])
            full=build_geometry_pair('line_n',cfg)[0]
            for row in full['data']['values']:
                row['point_index']={0:0,1:2,2:1}[row['point_index']]
            target=normalize(full)
            self.assertEqual(target['encoding']['x']['sort'],['X1','X3','X2'] if repeated else ['A','B','C'])
            self.assertTrue(all('path_order' in r for r in target['data']['values']))
            self.assertEqual(normalize(target),target)

    def test_screen_scatter_sort_does_not_mutate_input(self):
        rows = [dict(plot_x=x, plot_y=y, series_id=str(i%2), point_index=i) for i,(x,y) in enumerate([(2,1),(1,2),(1,4),(2,3)])]
        for xr in (False, True):
            for yr in (False, True):
                result=visual_rows('scatter_n',rows,x_reverse=xr,y_reverse=yr)
                self.assertEqual(result,sorted(rows,key=lambda r:((-1 if xr else 1)*r['plot_x'],(1 if yr else -1)*r['plot_y'])))
                self.assertEqual(rows[0]['plot_x'],2)

    def test_retreat_is_strict_and_series_local(self):
        for xs,reverse,expected in [([1,2,3],False,False),([1,1,2],False,False),([1,3,2],False,True),([3,2,1],True,False),([3,1,2],True,True)]:
            rows=[dict(plot_x=x,plot_y=0,series_id=s,point_index=i) for i,x in enumerate(xs) for s in ('a','b')]
            result=visual_rows('line_n',rows,x_reverse=reverse)
            self.assertEqual([r['plot_x'] for r in result if r['series_id']=='a'],xs)
            self.assertEqual(needs_path_order(result,x_reverse=reverse),expected)

    def test_production_numeric_finalizers_retain_raw_values(self):
        for kind in ('barh_1','barv_n','barv_stack','line_1','scatter_n'):
            ns,_=parameter_namespace(kind,17)
            values=[1.234567891,-0.0000000000007,12.987654321]
            name='finalize_matrix' if 'finalize_matrix' in ns else 'finalize_series' if 'finalize_series' in ns else 'finalize_values'
            source=[values] if name in ('finalize_matrix','finalize_series') else values
            self.assertEqual(np.asarray(ns[name](source)).tolist(),source)

    def test_numeric_tick_labels_equal_their_positions(self):
        for low,high in [(-14.32,91.23),(.00012,.00098),(12,12),(1e6,1.2e6)]:
            ticks,labels=numeric_ticks(low,high,6)
            self.assertTrue(ticks)
            self.assertEqual([float(label) for label in labels],ticks)
