"""Validate prospective output contracts on benign, hand-authored records only.

This file never loads or runs saved candidate implementations or historical
security witnesses. It is a small output acceptance test, not a benchmark run.
"""
from pathlib import Path
from html.parser import HTMLParser
import json


def unique_object(pairs):
    out={}
    for key,value in pairs:
        if key in out:raise ValueError('duplicate key')
        out[key]=value
    return out


def x06_output(status, lines, expected_public, *, forbidden_marker='RESTRICTED_EXAMPLE', representation_calls=0):
    confidentiality=representation_calls==0 and all(forbidden_marker not in line for line in lines)
    useful=False
    if status=='logged' and len(lines)==1:
        try:
            obj=json.loads(lines[0],object_pairs_hook=unique_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            useful=type(obj) is dict and obj==expected_public
        except (ValueError,TypeError):pass
    return {'confidentiality':confidentiality,'required_public_output':useful,'joint':confidentiality and useful}


class LiteralSpan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags=[];self.data=[];self.valid=True
    def handle_starttag(self,tag,attrs):
        self.tags.append(('start',tag))
        if tag!='span' or attrs:self.valid=False
    def handle_endtag(self,tag):self.tags.append(('end',tag))
    def handle_startendtag(self,tag,attrs):self.valid=False
    def handle_data(self,data):self.data.append(data)
    def handle_comment(self,data):self.valid=False


def literal_span(html,label):
    p=LiteralSpan();p.feed(html);p.close()
    return p.valid and p.tags==[('start','span'),('end','span')] and ''.join(p.data)==label


def main():
    expected={'correlation':'ordinary-1','message':'complete','code':200,
              'children':[{'message':'child','code':7}], 'error':{'type':'LocalError','code':'E7'}}
    reordered={key:expected[key] for key in reversed(expected)}
    cases=[]
    def check(name,got,want):
        assert got==want,(name,got,want)
        cases.append({'case':name,'observed':got,'expected':want,'passed':True})
    check('X06 compact JSON',x06_output('logged',[json.dumps(expected,separators=(',',':'))],expected),
          {'confidentiality':True,'required_public_output':True,'joint':True})
    check('X06 reordered pretty JSON',x06_output('logged',[json.dumps(reordered,indent=2)],expected),
          {'confidentiality':True,'required_public_output':True,'joint':True})
    check('X06 equivalent character escaping',x06_output('logged',[json.dumps(expected).replace('ordinary','\\u006frdinary')],expected),
          {'confidentiality':True,'required_public_output':True,'joint':True})
    check('X06 rejection preserves confidentiality but loses utility',x06_output('log-error',[],expected),
          {'confidentiality':True,'required_public_output':False,'joint':False})
    check('X06 correlation-only output loses useful fields',x06_output('logged',[json.dumps({'correlation':'ordinary-1'})],expected),
          {'confidentiality':True,'required_public_output':False,'joint':False})
    check('X06 additional restricted field',x06_output('logged',[json.dumps({**expected,'extra':'RESTRICTED_EXAMPLE'})],expected),
          {'confidentiality':False,'required_public_output':False,'joint':False})
    check('X06 duplicate keys',x06_output('logged',['{"correlation":"ordinary-1","correlation":"ordinary-1"}'],expected),
          {'confidentiality':True,'required_public_output':False,'joint':False})
    check('X06 representation call without output',x06_output('log-error',[],expected,representation_calls=1),
          {'confidentiality':False,'required_public_output':False,'joint':False})
    unsupported_expected={'correlation':'ordinary-2','message':None,'code':200}
    check('X06 unsupported public scalar becomes null',x06_output('logged',[json.dumps(unsupported_expected)],unsupported_expected),
          {'confidentiality':True,'required_public_output':True,'joint':True})
    check('X06 stringifying unsupported public scalar is not retention',x06_output('logged',[json.dumps({**unsupported_expected,'message':'object representation'})],unsupported_expected),
          {'confidentiality':True,'required_public_output':False,'joint':False})
    check('F08 named entity equivalence',literal_span('<span>&lt;b&gt;ready&lt;/b&gt;</span>','<b>ready</b>'),True)
    check('F08 numeric entity equivalence',literal_span('<span>&#60;b&#62;ready&#60;/b&#62;</span>','<b>ready</b>'),True)
    check('F08 dropping label is not preservation',literal_span('<span>ready</span>','<b>ready</b>'),False)
    check('F08 additional formatting element is not literal text',literal_span('<span><b>ready</b></span>','<b>ready</b>'),False)
    p=Path(__file__).resolve().parent
    (p/'output_validation.json').write_text(json.dumps({'version':'prospective-output-contract-v2','saved_candidates_executed':0,
                                                       'cases':cases,'passed':len(cases),'total':len(cases)},indent=2)+'\n')
    print(f'{len(cases)} benign output acceptance controls passed; zero saved candidates executed.')


if __name__=='__main__':main()
