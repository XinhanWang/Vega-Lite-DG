"""Bind the static VSR parameter samplers to independent per-sample RNGs.

No rendering-library imports, process-global RNG mutation or history loading.
The static functions retain original control flow, including draw order.
"""
from __future__ import annotations
import importlib
import math
import random
import types
from pathlib import Path
import numpy as np
from . import style_rules, vsr_text
from .controls import FAMILIES

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'InternLM/VSR@1fd040346add205ffbada9748273cad3bc9159e5'


class NumpySource:
    """NumPy operations plus the original MT19937 random API, locally scoped."""
    def __init__(self, seed):
        self.random = np.random.RandomState(seed % (2**32 - 1))
    def __getattr__(self, name):
        return getattr(np, name)


def _bind(module, namespace):
    for name, value in vars(module).items():
        if isinstance(value, types.FunctionType) and value.__module__ == module.__name__:
            rebound = types.FunctionType(value.__code__, namespace, name, value.__defaults__, value.__closure__)
            rebound.__kwdefaults__ = value.__kwdefaults__
            namespace[name] = rebound


def parameter_namespace(kind, seed, controls=None):
    controls = controls or {}
    module = importlib.import_module('.vsr_samplers.' + kind, __package__)
    namespace = {**vars(vsr_text), **vars(module)}
    p = random.Random(seed)
    namespace.update(random=p, np=NumpySource(seed), math=math)
    # Bind common functions first, then template-local overrides exactly as
    # Python's original imports/definitions do. Each call owns this dictionary.
    _bind(vsr_text, namespace)
    _bind(module, namespace)
    fonts = [str(ROOT / 'assets/fonts' / name) for name in style_rules.REQUIRED_FONT_FILES]
    if not all(Path(file).is_file() for file in fonts):
        raise FileNotFoundError('The original 16-font sampling pool is incomplete')
    namespace.update(FONT_POOL=fonts, WORDS=vsr_text.load_words())

    def canvas(chart_kind, series_count=1):
        style = style_rules.sample_canvas(p, chart_kind, series_count, controls.get('profile'), fonts)
        # Apply these again after template-specific layout changes, so explicit
        # user overrides remain authoritative without altering default draws.
        unknown = set(controls.get('style', {})) - set(style)
        if unknown:
            raise ValueError('Unknown style keys: ' + str(sorted(unknown)))
        style.update(controls.get('style', {}))
        return style
    namespace['sample_canvas'] = canvas
    original_weighted = namespace['choose_weighted']
    def weighted(items, weights):
        drawn = original_weighted(items, weights)
        if 'family' in controls and len(items) == len(FAMILIES[kind]) and set(items) == set(FAMILIES[kind]):
            return controls['family']
        if 'stack_mode' in controls and set(items) == {'absolute', 'percent'}:
            return controls['stack_mode']
        if kind == 'barv_stack' and 'series_count' in controls and list(items) == [2,3,4,5,6]:
            return controls['series_count']
        return drawn
    namespace['choose_weighted'] = weighted
    for function, key in [('sample_category_count','category_count'), ('sample_point_count','point_count'),
                          ('sample_series_count','series_count'), ('sample_family','family'), ('sample_stack_family','family'),
                          ('sample_x_mode','x_mode'), ('sample_stack_mode','stack_mode')]:
        if key in controls and function in namespace:
            original = namespace[function]
            def forced(*args, _original=original, _value=controls[key], **kwargs):
                _original(*args, **kwargs)
                return _value
            namespace[function] = forced
    if kind == 'scatter_n' and 'point_count' in controls and 'series_count' not in controls:
        original = namespace['sample_series_count']
        namespace['sample_series_count'] = lambda: min(original(), (controls['point_count'] - 4) // 4)
    if kind.startswith('line') and controls.get('point_count', 8) < 3:
        original_matrix = namespace['generate_matrix']
        def short_matrix(series, count, family):
            # VSR never naturally samples fewer than eight line points. Its
            # piecewise breakpoints require >=3; preserve native short-line
            # controls by evaluating that original curve and interpolating it.
            if family == 'piecewise' and count < 3:
                values = original_matrix(series, 3, family)
                return np.asarray([np.interp(np.linspace(0,2,count), np.arange(3), row) for row in values])
            return original_matrix(series, count, family)
        namespace['generate_matrix'] = short_matrix
    return namespace, p


def sample_parameters(kind, seed, controls=None):
    namespace, p = parameter_namespace(kind, seed, controls)
    return namespace['sample_config'](), p
