from types import SimpleNamespace
import pytest
from bookharbor import providers as p


def test_reject_unsafe_download_host_and_path():
    assert p.allowed_url('https://www.gutenberg.org/ebooks/1.epub', 'gutenberg')
    assert p.allowed_url('https://ia800301.us.archive.org/download/abc/a.pdf', 'archive')
    assert not p.allowed_url('https://evil.org/book.epub', 'archive')
    assert not p.allowed_url('http://localhost:8765/file.pdf', 'archive')
    assert not p.allowed_url('https://archive.org.evil.org/a.pdf', 'archive')
    assert not p.allowed_url('https://archive.org:443/a.pdf', 'archive')
    assert not p.safe_file_name('../a.epub')
    assert not p.safe_file_name('dir/../a.epub')
    assert p.safe_file_name('safe name.pdf')
    assert not p.safe_identifier('file/../../secrets')


def test_gutenberg_formats_and_titles(monkeypatch):
    monkeypatch.setattr(p, 'get_json', lambda *a, **k: {'results': [{
        'id': 1342, 'title': 'Pride and Prejudice', 'authors':[{'name':'Austen, Jane'}],
        'formats': {'application/epub+zip': 'https://www.gutenberg.org/ebooks/1342.epub3.images',
                    'application/pdf': 'https://elsewhere.org/file.pdf',
                    'text/plain; charset=utf-8': 'https://www.gutenberg.org/ebooks/1342.txt.utf-8'}
    }]})
    books = p.search_gutenberg('pride')
    assert books[0]['title'] == 'Pride and Prejudice'
    assert sorted(books[0]['formats']) == ['epub', 'txt']


def test_archive_skip_private_and_lending(monkeypatch):
    data = {'metadata': {'title': 'Some Book'}, 'files': [
        {'name': 'some_book.pdf', 'size': '1500'},
        {'name': 'some_book.epub', 'private': 'true'},
        {'name': 'no_access.zip', 'size': '2000'},
        {'name': '../escape.pdf'}
    ]}
    monkeypatch.setattr(p, 'get_json', lambda *a, **k: data)
    assert list(p.archive_formats('some_book')) == ['pdf']
    data['metadata']['lending___status'] = 'LENDABLE'
    assert p.archive_formats('some_book') == {}
    data['metadata'] = {'is_restricted': 'true'}
    assert p.archive_formats('some_book') == {}
    data['metadata'] = {}
    data['files'] = [{'name':'big.epub','size':str(p.MAX_FILE_BYTES+1)}]
    assert p.archive_formats('some_book') == {}


def test_openlibrary_public_only(monkeypatch):
    monkeypatch.setattr(p, 'get_json', lambda *a, **k: {'docs': [
       {'key':'/works/OL3W','title':'Yes', 'author_name':['A'], 'ebook_access':'public', 'ia':['public_scan']},
       {'key':'/works/OL4W','title':'No', 'ebook_access':'borrowable', 'ia':['borrowed_scan']}
    ]})
    books = p.search_openlibrary('test')
    assert len(books) == 1 and books[0]['id'] == 'public_scan'


def test_standard_recent_atom(monkeypatch):
    xml = b'''<feed xmlns="http://www.w3.org/2005/Atom">
    <entry><title>Example Book</title><author><name>Jane Writer</name></author>
    <link href="https://standardebooks.org/ebooks/jane/book" rel="alternate" type="text/html"/>
    <link href="https://standardebooks.org/downloads/book.epub" rel="enclosure" type="application/epub+zip"/>
    </entry></feed>'''
    class Response:
        content = xml
        def raise_for_status(self): pass
    monkeypatch.setattr(p.requests, 'get', lambda *a, **k: Response())
    books = p.search_standard('example')
    assert len(books)==1 and 'epub' in books[0]['formats']
    assert p.search_standard('another') == []


def test_preferred_format():
    formats = {'pdf':'a', 'epub':'b'}
    assert p.preferred_format(formats, 'auto') == ('epub','b')
    assert p.preferred_format(formats, 'pdf') == ('pdf','a')


def test_oapen_public_bitstream_and_language(monkeypatch):
    data = [{
        'type': 'item', 'name': 'Open Academic Book', 'handle': '20.500.12657/25312',
        'metadata': [
            {'key': 'dc.title', 'value': 'Open Academic Book'},
            {'key': 'dc.contributor.author', 'value': 'Academic Researcher'},
            {'key': 'dc.language.iso', 'value': 'eng'},
            {'key': 'dc.date.issued', 'value': '2021-03-01'}],
        'bitstreams': [
            {'bundleName': 'ORIGINAL', 'name': 'research.pdf', 'mimeType': 'application/pdf',
             'retrieveLink': '/bitstream/handle/20.500.12657/25312/research.pdf', 'sizeBytes': 12000},
            {'bundleName': 'LICENSE', 'name': 'license.txt', 'mimeType': 'text/plain',
             'retrieveLink': '/bitstream/handle/20.500.12657/25312/license.txt'},
            {'bundleName': 'ORIGINAL', 'name': 'offsite.epub', 'mimeType': 'application/epub+zip',
             'retrieveLink': 'https://untrusted.invalid/offsite.epub'}
        ]}]
    monkeypatch.setattr(p, 'get_json', lambda *args, **kwargs: data)
    found = p.search_oapen('open academic', 'en')
    assert found[0]['author'] == 'Academic Researcher'
    assert found[0]['year'] == '2021'
    assert list(found[0]['formats']) == ['pdf']
    assert p.search_oapen('open academic', 'el') == []
    assert p.allowed_url(found[0]['formats']['pdf'], 'oapen')
    assert not p.allowed_url('https://library.oapen.org.evil.invalid/file.pdf', 'oapen')


def test_gutenberg_falls_back_to_official_opds(monkeypatch):
    xml = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/terms/">
    <entry>
    <id>https://www.gutenberg.org/ebooks/1342</id>
    <title>Pride and Prejudice</title><author><name>Austen, Jane</name></author>
    <dc:language>en</dc:language>
    <link href="/ebooks/1342.epub3.images" rel="http://opds-spec.org/acquisition" type="application/epub+zip"/>
    <link href="https://untrusted.invalid/steal.pdf" rel="http://opds-spec.org/acquisition" type="application/pdf"/>
    <link href="/ebooks/1342.txt.utf-8" rel="http://opds-spec.org/acquisition/borrow" type="text/plain"/>
    </entry></feed>'''
    class Response:
        content = xml
        def raise_for_status(self): pass
    def fails(*a, **k):
        raise p.CatalogError('Gutendex service unavailable')
    monkeypatch.setattr(p, 'get_json', fails)
    monkeypatch.setattr(p.requests, 'get', lambda *a, **k: Response())
    books = p.search_gutenberg('pride', 'en')
    assert len(books) == 1
    assert books[0]['id'] == '1342'
    assert sorted(books[0]['formats']) == ['epub']
    assert books[0]['source'] == 'gutenberg'


def test_opds_malformed_response_is_error(monkeypatch):
    class Response:
        content = b'<html>This is an error page</html>'
        def raise_for_status(self): pass
    monkeypatch.setattr(p.requests, 'get', lambda *a, **k: Response())
    with pytest.raises(p.CatalogError):
        p.search_gutenberg_opds('test')


def test_openlibrary_sends_public_scan_filter(monkeypatch):
    def fake(url, *, params=None):
        assert url.endswith('search.json')
        assert params['public_scan'] == 'true'
        return {'docs': []}
    monkeypatch.setattr(p, 'get_json', fake)
    assert p.search_openlibrary('alice') == []


def test_oapen_oai_fallback_labels_partial_discovery(monkeypatch):
    p._oapen_oai_recent_records.cache_clear()
    xml = b'''<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
      <ListRecords><record><header><identifier>oai:library.oapen.org:20.500.12657/60001</identifier></header>
      <metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
        xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>Open Philosophy</dc:title><dc:creator>Researcher</dc:creator>
        <dc:language>eng</dc:language>
        <dc:subject>Philosophy</dc:subject>
        <dc:identifier>https://library.oapen.org/handle/20.500.12657/60001</dc:identifier>
      </oai_dc:dc></metadata></record></ListRecords></OAI-PMH>'''
    class Response:
        content = xml
        def raise_for_status(self): pass
    def blocked(*a, **k):
        raise p.CatalogError('403 OAPEN REST restricted')
    monkeypatch.setattr(p, 'get_json', blocked)
    monkeypatch.setattr(p.requests, 'get', lambda *a, **k: Response())
    result = p.search_oapen('philosophy', 'en')
    assert len(result) == 1
    assert result[0]['id'] == '20.500.12657/60001'
    assert result[0]['source'] == 'oapen'
    assert result[0]['formats'] == {}
    assert 'sample' in result[0]['access']
    p._oapen_oai_recent_records.cache_clear()


def test_archive_mirror_urls_are_metadata_approved(monkeypatch):
    identifier = 'public_book'
    canonical = 'https://archive.org/download/public_book/book.pdf'
    md = {'metadata': {'title': 'Public Book'},
          'files': [{'name': 'book.pdf', 'size': '1024'}],
          'dir': '/12/items/public_book',
          'd1': 'ia600308.us.archive.org',
          'd2': 'ia800308.us.archive.org'}
    monkeypatch.setattr(p, 'get_json', lambda *a, **kw: md)
    urls = p.archive_mirror_urls(identifier, canonical)
    assert len(urls) == 2
    assert urls[0] == 'https://ia600308.us.archive.org/12/items/public_book/book.pdf'
    md['metadata']['lending___status'] = 'LENDABLE'
    assert p.archive_mirror_urls(identifier, canonical) == []
    md['metadata'] = {}
    md['dir'] = '/12/items/../private_book'
    assert p.archive_mirror_urls(identifier, canonical) == []
    md['dir'] = '/12/items/public_book'
    md['d1'] = 'internal.evil.invalid'
    urls = p.archive_mirror_urls(identifier, canonical)
    assert len(urls) == 1
