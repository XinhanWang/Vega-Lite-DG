"""Export project font advances for offline Vega layout without node-canvas."""
import json
import sys
from fontTools.ttLib import TTFont


def font_metrics(record):
    with TTFont(record['file']) as font:
        cmap = font.getBestCmap()
        advances = font['hmtx'].metrics
        units = font['head'].unitsPerEm
        return {**record, 'advances': {str(c): advances[g][0] / units for c, g in cmap.items()}}


if __name__ == '__main__':
    print(json.dumps([font_metrics(r) for r in json.load(sys.stdin)]))
