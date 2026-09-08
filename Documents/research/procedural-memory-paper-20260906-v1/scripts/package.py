"""Create anonymous local ZIPs from an explicit whitelist; never publish them."""
from pathlib import Path
import hashlib
import json
import zipfile

from qa import ROOT, check_anonymous, public_paths


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
    analysis_paths = [p for p in paths if p.parts[-2] in {'data', 'generated', 'figures'} or
                      p.relative_to(ROOT).as_posix() in {'scripts/analyze.py', 'scripts/render_assets.py',
                                                        'requirements.txt', 'REVIEW_README.md'}]
    analysis = write_zip('anonymous-analysis.zip', analysis_paths)
    (ROOT / 'dist/package-report.json').write_text(json.dumps([source, analysis], indent=2) + '\n')
    print(json.dumps([source, analysis], indent=2))


if __name__ == '__main__':
    main()
