"""Validate saved-data arithmetic, builds, shared content, and anonymous artifacts.

Only local numerical records and manuscript artifacts are read. No agent,
candidate implementation, or evaluator is executed.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STYLE_SHA256 = 'c3fc2894e83d2517ca18b66741d6c595986d97957dc08ec08bb2125a7ec4555a'
ANON_PATTERNS = [r'/(?:home|Users|mnt/data)/', r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
                 r'\b[0-9a-f]{24}\b', r'\bnative-codex-home\b']


def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True)


def check_anonymous(text, label):
    for pattern in ANON_PATTERNS:
        assert not re.search(pattern, text), f'Identifying pattern in {label}: {pattern}'


def public_paths():
    names = ['iab.tex', 'aiwild.tex', 'preamble.tex', 'manuscript.tex', 'neurips_2026.sty',
             'references.bib', 'Makefile', 'requirements.txt', 'REVIEW_README.md',
             'scripts/analyze.py', 'scripts/render_assets.py', 'scripts/qa.py', 'scripts/package.py']
    paths = [ROOT / n for n in names]
    for directory in ['sections', 'data', 'generated', 'figures']:
        paths.extend(p for p in (ROOT / directory).iterdir() if p.is_file())
    return sorted(paths)


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    d = pd.read_csv(ROOT / 'data/outcomes.csv')
    assert len(d) == 624 and d.revised_valid.sum() == 595
    assert d.groupby(['model', 'family', 'condition']).size().eq(2).all()
    assert d.groupby('model').size().eq(104).all()
    assert d.family.nunique() == 13 and d.condition.nunique() == 4
    assert d.record.is_unique
    for version in ['original', 'revised']:
        valid = d[f'{version}_valid']
        assert d.loc[~valid, [f'{version}_{k}' for k in 'FSU']].isna().all().all()
        assert d.loc[valid, [f'{version}_{k}' for k in 'FSU']].notna().all().all()
        assert (d.loc[valid, f'{version}_U'].astype(bool) ==
                (d.loc[valid, f'{version}_F'].astype(bool) &
                 ~d.loc[valid, f'{version}_S'].astype(bool))).all()
    changed = d[d.revised_valid & (d.original_S != d.revised_S)]
    assert len(changed) == 4 and set(changed.model) == {'Devstral'}
    assert set(zip(changed.family, changed.condition, changed.rep)) == {
        ('X05', 'B', 1), ('X28', 'C', 2), ('X28', 'I', 1), ('X28', 'I', 2)}
    assert d.original_valid.equals(d.revised_valid)
    assert d.original_F.fillna(-1).equals(d.revised_F.fillna(-1))

    # Reconstruct contrasts independently from the long outcome table.
    contrasts = pd.read_csv(ROOT / 'generated/contrasts.csv')
    for _, row in contrasts.iterrows():
        a, b = row.contrast.split('-')
        omitted = {'all13': [], 'omitX06': ['X06'], 'omitReviewed': ['X05', 'X06', 'X28']}[row.scope]
        subset = d[(d.model == row.model) & d.condition.isin([a, b]) & ~d.family.isin(omitted)]
        differences, families = [], []
        for family, g in subset.groupby('family'):
            if not g[f'{row.version}_valid'].all():
                continue
            assert len(g) == 4
            means = g.groupby('condition')[[f'{row.version}_{k}' for k in 'FSU']].mean()
            differences.append((means.loc[a] - means.loc[b]).to_numpy(dtype=float))
            families.append(family)
        assert len(families) == row.n and ';'.join(families) == row.families
        assert np.allclose(np.mean(differences, axis=0) * 100, row[['F', 'S', 'U']].to_numpy(dtype=float))
    joint = pd.read_csv(ROOT / 'generated/joint_counts.csv')
    assert (joint[['FS', 'U', 'notF_S', 'notF_notS', 'invalid']].sum(axis=1) == 26).all()
    assert joint.valid.sum() == 595 and joint.invalid.sum() == 29
    assert joint.U.sum() == d.revised_U.sum()
    cases = json.loads((ROOT / 'data/cases.json').read_text())
    for case in cases:
        row = d.set_index('record').loc[case['record']]
        for key in ['family', 'model', 'condition', 'rep']:
            assert case[key] == row[key]
        for key in 'FSU':
            assert case[key] == bool(row[f'revised_{key}'])
    assert len(cases) == 6
    assert hashlib.sha256((ROOT / 'neurips_2026.sty').read_bytes()).hexdigest() == STYLE_SHA256
    for path in public_paths():
        if path.suffix != '.pdf':
            check_anonymous(path.read_text(), path.relative_to(ROOT))

    texts, builds = [], {}
    bibkeys = set(re.findall(r'@\w+\s*\{\s*([^,]+),', (ROOT / 'references.bib').read_text()))
    for wrapper, workshop in [('iab', 'Interpreting Agent Behavior'), ('aiwild', 'Agents in the Wild')]:
        source = (ROOT / f'{wrapper}.tex').read_text()
        assert r'\usepackage[dblblindworkshop]{neurips_2026}' in source
        assert r'\workshoptitle{' + workshop + '}' in source
        log = (ROOT / f'{wrapper}.log').read_text()
        assert not re.search(r'Overfull|undefined|Missing character|! LaTeX Error', log, re.I)
        aux = (ROOT / f'{wrapper}.aux').read_text()
        content = int(re.search(r'\\newlabel\{content:end\}\{\{[^}]*\}\{(\d+)\}', aux).group(1))
        assert content <= 9
        cited = set(re.findall(r'\\bibcite\{([^}]+)\}', aux))
        assert cited == bibkeys, (cited, bibkeys)
        info = command('pdfinfo', f'{wrapper}.pdf')
        assert re.search(r'^Author:\s*$', info, re.M)
        assert int(re.search(r'^Pages:\s*(\d+)', info, re.M).group(1)) >= content
        assert (ROOT / f'{wrapper}.pdf').stat().st_size < 50_000_000
        text = command('pdftotext', '-layout', f'{wrapper}.pdf', '-')
        check_anonymous(text + info, wrapper)
        assert '??' not in text
        assert workshop in text
        text = re.sub(r'Submitted to NeurIPS 2026 Workshop: .*?Do not distribute\.', '', text)
        texts.append(text)
        # Geometric smoke check; rendered-page inspection covers figure semantics.
        # Poppler can encode TeX extensible math delimiters as C0 controls.
        # Remove those characters for XML parsing, preserving all coordinates.
        bbox_text = command('pdftotext', '-bbox', f'{wrapper}.pdf', '-')
        bbox = ET.fromstring(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', bbox_text))
        for page in bbox.iter():
            if page.tag.split('}')[-1] != 'page':
                continue
            width, height = float(page.attrib['width']), float(page.attrib['height'])
            for word in page.iter():
                if word.tag.split('}')[-1] == 'word':
                    assert 0 <= float(word.attrib['xMin']) < float(word.attrib['xMax']) <= width
                    assert 0 <= float(word.attrib['yMin']) < float(word.attrib['yMax']) <= height
        builds[wrapper] = {'content_pages': content,
                           'total_pages': int(re.search(r'^Pages:\s*(\d+)', info, re.M).group(1)),
                           'bytes': (ROOT / f'{wrapper}.pdf').stat().st_size,
                           'sha256': hashlib.sha256((ROOT / f'{wrapper}.pdf').read_bytes()).hexdigest(),
                           'bibliography_entries': len(cited), 'author_metadata': 'empty',
                           'overfull_or_unresolved_references': False}
    assert texts[0] == texts[1], 'Scientific text differs between workshop wrappers'
    result = {'passed': True, 'builds': builds, 'identical_text_except_workshop_notice': True,
              'recorded': len(d), 'valid': int(d.revised_valid.sum()), 'scoring_corrections': len(changed),
              'independently_recomputed_contrast_rows': len(contrasts), 'verified_case_outcome_links': len(cases),
              'official_style_sha256': STYLE_SHA256,
              'visual_check': 'See BUILD_REPORT.md for separately recorded rendered-page inspection.'}
    (ROOT / 'build/qa.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
