import unittest
import warnings

warnings.filterwarnings("ignore", category=Warning)

from source_verifier import extract_sources


class SourceExtractionTests(unittest.TestCase):
    def extracted_sources(self, text):
        return [source["source"] for source in extract_sources(text)]

    def test_extracts_and_normalizes_supported_url_formats(self):
        cases = {
            "https://www.example.com/a/b?x=1#top": "https://www.example.com/a/b?x=1#top",
            "http://example.com": "http://example.com",
            "www.example.com": "https://www.example.com",
            "example.com": "https://example.com",
            "example.com/path": "https://example.com/path",
            "data.hangzhou.gov.cn": "https://data.hangzhou.gov.cn",
            "www.hangzhou.gov.cn": "https://www.hangzhou.gov.cn",
            "hangzhou.gov.cn": "https://hangzhou.gov.cn",
            "zj.gov.cn": "https://zj.gov.cn",
            "www.gov.cn": "https://www.gov.cn",
            "mca.gov.cn/article/xxx": "https://mca.gov.cn/article/xxx",
            "stats.gov.cn/sj/": "https://stats.gov.cn/sj/",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertIn(expected, self.extracted_sources(raw))

    def test_avoids_common_non_url_false_positives(self):
        text = "v1.2 1.5 score.2 abc.def file.name.txt 三模型横向对比Dashboard_单文件版.html"
        self.assertEqual(self.extracted_sources(text), [])

    def test_cleans_wrappers_punctuation_and_html_entities(self):
        text = 'Source: [example](https://example.com/page?x=1&amp;y=2#top)。 Also "www.gov.cn",'
        sources = self.extracted_sources(text)
        self.assertIn("https://example.com/page?x=1&y=2#top", sources)
        self.assertIn("https://www.gov.cn", sources)

    def test_deduplicates_and_prefers_https(self):
        sources = self.extracted_sources("http://example.com https://example.com example.com")
        self.assertEqual(sources, ["https://example.com"])


if __name__ == "__main__":
    unittest.main()
