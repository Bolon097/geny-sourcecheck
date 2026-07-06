import unittest
import warnings
from unittest.mock import patch

warnings.filterwarnings("ignore", category=Warning)

from source_verifier import extract_https_urls, extract_sources, verify_response


class SourceExtractionTests(unittest.TestCase):
    def extracted_sources(self, text):
        return extract_sources(text)

    def test_extract_https_urls_only_returns_explicit_https_urls(self):
        urls = extract_https_urls(
            "https://www.example.com/a/b?x=1#top http://example.com www.example.com"
        )
        self.assertEqual(urls, ["https://www.example.com/a/b?x=1#top"])

    def test_explicit_http_and_https_are_url_sources(self):
        sources = self.extracted_sources(
            "Source A: https://www.example.com/a/b?x=1#top Source B: http://example.com"
        )
        by_source = {source["source"]: source for source in sources}

        self.assertEqual(
            by_source["https://www.example.com/a/b?x=1#top"]["source_type"],
            "url",
        )
        self.assertTrue(by_source["https://www.example.com/a/b?x=1#top"]["is_machine_checkable"])
        self.assertEqual(by_source["http://example.com"]["source_type"], "url")
        self.assertTrue(by_source["http://example.com"]["is_machine_checkable"])

    def test_doi_references_are_normalized_and_machine_checkable(self):
        sources = self.extracted_sources("Source: doi:10.1234/example.doi")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["source"], "https://doi.org/10.1234/example.doi")
        self.assertEqual(sources[0]["source_type"], "doi")
        self.assertTrue(sources[0]["is_machine_checkable"])

    def test_deduplicates_explicit_http_and_https_and_prefers_https(self):
        sources = self.extracted_sources("http://example.com/report https://example.com/report")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["source"], "https://example.com/report")
        self.assertEqual(sources[0]["source_type"], "url")

    def test_bare_domains_are_level1_signals_without_https_normalization(self):
        sources = self.extracted_sources("Source: www.example.com and example.com/path")
        by_source = {source["source"]: source for source in sources}

        self.assertEqual(by_source["www.example.com"]["source_type"], "bare_domain")
        self.assertFalse(by_source["www.example.com"]["is_machine_checkable"])
        self.assertEqual(by_source["www.example.com"]["level2_status"], "not_checked")

        self.assertEqual(by_source["example.com/path"]["source_type"], "bare_domain")
        self.assertFalse(by_source["example.com/path"]["is_machine_checkable"])
        self.assertNotIn("https://www.example.com", by_source)
        self.assertNotIn("https://example.com/path", by_source)

    def test_avoids_common_non_source_false_positives(self):
        text = "v1.2 1.5 score.2 abc.def file.name.txt 三模型横向对比Dashboard_单文件版.html"
        self.assertEqual(self.extracted_sources(text), [])

    def test_cleans_wrappers_punctuation_and_html_entities(self):
        text = 'Source: [example](https://example.com/page?x=1&amp;y=2#top)。 Also "www.gov.cn",'
        sources = self.extracted_sources(text)
        by_source = {source["source"]: source for source in sources}

        self.assertEqual(by_source["https://example.com/page?x=1&y=2#top"]["source_type"], "url")
        self.assertEqual(by_source["www.gov.cn"]["source_type"], "bare_domain")
        self.assertNotIn("https://www.gov.cn", by_source)

    def test_bare_domain_is_not_checked_by_level2(self):
        def fail_if_called(url):
            raise AssertionError(f"_request_once should not be called for bare domains: {url}")

        with patch("source_verifier._request_once", side_effect=fail_if_called):
            result = verify_response("Source: www.example.com", perform_level2=True)

        self.assertEqual(result["url_count"], 0)
        self.assertEqual(result["doi_count"], 0)
        self.assertEqual(result["bare_domain_count"], 1)
        self.assertEqual(result["machine_checkable_count"], 0)
        self.assertEqual(result["not_machine_checked_count"], 1)
        self.assertEqual(result["failed_count"], 0)

        source = result["sources"][0]
        self.assertEqual(source["source"], "www.example.com")
        self.assertEqual(source["source_type"], "bare_domain")
        self.assertEqual(source["level2_status"], "not_machine_checked_level1_signal")
        self.assertIsNone(source["attempt_url"])
        self.assertIsNone(source["final_url"])
        self.assertIsNone(source["http_status"])
        self.assertIsNone(source["error"])

    def test_doi_is_level2_checked_after_normalization(self):
        attempted = []

        def fake_request(url):
            attempted.append(url)
            return {
                "level2_status": "accessible",
                "http_status": 200,
                "attempt_url": url,
                "final_url": url,
                "error": None,
            }

        with patch("source_verifier._request_once", side_effect=fake_request):
            result = verify_response("Source: doi:10.1234/xxxxx", perform_level2=True)

        self.assertEqual(attempted, ["https://doi.org/10.1234/xxxxx"])
        self.assertEqual(result["doi_count"], 1)
        self.assertEqual(result["machine_checkable_count"], 1)
        self.assertEqual(result["accessible_count"], 1)
        self.assertEqual(result["failed_count"], 0)

    def test_mixed_sources_only_checks_urls_and_dois(self):
        attempted = []

        def fake_request(url):
            attempted.append(url)
            return {
                "level2_status": "accessible",
                "http_status": 200,
                "attempt_url": url,
                "final_url": url,
                "error": None,
            }

        text = (
            "Source A: https://example.com/report "
            "Source B: http://example.net/report "
            "Source C: doi:10.5678/example.two "
            "Source D: www.example.org "
            "Source E: Hangzhou municipal government platform"
        )
        with patch("source_verifier._request_once", side_effect=fake_request):
            result = verify_response(text, perform_level2=True)

        self.assertEqual(
            attempted,
            [
                "https://example.com/report",
                "http://example.net/report",
                "https://doi.org/10.5678/example.two",
            ],
        )
        self.assertEqual(result["url_count"], 2)
        self.assertEqual(result["doi_count"], 1)
        self.assertEqual(result["bare_domain_count"], 1)
        self.assertEqual(result["machine_checkable_count"], 3)
        self.assertEqual(result["accessible_count"], 3)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(result["not_machine_checked_count"], 2)

    def test_source_wording_only_remains_level1_signal(self):
        sources = self.extracted_sources("According to government data, charging demand is increasing.")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["source_type"], "source_wording")
        self.assertFalse(sources[0]["is_machine_checkable"])
        self.assertEqual(sources[0]["level2_status"], "not_checked")


if __name__ == "__main__":
    unittest.main()
