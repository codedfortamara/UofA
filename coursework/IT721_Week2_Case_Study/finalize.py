"""Merge executed outputs into the freshly built notebook, inject the discussion text, export HTML.

python finalize.py <executed.ipynb>
"""
import sys, subprocess
from pathlib import Path
import nbformat as nbf
from interpretations import INTERP

HERE = Path(__file__).parent
clean = nbf.read(HERE / 'Week2_Case_Study_Tamara_Dinneen.ipynb', 4)
ran = nbf.read(sys.argv[1], 4)
outs = {c.source: (c.outputs, c.execution_count) for c in ran.cells if c.cell_type == 'code'}

missing = 0
for c in clean.cells:
    if c.cell_type == 'code':
        if c.source in outs:
            o, n = outs[c.source]
            # drop TensorFlow start-up log noise (stderr) from the deliverable
            c.outputs = [x for x in o if not (x.output_type == 'stream' and x.name == 'stderr'
                                              and ('absl::InitializeLog' in x.text or 'oneDNN' in x.text or 'cpu_feature_guard' in x.text))]
            c.execution_count = n
        else:
            missing += 1
    else:
        for key, text in INTERP.items():
            c.source = c.source.replace(f'<!--INTERP_{key}-->', text.strip('\n'))
left = [c.source for c in clean.cells if c.cell_type == 'markdown' and '<!--INTERP_' in c.source]
assert missing == 0, f'{missing} code cells have no executed output'
assert not left, f'unfilled markers: {left}'

# clean notebook (no outputs) for Colab, and the executed one for the HTML deliverable
nbf.write(clean, HERE / 'Week2_Case_Study_Tamara_Dinneen_executed.ipynb')
for c in clean.cells:
    if c.cell_type == 'code':
        c.outputs, c.execution_count = [], None
nbf.write(clean, HERE / 'Week2_Case_Study_Tamara_Dinneen.ipynb')
subprocess.run(['jupyter', 'nbconvert', '--to', 'html', str(HERE / 'Week2_Case_Study_Tamara_Dinneen_executed.ipynb'),
                '--output', 'Week2_Case_Study_Tamara_Dinneen'], check=True)
print('done')
