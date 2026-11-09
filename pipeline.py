"""Configuration-driven VSR + Vega-Lite dataset production.

Native author generators are pinned and unmodified. Outputs are isolated by run;
the Vega-Lite chart is always rendered from full.vl.json, never from native.png.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
KINDS = ['barh_1', 'barh_n', 'barv_1', 'barv_n', 'barv_stack',
         'line_1', 'line_n', 'scatter_1', 'scatter_n']
COMMIT = '1fd040346add205ffbada9748273cad3bc9159e5'


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def observation_key(obj):
    """JSON numbers 3 and 3.0 have identical observation meaning."""
    def numbers(value):
        if isinstance(value, dict):
            return {k: numbers(v) for k, v in value.items()}
        if isinstance(value, list):
            return [numbers(v) for v in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    return canonical(numbers(obj))


def dump(file, obj):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_name(file.name + '.tmp')
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(file)


def jsonl(file, rows):
    Path(file).write_text(''.join(canonical(x) + '\n' for x in rows), encoding='utf-8')


def read(file):
    return json.loads(Path(file).read_text(encoding='utf-8'))


def load_config(file):
    p = Path(file)
    if p.suffix in ('.yaml', '.yml'):
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding='utf-8'))
    else:
        cfg = read(p)
    if not isinstance(cfg, dict):
        raise ValueError('Config must be an object')
    if set(cfg) - {'seed', 'counts', 'controls', 'native', 'postprocess_native', 'workers', 'target_side', 'notes'}:
        raise ValueError('Unknown configuration keys: ' + str(set(cfg) - {'seed', 'counts', 'controls', 'native', 'postprocess_native', 'workers', 'target_side', 'notes'}))
    cfg.setdefault('seed', 20261109)
    cfg.setdefault('counts', dict.fromkeys(KINDS, 1))
    cfg.setdefault('controls', {})
    cfg.setdefault('native', True)
    cfg.setdefault('postprocess_native', True)
    cfg.setdefault('workers', 2)
    cfg.setdefault('target_side', 1036)
    for kind, count in cfg['counts'].items():
        if kind not in KINDS or not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f'Invalid count: {kind}={count}')
    if not isinstance(cfg['seed'], int) or cfg['seed'] < 0:
        raise ValueError('seed must be a nonnegative integer')
    if cfg['target_side'] < 64 or cfg['workers'] < 1:
        raise ValueError('Invalid target_side/workers')
    if cfg['postprocess_native'] and not cfg['native']:
        raise ValueError('postprocess_native requires native=true')
    return cfg


def task_seed(base, kind, index):
    return int.from_bytes(hashlib.sha256(f'{base}:{kind}:{index}'.encode()).digest()[:4], 'big') % (2**31 - 1)


def produce(task):
    from native import generate_native
    from adapter import build_pair, normalize
    out = Path(task['output'])
    out.mkdir(parents=True, exist_ok=True)
    try:
        result = generate_native(task['kind'], task['seed'], out, controls=task['controls'], render=task['native'])
        cfg = result['config']
        full, compact, source = build_pair(task['kind'], cfg)
        if normalize(full) != compact or normalize(compact) != compact:
            raise ValueError('Full-to-compact mapping/idempotence failed')
        dump(out / 'full.vl.json', full)
        dump(out / 'compact.vl.json', compact)
        dump(out / 'source.json', source)
        dump(out / 'plot-layout.json', source['plot_layout'])
        dump(out / 'generation.json', {**task, 'vsr_commit': COMMIT, 'sample_seed': result.get('sample_seed', task['seed']), 'diagnostics': result.get('diagnostics', {})})
        row = {k: task[k] for k in ['id', 'kind', 'index', 'seed']}
        row.update({'status': 'generated', 'sample': f'samples/{task["id"]}', 'config_sha256': digest(cfg), 'semantic_sha256': digest(compact), 'data_family': cfg.get('family'), 'x_mode': cfg.get('x_mode'), 'style_family': cfg.get('style', {}).get('style_family', cfg.get('style', {}).get('family')), 'series_count': cfg.get('n_series', 1)})
        dump(out / 'record.json', row)
        return row
    except Exception as e:
        error = {k: task[k] for k in ['id', 'kind', 'index', 'seed']}
        error.update(status='generation_failed', error=str(e), traceback=traceback.format_exc())
        dump(out / 'failure.json', error)
        return error


def native_export(out, records, cfg):
    groups = collections.defaultdict(list)
    for r in records:
        if r['status'] != 'generated':
            continue
        sample = out / r['sample']
        ann = read(sample / 'native.annotation.json')
        destination = out / 'native_outputs' / r['kind'] / f'seed_{cfg["seed"]:08d}'
        image = destination / 'images' / f'{r["id"]}.png'
        image.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sample / 'native.png', image)
        ann['image'] = f'images/{r["id"]}.png'
        groups[destination].append(ann)
    for directory, annotations in groups.items():
        dump(directory / 'annotations.json', annotations)
        dump(directory / 'manifest.json', {'seed': cfg['seed'], 'sample_count': len(annotations), 'vsr_commit': COMMIT, 'note': 'Individual deterministic sample seeds are in samples/*/generation.json.'})
    if cfg['postprocess_native']:
        scripts = ROOT / 'vendor/VSR/data_pipeline'
        subprocess.run([sys.executable, str(scripts / 'resize_and_remap.py'), '--input-root', str(out / 'native_outputs'), '--output-root', str(out / 'native_packaged'), '--target-side', str(cfg['target_side']), '--workers', str(cfg['workers'])], check=True)
        subprocess.run([sys.executable, str(scripts / 'render_anchors.py'), '--manifest', str(out / 'native_packaged/resized.json'), '--input-root', str(out / 'native_packaged'), '--output-root', str(out / 'native_packaged'), '--workers', str(cfg['workers'])], check=True)


def validate(out):
    import jsonschema
    from PIL import Image
    from adapter import normalize
    from compact import project_rows, semantic_rows
    from text_layout import audit_text
    records = read(out / 'generation-manifest.json')
    schema_paths = [ROOT / 'schema/vega-lite-6.5.0.schema.json',
                    ROOT / 'node_modules/vega-lite/build/vega-lite-schema.json',
                    ROOT.parent / 'node_modules/vega-lite/build/vega-lite-schema.json',
                    ROOT.parent / 'evidence/vega-lite-6.5.0.schema.json']
    schema_path = next((p for p in schema_paths if p.is_file()), None)
    if schema_path is None:
        raise FileNotFoundError('Pinned Vega-Lite schema is missing')
    schema = read(schema_path)
    validator = jsonschema.Draft7Validator(schema)
    render_report = read(out / 'render-report.json')
    render_rows = render_report.get('records', [])
    render_index = collections.defaultdict(list)
    for row in render_rows:
        render_index[row.get('id')].append(row)
    generated_count = sum(r['status'] == 'generated' for r in records)
    report_complete = render_report.get('total') == generated_count and render_report.get('processed') == generated_count and len(render_rows) == generated_count
    accepted, failures = [], []
    for row in records:
        if row['status'] != 'generated':
            failures.append(row)
            continue
        sample = out / row['sample']
        errors = []
        try:
            full, compact = read(sample / 'full.vl.json'), read(sample / 'compact.vl.json')
            for label, spec in [('full', full), ('compact', compact)]:
                for error in validator.iter_errors(spec):
                    errors.append(f'{label} schema: {error.message[:350]}')
            if normalize(full) != compact or normalize(compact) != compact:
                errors.append('Deterministic normalization mismatch')
            if project_rows(full) != semantic_rows(compact):
                errors.append('Compact observations or scientific meaning differ from source')
            if digest(compact) != row['semantic_sha256']:
                errors.append('Semantic hash mismatch')
            if not report_complete or len(render_index[row['id']]) != 1:
                errors.append('Renderer report is incomplete, missing or duplicated')
            elif render_index[row['id']][0].get('status') != 'rendered':
                errors.append('Renderer quality checks require review; see render-report.json')
            source = read(sample / 'source.json')
            if full['data']['values'] != source['rows']:
                errors.append('Vega-Lite observation table differs from source rows')
            text_audit = audit_text(full, (sample / 'chart.svg').read_text(encoding='utf-8'))
            dump(sample / 'text-audit.json', text_audit)
            errors.extend('full text: ' + message for message in text_audit['errors'])
            rows_by_id = {r['row_id']: r for r in source['rows']}
            if len(rows_by_id) != len(source['rows']):
                errors.append('Duplicate source row_id')
            if (sample / 'native.annotation.json').exists():
                native = read(sample / 'native.annotation.json')
                if native['data_ori'] != source['data_ori']:
                    errors.append('Vega-Lite source tuples differ from VSR native annotations')
            target_side = read(out / 'run.json')['config']['target_side']
            for filename in ['chart.png', 'compact.png', f'chart.{target_side}.png', f'compact.{target_side}.png']:
                with Image.open(sample / filename) as image:
                    image.load()
                    if min(image.size) < 30:
                        errors.append(f'{filename}: invalid dimensions')
            for variant, geometry_file, image_file in [('full', 'geometry.json', 'chart.png'), ('compact', 'compact.geometry.json', 'compact.png')]:
                geometry = read(sample / geometry_file)
                with Image.open(sample / image_file) as image:
                    if list(image.size) != [geometry['image']['width'], geometry['image']['height']]:
                        errors.append(f'{variant}: geometry/image dimensions differ')
                mark_names = {m['mark_id']: m.get('name', '') for m in geometry['marks']}
                observations = [e for e in geometry['elements'] if e.get('role') != 'decoration' and e.get('datum')]
                if variant == 'full':
                    observations = [e for e in observations if e['datum'].get('row_id') is not None]
                    if {e['datum']['row_id'] for e in observations} != set(rows_by_id):
                        errors.append('full: source row/geometry coverage mismatch')
                    for element in observations:
                        datum = element['datum']
                        original = rows_by_id.get(datum['row_id'])
                        if original is None or any(datum.get(k) != v for k, v in original.items()):
                            errors.append(f'full: scenegraph datum differs for {datum["row_id"]}')
                            break
                for element in observations:
                    if not all(math.isfinite(v) for v in element['bbox'] + element['anchor']):
                        errors.append(f'{variant}: nonfinite geometry')
                primary_type = 'rect' if row['kind'].startswith('bar') else 'line' if row['kind'].startswith('line') else 'symbol'
                primary = [e for e in observations if e['mark_type'] == primary_type and (variant == 'compact' or not row['kind'].startswith('bar') or mark_names[e['mark_id']].startswith('bars_'))]
                if variant == 'full':
                    if collections.Counter(e['datum']['row_id'] for e in primary) != collections.Counter(rows_by_id.keys()):
                        errors.append('full: expected one primary mark/vertex per source row')
                else:
                    data_rows = compact['data']['values']
                    keys = set().union(*(r.keys() for r in data_rows))
                    expected = collections.Counter(observation_key(r) for r in data_rows)
                    actual = collections.Counter(observation_key({k: e['datum'][k] for k in keys if k in e['datum']}) for e in primary)
                    if actual != expected:
                        errors.append('compact: expected one unchanged primary mark/vertex per observation, including duplicates')
                resized_file = sample / (f'geometry.{target_side}.json' if variant == 'full' else f'compact.geometry.{target_side}.json')
                resized = read(resized_file)
                trans = resized['resize']
                transformed = {e['element_id']: e for e in resized['elements']}
                for element in geometry['elements']:
                    actual = transformed[element['element_id']]['anchor']
                    expected = [element['anchor'][0] * trans['scale_x'] + trans['offset_x'], element['anchor'][1] * trans['scale_y'] + trans['offset_y']]
                    if max(abs(a-b) for a, b in zip(actual, expected)) > 1e-6:
                        errors.append(f'{variant}: resized pixel coordinate mismatch')
                        break
        except Exception as e:
            errors.append(str(e))
        if errors:
            failures.append({**row, 'status': 'rejected', 'errors': errors})
        else:
            accepted.append({**row, 'status': 'accepted', 'image': row['sample'] + '/chart.png', 'full': row['sample'] + '/full.vl.json', 'compact': row['sample'] + '/compact.vl.json', 'source': row['sample'] + '/source.json', 'geometry': row['sample'] + '/geometry.json'})
    jsonl(out / 'manifest.jsonl', accepted)
    jsonl(out / 'rejected.jsonl', failures)
    jsonl(out / 'train.jsonl', [{'id': r['id'], 'image': r['image'], 'messages': [{'role': 'user', 'content': '将图表转换为精简 Vega-Lite JSON。'}, {'role': 'assistant', 'content': canonical(read(out / r['compact']))}]} for r in accepted])
    summary = {'requested': len(records), 'accepted': len(accepted), 'rejected': len(failures), 'counts': dict(collections.Counter(r['kind'] for r in accepted)), 'data_families': {kind: dict(collections.Counter(str(r.get('data_family')) for r in accepted if r['kind'] == kind)) for kind in KINDS}, 'semantic_unique': len({r['semantic_sha256'] for r in accepted}), 'vsr_commit': COMMIT, 'limitations': ['Automated structural, numeric, render and coordinate checks do not certify all typography or visual readability.', 'Native VSR output and Vega-Lite output use separate renderers and are not pixel-identical.', 'No paper quality-filter checkpoint or 800K-scale dataset reproduction is claimed.']}
    dump(out / 'validation.json', summary)
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def generate(args):
    cfg = load_config(args.config)
    if args.workers:
        cfg['workers'] = args.workers
    out = Path(args.output).resolve()
    fingerprint = digest(cfg)
    if out.exists() and any(out.iterdir()):
        if not args.resume:
            raise ValueError('Output directory is not empty. Select a new run or use --resume with identical config.')
        previous = read(out / 'run.json')
        if previous['config_sha256'] != fingerprint:
            raise ValueError('Resume config differs from original run')
    out.mkdir(parents=True, exist_ok=True)
    dump(out / 'run.json', {'config': cfg, 'config_sha256': fingerprint, 'vsr_commit': COMMIT, 'python': sys.version, 'command': sys.argv})
    tasks, records = [], []
    for kind, count in cfg['counts'].items():
        for index in range(count):
            sample_id = f'{kind}-{index:06d}'
            sample = out / 'samples' / sample_id
            if args.resume and (sample / 'record.json').exists():
                records.append(read(sample / 'record.json'))
                continue
            controls = {**cfg['controls'].get('all', {}), **cfg['controls'].get(kind, {})}
            tasks.append({'id': sample_id, 'kind': kind, 'index': index, 'seed': task_seed(cfg['seed'], kind, index), 'output': str(sample), 'controls': controls, 'native': cfg['native']})
    if cfg['workers'] == 1:
        results = map(produce, tasks)
        for row in results:
            records.append(row)
            print(json.dumps({'id': row['id'], 'status': row['status'], 'done': len(records)}, ensure_ascii=False), flush=True)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=cfg['workers']) as pool:
            for row in pool.map(produce, tasks):
                records.append(row)
                print(json.dumps({'id': row['id'], 'status': row['status'], 'done': len(records)}, ensure_ascii=False), flush=True)
    records.sort(key=lambda r: (KINDS.index(r['kind']), r['index']))
    dump(out / 'generation-manifest.json', records)
    jobs = [{'id': r['id'], 'full': str(out / r['sample'] / 'full.vl.json'), 'compact': str(out / r['sample'] / 'compact.vl.json'), 'output': str(out / r['sample'])} for r in records if r['status'] == 'generated']
    dump(out / 'render-jobs.json', jobs)
    node = args.node or str(ROOT.parent / '.runtime/node')
    if not Path(node).exists():
        node = shutil.which('node') or node
    render = subprocess.run([node, str(ROOT / 'render.mjs'), '--input', str(out / 'render-jobs.json'), '--out', str(out / 'render-report.json'), '--target-side', str(cfg['target_side'])])
    if cfg['native'] and jobs:
        native_export(out, records, cfg)
    summary = validate(out)
    if summary['rejected'] or render.returncode:
        raise SystemExit(1)


def reproject(args):
    """Rebuild specs in a new run using saved data; preserve original runs."""
    from adapter import build_pair, normalize
    origin, out = Path(args.source).resolve(), Path(args.output).resolve()
    if origin == out or out.exists() and any(out.iterdir()):
        raise ValueError('Reprojection requires a new, empty output directory')
    previous = read(origin / 'run.json')
    cfg = previous['config']
    out.mkdir(parents=True, exist_ok=True)
    dump(out / 'run.json', {**previous, 'source_run': str(origin), 'contract': 'compact-v2', 'command': sys.argv})
    records = []
    for old in read(origin / 'generation-manifest.json'):
        if old['status'] != 'generated':
            records.append(old)
            continue
        source_dir, target = origin / old['sample'], out / old['sample']
        target.mkdir(parents=True)
        for name in ['config.json', 'native.raw.config.json', 'native.annotation.json',
                     'native.diagnostics.json', 'native.png', 'native.original.annotation.json', 'generation.json']:
            if (source_dir / name).is_file():
                shutil.copy2(source_dir / name, target / name)
        config = read(target / 'config.json')
        full, compact, source = build_pair(old['kind'], config)
        if normalize(full) != compact or normalize(compact) != compact:
            raise ValueError(f'Noncanonical compact: {old["id"]}')
        for name, value in [('full.vl.json', full), ('compact.vl.json', compact), ('source.json', source)]:
            dump(target / name, value)
        dump(target / 'plot-layout.json', source['plot_layout'])
        row = {**old, 'semantic_sha256': digest(compact), 'config_sha256': digest(config), 'contract': 'compact-v2'}
        dump(target / 'record.json', row)
        records.append(row)
    dump(out / 'generation-manifest.json', records)
    jobs = [{'id': r['id'], 'full': str(out / r['sample'] / 'full.vl.json'),
             'compact': str(out / r['sample'] / 'compact.vl.json'), 'output': str(out / r['sample'])}
            for r in records if r['status'] == 'generated']
    dump(out / 'render-jobs.json', jobs)
    if args.prepare_only:
        print(json.dumps({'prepared': len(jobs), 'source': str(origin), 'output': str(out)}))
        return
    node = args.node or str(ROOT.parent / '.runtime/node')
    if not Path(node).exists():
        node = shutil.which('node') or node
    render = subprocess.run([node, str(ROOT / 'render.mjs'), '--input', str(out / 'render-jobs.json'),
                             '--out', str(out / 'render-report.json'), '--target-side', str(cfg['target_side'])])
    summary = validate(out)
    if summary['rejected'] or render.returncode:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    gen = sub.add_parser('generate')
    gen.add_argument('--config', required=True)
    gen.add_argument('--output', required=True)
    gen.add_argument('--resume', action='store_true')
    gen.add_argument('--workers', type=int)
    gen.add_argument('--node')
    val = sub.add_parser('validate')
    val.add_argument('--output', required=True)
    rep = sub.add_parser('reproject')
    rep.add_argument('--source', required=True)
    rep.add_argument('--output', required=True)
    rep.add_argument('--prepare-only', action='store_true')
    rep.add_argument('--node')
    args = parser.parse_args()
    if args.command == 'generate':
        generate(args)
    elif args.command == 'reproject':
        reproject(args)
    else:
        if validate(Path(args.output).resolve())['rejected']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
