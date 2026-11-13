"""Stable Vega-Lite view syntax without rewriting data or expressions."""
import copy


# Position channels precede visual channels; other channels retain their order.
ENCODING_ORDER = ("x", "y", "xOffset", "yOffset", "x2", "y2",
                  "theta", "theta2", "radius", "radius2", "longitude",
                  "longitude2", "latitude", "latitude2", "color")


def format_spec(spec: dict) -> dict:
    """Object marks and ordered view keys; layered views start title/data/encoding/layer.

    Traverse only composition children: observations, config and usermeta may
    legitimately contain columns or properties named mark/title/spec.
    """
    result = copy.deepcopy(spec)

    def view(node):
        if isinstance(node.get("encoding"), dict):
            enc = node["encoding"]
            keys = [key for key in ENCODING_ORDER if key in enc]
            node["encoding"] = {key: enc[key] for key in keys + [k for k in enc if k not in keys]}
        if isinstance(node.get('mark'), str):
            node['mark'] = {'type': node['mark']}
        for key in ('layer', 'concat', 'hconcat', 'vconcat'):
            if key in node:
                node[key] = [view(child) for child in node[key]]
        if isinstance(node.get('spec'), dict):
            node['spec'] = view(node['spec'])
        priority = ('title', 'data', 'encoding', 'layer') if 'layer' in node else ('title', 'data', 'mark', 'encoding')
        keys = [key for key in priority if key in node]
        return {key: node[key] for key in keys + [k for k in node if k not in keys]}

    return view(result)
