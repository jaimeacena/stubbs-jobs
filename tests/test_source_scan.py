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


SEARCH = {'targetRoles': 'Data Analyst', 'keywords': '', 'regions': ''}
LEVER_ID = '6ed76ce8-4156-4b60-b120-403538bd66cd'


def lever_post(index, title='Data Analyst', country='ES', places=('Madrid', 'Remote Spain')):
    return {'id': f'{index:08d}-4156-4b60-b120-403538bd66cd', 'text': title, 'country': country,
            'hostedUrl': f'https://jobs.lever.co/test-company/{index:08d}-4156-4b60-b120-403538bd66cd',
            'categories': {'location': places[0], 'allLocations': list(places), 'commitment': 'Full-time'},
            'descriptionPlain': 'TEST description', 'lists': [{'text': 'TEST list', 'content': '<li>SQL &amp; Python</li>'}]}


class PortalScanTests(unittest.TestCase):
    """Fictional JSON/XML answers of hosted job boards; fetch is always replaced."""

    def scan(self, source, pages, search=SEARCH):
        def fetch(link, *args):
            answer = pages[link]
            if isinstance(answer, Exception):
                raise answer
            return answer
        with patch.object(scanner, 'CURRENT_SEARCH', search), patch.object(scanner, 'fetch', side_effect=fetch) as transport:
            result = scanner.scan({'id': 'test-portal', 'company': 'TEST company', **source})
        return result, [call.args[0] for call in transport.call_args_list]

    def test_each_portal_address_becomes_its_adapter_with_the_company_identifier(self):
        from personalization import blank_store, public_sources
        links = {'https://jobs.lever.co/test-company': {'kind': 'lever', 'board': 'test-company'},
                 'https://jobs.eu.lever.co/test-company/': {'kind': 'lever', 'board': 'test-company', 'region': 'eu'},
                 'https://apply.workable.com/test-company/': {'kind': 'workable', 'board': 'test-company'},
                 'https://test-company.jobs.personio.de/': {'kind': 'personio', 'board': 'test-company'},
                 'https://test-company.jobs.personio.com/?language=es': {'kind': 'personio', 'board': 'test-company'},
                 'https://jobs.smartrecruiters.com/TestCompany': {'kind': 'smartrecruiters', 'board': 'TestCompany'},
                 'https://careers.smartrecruiters.com/TestCompany': {'kind': 'smartrecruiters', 'board': 'TestCompany'},
                 'https://test-company.recruitee.com/': {'kind': 'recruitee', 'board': 'test-company'},
                 # A single offer or the vendor's own site is not a company listing.
                 'https://apply.workable.com/j/ABC123': {'kind': 'html'},
                 'https://app.recruitee.com/': {'kind': 'html'},
                 'https://jobs.lever.co/': {'kind': 'html'}}
        store = blank_store()
        store['app']['searchContext']['sourceUrls'] = '\n'.join(links)
        sources = {source['url']: source for source in public_sources(store)}
        for link, expected in links.items():
            with self.subTest(link=link):
                self.assertEqual({k: sources[link].get(k) for k in expected}, expected)
                self.assertEqual('region' in sources[link], 'region' in expected)
                if expected['kind'] != 'html':
                    self.assertEqual(sources[link]['company'], expected['board'])

    def test_portal_configuration_requires_a_valid_identifier(self):
        from personalization import validate_source_configuration
        base = {'id': 'test', 'company': 'TEST company'}
        validate_source_configuration([dict(base, kind='lever', board='test-company', region='eu')])
        for source in (dict(base, kind='lever'), dict(base, kind='workable', board='../escape'),
                       dict(base, kind='personio', board='test.evil'), dict(base, kind='recruitee', board='Test_Company'),
                       dict(base, kind='smartrecruiters', board='test/company'), dict(base, kind='workable', board='x', region='eu'),
                       dict(base, kind='lever', board='x', region='us')):
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_source_configuration([source])

    def test_portal_identities_are_stable_across_aliases_and_suffixes(self):
        from stubbs_jobs_core import identity
        groups = {f'lever:test-company:{LEVER_ID}': [f'https://jobs.lever.co/test-company/{LEVER_ID}',
                                                     f'https://jobs.lever.co/Test-Company/{LEVER_ID.upper()}/apply?lever-source=TEST'],
                  'workable:ABC123': ['https://apply.workable.com/j/ABC123', 'https://apply.workable.com/test-company/j/ABC123/'],
                  'personio:test-company:123': ['https://test-company.jobs.personio.de/job/123?language=en',
                                                'https://test-company.jobs.personio.com/job/123'],
                  'smartrecruiters:testcompany:7440001': ['https://jobs.smartrecruiters.com/TestCompany/7440001-data-analyst',
                                                          'https://jobs.smartrecruiters.com/testcompany/7440001'],
                  'recruitee:test-company:data-analyst': ['https://test-company.recruitee.com/o/data-analyst',
                                                          'https://test-company.recruitee.com/o/data-analyst/c/new']}
        for expected, links in groups.items():
            for link in links:
                with self.subTest(link=link):
                    self.assertEqual(identity(link), expected)
        self.assertTrue(identity('https://jobs.lever.co/test-company').startswith('url:'))

    def test_exclusive_portal_source_allows_only_the_same_company(self):
        from personalization import blank_store, source_allowed
        store = blank_store()
        store['app']['searchContext']['sourceUrls'] = '\n'.join((
            'https://jobs.lever.co/test-company', 'https://test-company.jobs.personio.de',
            'https://jobs.smartrecruiters.com/TestCompany', 'https://apply.workable.com/test-company',
            'https://test-company.recruitee.com'))
        allowed = ('https://jobs.lever.co/test-company/' + LEVER_ID, 'https://test-company.jobs.personio.com/job/1',
                   'https://careers.smartrecruiters.com/testcompany', 'https://apply.workable.com/test-company/j/ABC',
                   'https://test-company.recruitee.com/o/data-analyst')
        refused = ('https://jobs.lever.co/another-company', 'https://jobs.eu.lever.co/test-company',
                   'https://another.jobs.personio.de', 'https://jobs.smartrecruiters.com/Another',
                   'https://apply.workable.com/another', 'https://apply.workable.com/j/ABC',
                   'https://another.recruitee.com', 'https://example.org/jobs')
        for link in allowed:
            with self.subTest(link=link):
                self.assertTrue(source_allowed(store, link))
        for link in refused:
            with self.subTest(link=link):
                self.assertFalse(source_allowed(store, link))

    def test_lever_follows_pages_until_a_short_page_and_keeps_offer_details(self):
        base = 'https://api.lever.co/v0/postings/test-company?mode=json&limit=100'
        first = [lever_post(i, 'Data Analyst' if i == 0 else 'Office Manager') for i in range(100)]
        result, fetched = self.scan({'kind': 'lever', 'board': 'test-company'},
                                    {base + '&skip=0': first, base + '&skip=100': [lever_post(100, 'Senior Data Analyst', 'US')]})
        self.assertEqual(fetched, [base + '&skip=0', base + '&skip=100'])
        self.assertEqual((result['status'], result['totalPosts'], result['errors']), ('ok', 101, []))
        self.assertEqual(result['coverage'], {'method': 'api', 'pages': fetched, 'completeness': 'returned_listing',
                                              'scope': 'Listado recibido de la API; condiciones individuales pendientes de comprobar'})
        offer = result['candidates'][0]
        self.assertEqual((offer['title'], offer['location'], offer['employmentType']), ('Data Analyst', 'Madrid; Remote Spain', 'Full-time'))
        self.assertEqual(offer['id'], 'lever:test-company:00000000-4156-4b60-b120-403538bd66cd')
        self.assertIn('SQL & Python', offer['description'])
        self.assertEqual(len(result['candidates']), 2)

    def test_lever_countries_filter_the_requested_country_and_eu_uses_its_own_api(self):
        base = 'https://api.eu.lever.co/v0/postings/test-company?mode=json&limit=100&skip=0'
        result, fetched = self.scan({'kind': 'lever', 'board': 'test-company', 'region': 'eu'},
                                    {base: [lever_post(1, country='ES'), lever_post(2, country='US', places=('New York',))]},
                                    dict(SEARCH, regions='España'))
        self.assertEqual(fetched, [base])
        self.assertEqual([c['id'].rsplit(':', 1)[1][:8] for c in result['candidates']], ['00000001'])

    def test_lever_failed_or_unbounded_later_pages_are_partial_and_keep_offers(self):
        base = 'https://api.lever.co/v0/postings/test-company?mode=json&limit=100'
        failed, _ = self.scan({'kind': 'lever', 'board': 'test-company'},
                              {base + '&skip=0': [lever_post(i) for i in range(100)], base + '&skip=100': OSError('TEST unavailable')})
        self.assertEqual((failed['status'], failed['coverage']['completeness'], len(failed['candidates'])), ('partial', 'partial', 100))
        self.assertTrue(any('TEST unavailable' in item for item in failed['errors']))
        ignored, fetched = self.scan({'kind': 'lever', 'board': 'test-company'}, {base + '&skip=0': [lever_post(i) for i in range(101)]})
        self.assertEqual((ignored['status'], len(fetched)), ('partial', 1))
        self.assertTrue(any('tamaño de página' in item for item in ignored['errors']))
        repeated, _ = self.scan({'kind': 'lever', 'board': 'test-company'},
                                {base + '&skip=0': [lever_post(i) for i in range(100)], base + '&skip=100': [lever_post(99)]})
        self.assertEqual((repeated['status'], repeated['totalPosts']), ('partial', 100))
        self.assertTrue(any('repetida' in item for item in repeated['errors']))

    def test_first_page_failure_is_an_error_without_candidates(self):
        base = 'https://api.lever.co/v0/postings/test-company?mode=json&limit=100&skip=0'
        for answer in (OSError('TEST down'), {'jobs': []}):
            with self.subTest(answer=answer):
                result, _ = self.scan({'kind': 'lever', 'board': 'test-company'}, {base: answer})
                self.assertEqual((result['status'], result['coverage']['completeness'], result['candidates']), ('error', 'error', []))

    def smartrecruiters_post(self, index, title='Data Analyst'):
        return {'id': str(7440000 + index), 'name': title, 'company': {'identifier': 'TestCompany'},
                'releasedDate': '2026-10-16T14:09:41.440Z', 'typeOfEmployment': {'label': 'Full-time'},
                'location': {'city': 'Madrid', 'country': 'es', 'fullLocation': 'Madrid, Spain'}}

    def test_smartrecruiters_pages_by_offset_until_the_declared_total(self):
        base = 'https://api.smartrecruiters.com/v1/companies/TestCompany/postings?limit=100'
        pages = {base + '&offset=0': {'totalFound': 101, 'content': [self.smartrecruiters_post(i) for i in range(100)]},
                 base + '&offset=100': {'totalFound': 101, 'content': [self.smartrecruiters_post(100)]}}
        result, fetched = self.scan({'kind': 'smartrecruiters', 'board': 'TestCompany'}, pages, dict(SEARCH, regions='España'))
        self.assertEqual(fetched, list(pages))
        self.assertEqual((result['status'], result['totalPosts'], len(result['candidates'])), ('ok', 101, 101))
        self.assertEqual(result['coverage']['completeness'], 'returned_listing')
        offer = result['candidates'][0]
        self.assertEqual((offer['url'], offer['id'], offer['location'], offer['lastPublishedAt']),
                         ('https://jobs.smartrecruiters.com/TestCompany/7440000', 'smartrecruiters:testcompany:7440000',
                          'Madrid, Spain', '2026-10-16T14:09:41.440Z'))

    def test_smartrecruiters_short_listing_missing_total_or_page_limit_is_partial(self):
        base = 'https://api.smartrecruiters.com/v1/companies/TestCompany/postings?limit=100'
        short, _ = self.scan({'kind': 'smartrecruiters', 'board': 'TestCompany'},
                             {base + '&offset=0': {'totalFound': 5, 'content': []}})
        self.assertEqual(short['status'], 'partial')
        self.assertTrue(any('0 de 5' in item for item in short['errors']))
        unknown, _ = self.scan({'kind': 'smartrecruiters', 'board': 'TestCompany'},
                               {base + '&offset=0': {'content': [self.smartrecruiters_post(1)]}})
        self.assertEqual((unknown['status'], len(unknown['candidates'])), ('partial', 1))
        pages = {f'{base}&offset={page * 100}': {'totalFound': 99999, 'content': [self.smartrecruiters_post(page * 100 + i) for i in range(100)]}
                 for page in range(31)}
        limited, fetched = self.scan({'kind': 'smartrecruiters', 'board': 'TestCompany'}, pages)
        self.assertEqual((limited['status'], len(fetched)), ('partial', 30))
        self.assertTrue(any('Límite de paginación' in item for item in limited['errors']))

    def test_workable_widget_listing_with_locations_and_description(self):
        url = 'https://apply.workable.com/api/v1/widget/accounts/test-company?details=true'
        payload = {'name': 'TEST company', 'jobs': [
            {'title': 'Data Analyst', 'shortcode': 'ABC123', 'url': 'https://apply.workable.com/j/ABC123', 'published_on': '2026-10-01',
             'employment_type': 'Full-time', 'description': '<p>SQL &amp; dashboards</p>', 'country': 'Spain', 'city': 'Madrid',
             'locations': [{'country': 'Spain', 'countryCode': 'ES', 'city': 'Madrid', 'region': 'Madrid', 'hidden': False}]},
            {'title': 'Data Analyst', 'shortcode': 'DEF456', 'url': 'https://apply.workable.com/j/DEF456',
             'locations': [{'country': 'Poland', 'countryCode': 'PL', 'city': 'Warsaw', 'hidden': False}]},
            {'title': 'Chef', 'shortcode': 'GHI789', 'url': 'https://apply.workable.com/j/GHI789'}]}
        result, fetched = self.scan({'kind': 'workable', 'board': 'test-company'}, {url: payload}, dict(SEARCH, regions='España'))
        self.assertEqual((fetched, result['status'], result['totalPosts']), ([url], 'ok', 3))
        self.assertEqual([c['id'] for c in result['candidates']], ['workable:ABC123'])
        offer = result['candidates'][0]
        self.assertEqual((offer['location'], offer['description'], offer['lastPublishedAt']), ('Madrid, Spain', 'SQL & dashboards', '2026-10-01'))
        paged, _ = self.scan({'kind': 'workable', 'board': 'test-company'}, {url: {**payload, 'paging': {'next': 'TEST'}}})
        self.assertEqual((paged['status'], paged['coverage']['completeness']), ('partial', 'partial'))

    def test_recruitee_offers_keep_public_link_and_iso_publication(self):
        url = 'https://test-company.recruitee.com/api/offers/'
        payload = {'offers': [{'id': 1, 'slug': 'data-analyst', 'title': 'Data Analyst', 'careers_url': 'https://test-company.recruitee.com/o/data-analyst',
                               'location': 'Barcelona, Spain', 'country_code': 'ES', 'published_at': '2026-10-15 09:31:36 UTC',
                               'description': '<p>Reporting</p>', 'requirements': '<ul><li>SQL</li></ul>',
                               'employment_type_code': 'fulltime_permanent', 'locations': [{'name': 'Barcelona', 'country_code': 'ES'}]}]}
        result, fetched = self.scan({'kind': 'recruitee', 'board': 'test-company'}, {url: payload})
        self.assertEqual((fetched, result['status'], result['coverage']['completeness']), ([url], 'ok', 'returned_listing'))
        offer = result['candidates'][0]
        self.assertEqual((offer['id'], offer['location'], offer['description'], offer['lastPublishedAt']),
                         ('recruitee:test-company:data-analyst', 'Barcelona, Spain; Barcelona', 'Reporting\nSQL', '2026-10-15T09:31:36+00:00'))
        malformed, _ = self.scan({'kind': 'recruitee', 'board': 'test-company'}, {url: {'offers': [{'title': 'Data Analyst'}, 'TEST']}})
        self.assertEqual((malformed['status'], malformed['candidates']), ('partial', []))

    def test_personio_xml_positions_on_the_configured_domain(self):
        url = 'https://test-company.jobs.personio.com/xml'
        feed = ('<?xml version="1.0" encoding="UTF-8"?><workzag-jobs><position><id>123</id><office>Madrid</office>'
                '<additionalOffices><office>Remote Spain</office></additionalOffices><name>Data Analyst</name>'
                '<jobDescriptions><jobDescription><name>Tasks</name><value><![CDATA[<p>SQL &amp; BI</p>]]></value></jobDescription></jobDescriptions>'
                '<employmentType>permanent</employmentType><schedule>full-time</schedule></position>'
                '<position><id>124</id><office>London</office><name>Data Analyst</name></position></workzag-jobs>')
        source = {'kind': 'personio', 'board': 'test-company', 'url': 'https://test-company.jobs.personio.com/'}
        result, fetched = self.scan(source, {url: feed}, dict(SEARCH, regions='España'))
        self.assertEqual((fetched, result['status'], result['totalPosts']), ([url], 'ok', 2))
        self.assertEqual(len(result['candidates']), 1)
        offer = result['candidates'][0]
        self.assertEqual((offer['url'], offer['id'], offer['location'], offer['description'], offer['employmentType']),
                         ('https://test-company.jobs.personio.com/job/123', 'personio:test-company:123', 'Madrid; Remote Spain',
                          'SQL & BI', 'permanent, full-time'))
        default, fetched = self.scan({'kind': 'personio', 'board': 'test-company'},
                                     {'https://test-company.jobs.personio.de/xml': '<workzag-jobs></workzag-jobs>'})
        self.assertEqual((default['status'], default['totalPosts']), ('ok', 0))

    def test_personio_rejects_entities_and_unknown_documents_without_candidates(self):
        url = 'https://test-company.jobs.personio.de/xml'
        for feed in ('<!DOCTYPE x [<!ENTITY a "aaaa">]><workzag-jobs>&a;</workzag-jobs>', '<html><body>Jobs</body></html>', '<workzag-jobs>'):
            with self.subTest(feed=feed):
                result, _ = self.scan({'kind': 'personio', 'board': 'test-company'}, {url: feed})
                self.assertEqual((result['status'], result['candidates']), ('error', []))
