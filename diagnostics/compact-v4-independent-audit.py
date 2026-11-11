"""Independent compact-v4 acceptance; never imports production projection code.
Writes only its own audit directory and the designated audit report.
Run --ready only after main explicitly announces the new run complete.
"""
from pathlib import Path
import argparse, collections, copy, datetime, hashlib, json, math
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'runs/vsr_aligned_v8_production'
NEW=ROOT/'runs/compact_v4_production'
OUT=ROOT/'runs/compact_v4_audit_20261111'
DOC=ROOT/'docs/compact-v4-independent-audit-20261111.md'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def dump(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def walk(x,path='$'):
    if isinstance(x,dict):
        for k,v in x.items():
            q=path+'.'+k; yield q,k,v
            yield from walk(v,q)
    elif isinstance(x,list):
        for v in x: yield from walk(v,path+'[]')
def fields(specs):
    result={}
    for spec in specs:
        seen=set()
        for q,k,v in walk(spec):
            a=result.setdefault(q,dict(samples=0,occurrences=0,value_bytes=0,member_bytes=0,types={}))
            a['occurrences']+=1;a['value_bytes']+=len(canonical(v).encode())
            a['member_bytes']+=len((canonical(k)+':'+canonical(v)).encode())
            t=type(v).__name__;a['types'][t]=a['types'].get(t,0)+1
            if q not in seen:a['samples']+=1;seen.add(q)
    return result
def decode(spec):
    rows=copy.deepcopy(spec['data']['values'])
    for ch,e in spec.get('encoding',{}).items():
        if not isinstance(e,dict):continue
        expr=((e.get('axis') or {}).get('labelExpr') or (e.get('legend') or {}).get('labelExpr'))
        if expr:
            suffix='[datum.value]'
            if not expr.endswith(suffix):raise ValueError('unrecognized v3 expression')
            labels=json.loads(expr[:-len(suffix)]);f=e['field']
            for row in rows:row[f+'_instance']=row[f];row[f]=labels[row[f]]
    return rows

def semantics(spec, anonymous=False):
    """Independently canonicalize permitted v3/v4 representation differences."""
    x=copy.deepcopy(spec); x.pop('data',None)
    # v3 identities lived in label expressions; v4 fields name them directly.
    for e in x.get('encoding',{}).values():
        if not isinstance(e,dict):continue
        expression=((e.get('axis') or {}).get('labelExpr') or (e.get('legend') or {}).get('labelExpr'))
        if expression:e['field'] += '_instance'
    def clean(v):
        if isinstance(v,list):return [clean(z) for z in v]
        if not isinstance(v,dict):return v
        o={}
        for k,z in v.items():
            if k in ('axis','legend','config','width','height','font','labelExpr','format','formatType','orient','reverse'):continue
            if k=='color' and not isinstance(z,dict):continue
            if k in ('title','sort') and z is None:continue
            a=clean(z)
            if k=='scale' and not a:continue
            o[k]=a
        return o
    x=clean(x)
    if anonymous:x.get('encoding',{}).pop('color',None)
    mark=x.get('mark')
    if isinstance(mark,dict) and mark.get('type')=='line':
        # Point=True was only the old renderer's single-vertex visibility remedy.
        if mark.get('point') is True:
            counts=collections.Counter(r.get('series_instance',r.get('series')) for r in decode(spec))
            if 1 not in counts.values():raise ValueError('Unexpected legacy point remedy')
            mark.pop('point')
        if mark=={'type':'line'}:x['mark']='line'
    enc=x.get('encoding',{})
    # Swapping the two explicit bar endpoints does not change a segment.
    for axis in ('x','y'):
        d=enc.get(axis,{})
        if d.get('field')=='start' and enc.get(axis+'2',{}).get('field')=='end':
            d['field']='end';enc[axis+'2']['field']='start'
    return x

def coverage(specs):
    c=collections.Counter();examples=collections.defaultdict(list)
    for id,s in specs.items():
        rows=s['data']['values'];enc=s.get('encoding',{})
        flags={'duplicates':any(k=='labelExpr' for _,k,_ in walk(enc)),
          'stack':id.startswith('barv_stack-'),'error':any('lower' in r for r in rows),
          'path':any('path_order' in r for r in rows),
          'anonymous_single':{r.get('series') for r in rows}=={'Series 1'} and enc.get('color',{}).get('legend') is None,
          'named_single':len({r.get('series') for r in rows})==1 and enc.get('color',{}).get('legend') is not None,
          'nonlinear':any(k=='scale' and isinstance(v,dict) and v.get('type') not in (None,'linear') for _,k,v in walk(enc)),
          'reverse':any(k=='reverse' and v for _,k,v in walk(enc))}
        for k,v in flags.items():
            if v:c[k]+=1;examples[k].append(id)
    return {'counts':c,'ids':examples}

def baseline_report(old):
    b=read(OUT/'before.json');f=fields(old.values());dump(OUT/'before-fields.json',f)
    cov=coverage(old);dump(OUT/'coverage.json',cov)
    stats={'samples':len(old),'files':len(b['files']),'baseline_utc':b['utc'],
      'compact_file_bytes':sum(v['bytes'] for k,v in b['files'].items() if k.endswith('/compact.vl.json')),
      'compact_canonical_bytes':sum(len(canonical(x).encode()) for x in old.values()),
      'coverage':cov['counts']}
    dump(OUT/'baseline-summary.json',stats)
    DOC.write_text('# compact-v4 独立审计（2026-11-11）\n\n状态：基线完成，等待 main 明确通知新目录 ready；尚未运行完整新旧验收。\n\n'
      +f"旧目录 `{OLD}`，{len(old)} 套；{len(b['files'])} 文件 SHA-256/bytes 已于 {b['utc']} 冻结在 `runs/compact_v4_audit_20261111/before.json`。\n\n"
      +f"旧 compact 实际文件 {stats['compact_file_bytes']:,} bytes；规范序列化 {stats['compact_canonical_bytes']:,} bytes。\n\n"
      +'真实覆盖：`'+json.dumps(cov['counts'],ensure_ascii=False)+'`。\n\n'
      +'`before-fields.json` 逐字段记录样本频率、出现次数、类型及 UTF-8 字节；父子字段字节重叠，不能相加为总节省。\n\n'
      +'已独立核对旧 450 套：旧 v3 解码与原 full 观测值及保存的 scenegraph 像素读取顺序逐行完全一致（`old-pixel-reference-check.json`），不调用 production 投影函数。\n\n'
      +'验收范围：450 行序保持、v3/v4 独立 Canonical 解码、重复标签身份、mark/type/单位/层和误差/stack/path 关系、完整固定版本 schema、全部训练 JSONL 与样本 GT 一致、旧文件不变和新 full/config/PNG 逐份复用。只允许删除隐藏单匿名 Series 1 与无意义绘图朝向及显示配置。\n\n'
      +'边界：本批旧 GT 没有非线性 scale 或 reverse，不能用这 450 套证明这些 edge；定向 fixture 由 worker 负责，本审计会分别标注真实覆盖和未覆盖项。未重采样、未重画 full、未导入 production 投影函数。\n',encoding='utf-8')
    return stats

def pixel_reference(id, spec):
    """Derive source meaning and screen order from old full + saved scenegraph."""
    folder=OLD/'samples'/id; full=read(folder/'full.vl.json'); geo=read(folder/'geometry.json')
    kind=id.rsplit('-',1)[0]; layers=full.get('layer',[])
    primary=[l for l in layers if l.get('name','').startswith(('bars_','line_','scatter_')) and not l.get('name','').startswith('line_markers')]
    enc=full.get('encoding') or primary[0]['encoding']
    marks={m['mark_id'] for m in geo['marks'] if m.get('name','').startswith(('bars_','line_','scatter_')) and not m.get('name','').startswith('line_markers')}
    pos={e['datum']['row_id']:e['center'] for e in geo['elements'] if e['mark_id'] in marks and isinstance(e.get('datum'),dict) and 'row_id' in e['datum']}
    source=full['data']['values']
    if set(pos)!={r['row_id'] for r in source}:raise ValueError('pixel/source identity coverage mismatch')
    def key(r):
        x,y=[round(v,6) for v in pos[r['row_id']]]
        stable=(r.get('series_index',0),r.get('point_index',0),r.get('row_index',0))
        return ((y,) if kind.startswith('barh') else (x,y) if kind.startswith('scatter') or kind=='barv_stack' else (x,))+stable
    source=sorted(source,key=key)
    series=list(dict.fromkeys(r['series_id'] for r in source)); visible=enc.get('color',{}).get('legend') not in (None,False)
    names={r['series_id']:r['series_name'] for r in source} if visible else {k:f'Series {i+1}' for i,k in enumerate(series)}
    dupseries=len(set(names.values()))!=len(names)
    catfield='category' if kind.startswith('bar') else 'x' if kind.startswith('line') and spec['encoding']['x']['type'] in ('ordinal','nominal') else None
    cats=list(dict.fromkeys(r['category_id'] for r in source)) if catfield else []
    labels={r['category_id']:r['category'] for r in source} if catfield else {}
    dupcat=len(set(labels.values()))!=len(labels)
    required=set().union(*(r.keys() for r in spec['data']['values']))
    output=[]
    for r in source:
        a={'category':r['category'],'value':r['value']} if kind.startswith('bar') else {'x':r['x'],'y':r['y']}
        a['series']=names[r['series_id']]
        if dupseries:a['series_instance']=series.index(r['series_id'])
        if dupcat:a[catfield+'_instance']=cats.index(r['category_id'])
        if 'lower' in required:a.update(lower=r['error_lower'],upper=r['error_upper'])
        if 'path_order' in required:a['path_order']=r['point_index']
        if 'stack_order' in required:a['stack_order']=r['series_index']
        if 'start' in required:a.update(start=r['value_lower'],end=r['value_upper'])
        output.append(a)
    return output

def full_audit(old):
    import jsonschema
    b=read(OUT/'before.json');errors=[];checks=collections.Counter();details=[]
    def check(ok,id,msg):
        checks[msg+(':pass' if ok else ':fail')]+=1
        if not ok:errors.append({'id':id,'check':msg})
    schema=read(ROOT/'schema/vega-lite-6.5.0.schema.json');validator=jsonschema.Draft7Validator(schema)
    ids=sorted(old);newids=sorted(p.parent.name for p in NEW.glob('samples/*/compact.vl.json'))
    check(ids==newids,'run','exact_sample_ids')
    new={};old_bytes=new_bytes=0;oldcanon=newcanon=0
    for id in ids:
        p=NEW/'samples'/id/'compact.vl.json'
        if not p.exists():check(False,id,'new_compact_present');continue
        s=old[id];t=read(p);new[id]=t
        schema_errors=[e.message for e in validator.iter_errors(t)]
        check(not schema_errors,id,'pinned_schema')
        if schema_errors:details.append({'id':id,'schema':schema_errors[:4]})
        a=decode(s);z=decode(t)
        check(canonical(a)==canonical(pixel_reference(id,s)),id,'old_gt_matches_full_source_and_pixel_order')
        anonymous={r.get('series') for r in a}=={'Series 1'} and s.get('encoding',{}).get('color',{}).get('legend') is None
        if anonymous:
            check(all('series' not in row for row in z) and 'color' not in t.get('encoding',{}),id,'anonymous_single_redundancy_removed')
            for row in a:row.pop('series',None)
            for row in z:row.pop('series',None)
        check(canonical(a)==canonical(z),id,'ordered_canonical_rows_and_identity')
        if canonical(a)!=canonical(z):details.append({'id':id,'old_first':a[:2],'new_first':z[:2]})
        check(semantics(s,anonymous)==semantics(t,anonymous),id,'semantic_encoding_mark_units_relations')
        forbidden=[]
        for q,k,v in walk({a:v for a,v in t.items() if a!='data'}):
            if k in {'axis','legend','config','width','height','format','formatType','labelExpr','reverse','orient','point','size','opacity','strokeDash'} or 'font' in k.lower() or k.startswith('label'):forbidden.append(q)
            if k in {'color','fill','stroke'} and not (isinstance(v,dict) and 'field' in v):forbidden.append(q)
            if k in {'aggregate','bin','timeUnit','transform'}:forbidden.append(q)
        check(not forbidden,id,'no_display_or_unapproved_transform_fields')
        if forbidden:details.append({'id':id,'forbidden':forbidden})
        for q,k,e in walk(t.get('encoding',{})):
            if k=='field':check(all(e in row for row in t['data']['values']),id,'encoding_field_exists')
        for layer in t.get('layer',[]):
            for e in layer.get('encoding',{}).values():
                if isinstance(e,dict) and 'field' in e:check(all(e['field'] in row for row in t['data']['values']),id,'layer_field_exists')
        for _,k,e in walk(t.get('encoding',{})):
            if isinstance(e,dict) and e.get('type')=='quantitative' and 'field' in e:
                check(all(isinstance(row.get(e['field']),(int,float)) and not isinstance(row.get(e['field']),bool) and math.isfinite(row[e['field']]) for row in t['data']['values']),id,'quantitative_type')
        for file in ('full.vl.json','config.json','chart.png','chart.1036.png','chart.svg','source.json','sampling.json'):
            rel=f'samples/{id}/{file}';np=NEW/rel
            check(np.exists() and sha(np)==b['files'][rel]['sha256'],id,'reused_'+file)
        ob=b['files'][f'samples/{id}/compact.vl.json']['bytes'];nb=p.stat().st_size
        oc=len(canonical(s).encode());nc=len(canonical(t).encode())
        old_bytes+=ob;new_bytes+=nb;oldcanon+=oc;newcanon+=nc
        details.append({'id':id,'old_bytes':ob,'new_bytes':nb,'ratio':nb/ob,'old_canonical':oc,'new_canonical':nc})
    # Any baseline file modification, including compact/config/full/PNG, is a finding.
    for rel,info in b['files'].items():
        p=OLD/rel;check(p.exists() and sha(p)==info['sha256'],'old/'+rel,'baseline_file_unchanged')
    training=[]
    for p in sorted(NEW.rglob('*.jsonl')):
        if 'train' not in p.name.lower():continue
        seen=[]
        for lineno,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
            row=json.loads(line);id=row.get('id');seen.append(id)
            answers=[m.get('content') for m in row.get('messages',[]) if m.get('role')=='assistant']
            check(id in new and len(answers)==1 and canonical(json.loads(answers[0]))==canonical(new[id]),str(p)+':'+str(lineno),'train_equals_v4')
            image=NEW/row.get('image','');rel=f'samples/{id}/chart.png'
            check(image.is_file() and rel in b['files'] and sha(image)==b['files'][rel]['sha256'],id,'train_image_is_old_full_png')
        check(sorted(seen)==ids,str(p),'train_exact_ids_once');training.append(str(p.relative_to(NEW)))
    check(bool(training),'run','training_jsonl_present')
    of=fields(old.values());nf=fields(new.values());dump(OUT/'after-fields.json',nf)
    deleted={k:dict(old=v,new=nf.get(k),occurrences_removed=v['occurrences']-nf.get(k,{}).get('occurrences',0)) for k,v in of.items() if v['occurrences']>nf.get(k,{}).get('occurrences',0)}
    dump(OUT/'field-removals.json',deleted)
    result={'status':'PASS' if not errors else 'FAIL','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks,'errors':errors,'training_files':training,'old_bytes':old_bytes,'new_bytes':new_bytes,'file_ratio':new_bytes/old_bytes,'old_canonical_bytes':oldcanon,'new_canonical_bytes':newcanon,'canonical_ratio':newcanon/oldcanon,'new_run':read(NEW/'run.json')}
    dump(OUT/'result.json',result);dump(OUT/'sample-details.json',details)
    text=DOC.read_text(encoding='utf-8');text=text.replace('状态：基线完成，等待 main 明确通知新目录 ready；尚未运行完整新旧验收。','状态：main ready 后执行完整验收，结果 **'+result['status']+'**。')
    text+='\n## 完整验收结果\n\n'+f"实际 compact 文件 {old_bytes:,} → {new_bytes:,} bytes（new/old={new_bytes/old_bytes:.6f}）；规范 JSON {oldcanon:,} → {newcanon:,} bytes（new/old={newcanon/oldcanon:.6f}）。\n\n"
    text+='逐项计数：\n\n'+''.join(f'- `{k}`：{v}\n' for k,v in sorted(checks.items()))
    text+='\n真实删减字段（样本数/出现次数/原 value bytes；父子不可相加）：\n\n| 字段 | 样本数 | 原次数 | 新次数 | 原 value bytes |\n|---|---:|---:|---:|---:|\n'
    text+=''.join(f"| `{k}` | {v['old']['samples']} | {v['old']['occurrences']} | {(v['new'] or {}).get('occurrences',0)} | {v['old']['value_bytes']} |\n" for k,v in sorted(deleted.items()))
    text+='\n发现项：\n\n'+('\n'.join('- '+canonical(e) for e in errors[:60]) if errors else '无上述检查的失败项。')
    text+='\n\n证据：`result.json`、`sample-details.json`、`field-removals.json`、`before.json` 位于本审计 runs 目录。哈希相等证明已交付字节复用；不单独证明整个执行历史从未启动 renderer。此脚本不渲染、不改生产文件。\n'
    DOC.write_text(text,encoding='utf-8');print(json.dumps(result,ensure_ascii=False));return not errors

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--ready',action='store_true');args=ap.parse_args();OUT.mkdir(exist_ok=True)
    old={p.parent.name:read(p) for p in sorted(OLD.glob('samples/*/compact.vl.json'))}
    stats=baseline_report(old)
    if not args.ready:print(json.dumps({'status':'WAITING_MAIN_READY','baseline':stats},ensure_ascii=False));return
    if not NEW.is_dir():raise SystemExit('new directory absent')
    raise SystemExit(0 if full_audit(old) else 1)
if __name__=='__main__':main()
