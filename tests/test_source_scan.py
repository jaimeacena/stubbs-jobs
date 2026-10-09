"""Synthetic listing pages; fetching is always replaced, never visits a board."""
import unittest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import scan_boards as scanner


class SourceScanTests(unittest.TestCase):
    def test_invalid_source_id_is_rejected_before_network_or_output_in_main(self):
        from personalization import blank_store
        store = blank_store()
        store['app']['setupComplete'] = True
        for identifier in ('../escaped', '..\\escaped', '/escaped', 'C:/escaped', 'CON', 'unsafe?.txt'):
            with self.subTest(identifier=identifier), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source = {'id': identifier, 'company': 'TEST source', 'kind': 'html',
                          'url': 'https://example.org/careers', 'enabled': True}
                with patch.object(scanner, 'ROOT', root), patch.object(scanner, 'configure_stdio'), \
                        patch('stubbs_jobs_core.read_store', return_value=store), \
                        patch('personalization.public_sources', return_value=[source]), \
                        patch.object(scanner, 'fetch') as transport, \
                        patch.object(sys, 'argv', ['scan_boards.py']):
                    with self.assertRaisesRegex(ValueError, 'identificador'):
                        scanner.main()
                    transport.assert_not_called()
                self.assertEqual(list(root.rglob('*')), [])

    def test_filtered_source_does_not_skip_validation_of_an_unsafe_configuration(self):
        from personalization import blank_store
        store = blank_store()
        store['app']['setupComplete'] = True
        safe = {'id': 'safe', 'company': 'TEST source', 'kind': 'html', 'url': 'https://example.org/careers'}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(scanner, 'ROOT', root), patch.object(scanner, 'configure_stdio'), \
                    patch('stubbs_jobs_core.read_store', return_value=store), \
                    patch('personalization.public_sources', return_value=[safe, dict(safe, id='../escaped')]), \
                    patch.object(scanner, 'fetch') as transport, \
                    patch.object(sys, 'argv', ['scan_boards.py', '--source', 'safe']):
                with self.assertRaisesRegex(ValueError, 'identificador'):
                    scanner.main()
                transport.assert_not_called()
            self.assertFalse((root / 'outputs').exists())

    def test_direct_scan_also_rejects_unsafe_source_before_transport(self):
        with patch.object(scanner, 'fetch') as transport:
            with self.assertRaisesRegex(ValueError, 'identificador'):
                scanner.scan({'id': '../escaped', 'company': 'TEST source', 'kind': 'html',
                              'url': 'https://example.org/careers'})
            transport.assert_not_called()

    def test_real_https_opener_keeps_tls_verification_with_a_simulated_transport(self):
        import email.message
        import io
        from urllib.request import build_opener, ProxyHandler, Request

        connections = []
        class Connection(scanner.PinnedHTTPSConnection):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                connections.append(self)

            def request(self, *args, **kwargs):
                pass  # The entire transport is synthetic; no socket is opened.

            def getresponse(self):
                response = io.BytesIO(b'{"jobs":[]}')
                response.status, response.code, response.reason = 200, 200, 'OK'
                response.headers = email.message.Message()
                response.info = lambda: response.headers
                return response

        with patch.object(scanner, 'PinnedHTTPSConnection', Connection):
            opener = build_opener(ProxyHandler({}), scanner.PublicHTTPSHandler())
            with opener.open(Request('https://example.org/jobs'), timeout=1) as response:
                self.assertEqual(response.read(), b'{"jobs":[]}')
        self.assertEqual(len(connections), 1)
        self.assertTrue(connections[0]._context.check_hostname)

    def scan(self, pages, url='https://example.org/careers'):
        with patch.object(scanner, 'CURRENT_SEARCH', {'targetRoles': 'Data Analyst', 'keywords': '', 'regions': ''}), \
                patch.object(scanner, 'fetch', side_effect=lambda link, *args: pages[link]) as fetch:
            result = scanner.scan({'id': 'test-source', 'company': 'TEST source', 'kind': 'html', 'url': url})
        return result, fetch

    def test_careers_page_pagination_is_followed_and_unproven_extent_is_partial(self):
        pages = {'https://example.org/careers': '<a href="/jobs/1">Data Analyst</a><a href="/careers?page=2">Siguiente</a>',
                 'https://example.org/careers?page=2': '<a href="/jobs/2">Data Analyst</a>'}
        result, fetch = self.scan(pages)
        self.assertEqual(result['totalPosts'], 2)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['coverage']['pages'], list(pages))
        self.assertEqual(result['coverage']['completeness'], 'partial')

    def test_numbered_careers_pagination_with_a_total_has_explicit_listing_scope(self):
        pages = {'https://example.org/careers': '<p>2 ofertas</p><a href="/jobs/1">Data Analyst</a><a href="?page=2">2</a>',
                 'https://example.org/careers?page=2': '<a href="/jobs/2">Data Analyst</a>'}
        result, _ = self.scan(pages)
        self.assertEqual((result['status'], result['totalPosts']), ('ok', 2))
        self.assertEqual(result['coverage']['completeness'], 'declared_count')
        self.assertIn('condiciones individuales pendientes', result['coverage']['scope'])

    def test_unhandled_pagination_is_not_a_clean_source_even_when_first_page_has_all_declared_links(self):
        pages = {'https://example.org/careers': '<p>1 vacantes</p><a href="/jobs/1">Data Analyst</a><a href="/other?page=2">Siguiente</a>'}
        result, fetch = self.scan(pages)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(any('paginación no comprobado' in item for item in result['errors']))

    def test_cross_site_next_and_scripted_more_are_partial_without_fetching_unsafe_links(self):
        for control in ('<a href="https://elsewhere.example/careers?page=2">Next</a>',
                        '<button>Load more</button>', '<a href="javascript:more()">Mostrar más</a>',
                        '<a>Ver más</a>'):
            with self.subTest(control=control):
                result, fetch = self.scan({'https://example.org/careers': '<p>1 ofertas</p><a href="/jobs/1">Data Analyst</a>' + control})
                self.assertEqual((result['status'], fetch.call_count), ('partial', 1))

    def test_rel_next_without_label_is_followed(self):
        pages = {'https://example.org/careers': '<link rel="next" href="?cursor=test"><p>2 ofertas</p><a href="/jobs/1">Data Analyst</a>',
                 'https://example.org/careers?cursor=test': '<a href="/jobs/2">Data Analyst</a>'}
        result, _ = self.scan(pages)
        self.assertEqual((result['status'], result['totalPosts']), ('ok', 2))

    def test_failed_second_page_preserves_candidates_and_reports_partial_scope(self):
        pages = {'https://example.org/careers': '<p>2 vacantes</p><a href="/jobs/1">Data Analyst</a><a href="?page=2">Next</a>'}
        def fetch(link, *args):
            if link not in pages:
                raise OSError('TEST second page unavailable')
            return pages[link]
        with patch.object(scanner, 'fetch', side_effect=fetch):
            result = scanner.scan({'id': 'test', 'company': 'TEST source', 'kind': 'html', 'url': 'https://example.org/careers'})
        self.assertEqual((result['status'], result['totalPosts']), ('partial', 1))
        self.assertEqual(len(result['candidates']), 1)
        self.assertTrue(any('TEST second page unavailable' in item for item in result['errors']))

    def test_explicit_empty_listing_is_ok_but_an_empty_unknown_page_is_partial(self):
        empty, _ = self.scan({'https://example.org/careers': '<p>0 ofertas</p>'})
        unknown, _ = self.scan({'https://example.org/careers': '<p>Careers loading</p>'})
        self.assertEqual((empty['status'], empty['totalPosts']), ('ok', 0))
        self.assertEqual(unknown['status'], 'partial')

    def test_pagination_limit_is_partial(self):
        pages = {f'https://example.org/careers?page={page}': f'<a href="/jobs/{page}">Data Analyst</a><a href="?page={page+1}">Next</a>' for page in range(1, 32)}
        result, fetch = self.scan(pages, 'https://example.org/careers?page=1')
        self.assertEqual((result['status'], fetch.call_count), ('partial', 30))
        self.assertTrue(any('Límite de paginación' in item for item in result['errors']))

    def test_unknown_adapter_is_explicitly_unsupported_without_fetch(self):
        with patch.object(scanner, 'fetch') as fetch:
            result = scanner.scan({'id': 'test', 'company': 'TEST source', 'kind': 'unknown', 'url': 'https://example.org/careers'})
        fetch.assert_not_called()
        self.assertEqual((result['status'], result['coverage']['completeness']), ('unsupported', 'unsupported'))

    def test_api_truncation_flag_prevents_ok_while_retaining_observed_jobs(self):
        with patch.object(scanner, 'fetch', return_value={'jobs': [], 'hasMore': True}):
            result = scanner.scan({'id': 'test', 'company': 'TEST source', 'kind': 'greenhouse', 'board': 'test'})
        self.assertEqual((result['status'], result['coverage']['completeness']), ('partial', 'partial'))


if __name__ == '__main__':
    unittest.main()


class PageEncodingTests(unittest.TestCase):
    def response(self, raw, content_type=None):
        import email.message
        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self, *a): return raw
        response = Response()
        response.headers = email.message.Message()
        if content_type: response.headers['Content-Type'] = content_type
        return response

    def fetch_page(self, raw, content_type=None):
        with patch.object(scanner, 'public_destination'), patch.object(scanner, 'build_opener') as factory:
            factory.return_value.open.return_value = self.response(raw, content_type)
            return scanner.fetch('https://example.org/jobs', False)

    def test_declared_page_charset_is_honoured(self):
        page = '<a href="/jobs/1">Analista de datos · Logroño</a>'.encode('iso-8859-1', errors='ignore')
        self.assertIn('Logroño', self.fetch_page(page, 'text/html; charset=ISO-8859-1'))
        meta = b'<meta charset="windows-1252"><a href="/jobs/2">Ingenier\xeda</a>'
        self.assertIn('Ingeniería', self.fetch_page(meta, 'text/html'))

    def test_valid_utf8_is_kept_even_when_the_declared_charset_is_wrong(self):
        self.assertIn('Año', self.fetch_page('<p>Año</p>'.encode('utf-8'), 'text/html; charset=ISO-8859-1'))
        self.assertIn('Año', self.fetch_page('<p>Año</p>'.encode('utf-8'), 'text/html; charset=rot13'))

    def test_undeclared_or_unknown_charsets_remain_strict_utf8(self):
        with self.assertRaises(UnicodeDecodeError):
            self.fetch_page(b'<p>A\xf1o</p>', 'text/html')
        with self.assertRaises(UnicodeDecodeError):
            self.fetch_page(b'<p>A\xf1o</p>', 'text/html; charset=rot13')
