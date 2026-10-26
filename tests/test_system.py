import copy
import hashlib
import json
import re
import shutil
import sys
import unittest
import urllib.parse
import uuid
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build
import publications as pub
import sync_publications


def example(doi='10.5555/verified-test', given='Ming-Qiang', orcid=pub.ORCID):
    author = {'given': given, 'family': 'Liang'}
    if orcid:
        author['ORCID'] = 'https://orcid.org/' + orcid
    return {'DOI':doi,'title':['Verified δ18O climate study & model comparison'], 'container-title':['Test Journal'],
            'author':[author, {'given':'A.', 'family':'Colleague'}], 'published':{'date-parts':[[2026,1,2]]},
            'type':'journal-article','volume':'8','issue':'2','article-number':'123'}


class TestSystem(unittest.TestCase):
    def setUp(self):
        self.database = pub.read_json(ROOT / 'data/publications.json')

    def sandbox(self):
        folder = ROOT / 'work/tests' / uuid.uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        # Test output is confined to the ignored workspace and retained for diagnostics.
        for directory in ['scripts', 'data', 'templates']:
            shutil.copytree(ROOT / directory, folder / directory, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(ROOT/'requirements.txt',folder/'requirements.txt')
        return folder

    def test_A_original_selected_three_and_contributions(self):
        expected = {
            '10.1016/j.gloplacha.2025.105115':(11,False,True,12,'Liang2025_midHocene.pdf'),
            '10.1016/j.quascirev.2024.108946':(1,False,False,8,'Liang2024_orbital_monsson.pdf'),
            '10.1016/j.quascirev.2022.107420':(2,True,False,5,'Liang2022_enso_monsoon.pdf')}
        rows={r['doi']:pub.effective(r) for r in self.database['records']}
        for d,(position,co,corr,count,pdf) in expected.items():
            p=rows[d]
            self.assertTrue(p['show_on_homepage'])
            self.assertEqual((p['my_author_position'],p['co_first_author'],p['corresponding_author'],len(p['authors'])),(position,co,corr,count))
            self.assertTrue(p['local_pdf'].endswith(pdf))
            self.assertGreaterEqual(len(p['keywords']),3)
        ordered=[p['doi'] for p in build.ordered(self.database,'show_on_homepage') if p['doi'] in expected]
        self.assertEqual(ordered,list(expected))

    def test_A_all_existing_CV_outputs_preserved(self):
        baseline=json.loads((ROOT/'tests/fixtures/migration-inventory.json').read_text(encoding='utf-8'))
        self.assertTrue(set(baseline['dois']) <= {r['doi'] for r in self.database['records']})
        self.assertEqual(hashlib.sha256((ROOT/'assets/CV/260310_Mingqiang_Liang_CV.pdf').read_bytes()).hexdigest(),baseline['original_cv_sha256'])

    def test_B_verified_new_paper_reaches_both_artifacts(self):
        work=example()
        new, pending, events=pub.reconcile(self.database,{work['DOI']:{'orcid':True}},{work['DOI']:work})
        self.assertFalse(pending)
        folder=self.sandbox()
        pub.write_json(folder/'data/publications.json',new)
        self.assertTrue(build.build(folder,'2026-10-26'))
        self.assertIn(work['title'][0].replace('&','&amp;'),(folder/'index.html').read_text(encoding='utf-8'))
        from pypdf import PdfReader
        text=' '.join(p.extract_text() for p in PdfReader(folder/'assets/CV/Mingqiang_Liang_CV.pdf').pages)
        self.assertIn(work['DOI'],text)
        self.assertIn('δ18O',text)

    def test_C_normalize_doi_and_deduplicate_sources(self):
        self.assertEqual(pub.doi(' HTTPS://DOI.ORG/10.5555/ABC '),'10.5555/abc')
        work=example()
        evidence={work['DOI']:{'orcid':True,'crossref_search':True,'openalex':{}}}
        new,_,_=pub.reconcile(self.database,evidence,{work['DOI']:work})
        again,_,_=pub.reconcile(new,evidence,{work['DOI']:work})
        self.assertEqual(new,again)
        self.assertEqual(sum(r['doi']==work['DOI'] for r in new['records']),1)

    def test_D_name_alone_never_auto_publishes(self):
        work=example(orcid=None)
        new,pending,_=pub.reconcile(self.database,{work['DOI']:{}},{work['DOI']:work})
        self.assertEqual(new,self.database)
        self.assertIn('identity uncertain',pending[0]['reason'])

    def test_D_conflicting_author_ORCID_rejected_even_on_owner_record(self):
        work=example(orcid='0000-0000-0000-0000')
        new,pending,_=pub.reconcile(self.database,{work['DOI']:{'orcid':True}},{work['DOI']:work})
        self.assertEqual(new,self.database)
        self.assertTrue(pending)

    def test_D_other_given_name_not_accepted(self):
        work=example(given='Other')
        new,pending,_=pub.reconcile(self.database,{work['DOI']:{'orcid':True}},{work['DOI']:work})
        self.assertEqual(new,self.database)
        self.assertTrue(pending)

    def test_D_openalex_identity_requires_matching_title_and_full_name(self):
        work=example(orcid=None)
        ev={'openalex':{'name':'Ming-Qiang Liang','orcid':'https://orcid.org/'+pub.ORCID,'title':work['title'][0]}}
        new,pending,_=pub.reconcile(self.database,{work['DOI']:ev},{work['DOI']:work})
        self.assertFalse(pending)
        self.assertEqual(len(new['records']),len(self.database['records'])+1)
        ev['openalex']['title']='Unrelated title'
        new,pending,_=pub.reconcile(self.database,{work['DOI']:ev},{work['DOI']:work})
        self.assertEqual(new,self.database)

    def test_E_author_flags_render_and_manual_fields_are_protected(self):
        paper=next(pub.effective(r) for r in self.database['records'] if r['doi'].endswith('107420'))
        self.assertIn('<strong>Liang, M.-Q. (co-first author)</strong>',build.author_text(paper))
        self.assertIn('<super>†</super>',build.author_text(paper,cv=True))
        paper['corresponding_author']=True
        self.assertIn('†*',build.author_text(paper,cv=True))
        d=next(r['doi'] for r in self.database['records'] if r['doi'].endswith('105115'))
        record=next(r for r in self.database['records'] if r['doi']==d)
        old=copy.deepcopy(record['manual'])
        work=example(d)
        new,pending,_=pub.reconcile(self.database,{d:{'orcid':True}},{d:work})
        self.assertEqual(next(r for r in new['records'] if r['doi']==d)['manual'],old)
        self.assertIn('bibliographic conflict',pending[0]['reason'])

    def test_F_source_failure_is_transactional(self):
        class Broken:
            def get(self,*a,**kw):
                raise pub.SourceError('timeout')
        before=json.dumps(self.database,sort_keys=True)
        with self.assertRaises(pub.SourceError): pub.sync(self.database,Broken())
        self.assertEqual(json.dumps(self.database,sort_keys=True),before)

    def test_F_invalid_empty_orcid_schema_fails_safely(self):
        for response in [{},{'group':None},{'error':'429'}]:
            class Broken:
                def get(self,*a,**kw): return response
            with self.assertRaises(pub.SourceError): pub.sync(self.database,Broken())

    def test_F_partial_or_wrong_doi_kept_for_review(self):
        for work in [{},example('10.5555/other')]:
            new,pending,_=pub.reconcile(self.database,{'10.5555/verified-test':{'orcid':True}},{'10.5555/verified-test':work})
            self.assertEqual(new,self.database)
            self.assertTrue(pending)

    def test_F_cli_failure_preserves_all_tracked_data(self):
        folder=self.sandbox()
        before=(folder/'data/publications.json').read_bytes()
        with patch.object(sys,'argv',['sync','--root',str(folder),'--report',str(folder/'work/report.json')]), patch.object(pub.Client,'get',side_effect=pub.SourceError('HTTP 429')):
            self.assertEqual(sync_publications.main(),1)
        self.assertEqual((folder/'data/publications.json').read_bytes(),before)
        self.assertFalse((folder/'index.html').exists())

    def test_F_timeout_retry_and_bad_json(self):
        class BrokenOpener:
            def open(self,*args,**kwargs): raise TimeoutError()
        client=pub.Client()
        client.opener=BrokenOpener()
        with patch('publications.time.sleep') as sleeper:
            with self.assertRaises(pub.SourceError): client.get('https://api.crossref.org/works')
            self.assertEqual(sleeper.call_count,2)

    def test_F_empty_and_malformed_JSON_retried_without_mutation(self):
        import io
        for raw in [b'',b'{not json',b'[]']:
            class Opener:
                def open(self,*args,**kwargs): return io.BytesIO(raw)
            client=pub.Client()
            client.opener=Opener()
            with patch('publications.time.sleep'):
                with self.assertRaises(pub.SourceError): client.get('https://api.crossref.org/works')

    def test_source_pagination_and_missing_DOI_review_queue(self):
        calls=[]
        work=example()
        class FakeClient:
            def get(self,url,*args):
                calls.append(url)
                parsed=urllib.parse.urlsplit(url)
                params=urllib.parse.parse_qs(parsed.query)
                if parsed.hostname=='pub.orcid.org':
                    return {'group':[{'work-summary':[{'put-code':7,'title':{'title':{'value':'No DOI work'}}}],'external-ids':{'external-id':[]}}]}
                if '/authors/' in parsed.path: return {'id':pub.OPENALEX,'orcid':'https://orcid.org/'+pub.ORCID}
                if parsed.hostname=='api.openalex.org':
                    if params['cursor']==['*']:
                        return {'results':[{'doi':work['DOI'],'title':work['title'][0],'authorships':[{'author':{'id':pub.OPENALEX,'orcid':'https://orcid.org/'+pub.ORCID,'display_name':'Ming-Qiang Liang'}}]}], 'meta':{'next_cursor':'page-two'}}
                    return {'results':[],'meta':{'next_cursor':None}}
                return {'message':{'items':[work]*100 if params['cursor']==['*'] else [],'next-cursor':'second'}}
        evidence,queue=pub.collect(FakeClient())
        self.assertEqual(list(evidence),[work['DOI']])
        self.assertTrue(evidence[work['DOI']]['crossref_search'])
        self.assertIn('without a usable self DOI',queue[0]['reason'])
        self.assertEqual(len(calls),6)

    def test_changed_openalex_identity_fails_safely(self):
        class FakeClient:
            def get(self,url,*args):
                return {'group':[]} if 'pub.orcid' in url else {'id':'https://openalex.org/OTHER','orcid':'https://orcid.org/'+pub.ORCID}
        with self.assertRaises(pub.SourceError): pub.collect(FakeClient())

    def test_retraction_and_conflicting_sources_queued(self):
        work=example()
        for oa in [{'is_retracted':True},{'title':'A completely different paper'}]:
            new,pending,_=pub.reconcile(self.database,{work['DOI']:{'orcid':True,'openalex':oa}},{work['DOI']:work})
            self.assertEqual(new,self.database)
            self.assertTrue(pending)

    def test_G_no_change_preserves_pdf_bytes_date_and_mtime(self):
        folder=self.sandbox()
        build.build(folder,'2026-10-26')
        files=[folder/'index.html',folder/'assets/CV/Mingqiang_Liang_CV.pdf',folder/'data/build-state.json']
        before=[(p.read_bytes(),p.stat().st_mtime_ns) for p in files]
        with patch('build.create_cv',side_effect=AssertionError('unnecessary PDF rebuild')):
            self.assertFalse(build.build(folder,'2027-01-04'))
        self.assertEqual(before,[(p.read_bytes(),p.stat().st_mtime_ns) for p in files])

    def test_G_deterministic_pdf_regeneration(self):
        folder=self.sandbox()
        content=pub.read_json(folder/'templates/cv-content.json')
        first,second=folder/'one.pdf',folder/'two.pdf'
        build.create_cv(self.database,content,first)
        build.create_cv(self.database,content,second)
        self.assertEqual(first.read_bytes(),second.read_bytes())

    def test_G_review_only_change_does_not_rebuild(self):
        folder=self.sandbox()
        build.build(folder,'2026-10-26')
        pub.write_json(folder/'data/pending-publications.json',[{'doi':'10.5555/uncertain','reason':'identity'}])
        self.assertFalse(build.build(folder,'2027-01-04'))

    def test_G_checkout_line_endings_do_not_rebuild(self):
        folder=self.sandbox()
        build.build(folder,'2026-10-26')
        for name in ['templates/index.html','templates/cv-content.json','scripts/build.py','requirements.txt']:
            file=folder/name
            file.write_bytes(file.read_text(encoding='utf-8').replace('\n','\r\n').encode('utf-8'))
        self.assertFalse(build.build(folder,'2027-01-04'))

    def test_H_non_publication_content_and_searchable_pdf(self):
        pages,checks=build.check_cv(ROOT/'assets/CV/Mingqiang_Liang_CV.pdf',self.database,pub.read_json(ROOT/'templates/cv-content.json'))
        self.assertGreater(checks,60)
        self.assertGreaterEqual(pages,3)

    def test_I_CSS_and_unrelated_content_unchanged(self):
        original=(ROOT/'tests/fixtures/original-index.html').read_text(encoding='utf-8')
        template=(ROOT/'templates/index.html').read_text(encoding='utf-8')
        self.assertEqual(re.search(r'<style>.*?</style>',original,re.S).group(),re.search(r'<style>.*?</style>',template,re.S).group())
        for start,end in [('<main id="home"','<section id="publications"'),('<section id="contact"','</main>')]:
            self.assertEqual(original[original.index(start):original.index(end)],template[template.index(start):template.index(end)])

    def test_I_all_local_links_exist_and_original_assets_kept(self):
        class Links(HTMLParser):
            links=[]
            def handle_starttag(self,tag,attrs):
                for k,v in attrs:
                    if k in ('href','src'): self.links.append(v)
        parser=Links()
        parser.feed((ROOT/'index.html').read_text(encoding='utf-8'))
        for link in parser.links:
            if link.startswith(('#','https:','http:','mailto:')): continue
            self.assertTrue((ROOT/urllib.parse.unquote(link)).is_file(),link)

    def test_J_timezone_dispatch_permissions_and_deployment_gates(self):
        import yaml
        workflow=yaml.load((ROOT/'.github/workflows/update-publications.yml').read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
        self.assertEqual(workflow['on']['schedule'],[{'cron':'17 9 * * 1','timezone':'Europe/Brussels'}])
        self.assertIn('workflow_dispatch',workflow['on'])
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        deploy=workflow['jobs']['deploy']
        self.assertIn("needs.prepare.outputs.publish == 'true'",deploy['if'])
        self.assertEqual(deploy['permissions'],{'contents':'write','pages':'write','id-token':'write'})
        steps=deploy['steps']
        deploy_index=next(i for i,s in enumerate(steps) if s.get('id')=='deployment')
        commit_index=next(i for i,s in enumerate(steps) if s.get('name')=='Commit only after successful publication')
        self.assertLess(deploy_index,commit_index)
        for job in workflow['jobs'].values():
            for step in job['steps']:
                if 'uses' in step: self.assertRegex(step['uses'],r'@[0-9a-f]{40}$')

    def test_preprint_and_retraction_not_new_journal_articles(self):
        for kind in ['posted-content','proceedings-article']:
            work=example()
            work['type']=kind
            new,pending,_=pub.reconcile(self.database,{work['DOI']:{'orcid':True}},{work['DOI']:work})
            self.assertEqual(new,self.database)
            self.assertTrue(pending)

    def test_publication_type_and_author_date_validation(self):
        for mutate in [lambda w:w.update(author=[]),lambda w:w.update(title=[]),lambda w:w.update(published={'date-parts':[[2025,13,1]]})]:
            work=example()
            mutate(work)
            with self.assertRaises((ValueError,IndexError)): pub.metadata(work)

    def test_duplicate_database_and_empty_database_rejected(self):
        for bad in [{'schema_version':1,'records':[]},{**self.database,'records':self.database['records']+[self.database['records'][0]]}]:
            with self.assertRaises(ValueError): pub.validate(bad)

    def test_generated_site_does_not_expose_internal_files(self):
        folder=self.sandbox()
        shutil.copyfile(ROOT/'index.html',folder/'index.html')
        shutil.copytree(ROOT/'assets/CV',folder/'assets/CV')
        build.stage_site(folder,folder/'_site')
        self.assertFalse((folder/'_site/data').exists())
        self.assertFalse((folder/'_site/templates').exists())
        self.assertTrue((folder/'_site/assets/CV/Mingqiang_Liang_CV.pdf').exists())


if __name__=='__main__':
    unittest.main()
