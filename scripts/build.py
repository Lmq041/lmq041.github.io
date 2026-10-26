"""Deterministic static HTML and searchable, complete CV from one publication database."""
from __future__ import annotations
import argparse
import hashlib
import html
import io
import json
import os
import re
import shutil
import tempfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from publications import effective, read_json, validate, write_json


def ordered(database, flag):
    return sorted([effective(r) for r in database['records'] if effective(r).get(flag)],
                  key=lambda p: (p['publication_date'], p['doi']), reverse=True)


def short_name(author):
    given = author['given']
    initials = '-'.join(''.join(p[0] + '.' for p in group.split() if p) for group in given.split('-'))
    return author['family'] + ', ' + initials


def author_text(p, cv=False):
    names = []
    for i, author in enumerate(p['authors'], 1):
        name = html.escape(short_name(author))
        if i == p['my_author_position']:
            if cv:
                marks = ('†' if p.get('co_first_author') else '') + ('*' if p.get('corresponding_author') else '')
                name = '<b>' + name + '</b>' + ('<super>' + marks + '</super>' if marks else '')
            else:
                note = p.get('contribution_note') or ('co-first author' if p.get('co_first_author') else 'Corresponding author' if p.get('corresponding_author') else '')
                name = '<strong>' + name + (' (' + html.escape(note) + ')' if note else '') + '</strong>'
        names.append(name)
    return ', '.join(names)


def cards(database):
    rendered = []
    for p in ordered(database, 'show_on_homepage'):
        links = []
        if p.get('local_pdf'):
            links.append(f'<a href="{html.escape(p["local_pdf"], quote=True)}" target="_blank" rel="noopener">PDF</a>')
        links.append(f'<a href="{html.escape(p["online_url"], quote=True)}" target="_blank" rel="noopener">Article Online</a>')
        keywords = '              <div class="pub-meta">Keywords: ' + html.escape(', '.join(p.get('keywords', []))) + '</div>\n' if p.get('keywords') else ''
        rendered.append(f'''            <article class="pub-card">
              {author_text(p)} ({p['year']}). {html.escape(p['title'])}. <em>{html.escape(p['journal'])}</em>.
{keywords}              <div class="pub-links">{' '.join(links)}</div>
            </article>''')
    return '\n\n'.join(rendered)


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = TextOnly()
    parser.feed(value)
    return ''.join(parser.parts)


def create_cv(database, content, destination):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    fonts = Path(__file__).resolve().parents[1] / 'templates/fonts'
    for suffix, file in [('', 'DejaVuSerif.ttf'), ('-Bold', 'DejaVuSerif-Bold.ttf'), ('-Italic', 'DejaVuSerif-Italic.ttf'), ('-BoldItalic', 'DejaVuSerif-BoldItalic.ttf')]:
        pdfmetrics.registerFont(TTFont('CV' + suffix, str(fonts / file)))
    pdfmetrics.registerFontFamily('CV', normal='CV', bold='CV-Bold', italic='CV-Italic', boldItalic='CV-BoldItalic')
    body = ParagraphStyle('Body', fontName='CV', fontSize=9, leading=12.5, spaceAfter=4)
    heading = ParagraphStyle('Heading', parent=body, fontName='CV-Bold', textColor=colors.HexColor('#bd0000'), fontSize=10.5, spaceBefore=10, spaceAfter=5, keepWithNext=True)
    subheading = ParagraphStyle('Subheading', parent=body, fontName='CV-Bold', spaceBefore=5, keepWithNext=True)
    center = ParagraphStyle('Center', parent=body, alignment=TA_CENTER, spaceAfter=3)
    title = ParagraphStyle('Title', parent=center, fontName='CV-Bold', fontSize=18, leading=23, textColor=colors.HexColor('#bd0000'), spaceAfter=8)
    story = [Paragraph(html.escape(content['name']), title)]
    story += [Paragraph(line, center) for line in content['header']]
    story.append(Spacer(1, 8))

    def section(section, level=0):
        story.append(Paragraph(html.escape(section['heading']), heading if level == 0 else subheading))
        for i, paragraph in enumerate(section.get('paragraphs', []), 1):
            story.append(Paragraph((f'[{i}] ' if section.get('numbered') else '') + paragraph, body))
        for sub in section.get('subsections', []):
            section_fn(sub, level + 1)
    section_fn = section
    for item in content['before_publications']:
        section(item)
    story.append(Paragraph('Publications', heading))
    story.append(Paragraph('† Co-first author; * Corresponding author. Author contribution designations are retained from the confirmed source.', body))
    if content.get('in_preparation'):
        story.append(Paragraph('In Preparation', subheading))
        story += [Paragraph(p, body) for p in content['in_preparation']]
    publications = ordered(database, 'show_in_cv')
    journals = [p for p in publications if p['publication_type'] == 'journal-article']
    other = [p for p in publications if p['publication_type'] != 'journal-article']
    for label, entries in [('Published Journal Articles', journals), ('Preprints and Other Existing Outputs', other)]:
        if not entries:
            continue
        prefix = [Paragraph(label, subheading)]
        year = None
        for i, p in enumerate(entries, 1):
            if p['year'] != year:
                year = p['year']
                prefix.append(Paragraph(str(year), subheading))
            publication = f"[{i}] {author_text(p, cv=True)} ({p['year']}). {html.escape(p['title'])}. <i>{html.escape(p['journal'])}</i>"
            volume = p.get('volume', '') + ('(' + p['issue'] + ')' if p.get('issue') else '')
            if volume:
                publication += ', ' + html.escape(volume)
            if p.get('article_number') or p.get('pages'):
                publication += ', ' + html.escape(p.get('article_number') or p['pages'])
            publication += f'. <link href="{html.escape(p["online_url"], quote=True)}" color="#145c9e">{html.escape(p["online_url"])}</link>'
            story.append(KeepTogether(prefix + [Paragraph(publication, body)]))
            prefix = []
    for item in content['after_publications']:
        section(item)

    def page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont('CV', 8)
        canvas.setFillColor(colors.HexColor('#777777'))
        canvas.drawRightString(A4[0] - 45, 25, str(doc.page))
        canvas.restoreState()

    document = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=45, rightMargin=45, topMargin=42, bottomMargin=42,
                                 title='Ming-Qiang Liang - Curriculum Vitae', author=content['name'], invariant=1, pageCompression=1)
    document.build(story, onFirstPage=page_number, onLaterPages=page_number)
    check_cv(destination, database, content)


def check_cv(path, database, content):
    from pypdf import PdfReader
    reader = PdfReader(path)
    text = ' '.join(page.extract_text() or '' for page in reader.pages)
    norm = lambda v: re.sub(r'\s+', '', v)
    expected = [content['name'], *[plain(line) for line in content['header']], *[plain(x) for x in content.get('in_preparation', [])]]
    def walk(section):
        expected.append(section['heading'])
        expected.extend(plain(line) for line in section.get('paragraphs', []))
        for sub in section.get('subsections', []):
            walk(sub)
    for section in content['before_publications'] + content['after_publications']:
        walk(section)
    for p in ordered(database, 'show_in_cv'):
        expected.extend([p['title'], p['online_url']])
    missing = [value for value in expected if norm(value) not in norm(text)]
    if missing or len(text) < 5000 or '\ufffd' in text or '\x00' in text:
        raise ValueError('CV completeness check failed: ' + str(missing))
    return len(reader.pages), len(expected)


def content_hash(root, database):
    # Operational provenance, API retrieval times and review queue do not rebuild public artifacts.
    fields = {'doi', 'title', 'authors', 'journal', 'year', 'volume', 'issue', 'pages', 'article_number',
              'publication_date', 'publication_type', 'online_url', 'local_pdf', 'keywords', 'my_author_position',
              'co_first_author', 'corresponding_author', 'contribution_note', 'show_on_homepage', 'show_in_cv'}
    public = [{k:v for k,v in effective(r).items() if k in fields} for r in database['records']
              if effective(r).get('show_in_cv') or effective(r).get('show_on_homepage')]
    public.sort(key=lambda p: p['doi'])
    digest = hashlib.sha256(json.dumps(public, sort_keys=True, ensure_ascii=False).encode())
    for file in ('templates/index.html', 'templates/cv-content.json', 'scripts/build.py', 'requirements.txt'):
        digest.update((root / file).read_text(encoding='utf-8').encode('utf-8'))
    for file in sorted((root / 'templates/fonts').glob('*.ttf')):
        digest.update(file.read_bytes())
    return digest.hexdigest()


def build(root, as_of=None):
    root = Path(root)
    database = read_json(root / 'data/publications.json')
    validate(database)
    content = read_json(root / 'templates/cv-content.json')
    state = read_json(root / 'data/build-state.json')
    digest = content_hash(root, database)
    pdf = root / 'assets/CV/Mingqiang_Liang_CV.pdf'
    if state.get('content_hash') == digest and pdf.exists() and (root / 'index.html').exists():
        print('No public content change; HTML, PDF and date untouched.')
        return False
    updated = date.fromisoformat(as_of) if as_of else date.today()
    text = (root / 'templates/index.html').read_text(encoding='utf-8')
    if text.count('<!-- PUBLICATIONS -->') != 1 or text.count('<!-- UPDATED -->') != 1:
        raise ValueError('template anchors missing/ambiguous')
    text = text.replace('<!-- PUBLICATIONS -->', cards(database))
    text = text.replace('<!-- UPDATED -->', f'© <span id="copyright-year">{updated.year}</span> Ming-Qiang Liang. Last updated: {updated.strftime("%B %Y")}.')
    # Generate and verify everything before replacing any public artifact.
    staged = root / 'work/build-staging'
    staged.mkdir(parents=True, exist_ok=True)
    create_cv(database, content, staged / 'cv.pdf')
    # The original repository stores index.html with CRLF; preserve it to keep the review focused.
    (staged / 'index.html').write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    pdf.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged / 'cv.pdf', pdf)
    os.replace(staged / 'index.html', root / 'index.html')
    write_json(root / 'data/build-state.json', {'schema_version':1,'content_hash':digest,'last_updated':updated.isoformat()})
    print(f'Generated homepage and complete CV for {updated.isoformat()}.')
    return True


def stage_site(root, destination):
    """Publish an explicit allowlist; internal source, logs and review queue stay out of Pages."""
    root, destination = Path(root), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / 'index.html', destination / 'index.html')
    shutil.copytree(root / 'assets', destination / 'assets', dirs_exist_ok=True)
    (destination / '.nojekyll').touch()
    if (root / 'CNAME').exists():
        shutil.copyfile(root / 'CNAME', destination / 'CNAME')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--date')
    parser.add_argument('--stage', type=Path)
    args = parser.parse_args()
    build(args.root, args.date)
    if args.stage:
        stage_site(args.root, args.stage)
