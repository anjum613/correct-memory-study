"""Render every manuscript figure with Matplotlib from saved numerical records.

No image-generation service, raster artwork, or candidate execution is used.
Figures are drawn at the manuscript's 5.5 inch text width and saved as vectors.
"""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle, FancyArrowPatch
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODELS = ['GPT55', 'Luna', 'Terra', 'QwenNext', 'Qwen30', 'Devstral']
LABELS = ['GPT-5.5 Low', 'Luna Medium', 'Terra Medium',
          'Qwen Next', 'Qwen 30B', 'Devstral']
FAMILIES = ['F01', 'F02', 'F04', 'F08', 'F17', 'F20', 'X02',
            'X05', 'X06', 'X11', 'X20', 'X24', 'X28']
CONDITIONS = ['N', 'C', 'I', 'B']
# Matplotlib's conventional Tableau blue, red and orange; neutral grays.
COLORS = {'FS': '#1f77b4', 'U': '#d62728', 'notF_S': '#ff7f0e',
          'notF_notS': '#4d4d4d', 'invalid': '#d0d0d0'}
LEGEND = ['F pass, S pass', 'F pass, S fail (U)', 'F fail, S pass',
          'F fail, S fail', 'Technical invalid']
FIGURES = ['design_overview.pdf', 'joint_outcomes.pdf',
           'treatment_contrasts.pdf', 'family_overview.pdf']


def save(fig, name):
    """Keep exact print width and omit volatile PDF dates for reproducibility."""
    assert np.isclose(fig.get_figwidth(), 5.5)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    labels = []
    drawn = list(fig.texts)
    legends = list(fig.legends)
    for ax in fig.axes:
        drawn.extend(ax.texts)
        drawn.extend([ax.title, ax._left_title, ax._right_title])
        if ax.get_legend() is not None:
            legends.append(ax.get_legend())
        if ax.axison:
            for axis in [ax.xaxis, ax.yaxis]:
                if axis.get_visible():
                    drawn.extend(axis.get_ticklabels(which='both'))
                    drawn.extend([axis.label, axis.get_offset_text()])
    for legend in legends:
        drawn.extend(legend.get_texts())
        drawn.append(legend.get_title())
    for label in drawn:
        if label.get_visible() and label.get_text().strip():
            assert label.get_fontsize() >= 8, (name, label.get_text())
            bounds = label.get_window_extent(renderer)
            assert bounds.x0 >= -1 and bounds.y0 >= -1, (name, label.get_text(), bounds)
            assert bounds.x1 <= fig.bbox.x1 + 1 and bounds.y1 <= fig.bbox.y1 + 1, (name, label.get_text(), bounds)
            labels.append((label.get_text(), bounds))
    for i, (text_a, a) in enumerate(labels):
        for text_b, b in labels[i + 1:]:
            overlap_x = min(a.x1, b.x1) - max(a.x0, b.x0)
            overlap_y = min(a.y1, b.y1) - max(a.y0, b.y0)
            assert overlap_x <= .5 or overlap_y <= .5, (name, 'overlapping labels', text_a, text_b)
    fig.savefig(ROOT / 'figures' / name,
                metadata={'Creator': 'Matplotlib', 'Author': '',
                          'CreationDate': None, 'ModDate': None})
    plt.close(fig)


def legend_handles():
    return [Patch(facecolor=color, edgecolor='white', label=label)
            for color, label in zip(COLORS.values(), LEGEND)]


def design_overview():
    fig, ax = plt.subplots(figsize=(5.5, 2.8))
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set(xlim=(0, 5.5), ylim=(0, 2.8))
    ax.axis('off')

    def box(x, y, width, height, heading, body, accent=False):
        edge = COLORS['FS'] if accent else '#555555'
        ax.add_patch(Rectangle((x, y), width, height, facecolor='white',
                               edgecolor=edge, linewidth=1.0))
        ax.text(x + width / 2, y + height - .13, heading, ha='center',
                va='top', fontsize=9, fontweight='bold', color=edge)
        ax.text(x + width / 2, y + .10, body, ha='center', va='bottom',
                fontsize=8.5, linespacing=1.25)

    def arrow(start, end):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>',
                                    mutation_scale=8, linewidth=.9,
                                    color='#555555'))

    ax.text(.12, 2.72, 'Source and target construction: F08', fontsize=9,
            ha='left', va='top', fontweight='bold')
    box(.12, 2.02, 1.53, .51, 'Source assumption', 'Numeric status value')
    box(1.985, 2.02, 1.53, .51, 'Valid procedure', 'Interpolate into HTML')
    box(3.85, 2.02, 1.53, .51, 'Shifted target', 'Caller controlled text', True)
    arrow((1.66, 2.275), (1.97, 2.275))
    arrow((3.53, 2.275), (3.84, 2.275))

    # The branch explicitly holds the target fixed across all four conditions.
    ax.plot([4.615, 4.615], [2.02, 1.82], color='#555555', lw=.9)
    ax.plot([.73, 4.765], [1.82, 1.82], color='#555555', lw=.9)
    ax.text(2.30, 1.91, 'Same target task in every condition', fontsize=8.5,
            va='center', ha='center', bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 1})
    centers = [.73, 2.075, 3.42, 4.765]
    items = [('N', 'No memory'), ('C', 'Correct source\nmemory'),
             ('I', 'Irrelevant\nmemory'), ('B', 'Correct memory\n+ reminder')]
    for x, (arm, body) in zip(centers, items):
        arrow((x, 1.82), (x, 1.59))
        box(x - .61, .93, 1.22, .64, arm, body)
        ax.plot([x, x], [.93, .75], color='#555555', lw=.9)
    ax.plot([centers[0], centers[-1]], [.75, .75], color='#555555', lw=.9)
    arrow((2.75, .75), (2.75, .59))
    ax.add_patch(Rectangle((.12, .09), 5.26, .49, facecolor='#f3f3f3',
                           edgecolor='#555555', linewidth=1))
    ax.text(2.75, .45, 'Evaluate the saved implementation', ha='center',
            va='center', fontsize=9, fontweight='bold')
    ax.text(2.75, .23, r'Functionality $F$ and focal witness $S$;  $U = F \wedge \neg S$',
            ha='center', va='center', fontsize=9)
    save(fig, 'design_overview.pdf')


def treatment_contrasts(contrasts):
    q = contrasts[(contrasts.version == 'revised') & (contrasts.scope == 'all13')]
    fig = plt.figure(figsize=(5.5, 3.5))
    grid = fig.add_gridspec(1, 5, width_ratios=[1.04, 1.42, .74, 1.42, .74],
                           left=.015, right=.99, bottom=.19, top=.86, wspace=.10)
    label_ax, left_ax, left_num, right_ax, right_num = [fig.add_subplot(grid[0, j]) for j in range(5)]
    y = np.array([6, 5, 4, 2, 1, 0])
    for ax in [label_ax, left_ax, left_num, right_ax, right_num]:
        ax.set_ylim(-.55, 7.10)
        ax.axhline(3.0, color='#c0c0c0', linewidth=.7, zorder=0)
    label_ax.set_xlim(0, 1)
    label_ax.axis('off')
    for yi, label in zip(y, LABELS):
        label_ax.text(0, yi, label, va='center', fontsize=8.0)
    for yi, name in [(6.75, 'Codex'), (2.75, 'MiniSWE')]:
        label_ax.text(0, yi, name, fontsize=8.0, fontweight='bold', va='center')

    for ax, num, contrast, title, color in [
            (left_ax, left_num, 'C-N', 'Correct memory\nC − N', COLORS['FS']),
            (right_ax, right_num, 'B-C', 'Applicability reminder\nB − C', '#333333')]:
        g = q[q.contrast == contrast].set_index('model').loc[MODELS]
        ax.axvline(0, color='#555555', linewidth=.8, zorder=1)
        ax.errorbar(g.U, y, xerr=np.vstack([g.U - g.U_lo, g.U_hi - g.U]),
                    fmt='o', color=color, ecolor=color, elinewidth=1.2,
                    capsize=2.5, markersize=4.3, zorder=3)
        ax.set_xlim(-63, 44)
        ax.set_xticks([-60, -30, 0, 30])
        ax.tick_params(axis='x', labelsize=8, length=3)
        ax.set_yticks([])
        ax.grid(axis='x', color='#e2e2e2', linewidth=.6)
        ax.set_title(title, fontsize=8.5, pad=9, fontweight='bold')
        ax.spines[['left', 'right', 'top']].set_visible(False)
        num.set_xlim(0, 1)
        num.axis('off')
        num.set_title(r'$\Delta U$; $n$', fontsize=8.5, pad=9)
        for yi, (_, row) in zip(y, g.iterrows()):
            estimate = '0.0' if abs(row.U) < 1e-9 else f'{row.U:+.1f}'
            num.text(.98, yi, f'{estimate}; {int(row.n)}', ha='right', va='center', fontsize=8)
    fig.text(.61, .055, 'Change in U (percentage points)', ha='center', fontsize=9)
    save(fig, 'treatment_contrasts.pdf')


def joint_outcomes(counts):
    fig, axes = plt.subplots(2, 3, figsize=(5.5, 3.65), sharex=True, sharey=True)
    fig.subplots_adjust(left=.065, right=.985, top=.89, bottom=.235, hspace=.61, wspace=.23)
    for ax, model, label in zip(axes.flat, MODELS, LABELS):
        q = counts[counts.model == model].set_index('condition').loc[CONDITIONS]
        left = np.zeros(4)
        for key, color in COLORS.items():
            ax.barh(np.arange(4), q[key], left=left, color=color, height=.72,
                    edgecolor='white', linewidth=.25)
            for yi, (offset, width) in enumerate(zip(left, q[key])):
                if width >= 2:
                    ax.text(offset + width / 2, yi, str(width), ha='center', va='center',
                            fontsize=8.5, color='white' if key in ['FS', 'U', 'notF_notS'] else 'black')
            left += q[key].to_numpy()
        ax.set_yticks(range(4), CONDITIONS)
        ax.set_ylim(3.55, -.55)
        ax.set_xlim(0, 26)
        ax.set_xticks([0, 13, 26])
        ax.tick_params(axis='both', labelsize=8.5, length=2)
        ax.set_title(label, fontsize=9, pad=5)
        ax.spines[['top', 'right', 'left']].set_visible(False)
    fig.text(.065, .977, 'Codex', ha='left', va='top', fontsize=9, fontweight='bold')
    fig.text(.065, .605, 'MiniSWE', ha='left', va='top', fontsize=9, fontweight='bold')
    fig.text(.53, .151, 'Recorded runs per condition', ha='center', fontsize=8.5)
    fig.legend(handles=legend_handles(), loc='lower center', bbox_to_anchor=(.5, .012),
               ncol=3, frameon=False, fontsize=8, columnspacing=1, handlelength=1.25)
    save(fig, 'joint_outcomes.pdf')


def family_overview(outcomes):
    fig, axes = plt.subplots(1, 6, figsize=(5.5, 4.0), sharey=True)
    fig.subplots_adjust(left=.075, right=.985, top=.79, bottom=.15, wspace=.16)
    titles = ['GPT-5.5\nLow', 'Luna\nMedium', 'Terra\nMedium',
              'Qwen\nNext', 'Qwen\n30B', 'Devstral']
    for ax, model, title in zip(axes, MODELS, titles):
        q = outcomes[outcomes.model == model].set_index(['family', 'condition', 'rep'])
        for yi, family in enumerate(FAMILIES):
            for xi, condition in enumerate(CONDITIONS):
                for ri in range(2):
                    row = q.loc[(family, condition, ri + 1)]
                    key = 'invalid' if not row.revised_valid else (
                        'FS' if row.revised_F and row.revised_S else 'U' if row.revised_F
                        else 'notF_S' if row.revised_S else 'notF_notS')
                    ax.add_patch(Rectangle((xi + ri * .5, yi), .5, 1, facecolor=COLORS[key],
                                           edgecolor='white', linewidth=.35))
        ax.set(xlim=(0, 4), ylim=(13, 0))
        ax.set_xticks(np.arange(4) + .5, CONDITIONS)
        ax.xaxis.tick_top()
        ax.set_yticks(np.arange(13) + .5, FAMILIES)
        ax.tick_params(length=0, labelsize=8.5)
        ax.set_title(title, fontsize=8.5, pad=23)
        for spine in ax.spines.values():
            spine.set_visible(False)
    fig.text(.295, .975, 'Codex', ha='center', va='top', fontsize=9, fontweight='bold')
    fig.text(.775, .975, 'MiniSWE', ha='center', va='top', fontsize=9, fontweight='bold')
    fig.legend(handles=legend_handles(), loc='lower center', bbox_to_anchor=(.5, .005),
               ncol=3, frameon=False, fontsize=8, columnspacing=1, handlelength=1.25)
    save(fig, 'family_overview.pdf')


def render_all(root=None):
    global ROOT
    if root is not None:
        ROOT = Path(root)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9,
                         'pdf.fonttype': 42, 'ps.fonttype': 42,
                         'axes.spines.top': False, 'axes.spines.right': False})
    d = pd.read_csv(ROOT / 'data/outcomes.csv')
    counts = pd.read_csv(ROOT / 'generated/joint_counts.csv')
    contrasts = pd.read_csv(ROOT / 'generated/contrasts.csv')
    assert len(d) == 624 and d.revised_valid.sum() == 595
    assert (counts[list(COLORS)].sum(axis=1) == 26).all()
    (ROOT / 'figures').mkdir(exist_ok=True)
    design_overview()
    joint_outcomes(counts)
    treatment_contrasts(contrasts)
    family_overview(d)
    inputs = ['data/outcomes.csv', 'generated/joint_counts.csv', 'generated/contrasts.csv',
              'evidence/families/F08.json', 'scripts/plot_figures.py']
    def digest(path):
        return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    report = {'renderer': 'Python / Matplotlib', 'matplotlib_version': matplotlib.__version__,
              'image_generation_used': False, 'raster_artwork_used': False,
              'width_inches': 5.5, 'minimum_text_size_points': 8,
              'text_inside_canvas_checked': True, 'text_overlap_checked': True, 'palette': COLORS,
              'inputs': {p: digest(p) for p in inputs if (ROOT / p).exists()},
              'outputs': {name: digest('figures/' + name) for name in FIGURES}}
    (ROOT / 'generated/figure_manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Rendered all four vector figures using Matplotlib; saved figure_manifest.json.')


if __name__ == '__main__':
    render_all()
