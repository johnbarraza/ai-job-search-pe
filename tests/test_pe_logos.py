"""tools/pe_logos.py and the logo cell of tools/pe_revision.py."""

import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pl = load("pe_logos")
pr = load("pe_revision")

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


class Hosts(unittest.TestCase):
    def test_only_https_on_the_known_image_hosts(self):
        self.assertTrue(pl.allowed("https://media.licdn.com/dms/image/v2/x/company-logo_100_100/0/1/acme"))
        self.assertTrue(pl.allowed("https://firebasestorage.googleapis.com/v0/b/x/o/company_logos%2Fa.jpg?alt=media"))
        self.assertFalse(pl.allowed("http://media.licdn.com/x"))
        self.assertFalse(pl.allowed("https://media.licdn.com.evil.example/x"))
        self.assertFalse(pl.allowed("https://example.com/logo.png"))
        self.assertFalse(pl.allowed(None))


class PostingLogos(unittest.TestCase):
    def test_reads_details_search_outputs_and_skips_foreign_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            detail = Path(tmp) / "d.json"
            detail.write_text(json.dumps({"company": "Banco Falabella Perú",
                                          "companyLogo": "https://media.licdn.com/a/company-logo_100_100/x"}), encoding="utf-8")
            search = Path(tmp) / "s.json"
            search.write_text(json.dumps({"results": [
                {"company": "MAPFRE PERU", "companyLogo": "https://imgbum.jobscdn.com/logo.jpg"},
                {"company": "Acme", "companyLogo": "https://tracker.example/pixel.gif"},
            ]}), encoding="utf-8")
            found = pl.posting_logos([detail, search])
        self.assertEqual(set(found), {"banco-falabella-perú", "mapfre-peru"})
        self.assertEqual(found["mapfre-peru"], ("MAPFRE PERU", "https://imgbum.jobscdn.com/logo.jpg"))

    def test_anonymous_employers_never_get_a_logo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps({"results": [
                {"company": "Importante empresa del sector", "companyLogo": "https://ii.ct-stc.com/3/logos/empresas/x.png"},
                {"company": "Confidencial", "companyLogo": "https://imgbum.jobscdn.com/y.jpg"},
            ]}), encoding="utf-8")
            self.assertEqual(pl.posting_logos([path]), {})

    def test_a_close_company_name_reuses_the_posting_logo(self):
        posted = {"santander-perú": ("Santander Perú", "https://imgbum.jobscdn.com/s.jpg"),
                  "banco-falabella-perú": ("Banco Falabella Perú", "https://media.licdn.com/f")}
        match = pl.load_matcher()
        self.assertEqual(pl.fuzzy_posting_logo(match, posted, "Banco Santander Perú"), "https://imgbum.jobscdn.com/s.jpg")
        self.assertIsNone(pl.fuzzy_posting_logo(match, posted, "VVVM Consulting"))

    def test_keys_match_the_review_page_lookup(self):
        self.assertEqual(pl.company_file("  Banco  Falabella Perú "), "banco-falabella-perú")


@unittest.skipIf(Image is None, "Pillow not installed")
class Images(unittest.TestCase):
    def jpeg(self, size=(400, 200)):
        out = io.BytesIO()
        Image.new("RGB", size, (200, 30, 30)).save(out, format="JPEG")
        return out.getvalue()

    def test_reencodes_as_a_small_png(self):
        png = pl.to_png(self.jpeg())
        self.assertTrue(png.startswith(b"\x89PNG"))
        with Image.open(io.BytesIO(png)) as img:
            self.assertLessEqual(max(img.size), pl.SIZE)

    def test_bytes_that_are_not_an_image_are_rejected(self):
        with self.assertRaises(Exception):
            pl.to_png(b"<script>alert(1)</script>")

    def test_review_page_embeds_the_cached_logo_and_falls_back_to_initials(self):
        with tempfile.TemporaryDirectory() as tmp:
            research = Path(tmp)
            (research / "logos").mkdir()
            (research / "logos" / "acme.png").write_bytes(pl.to_png(self.jpeg((50, 50))))
            (research / "logos" / "index.json").write_text(json.dumps({
                "acme": {"file": "acme.png"},
                "evil": {"file": "../../secret.png"},
            }), encoding="utf-8")
            logos = pr.load_logos(research)
            uri = pr.logo_uri(research, logos, "Acme")
            self.assertTrue(uri.startswith("data:image/png;base64,"))
            self.assertIsNone(pr.logo_uri(research, logos, "Evil"))
            self.assertIsNone(pr.logo_uri(research, logos, "Nobody"))
        self.assertIn('<img class="logo"', pr.logo_html({"logo": uri}))
        self.assertIn(">BF<", pr.logo_html({"company": "Banco Falabella"}))


class FreshnessWithoutDetail(unittest.TestCase):
    def test_a_pasted_posting_gets_freshness_from_its_publication_date(self):
        from datetime import date
        seen = {"k": {"status": "ranked", "rank_verdict": "Strong Fit", "rank_score": 80, "company": "Credicorp",
                      "title": "Practicante", "url": None, "posted_date": "2026-10-19"}}
        row = pr.collect({"seen": seen}, [{"url": "", "freshness": "baja"}], Path(tempfile.mkdtemp()),
                         today=date(2026, 10, 20))["ranked"][0]
        self.assertEqual((row["fresh"]["freshness"], row["fresh"]["age_days"], row["action"]), ("muy alta", 1, "ya"))

    def test_no_date_means_no_freshness(self):
        self.assertIsNone(pr.fresh_from_state({"posted_date": None}, __import__("datetime").date(2026, 10, 20)))


if __name__ == "__main__":
    unittest.main()
