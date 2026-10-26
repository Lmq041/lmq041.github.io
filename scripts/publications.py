"""Conservative public-metadata ingestion. No ResearchGate requests or PDF uploads."""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ORCID = '0000-0003-3348-135X'
OPENALEX = 'https://openalex.org/A5103046078'
DOI_RE = re.compile(r'^10\.\d{4,9}/\S+$', re.I)


class SourceError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def doi(value):
    value = str(value or '').strip().lower()
    value = re.sub(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', '', value)
    return value if DOI_RE.fullmatch(value) else None


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if c.isalnum())


def own_author(author):
    return (normalized(author.get('family', '')) == 'liang'
            and normalized(author.get('given', '')) in {'mingqiang', 'mq', 'm'})


def effective(record):
    return {**record['metadata'], **record.get('manual', {}), 'id': record['id'], 'doi': record['doi']}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n', dir=path.parent, delete=False) as f:
        f.write(content)
        tmp = Path(f.name)
    os.replace(tmp, path)
    return True


class Client:
    def __init__(self, direct=False):
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if direct else urllib.request.build_opener()

    def get(self, url, token=None):
        headers = {'Accept': 'application/json', 'User-Agent': 'LiangAcademicHomepage/1.0 (mailto:lmq041@gmail.com)'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        for attempt in range(3):
            try:
                with self.opener.open(urllib.request.Request(url, headers=headers), timeout=25) as response:
                    raw = response.read(20_000_001)
                if len(raw) > 20_000_000:
                    raise ValueError('response exceeds size limit')
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError('expected JSON object')
                return obj
            except (OSError, ValueError, TimeoutError) as exc:
                retryable = not isinstance(exc, urllib.error.HTTPError) or exc.code in {429, 500, 502, 503, 504}
                if attempt == 2 or not retryable:
                    # Do not log URLs: OpenAlex credentials can be in query parameters.
                    status = getattr(exc, 'code', None)
                    raise SourceError(f'{urllib.parse.urlsplit(url).hostname}: {type(exc).__name__}' + (f' HTTP {status}' if status else ''), status=status) from exc
                time.sleep(min(2 ** attempt, 4))


def collect(client):
    evidence = {}
    notices = []
    orcid = client.get(f'https://pub.orcid.org/v3.0/{ORCID}/works', os.getenv('ORCID_READ_PUBLIC_TOKEN'))
    if not isinstance(orcid.get('group'), list):
        raise SourceError('ORCID works schema missing group')
    for group in orcid['group']:
        summaries = group.get('work-summary', [])
        identifiers = group.get('external-ids', {}).get('external-id', [])
        for summary in summaries:
            identifiers += summary.get('external-ids', {}).get('external-id', [])
        found = False
        for identifier in identifiers:
            if identifier.get('external-id-type') == 'doi' and identifier.get('external-id-relationship') == 'self':
                d = doi(identifier.get('external-id-value'))
                if d:
                    found = True
                    evidence.setdefault(d, {})['orcid'] = True
                else:
                    notices.append({'reason': 'malformed ORCID DOI', 'value': identifier.get('external-id-value')})
        if not found and summaries:
            summary = summaries[0]
            notices.append({'id': 'orcid-put-code:' + str(summary.get('put-code')), 'title': summary.get('title', {}).get('title', {}).get('value', ''), 'reason': 'ORCID work without a usable self DOI; manual review only'})

    key = os.getenv('OPENALEX_API_KEY')
    suffix = ('?api_key=' + urllib.parse.quote(key)) if key else ''
    author = client.get(f'https://api.openalex.org/authors/https://orcid.org/{ORCID}' + suffix)
    if author.get('id') != OPENALEX or str(author.get('orcid', '')).rstrip('/').split('/')[-1] != ORCID:
        raise SourceError('OpenAlex author identity changed; manual review required')
    cursor = '*'
    seen = set()
    while cursor:
        if cursor in seen or len(seen) >= 100:
            raise SourceError('OpenAlex pagination loop/limit')
        seen.add(cursor)
        params = {'filter': 'authorships.author.id:' + OPENALEX.split('/')[-1], 'per-page': 200, 'cursor': cursor}
        if key:
            params['api_key'] = key
        page = client.get('https://api.openalex.org/works?' + urllib.parse.urlencode(params))
        if not isinstance(page.get('results'), list) or 'meta' not in page:
            raise SourceError('OpenAlex works schema')
        for work in page['results']:
            d = doi(work.get('doi'))
            matches = [a for a in work.get('authorships', []) if a.get('author', {}).get('id') == OPENALEX]
            if d and len(matches) == 1:
                evidence.setdefault(d, {})['openalex'] = {
                    'title': work.get('title', ''),
                    'orcid': matches[0]['author'].get('orcid'),
                    'name': matches[0]['author'].get('display_name', ''),
                    'is_retracted': work.get('is_retracted', False),
                }
            elif work.get('id'):
                notices.append({'id': work['id'], 'reason': 'no DOI or ambiguous OpenAlex authorship'})
        cursor = page['meta'].get('next_cursor') if page['results'] else None

    cursor = '*'
    seen = set()
    while cursor:
        if cursor in seen or len(seen) >= 100:
            raise SourceError('Crossref pagination loop/limit')
        seen.add(cursor)
        params = {'filter': 'orcid:' + ORCID, 'rows': 100, 'cursor': cursor, 'mailto': 'lmq041@gmail.com'}
        page = client.get('https://api.crossref.org/works?' + urllib.parse.urlencode(params)).get('message', {})
        if not isinstance(page.get('items'), list):
            raise SourceError('Crossref search schema')
        for work in page['items']:
            d = doi(work.get('DOI'))
            if d:
                evidence.setdefault(d, {})['crossref_search'] = True
        cursor = page.get('next-cursor') if len(page['items']) == 100 else None
    return evidence, notices


def metadata(work):
    d = doi(work.get('DOI'))
    titles, journals, authors = work.get('title'), work.get('container-title'), work.get('author')
    if not d or not isinstance(titles, list) or not titles or not isinstance(authors, list) or not authors:
        raise ValueError('incomplete Crossref metadata')
    if not all(isinstance(a, dict) and a.get('family') and a.get('given') for a in authors):
        raise ValueError('incomplete author list')
    publication_type = work.get('type')
    if publication_type == 'journal-article' and (not journals or not isinstance(journals, list)):
        raise ValueError('journal missing')
    parts = work.get('published', {}).get('date-parts', [[]])[0]
    if not parts or not 1800 <= int(parts[0]) <= date.today().year + 1:
        raise ValueError('invalid publication date')
    pd = '-'.join([str(parts[0])] + [f'{int(x):02}' for x in parts[1:]])
    date.fromisoformat(pd + ('-01' * (3 - len(parts))))
    title = ' '.join(str(titles[0]).split())
    if '<' in title or '\ufffd' in title:
        raise ValueError('invalid title')
    return {
        'title': title, 'authors': [{k: a[k] for k in ('given', 'family', 'ORCID') if k in a} for a in authors],
        'journal': journals[0] if journals else 'Preprint', 'year': int(parts[0]),
        'volume': work.get('volume', ''), 'issue': work.get('issue', ''),
        'pages': work.get('page', ''), 'article_number': work.get('article-number', ''),
        'publication_date': pd, 'publication_type': publication_type,
        'online_url': 'https://doi.org/' + d, 'local_pdf': None, 'keywords': [],
        'my_author_position': next((i + 1 for i, a in enumerate(authors) if own_author(a)), None),
        'co_first_author': False, 'corresponding_author': False, 'contribution_note': '',
        'show_on_homepage': True, 'show_in_cv': True,
        'verification_status': 'verified', 'metadata_source': ['Crossref'],
    }


def reconcile(database, evidence, works):
    updated = copy.deepcopy(database)
    by_doi = {r['doi']: r for r in updated['records']}
    pending = {}
    events = []
    for d in sorted(evidence):
        ev = evidence[d]
        work = works[d]
        try:
            item = metadata(work)
            if doi(work.get('DOI')) != d:
                raise ValueError('Crossref DOI mismatch')
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            pending[d] = {'doi': d, 'reason': str(exc)}
            continue
        own = [a for a in item['authors'] if own_author(a)]
        existing = by_doi.get(d)
        orcid_authors = [a for a in item['authors'] if str(a.get('ORCID', '')).split('/')[-1] == ORCID]
        wrong_orcid = any(a.get('ORCID') and str(a['ORCID']).split('/')[-1] != ORCID for a in own)
        oa = ev.get('openalex', {})
        oa_identity = (str(oa.get('orcid', '')).split('/')[-1] == ORCID
                       and normalized(oa.get('name')) == 'mingqiangliang'
                       and normalized(oa.get('title')) == normalized(item['title'])
                       and len(own) == 1 and normalized(own[0]['given']) == 'mingqiang')
        confirmed = existing and effective(existing).get('verification_status') in {'manually-confirmed', 'legacy-confirmed'}
        identity = len(own) == 1 and not wrong_orcid and (ev.get('orcid') or len(orcid_authors) == 1 or oa_identity or confirmed)
        reason = None
        if not identity:
            reason = 'identity uncertain/conflicting; name alone is insufficient'
        elif item['publication_type'] != 'journal-article':
            reason = 'not a formal journal article; preserved for review'
        elif work.get('update-to') or oa.get('is_retracted'):
            reason = 'correction/retraction evidence; manual review'
        elif oa.get('title') and normalized(oa['title']) != normalized(item['title']):
            reason = 'OpenAlex/Crossref title disagreement; manual review'
        elif (item['publication_date'] + '-01-01')[:10] > date.today().isoformat():
            # Future print dates are allowed only if an online publication date is already available.
            online = work.get('published-online', {}).get('date-parts', [[]])[0]
            if not online or date(*((online + [1, 1])[:3])) > date.today():
                reason = 'future publication without confirmed online date'
        if existing:
            old = effective(existing)
            # Significant conflicts never replace existing confirmed authors/titles.
            if normalized(old['title']) != normalized(item['title']) or [normalized(a['family'] + a['given']) for a in old['authors']] != [normalized(a['family'] + a['given']) for a in item['authors']]:
                reason = 'bibliographic conflict with existing confirmed record'
            if reason:
                pending[d] = {'doi': d, 'reason': reason}
                events.append({'doi': d, 'action': 'preserved', 'reason': reason})
                continue
            for field in ('volume', 'issue', 'pages', 'article_number', 'publication_date', 'journal', 'year'):
                if item[field] and field not in existing.get('manual', {}):
                    existing['metadata'][field] = item[field]
            events.append({'doi': d, 'action': 'checked'})
        elif reason:
            pending[d] = {'doi': d, 'title': item['title'], 'reason': reason}
        else:
            item['metadata_source'] = sorted(['Crossref'] + (['ORCID'] if ev.get('orcid') else []) + (['OpenAlex'] if oa else []))
            record = {'id': 'doi:' + d, 'doi': d, 'metadata': item, 'manual': {}}
            updated['records'].append(record)
            by_doi[d] = record
            events.append({'doi': d, 'action': 'added', 'evidence': item['metadata_source']})
    updated['records'].sort(key=lambda r: r['doi'])
    validate(updated)
    return updated, list(pending.values()), events


def validate(database):
    if database.get('schema_version') != 1 or not database.get('records'):
        raise ValueError('invalid/empty database')
    identifiers, dois = set(), set()
    for record in database['records']:
        d = doi(record.get('doi'))
        if not d or d != record['doi'] or d in dois or record['id'] in identifiers:
            raise ValueError('duplicate or invalid DOI/id')
        dois.add(d)
        identifiers.add(record['id'])
        p = effective(record)
        for field in ('title', 'authors', 'journal', 'year', 'publication_date', 'verification_status'):
            if not p.get(field):
                raise ValueError('missing ' + field)
        position = p.get('my_author_position')
        if not isinstance(p['authors'], list) or not all(isinstance(a, dict) and a.get('family') and a.get('given') for a in p['authors']):
            raise ValueError('invalid author list')
        if not isinstance(position, int) or not 1 <= position <= len(p['authors']):
            raise ValueError('invalid author position')
        if not own_author(p['authors'][position - 1]):
            raise ValueError('author position does not identify the owner')
        for flag in ('co_first_author', 'corresponding_author', 'show_on_homepage', 'show_in_cv'):
            if not isinstance(p.get(flag), bool):
                raise ValueError('invalid boolean: ' + flag)
        if not isinstance(p.get('keywords'), list) or not all(isinstance(k, str) for k in p['keywords']):
            raise ValueError('invalid keywords')
        pd = p['publication_date']
        if not re.fullmatch(r'\d{4}(-\d{2}){0,2}', pd):
            raise ValueError('invalid date precision')
        date.fromisoformat(pd + '-01' * (2 - pd.count('-')))
        if p.get('local_pdf'):
            path = Path(p['local_pdf'])
            if path.is_absolute() or '..' in path.parts or not str(path).replace('\\', '/').startswith('assets/papers/'):
                raise ValueError('unsafe local PDF path')
        if p.get('online_url') != 'https://doi.org/' + d:
            raise ValueError('unexpected online URL')


def sync(database, client):
    validate(database)
    evidence, notices = collect(client)
    # Existing records are refreshed even when absent from a provider; absence never deletes.
    for record in database['records']:
        evidence.setdefault(record['doi'], {})
    works = {}
    for d in sorted(evidence):
        try:
            response = client.get('https://api.crossref.org/works/' + urllib.parse.quote(d, safe='/'))
        except SourceError as exc:
            if exc.status != 404:
                raise
            # Unregistered/DataCite DOI: retain candidate for review, never drop an existing record.
            works[d] = {}
            continue
        if not isinstance(response.get('message'), dict):
            raise SourceError('Crossref work schema')
        works[d] = response['message']
    new, pending, events = reconcile(database, evidence, works)
    review = {json.dumps(item, ensure_ascii=False, sort_keys=True): item for item in pending + notices}
    return new, [review[k] for k in sorted(review)], events
