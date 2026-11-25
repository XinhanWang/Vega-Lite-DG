"""Create a sample or safely recover its verified sampling provenance."""
from pathlib import Path

from generation import GENERATOR_VERSION, generate_chart
from generation.core import sample_at_precision, sampling_diagnostics
from generation.controls import normalize_controls
from .io import canonical, digest, dump, read


def obtain_sample(task):
    output = Path(task['output'])
    config_file, provenance_file = output / 'config.json', output / 'sampling.json'
    kind, seed = task['kind'], task['seed']
    controls = normalize_controls(kind, task['controls'])
    sampling = task.get('sampling')
    if not config_file.is_file():
        return generate_chart(kind, seed, output, controls=controls, sampling=sampling)
    config = read(config_file)
    if config.get('sampling') != sampling:
        raise ValueError('Saved sampling policy differs from the request')
    expected = {'generator_version': GENERATOR_VERSION, 'kind': kind,
                'requested_seed': seed, 'controls': controls}
    diagnostics = read(provenance_file) if provenance_file.is_file() else None
    if diagnostics is not None:
        for key, value in expected.items():
            if canonical(diagnostics.get(key)) != canonical(value):
                raise ValueError(f'Saved sampling provenance differs in {key}; refusing to relabel existing data')
        if diagnostics.get('config_sha256'):
            if diagnostics['config_sha256'] != digest(config):
                raise ValueError('Saved sampling configuration hash mismatch')
    if diagnostics is None or not diagnostics.get('config_sha256') or diagnostics.get('sample_seed') != seed:
        expected_config, sample_seed, attempts = sample_at_precision(kind, seed, controls, sampling)
        if config != expected_config or (diagnostics is not None and diagnostics.get('sample_seed') != sample_seed):
            raise ValueError('Saved configuration differs from deterministic sampling')
        if diagnostics is None or not diagnostics.get('config_sha256'):
            diagnostics = sampling_diagnostics(kind, seed, config, controls, sample_seed=sample_seed, attempts=attempts)
            dump(provenance_file, diagnostics)
    return {'config': config, 'sample_seed': diagnostics['sample_seed'],
            'diagnostics': {**diagnostics, 'reused_saved_config': True}}
