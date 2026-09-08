"""Create anonymous local ZIPs from an explicit whitelist; never publish them."""
from pathlib import Path
import hashlib
import json
import zipfile

from qa import ROOT, check_anonymous, public_paths, evidence_paths


def write_zip(name, paths):
    manifest = []
    destination = ROOT / 'dist' / name
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            relative = path.relative_to(ROOT).as_posix()
            assert relative.split('/')[0] not in {'private', 'build', 'dist'}
            assert path.is_file() and not path.is_symlink()
            payload = path.read_bytes()
            if path.suffix != '.pdf':
                check_anonymous(payload.decode(), relative)
            archive.writestr(relative, payload)
            manifest.append({'file': relative, 'bytes': len(payload),
                             'sha256': hashlib.sha256(payload).hexdigest()})
        archive.writestr('PACKAGE_MANIFEST.json', json.dumps(manifest, indent=2) + '\n')
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
    return {'file': name, 'bytes': destination.stat().st_size,
            'files': len(manifest), 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


def main():
    qa = json.loads((ROOT / 'build/qa.json').read_text())
    assert qa['passed']
    for wrapper in ['iab', 'aiwild']:
        assert hashlib.sha256((ROOT / f'{wrapper}.pdf').read_bytes()).hexdigest() == qa['builds'][wrapper]['sha256']
    (ROOT / 'dist').mkdir(exist_ok=True)
    paths = public_paths()
    source = write_zip('anonymous-paper-source.zip', paths + [ROOT / 'iab.pdf', ROOT / 'aiwild.pdf'])
    generated_names = {
        'annotation_agreement.tex', 'annotation_full_counts.tex', 'annotation_numbers.tex',
        'bounds_information_comparison.tex', 'c_minus_i.tex', 'cases.tex',
        'config_details.tex', 'contrasts.tex', 'correction_contrasts.tex',
        'corrections.tex', 'design.tex', 'diagnostics.tex', 'eligibility.tex',
        'family_definitions.tex', 'joint_counts.tex', 'measurement_coverage.tex',
        'missingness.tex', 'numbers.tex', 'observer_contract_review.tex',
        'sensitivity.tex'
    }
    overleaf_paths = [ROOT / name for name in [
        'iab.tex', 'aiwild.tex', 'manuscript.tex', 'preamble.tex',
        'neurips_2026.sty', 'references.bib'
    ]]
    overleaf_paths += sorted((ROOT / 'sections').glob('*.tex'))
    overleaf_paths += sorted(p for p in (ROOT / 'generated').glob('*.tex') if p.name in generated_names)
    overleaf_paths += sorted((ROOT / 'figures').glob('*.pdf'))
    overleaf = write_zip('overleaf-source.zip', overleaf_paths)
    analysis_paths = [p for p in paths if p.relative_to(ROOT).parts[0] in {'data','generated','figures','annotation','measurement-v2','prospective'} or
                      p.relative_to(ROOT).as_posix() in {'scripts/analyze.py','scripts/plot_figures.py','scripts/render_assets.py','scripts/analyze_missingness.py','scripts/analyze_annotations.py','scripts/render_observer_review.py','scripts/verify_evidence.py','requirements.txt','REVIEW_README.md'}]
    analysis = write_zip('anonymous-analysis.zip', analysis_paths)
    evidence = write_zip('anonymous-static-evidence.zip', evidence_paths())
    report=[overleaf,source,analysis,evidence]
    (ROOT / 'dist/package-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))



if __name__ == '__main__':
    main()
