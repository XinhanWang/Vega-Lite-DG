"""Native errorbar GT contract and real interval geometry regressions."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from adapter import build_geometry_pair
from compact import normalize, project_rows, semantic_rows, validate_target
from compact_display import render_spec
from test_adapter import fixture

BAR_KINDS = ['barh_1', 'barh_n', 'barv_1', 'barv_n', 'barv_stack']


def target_for(kind, endpoints=False):
    cfg = fixture(kind)
    if kind == 'barv_stack':
        cfg.update(show_error=True, matrix=[[2, 3, 1], [4, 5, 2]],
                   bottoms=[[5, 5, 5], [7, 8, 6]] if endpoints else [[0, 0, 0], [2, 3, 1]])
    full = build_geometry_pair(kind, cfg)[0]
    return full, normalize(full)


class NativeErrorbarTests(unittest.TestCase):
    def test_all_bar_kinds_are_lossless_native_intervals(self):
        for kind in BAR_KINDS:
            with self.subTest(kind=kind):
                full, gt = target_for(kind)
                before = copy.deepcopy(full)
                validate_target(gt)
                axis = 'x' if kind.startswith('barh') else 'y'
                self.assertEqual(gt['layer'][1]['mark'], {'type': 'errorbar'})
                self.assertEqual(gt['layer'][1]['encoding'][axis]['field'], 'lower')
                self.assertEqual(gt['layer'][1]['encoding'][axis + '2'], {'field': 'upper'})
                self.assertEqual(semantic_rows(gt), project_rows(full))
                self.assertEqual(normalize(gt), gt)
                self.assertEqual(render_spec(gt)['data'], gt['data'])
                self.assertEqual(full, before)
                if kind == 'barv_stack':
                    self.assertIsNone(gt['layer'][1]['encoding'][axis]['stack'])
                legacy = copy.deepcopy(gt)
                legacy['layer'][1]['mark'] = {'type': 'rule'}
                with self.assertRaisesRegex(ValueError, 'unsupported layer structure'):
                    validate_target(legacy)

    def test_explicit_stack_endpoints_keep_absolute_errors(self):
        full, gt = target_for('barv_stack', endpoints=True)
        self.assertEqual(gt['encoding']['y']['field'], 'end')
        self.assertEqual(gt['encoding']['y2'], {'field': 'start'})
        self.assertIsNone(gt['layer'][1]['encoding']['y']['stack'])
        self.assertEqual(semantic_rows(gt), project_rows(full))

    def test_real_native_errorbar_geometry(self):
        modules = os.environ.get('VSR_TEXT_TEST_MODULES')
        if not modules or not shutil.which('node'):
            self.skipTest('Set VSR_TEXT_TEST_MODULES to installed Vega dependencies')
        fixtures = [(kind, target_for(kind)[1]) for kind in BAR_KINDS]
        fixtures.append(('barv_stack_endpoints', target_for('barv_stack', endpoints=True)[1]))
        log = copy.deepcopy(fixtures[0][1])
        for row in log['data']['values']:
            row['value'] = abs(row['value']) + 2
            row['lower'], row['upper'] = row['value'] / 2, row['value'] * 2
        # Explicit non-stacked log bars must not add a zero baseline to the log domain.
        log['encoding'].pop('color', None)
        for row in log['data']['values']:
            row.pop('series', None)
        log['encoding']['x']['scale'] = {'type': 'log', 'base': 2}
        log['encoding']['x']['stack'] = None
        validate_target(log)
        fixtures.append(('barh_log', log))
        js = r"""
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{createRequire}=require('module'),{pathToFileURL}=require('url');
const req=createRequire(path.resolve(process.env.VSR_TEXT_TEST_MODULES,'__errorbar.cjs'));
(async()=>{
 const v=await import(pathToFileURL(req.resolve('vega'))),vl=await import(pathToFileURL(req.resolve('vega-lite')));
 const results=[];
 for(const [name,gt] of JSON.parse(fs.readFileSync(0,'utf8'))){
  const warnings=[],logger=v.logger(v.Warn);logger.warn=(...a)=>{warnings.push(a.join(' '));return logger};
  const compiled=vl.compile(gt,{logger}).spec,view=new v.View(v.parse(compiled),{renderer:'none',logger});
  await view.runAsync();const marks=[];
  function visit(s){for(const i of s.items||[]){if(s.role==='mark')marks.push({type:s.marktype,i});if(i.items)visit(i)}}
  visit(view.scenegraph().root);
  const bars=marks.filter(m=>m.type==='rect'),rules=marks.filter(m=>m.type==='rule');
  assert.equal(bars.length,gt.data.values.length,name+' bar count');assert.equal(rules.length,bars.length,name+' error count');
  const h=gt.encoding.x.field==='value',val=h?'x':'y',cat=h?'y':'x';
  for(const {i} of rules){
   const bar=bars.find(b=>['category','category_id','series','series_id'].every(k=>b.i.datum[k]===i.datum[k]))?.i;
   assert(bar,name+' matching bar');
   const actual=[i[val],i[val+'2']].sort((a,b)=>a-b),expected=[view.scale(val)(i.datum.lower),view.scale(val)(i.datum.upper)].sort((a,b)=>a-b);
   assert([...expected,...actual].every(Number.isFinite),name+' nonfinite geometry');
   expected.forEach((p,j)=>assert(Math.abs(p-actual[j])<1e-6,name+' absolute endpoint drift'));
   assert(Math.abs(i[cat]-(bar[cat]+bar[h?'height':'width']/2))<1e-6,name+' category/group center drift');
  }
  assert.equal(warnings.length,0,name+': '+warnings.join('; '));assert((await view.toSVG()).includes('<svg'));
  view.finalize();results.push({name,intervals:rules.length,warnings});
 }
 process.stdout.write(JSON.stringify(results));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
"""
        completed = subprocess.run(['node', '-e', js], input=json.dumps([(n, render_spec(t)) for n, t in fixtures]),
                                   text=True, capture_output=True, env=os.environ.copy())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        results = json.loads(completed.stdout)
        self.assertEqual(len(results), 7)
        self.assertTrue(all(r['intervals'] > 0 and not r['warnings'] for r in results))


if __name__ == '__main__':
    unittest.main()
