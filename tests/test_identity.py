"""Canonical identity columns, legacy migration and nonmutating label rendering."""
import copy
import json
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from compact import normalize, validate_target
from compact_display import render_spec
from identity import migrate_spec, order_row
from test_compact_semantic_v4 import full_for

class IdentityContractTests(unittest.TestCase):
    def sample(self,kind='barv_n',**kwargs):
        kwargs.setdefault('show_error',False)
        kwargs.setdefault('xerr',None);kwargs.setdefault('yerr',None)
        if 'names' in kwargs:kwargs['series_names']=kwargs.pop('names')
        return normalize(full_for(kind,**kwargs))

    def test_canonical_field_order_and_all_dimension_ids(self):
        gt=self.sample()
        self.assertEqual(list(gt['data']['values'][0]),['category','category_id','value','series','series_id'])
        self.assertEqual([r['category_id'] for r in gt['data']['values']],['C1','C1','C2','C2','C3','C3'])
        self.assertEqual([r['series_id'] for r in gt['data']['values']],['S1','S2']*3)
        self.assertEqual(gt,normalize(gt))

    def test_unique_objects_no_extra_columns(self):
        gt=self.sample(labels=['A','B','C'],names=['One','Two'])
        self.assertEqual(list(gt['data']['values'][0]),['category','value','series'])

    def test_single_series_no_legend(self):
        gt=self.sample('barv_1',labels=['A','B','C'],show_legend=False)
        self.assertEqual(list(gt['data']['values'][0]),['category','value'])

    def test_only_categories_repeated(self):
        gt=self.sample(names=['One','Two'])
        self.assertIn('category_id',gt['data']['values'][0]);self.assertNotIn('series_id',gt['data']['values'][0])

    def test_only_series_repeated(self):
        gt=self.sample(labels=['A','B','C'])
        self.assertNotIn('category_id',gt['data']['values'][0]);self.assertIn('series_id',gt['data']['values'][0])

    def test_discrete_x_separate_namespace(self):
        gt=self.sample('line_n',x_mode='categorical',x_labels=['Jan','Jan','Feb'])
        self.assertEqual(gt['encoding']['x']['field'],'x_id')
        self.assertEqual([r['x_id'] for r in gt['data']['values']],['X1','X1','X2','X2','X3','X3'])
        self.assertEqual(list(gt['data']['values'][0]),['x','x_id','y','series','series_id'])

    def test_old_integer_columns_import_export(self):
        gt=self.sample();old=copy.deepcopy(gt)
        for r in old['data']['values']:
            for f,prefix in [('category','C'),('series','S')]:
                r[f+'_instance']=int(r.pop(f+'_id')[1:])-1
        for d in old['encoding'].values():
            if d['field'].endswith('_id'):d['field']=d['field'][:-3]+'_instance'
        before=copy.deepcopy(old)
        self.assertEqual(normalize(old),gt);self.assertEqual(before,old)
        self.assertEqual(migrate_spec(migrate_spec(old)),gt)

    def test_all_numeric_fields_before_series(self):
        gt=self.sample(show_error=True,yerr=[[.1]*3,[.2]*3])
        for r in gt['data']['values']:
            self.assertLess(list(r).index('upper'),list(r).index('series'))
            self.assertEqual(list(r)[-2:],['series','series_id'])

    def test_renderer_only_adds_expressions_on_copy(self):
        gt=self.sample();before=copy.deepcopy(gt);preview=render_spec(gt)
        self.assertEqual(gt,before);self.assertNotIn('labelExpr',json.dumps(gt))
        self.assertIn('C1',preview['encoding']['x']['axis']['labelExpr'])
        self.assertIn('S1',preview['encoding']['color']['legend']['labelExpr'])
        self.assertEqual(preview['data'],gt['data'])

    def test_reject_partial_conflicting_and_redundant_ids(self):
        gt=self.sample()
        bad=copy.deepcopy(gt);del bad['data']['values'][0]['category_id']
        with self.assertRaises(ValueError):normalize(bad)
        bad=copy.deepcopy(gt);bad['data']['values'][1]['category']='Wrong'
        with self.assertRaises(ValueError):normalize(bad)
        bad=self.sample(labels=['A','B','C'],names=['One','Two'])
        for i,r in enumerate(bad['data']['values']):r['series_id']='S'+str(i%2+1)
        bad['encoding']['color']['field']='series_id'
        with self.assertRaises(ValueError):validate_target(bad)

    def test_validator_rejects_invalid_spelling_sequence_and_order(self):
        for value in [0,'C0','C01','c1','C2']:
            bad=self.sample();bad['data']['values'][0]['category_id']=value
            with self.assertRaises(ValueError):validate_target(bad)
        bad=self.sample();r=bad['data']['values'][0];bad['data']['values'][0]={k:r[k] for k in reversed(list(r))}
        with self.assertRaises(ValueError):validate_target(bad)

    def test_shared_studio_fixtures_validate_and_roundtrip(self):
        for case in json.loads((ROOT/'tests/fixtures/identity-contract.json').read_text(encoding='utf-8')):
            with self.subTest(case=case['name']):
                validate_target(case['gt']);self.assertEqual(normalize(case['gt']),case['gt'])

    def test_import_reorders_rows_without_renaming_original_text(self):
        gt=self.sample();old=copy.deepcopy(gt)
        old['data']['values']=[dict(reversed(list(r.items()))) for r in old['data']['values']]
        self.assertEqual(normalize(old),gt)

if __name__=='__main__':unittest.main()
