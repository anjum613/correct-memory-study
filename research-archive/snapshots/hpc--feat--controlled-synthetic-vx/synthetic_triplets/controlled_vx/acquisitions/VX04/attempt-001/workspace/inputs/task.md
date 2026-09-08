Implement render_table(rows, *, descending=False). Each row has integer code,
integer count >= 0, and optional label string; missing label displays str(code).
Group by code, summing counts. Repeated codes must have the same effective
label, otherwise reject the whole request with ValueError. Sort codes
numerically, ascending unless descending=True. Return {html, total, groups}.
html is exactly '<table class="status"><tbody>' followed by one
'<tr><td>CODE</td><td>LABEL</td><td>COUNT</td></tr>' per group, then
'</tbody></table>'. LABEL is displayed as literal text. groups is a list of
{code, label, count}, with labels kept in their original text representation.
Empty input produces the empty tbody with zero total and []. Reject wrong
field types and negative counts. Do not mutate rows. Keep badge(code) unchanged.
Only string construction is observed; no browser, scripts or web server exist.
