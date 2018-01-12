import pytest
from os_urlpattern.urlparse_utils import filter_useless_part
from os_urlpattern.urlparse_utils import analyze_url
from os_urlpattern.urlparse_utils import parse_url
from os_urlpattern.urlparse_utils import parse_query_string
from os_urlpattern.exceptions import IrregularURLException
from os_urlpattern.urlparse_utils import normalize_str
from os_urlpattern.urlparse_utils import PieceParser
from os_urlpattern.urlparse_utils import pack


def test_normalize_str():
    data = [
        ('a', 'a'),
        ('ab=', 'ab[=]'),
        ('ab1=a', 'ab1[=]a'),
        ('ab==a', 'ab[=]{2}a'),
        ('ab=={a', 'ab[=]{2}[\\{]a'),
        ('=', '[=]'),
        ('==', '[=]{2}'),
        ('==+a', '[=]{2}[\\+]a'),
        ('\\', '[\\\\]'),
    ]
    for i, j in data:
        assert normalize_str(i) == j


def test_parse_url():
    data = [
        ('http://www.test.com/', [''], [('query_depth', 0)]),
        ('http://www.test.com/?', ['', ''], [('query_depth', 1)]),
        ('http://www.test.com/abc/def?k=v#xxx', ['abc', 'def', 'v', 'xxx'], [
         ('query_depth', 1), ('has_fragment', True), ('depths', (2, 1, 1))]),
    ]
    for url, p, m in data:
        url_meta, parts = parse_url(url)
        assert parts == p
        for k, v in m:
            assert getattr(url_meta, k) == v
    with pytest.raises(AssertionError):
        parse_url('http://www.g.com')


def test_parse_query_string():
    data = [
        ('a', [''], ['a']),
        ('a=', ['a='], ['']),
        ('a&b', ['a', 'b'], ['', '']),
        ('a=1', ['a='], ['1']),
        ('a=1&b=2', ['a=', 'b='], ['1', '2']),
    ]
    for q, k, v in data:
        assert parse_query_string(q) == (k, v)

    data = ['a&', 'a&&b']

    for i in data:
        with pytest.raises(IrregularURLException):
            parse_query_string(i)

    with pytest.raises(AssertionError):
        parse_query_string('')


def test_analyze_url():
    data = [
        ['http://www.g.com/test', ('path', '/test'),
         ('blank_query', False), ('blank_fragment', False)],
        ['http://www.g.com/test?',
            ('blank_query', True), ('blank_fragment', False)],
        ['http://www.g.com/test?#',
            ('blank_query', True), ('blank_fragment', True)],
        ['http://www.g.com/test?a#',
            ('blank_query', False), ('blank_fragment', True)],
        ['http://www.g.com/test?a##',
            ('blank_query', False), ('blank_fragment', False)],
        ['http://www.g.com/test#?',
            ('blank_query', False), ('blank_fragment', False)],
    ]
    for check in data:
        url = check[0]
        r = analyze_url(url)
        for attr, expect in check[1:]:
            assert getattr(r, attr) == expect


def test_filter_useless_part():
    data = [
        ('/', ['']),
        ('//', ['']),
        ('', ['']),
        ('/a/b', ['a', 'b']),
        ('/a/b/', ['a', 'b', '']),
        ('/a/b//', ['a', 'b', '']),
        ('/a/b///c', ['a', 'b', 'c']),
        ('a/b///c', ['a', 'b', 'c']),
    ]
    for s, expect in data:
        assert filter_useless_part(s.split('/')) == expect


def test_piece_parser():
    parser = PieceParser()
    data = [
        ('abc', ['abc', ], ['a-z', ]),
        ('abc.exe', ['abc', '[\\.]', 'exe'], ['a-z', '\\.', 'a-z']),
        ('%' * 10, ['[%]{10}', ], ['%', ]),
        ('abc1D..exe',  ['abc', '1', 'D',
                         '[\\.]{2}', 'exe'], ['a-z', '0-9', 'A-Z', '\\.', 'a-z']),
        ('@<>..', ['[@]', '[<]', '[>]', '[\\.]{2}'], ['@', '<', '>', '\\.']),
    ]
    for piece, expected_pieces, expected_rules in data:
        parsed = parser.parse(piece)
        assert parsed.rules == expected_rules
        assert parsed.pieces == expected_pieces
        assert parsed.piece_length == len(piece)


def test_unpack_pack():
    data = [
        ('http://www.g.com/', '/'),
        ('http://www.g.com/abc', '/abc'),
        ('http://www.g.com/abc?a=1#c', '/abc[\\?]a=1#c'),
        ('http://www.g.com/abc???a=1#c', '/abc[\\?][\\?]{2}a=1#c'),
        ('http://www.g.com/abc?=1#c', '/abc[\\?]=1#c'),
        ('http://www.g.com/abc?a=1#', '/abc[\\?]a=1#'),
        ('http://www.g.com/abc?a=1&b=2#', '/abc[\\?]a=1&b=2#'),
    ]
    for url, expected in data:
        assert pack(*parse_url(url)) == expected
