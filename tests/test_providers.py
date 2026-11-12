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
