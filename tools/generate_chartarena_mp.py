"""Generate a validated ChartArena dataset with bounded, resumable index ranges."""
from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Lock
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generation import KINDS
from generation.sampling_policy import EXTENSIONS, validate as validate_policy
from workflow.config import load_config

ARTIFACTS = ('sample', 'image', 'full', 'compact', 'compact_image', 'source', 'geometry')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def rows(path):
    if path.is_file():
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def prefix(record, shard):
    return {**record, **{key: f'{shard}/{record[key]}' for key in ARTIFACTS if key in record}}


def engine_config(config, kind, count):
    kinds = EXTENSIONS if kind in EXTENSIONS else set(KINDS)
    sampling = {}
    for key, value in config['sampling'].items():
        if key in ('weighted', 'ranges', 'label_probability'):
            value = {name: v for name, v in value.items() if name in kinds or name == 'all'}
        sampling[key] = value
    validate_policy(sampling, kinds)
    sub = {**config, 'sampling':sampling}
    if kind in EXTENSIONS:
        return {k:sub[k] for k in ('sampling','seed','target_side')} | {
            'counts': {name: count if name==kind else 0 for name in sorted(EXTENSIONS)}}
    return {**sub, 'counts':{kind:count}}


def format_duration(start):
    return round(monotonic()-start, 3)


class Production:
    def __init__(self, config, output, scratch, node, native_slots, ext_slots):
        self.config = config
        self.output = output
        self.scratch = scratch
        self.node = node
        self.native_slots = native_slots
        self.ext_slots = ext_slots
        self.log_lock = Lock()
        self.copy_slots = BoundedSemaphore(6)
        self.start = monotonic()

    def log(self, event, **fields):
        with self.log_lock:
            print(json.dumps(dict(event=event, elapsed_s=format_duration(self.start), **fields)), flush=True)

    def shard(self, kind, first, count):
        engine = 'extensions' if kind in EXTENSIONS else 'native'
        name = f'{first:06d}-{count:04d}'
        relative = f'shards/{kind}/{name}'
        dest = self.output/relative
        marker = dest/'committed.json'
        if marker.exists():
            summary = read(marker)
            self.log('reused',kind=kind,first=first,count=count,**summary)
            return [relative]
        cfg = engine_config(self.config,kind,count)
        started = monotonic()
        log = self.output/'logs'/f'{kind}-{name}.log'
        with TemporaryDirectory(dir=self.scratch, prefix=f'{kind}-{name}-') as temp:
            work = Path(temp)
            input_path = work/'config.json'
            result = work/'output'
            dump(input_path,cfg)
            if engine == 'native':
                load_config(input_path)
                command = [sys.executable,'-B',str(ROOT/'pipeline.py'),'generate','--config',str(input_path),
                           '--output',str(result),'--node',str(self.node),'--start-index',str(first)]
            else:
                command = [str(self.node),str(ROOT/'generate_chartarena_extensions.mjs'),
                           str(input_path),str(result),str(first)]
            with log.open('w',encoding='utf-8') as stream:
                code = subprocess.run(command, cwd=ROOT, stdout=stream,stderr=subprocess.STDOUT).returncode
            stats = result/'validation.json'
            if not stats.is_file():
                if engine!='extensions':
                    raise RuntimeError(f'{kind} {name}: pipeline exited {code}, see {log}')
                self.log('extension_failure',kind=kind,first=first,count=count,exit=code)
                if count>1:
                    half=count//2
                    return self.shard(kind,first,half)+self.shard(kind,first+half,count-half)
                result.mkdir(exist_ok=True)
                ident = f'{kind}-{first:06d}'
                error={'id':ident,'kind':kind,'status':'rejected','log':f'logs/{log.name}'}
                (result/'rejected.jsonl').write_text(json.dumps(error)+'\n')
                dump(stats,dict(requested=1,accepted=0,rejected=1))
            summary=read(stats)
            accepted=list(rows(result/'manifest.jsonl'))
            rejected=list(rows(result/'rejected.jsonl'))
            expected={f'{kind}-{index:06d}' for index in range(first, first+count)}
            assert len(accepted)+len(rejected)==count and {r['id'] for r in accepted+rejected}==expected
            assert len(accepted)==summary['accepted'] and len(rejected)==summary['rejected']
            training=list(rows(result/'train.jsonl'))
            assert [(r['id'],r['image']) for r in accepted]==[(r['id'],r['image']) for r in training]
            for sample,pair in zip(accepted,training):
                for key in ('image','full','compact'):
                    assert (result/sample[key]).is_file()
                assert read(result/sample['compact'])==json.loads(pair['messages'][-1]['content'])
            partial=dest.with_name(dest.name+'.partial')
            partial.mkdir(parents=True,exist_ok=True)
            with self.copy_slots:
                subprocess.run(['rsync','-a','--delete','--exclude=.render-state',str(result)+'/',str(partial)+'/'],check=True)
            counts=dict(accepted=len(accepted),rejected=len(rejected))
            dump(partial/'committed.json',counts)
            partial.rename(dest)
        self.log('committed',kind=kind,first=first,count=count,seconds=format_duration(started),**counts)
        return [relative]

    def run(self):
        by_kind = list(self.config['counts'])
        requested=self.config['counts']
        accepted=Counter()
        next_index=Counter()
        shards=[]
        with ThreadPoolExecutor(max_workers=self.native_slots) as native, ThreadPoolExecutor(max_workers=self.ext_slots) as ext:
            while accepted != Counter(requested):
                batches=[]
                for kind in by_kind:
                    left=requested[kind]-accepted[kind]
                    if left<=0:
                        continue
                    offset=next_index[kind]
                    if offset>=requested[kind]*3:
                        raise RuntimeError(f'{kind}: acceptance rate too low to reach configured count')
                    size=64 if kind in EXTENSIONS else 96
                    for start in range(offset,offset+left,size):
                        batches.append((kind,start,min(size,offset+left-start)))
                    next_index[kind]+=left
                # Round-robin kinds at each index, including original and extension batches.
                batches.sort(key=lambda b:(b[1],-requested[b[0]]))
                future_kind={(ext if k in EXTENSIONS else native).submit(self.shard,k,i,n):k for k,i,n in batches}
                for future in as_completed(future_kind):
                    kind=future_kind[future]
                    for relative in future.result():
                        accepted[kind]+=read(self.output/relative/'committed.json')['accepted']
                        shards.append(relative)
                self.log('wave_done',by_kind=dict(accepted),requested=sum(requested.values()))
        order={kind:i for i,kind in enumerate(by_kind)}
        shards.sort(key=lambda path:(order[path.split('/')[1]],path))
        ids=set()
        names=('manifest','train','rejected')
        published=Counter()
        with TemporaryDirectory(dir=self.output,prefix='.publish-') as temp:
            stage=Path(temp)
            for name in names:
                with (stage/(name+'.jsonl')).open('w',encoding='utf-8') as stream:
                    for rel in shards:
                        for row in rows(self.output/rel/(name+'.jsonl')):
                            if name=='manifest':
                                assert row['id'] not in ids, row['id']
                                ids.add(row['id'])
                                published[row['kind']]+=1
                            stream.write(json.dumps(prefix(row,rel),ensure_ascii=False,separators=(',',':'))+'\n')
            assert published==Counter(requested)
            for name in names:
                file=name+'.jsonl'
                (stage/file).replace(self.output/file)
            dump(stage/'validation.json',{'accepted':sum(accepted.values()),'requested':sum(requested.values()),
                 'rejected_candidates':sum(next_index.values())-sum(accepted.values()),'counts':dict(published),'shards':len(shards)})
            (stage/'validation.json').replace(self.output/'validation.json')
        self.log('complete',**read(self.output/'validation.json'))


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scratch',type=Path,default=Path('/tmp'))
    parser.add_argument('--native-slots',type=int,default=16)
    parser.add_argument('--extension-slots',type=int,default=6)
    parser.add_argument('--node',type=Path,default=ROOT.parent/'.runtime/node')
    args=parser.parse_args()
    config=read(args.config)
    assert set(config['counts'])==set(KINDS)|EXTENSIONS and all(n>0 for n in config['counts'].values())
    assert args.native_slots>0 and args.extension_slots>0
    assert (ROOT/'assets/fonts/NotoSansCJKsc-Regular.otf').is_file()
    assert list((ROOT/'docs/font-licenses').glob('*.tar.gz'))
    output=args.output.resolve()
    assert output!=ROOT and output!=ROOT.parent
    (output/'logs').mkdir(parents=True,exist_ok=True)
    with (output/'.lock').open('w') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        meta=dict(config=config, head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  source_diffs_sha256=sha256(subprocess.check_output(['git','diff','HEAD'],cwd=ROOT)).hexdigest(),
                  launcher_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
        record=output/'run.json'
        if record.is_file():
            assert read(record)==meta, 'Existing dataset was created with a different source or configuration'
        else:
            dump(record,meta)
        Production(config,output,args.scratch,args.node.resolve(),args.native_slots,args.extension_slots).run()


if __name__=='__main__':
    main()
