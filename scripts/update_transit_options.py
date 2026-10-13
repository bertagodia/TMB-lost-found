"""Refresh the offline TMB catalogue from a downloaded official transport page.
Usage: python scripts/update_transit_options.py /tmp/tmb-lines.html
Download https://www.tmb.cat/ca/transport-barcelona first. No API keys are saved.
"""
import json
from pathlib import Path
import re
import sys


def extract(html):
    html = html.replace("\\'", "'")  # JS single-quoted JSON payload
    decoder = json.JSONDecoder()
    buses = {}
    for match in re.finditer(r'\{"type":"FeatureCollection"', html):
        try:
            data, _ = decoder.raw_decode(html[match.start():])
        except ValueError:
            continue
        for feature in data.get('features', []):
            p = feature.get('properties', {})
            if p.get('NOM_TIPUS_TRANSPORT') == 'BUS':
                buses[p['NOM_LINIA']] = p['DESC_LINIA']
    metro = list(dict.fromkeys(re.findall(r'id="line-metro-([A-Z0-9]+)"', html)))
    if len(buses) < 90 or len(metro) < 10:
        raise ValueError('Incomplete source; refusing to replace the catalogue')
    return {'source': 'https://www.tmb.cat/ca/transport-barcelona',
            'scope': 'TMB services listed by the official website; other operators excluded',
            'modes': {'bus': [{'id': k, 'label': k + ' · ' + v} for k,v in buses.items()],
                      'metro': [{'id': k, 'label': 'FM · Funicular de Montjuïc' if k == 'FM' else k} for k in metro]}}

if __name__ == '__main__':
    from datetime import date
    data = extract(Path(sys.argv[1]).read_text())
    data['updated'] = date.today().isoformat()
    target = Path(__file__).resolve().parents[1]/'client/transit-options.json'
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print({k:len(v) for k,v in data['modes'].items()})
