"""Package observed compact-v4 results and a self-contained comparison gallery."""
from pathlib import Path
import base64, copy, datetime, hashlib, html, importlib.util, json, shutil, subprocess, tarfile
from PIL import Image, ImageOps, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'runs/vsr_aligned_v8_production'; NEW=ROOT/'runs/compact_v4_production'; FRESH=ROOT/'runs/compact_v4_fresh_20261111'
AUDIT=ROOT/'runs/compact_v4_audit_20261111'; OUT=ROOT/'deliveries/compact_v4_20261111'
OUT.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pretty(v):return json.dumps(v,ensure_ascii=False,indent=2)
def embed(p):return 'data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()
r=read(AUDIT/'result.json');v=read(NEW/'validation.json');fresh=read(FRESH/'validation.json')
assert r['status']=='PASS' and not r['errors'] and v['accepted']==450 and fresh['accepted']==27
# Repair inherited command provenance using the command actually executed and retained in this chat/log.
p=NEW/'run.json';before=read(p)
if 'source_command' not in before:
    after={**before,'source_command':before.get('command'),'command':['pipeline.py','reproject','--source','runs/vsr_aligned_v8_production','--output','runs/compact_v4_production','--compact-only'],
           'validation_command':['pipeline.py','validate','--output','runs/compact_v4_production']}
    dump(OUT/'provenance-correction.json',{'reason':'Migration originally inherited the source command; explicit migration/source commands are now separate. No sample files changed.','before':before,'after':after})
    dump(p,after)
# Independent checker mutation controls: no production projection import.
spec=importlib.util.spec_from_file_location('independent',ROOT/'diagnostics/compact-v4-independent-audit.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
controls=[]
ids=sorted(x.parent.name for x in NEW.glob('samples/*/compact.vl.json'))
for mutation in ('observation','row_order','unit','grouping','identity','error','stack','path'):
    target=None
    for id in ids:
        t=read(NEW/'samples'/id/'compact.vl.json');fields=set(t['data']['values'][0]);enc=t['encoding']
        if mutation=='grouping' and 'xOffset' not in enc and 'yOffset' not in enc:continue
        if mutation=='identity' and not any(k.endswith('_instance') for k in fields):continue
        if mutation=='error' and 'lower' not in fields:continue
        if mutation=='stack' and not {'stack_order','start'} & fields:continue
        if mutation=='path' and 'path_order' not in fields:continue
        if mutation=='row_order' and len(t['data']['values'])<2:continue
        target=(id,t);break
    assert target is not None,mutation
    id,t=target;bad=copy.deepcopy(t);rows=bad['data']['values']
    if mutation=='observation':rows[0]['value' if 'value' in rows[0] else 'y']+=1
    elif mutation=='row_order':rows.reverse()
    elif mutation=='unit':bad['encoding']['y']['title']='DIFFERENT UNIT'
    elif mutation=='grouping':bad['encoding'].pop('xOffset' if 'xOffset' in bad['encoding'] else 'yOffset')
    elif mutation=='identity':rows[0][next(k for k in rows[0] if k.endswith('_instance'))]+=100
    elif mutation=='error':rows[0]['lower']-=1
    elif mutation=='stack':rows[0]['stack_order' if 'stack_order' in rows[0] else 'start']+=100
    elif mutation=='path':rows[0]['path_order']+=100
    detected=a.decode(t)!=a.decode(bad) or a.semantics(t)!=a.semantics(bad)
    assert detected,mutation
    controls.append({'mutation':mutation,'sample':id,'detected':detected})
dump(OUT/'audit-mutation-controls.json',controls)
# Current snapshots plus original, untouched audit outcome.
for name in ('result.json','sample-details.json','field-removals.json','coverage.json','before-fields.json','after-fields.json','before.json'):
    shutil.copy2(AUDIT/name,OUT/name)
for folder,label in ((NEW,'migration-validation.json'),(FRESH,'fresh-validation.json')):
    shutil.copy2(folder/'validation.json',OUT/label)
shutil.copy2(NEW/'run.json',OUT/'current-migration-run.json')
log=(ROOT/'history/compact-v4-resume-20261111/regression-final.log').read_text()
import re
count=int(re.search(r'Ran (\d+) tests',log)[1]);assert '\nOK\n' in log
shutil.copy2(ROOT/'history/compact-v4-resume-20261111/regression-final.log',OUT/'regression-final.log')
# Verify all fresh targets match exported answers and every rendered SVG includes embedded fonts.
answers={t['id']:json.loads(t['messages'][1]['content']) for t in map(json.loads,(FRESH/'train.jsonl').read_text().splitlines())}
svg_count=0
for id,t in answers.items():
    s=FRESH/'samples'/id;assert t==read(s/'compact.vl.json')
    assert read(s/'compact.preview.vl.json')['data']==t['data']
    for name in ('chart.svg','compact.svg'):
        svg=(s/name).read_text();assert '@font-face' in svg and 'data:font/' in svg and '<text' in svg
        svg_count+=1
dump(OUT/'fresh-artifact-audit.json',{'samples':len(answers),'embedded_font_svgs':svg_count,'training_gt_equal':True,'preview_data_equal':True})
cov=read(AUDIT/'coverage.json');selection={kind:next(id for id in ids if id.startswith(kind+'-')) for kind in read(NEW/'run.json')['config']['counts']}
for feature,choices in cov['ids'].items():
    if choices:selection['feature_'+feature]=choices[0]
cards=[];examples=OUT/'examples';examples.mkdir(exist_ok=True)
for label,id in selection.items():
    s=NEW/'samples'/id;o=OLD/'samples'/id;t=read(s/'compact.vl.json');old=read(o/'compact.vl.json')
    d=examples/id;d.mkdir(exist_ok=True)
    for name in ('compact.vl.json','compact.preview.vl.json','chart.png'):
        shutil.copy2(s/name,d/name)
    shutil.copy2(o/'compact.vl.json',d/'compact.v3.vl.json')
    def snippet(spec):
        x=copy.deepcopy(spec);x['data']['values']=x['data']['values'][:8]
        return html.escape(pretty(x))
    same=sha(o/'chart.png')==sha(s/'chart.png');assert same
    cards.append('<section><h2>'+html.escape(label+' / '+id)+'</h2><p>完整图片逐字节复用；下方只展示前 8 行，完整 GT 在 examples 包内。总行数 '+str(len(t['data']['values']))+'</p><img src="'+embed(s/'chart.png')+'"><div class="pair"><div><h3>旧 compact-v3</h3><pre>'+snippet(old)+'</pre></div><div><h3>新 compact-v4</h3><pre>'+snippet(t)+'</pre></div></div></section>')
fresh_cards=[];thumbs=[]
for kind in read(NEW/'run.json')['config']['counts']:
    s=FRESH/'samples'/(kind+'-000000')
    fresh_cards.append('<section><h2>新生成 / '+kind+'</h2><div class="pair"><div><h3>Full（训练输入）</h3><img src="'+embed(s/'chart.png')+'"></div><div><h3>Compact-preview（不作训练标签）</h3><img src="'+embed(s/'compact.png')+'"></div></div></section>')
    tile=Image.new('RGB',(680,275),'white');draw=ImageDraw.Draw(tile);draw.text((10,5),kind,fill='black')
    for index,name in enumerate(('chart.png','compact.png')):
        im=Image.open(s/name).convert('RGB');im.thumbnail((330,240));tile.paste(im,(index*340+(330-im.width)//2,30+(240-im.height)//2))
    thumbs.append(tile)
contact=Image.new('RGB',(1360,275*5),(234,237,243))
for i,tile in enumerate(thumbs):contact.paste(tile,((i%2)*680,(i//2)*275))
contact.save(OUT/'fresh-contact.png')
page='<!doctype html><meta charset="utf-8"><title>Compact-v4 语义对照</title><style>body{font:15px system-ui;max-width:1500px;margin:30px auto;background:#edf1f5;color:#17233b}section{background:white;border-radius:12px;padding:22px;margin:24px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}img{max-width:100%;max-height:600px}pre{background:#f6f8fa;padding:14px;overflow:auto;max-height:650px;font:13px monospace}p{color:#456}@media(max-width:800px){.pair{display:block}}</style><h1>Compact-v4：图片与核心语义分离</h1><p>450 套历史迁移 + 27 套新生成。数据来源为合成图；这是结构/数值/字节审计，不是全部随机布局的人工作品验收。</p><h2>历史 GT 清理，Full 图片保持不变</h2>'+''.join(cards)+'<h2>新生成的 Full 与派生预览实际渲染</h2>'+''.join(fresh_cards)
(OUT/'comparison.html').write_text(page,encoding='utf-8')
removed=read(AUDIT/'field-removals.json')
report=f'''# Compact-v4 语义 GT 清理交付 — 2026-11-11

## 结论与范围

本轮接续“full 用于绘图，compact 用作训练 GT”的要求。代码修改于开发机本项目工作区，保留已有未提交修改；本轮不改采样分布或字体池、不重画历史 full。代码尚未提交/推送。

已完成严格 compact-v4 投影、独立预览模块、生产/验证/恢复链路及无渲染迁移入口。GT 合约 compact-v4；采样版本仍 vega-lite-native/1.2，投影版本 3.0.0。这三个标识承担不同职责。

## 保留与删除

保留 data.values 中的原数值与可见文字、标题与轴变量/单位、图表类型、分组偏移、系列字段关系、误差 lower/upper、堆叠零基线或显式 start/end、必要 path_order/stack_order、离散 sort:null，以及 log/pow/sqrt/symlog 的适用参数。重复类别或系列名称采用文字 + *_instance 身份字段，不再依赖 axis/legend.labelExpr。

删除字体、画布尺寸/背景、具体颜色、轴/图例布局与刻度选择、标签格式与旋转、绘图朝向 scale.reverse、单点折线 point=True 显示补丁。163 套隐藏单匿名系列删除 Series 1 列和冗余 color 通道；多个隐藏系列仍保留稳定身份，具名可见单系列仍保留名字。color.field 与 xOffset/yOffset 是分组关系，不作为装饰删除。

compact_display.render_spec() 从 GT 深拷贝生成 compact.preview.vl.json；观察表和顺序严格相同。标签完整显示、重复身份到文字映射、抑制默认标题和单点可见性仅在预览层。训练 JSONL 只读取 compact.vl.json。原尺寸检查发现默认 preview 图例会截断长名称；仅在显示层增加 legend.labelLimit=0，并通过实际 SVG 全名称断言，GT 不含该字段。

## 实际执行结果

| 检查 | 结果 |
|---|---|
| 旧 v3 → 新 v4，九类各 50 | {v['accepted']}/450 接受，{v['rejected']} 拒绝 |
| 独立 v3/v4 解码、数据/身份/行序、变量/单位/结构关系 | 450/450 通过 |
| 旧 full/config/source/chart.png/chart.1036.png/chart.svg/sampling 逐份字节复用 | 各 450/450 SHA-256 相等 |
| 原目录冻结文件不变 | 9,099/9,099 哈希相等 |
| 训练答案等于新版 compact，输入图是原 full PNG | 450/450 |
| 新生成（九类各 3），full 与 preview 实际渲染 | {fresh['accepted']}/27 接受，{fresh['rejected']} 拒绝 |
| 新生成字体 data URI + 搜索文本、答案/GT、preview data 相等 | 27 套、{svg_count} 个 SVG |
| 回归 | {count} 项全部通过 |
| 独立审计故障注入 | 8 种语义修改均被检测 |

compact 实际文件 {r['old_bytes']:,} → {r['new_bytes']:,} bytes，减少 {(1-r['file_ratio'])*100:.2f}%；规范 JSON {r['old_canonical_bytes']:,} → {r['new_canonical_bytes']:,} bytes，减少 {(1-r['canonical_ratio'])*100:.2f}%。这是同 450 套、同观察表的比较，不由重采样造成。字段删减逐项证据在 field-removals.json；父子字段字节重叠，不能相加为总节省。

真实覆盖：{pretty(cov['counts'])}。450 套没有非线性轴或 reverse；其能力由定向测试覆盖，不能把批量结果说成这些特性已有自然样本验收。定向测试包括全部四种非线性尺度、重复标签、重复观察、乱序路径、任意堆叠基线和非对称误差、常规 preview 实际 Vega 编译与 SVG。

## 无重画迁移与复现

Linux 开发机项目根目录：

```bash
python3 pipeline.py reproject --source runs/old_run --output runs/new_compact_v4 --compact-only
python3 pipeline.py validate --output runs/new_compact_v4
PATH="$PWD/../.runtime:$PATH" VSR_TEXT_TEST_MODULES="$PWD/../node_modules" VSR_FONT_INTEGRATION=1 python3 -m unittest discover -s tests -v
```

compact-only 读取保存 full，不调用采样器或渲染器，复制并验证 full 证据，写新 GT、preview 规格及训练答案。迁移的 preview 未渲染，报告显式标记 false；不复制旧 compact PNG/SVG 为当前输出。generate --resume 只能用于相同合约/采样版本的生成运行，不能恢复 projection/migration 运行。实际迁移目录 runs/compact_v4_production；新生成目录 runs/compact_v4_fresh_20261111。

## 验证过程与边界

初次回归 148 项中有 4 个失败、10 个错误：旧测试假定 compact error layer 有 name；旧端点通道方向期望未更新；两项原几何测试把 visibility-fitted full 当作未经调整的原几何。本轮分别检查语义端点、改用无装饰 name 判断、明确原始几何与拟合后布局，并保留数据不可变断言。最终日志不是初次失败日志。

初次无渲染迁移的验收仍要求 compact PNG，导致 450 套拒绝；已修复 full-only 验证的图片列表，现有迁移目录重新验收 450/450。新增真实 render→migration→重复 validate 回归，确认无旧 compact 图也能通过且不调用重采样/重画。失败日志保留在 history/compact-v4-resume-20261111/。

迁移初始 run.command 继承旧生成命令，已单独纠正为实际迁移命令并保留 source_command；provenance-correction.json 记录前后元数据，不改变样本文件。独立审计 result.json 保存原始验收快照，当前运行元数据另存 current-migration-run.json。

本轮没有消除原先记录的 Vega 与 Matplotlib 布局/字体测量/纹理近似，也不声称 production_no_clip_v3 的像素等价。字体嵌入实现未改；历史 SVG 字节一致。新 SVG 字体检查是结构证据，不替代此前字体隔离浏览器审计。未逐张人工检查全部 450 张；新图联系表与例图实际查看记录随交付。

## 交付内容

comparison.html 为离线自含图库（历史 full + v3/v4 GT，新生成 full + compact-preview）。examples/ 提供完整的前后 GT 和 PNG；fresh-contact.png 为九类新图联系表。changes.patch 与 code-changes.tar.gz 包含工作区修改；数值/样式/font 既有实现与产物保留。
'''
(OUT/'VISUAL_QA.md').write_text('实际查看九类新图联系表、line_n full/preview 原尺寸图和 barv_1 full 原尺寸图。原 full 标题/纹理/标签保留，预览为默认样式，不用于训练输入或字体隔离论证。发现预览长图例名称截断后在显示层修复，并新增实际 SVG 标签断言。缩图会使长宽比较大的 full 文字显得较小；未逐张人工验收全部历史图。\n',encoding='utf-8')
(OUT/'README.md').write_text(report,encoding='utf-8');(ROOT/'docs/compact-v4-delivery-20261111.md').write_text(report,encoding='utf-8')
for name in ('compact-v4-independent-audit-20261111.md','compact-v4-projection-baseline-20261111.md'):
    shutil.copy2(ROOT/'docs'/name,OUT/name)
changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
paths=sorted(set(changed+untracked+['diagnostics/compact-v4-independent-audit.py','diagnostics/compact-v4-package-delivery.py','diagnostics/compact-v4-fresh-20261111.json']));assert all(not p.startswith(('runs/','history/','deliveries/')) for p in paths)
(OUT/'changes.patch').write_bytes(subprocess.check_output(['git','diff','--binary'],cwd=ROOT))
with tarfile.open(OUT/'code-changes.tar.gz','w:gz') as tar:
    for p in paths:tar.add(ROOT/p,arcname=p)
with tarfile.open(ROOT/'deliveries/compact_v4_20261111.tar.gz','w:gz') as tar:tar.add(OUT,arcname='compact_v4_20261111')
print(json.dumps({'audit':r['status'],'migration_accepted':v['accepted'],'fresh_accepted':fresh['accepted'],'tests':count,'gt_reduction_percent':(1-r['file_ratio'])*100,'gallery_cards':len(cards),'code_paths':paths,'archive_sha256':sha(ROOT/'deliveries/compact_v4_20261111.tar.gz')},ensure_ascii=False))
