import unittest
import sys
import os

# Ensure src is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from media_downloader.platforms.instagram import InstagramDownloader


class TestInstagramUrlExtraction(unittest.TestCase):
    def setUp(self):
        self.downloader = InstagramDownloader()

    def test_extract_post_id_reels(self):
        test_cases = [
            ("https://www.instagram.com/reels/C_abcdef123/", "C_abcdef123"),
            ("https://www.instagram.com/reels/C_abcdef123", "C_abcdef123"),
            ("https://instagram.com/reels/C_abcdef123/", "C_abcdef123"),
            ("http://www.instagram.com/reels/C_abcdef123/", "C_abcdef123"),
            ("https://www.instagram.com/reels/C_abcdef123?igsh=MTc4MmM1YmI2Ng==", "C_abcdef123"),
            ("https://www.instagram.com/reels/C_abcdef123#comments", "C_abcdef123"),
            ("https://www.instagram.com/username/reels/C_abcdef123/", "C_abcdef123"),
            ("https://www.instagram.com/user.name_123/reels/C_abcdef123", "C_abcdef123"),
            ("instagram.com/reels/C_abcdef123", "C_abcdef123"),
            ("reels/C_abcdef123", "C_abcdef123"),
            ("/reels/C_abcdef123/", "C_abcdef123"),
        ]
        for url, expected_id in test_cases:
            with self.subTest(url=url):
                self.assertEqual(self.downloader.extract_post_id(url), expected_id)

    def test_extract_post_id_reel_singular(self):
        test_cases = [
            ("https://www.instagram.com/reel/C_abcdef123/", "C_abcdef123"),
            ("https://www.instagram.com/reel/C_abcdef123", "C_abcdef123"),
            ("https://www.instagram.com/username/reel/C_abcdef123/", "C_abcdef123"),
            ("https://www.instagram.com/reel/C_abcdef123?igsh=xyz", "C_abcdef123"),
        ]
        for url, expected_id in test_cases:
            with self.subTest(url=url):
                self.assertEqual(self.downloader.extract_post_id(url), expected_id)

    def test_extract_post_id_post_and_tv(self):
        test_cases = [
            ("https://www.instagram.com/p/C_abcdef123/", "C_abcdef123"),
            ("https://www.instagram.com/p/C_abcdef123", "C_abcdef123"),
            ("https://www.instagram.com/username/p/C_abcdef123/", "C_abcdef123"),
            ("https://www.instagram.com/tv/C_abcdef123/", "C_abcdef123"),
            ("https://www.instagram.com/username/tv/C_abcdef123", "C_abcdef123"),
        ]
        for url, expected_id in test_cases:
            with self.subTest(url=url):
                self.assertEqual(self.downloader.extract_post_id(url), expected_id)

    def test_extract_post_id_invalid(self):
        invalid_urls = [
            "https://www.instagram.com/explore/",
            "https://www.instagram.com/",
            "https://google.com/test",
            "not a url",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self.downloader.extract_post_id(url, raise_error=True)
                self.assertEqual(self.downloader.extract_post_id(url, raise_error=False), "")


if __name__ == "__main__":
    unittest.main()
