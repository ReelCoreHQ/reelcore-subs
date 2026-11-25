import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check  # noqa: E402

ASS = """[Script Info]
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour
Style: Default,方正兰亭黑_GBK,60,&H00FFFFFF

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:01.00,0:00:02.00,Default,{\\fnNoto Sans CJK SC\\b1}你好
"""

MOVIE_META = """title = "重庆森林"
year = 1994
authors = ["a"]
fonts = ["方正兰亭黑_GBK", "Noto Sans CJK SC"]
[source]
release = "Chungking Express 1994 1080p Blu-ray"
fps = "24000/1001"
frames = 147997
"""


class Tree(unittest.TestCase):
    def make(self, files: dict[str, str]) -> Path:
        d = Path(tempfile.mkdtemp())
        for k, v in files.items():
            (d / k).parent.mkdir(parents=True, exist_ok=True)
            (d / k).write_text(v, encoding="utf-8")
        return d

    def test_good_movie(self):
        d = self.make({"movie/11104/meta.toml": MOVIE_META, "movie/11104/zh-Hans+en.ass": ASS})
        self.assertEqual(check.check_tree(d), [])

    def test_missing_font_and_meta(self):
        meta = MOVIE_META.replace('"Noto Sans CJK SC"', '"x"').replace("frames = 147997\n", "")
        d = self.make({"movie/11104/meta.toml": meta, "movie/11104/zh-Hans.ass": ASS})
        errs = "\n".join(check.check_tree(d))
        self.assertIn("Noto Sans CJK SC", errs)
        self.assertIn("source.frames 或 source.duration", errs)

    def test_bad_paths(self):
        d = self.make({"movie/重庆森林/zh.ass": ASS, "tv/1399/s1/e01.zh-Hans.ass": ASS, "x.txt": ""})
        self.assertEqual(len(check.check_tree(d)), 3)

    def test_tv_meta_inherits(self):
        show = 'title = "权力的游戏"\nyear = 2011\nfonts = ["方正兰亭黑_GBK", "Noto Sans CJK SC"]\n'
        season = 'authors = ["a"]\n[source]\nrelease = "GoT S01 BD"\nfps = "24000/1001"\n'
        d = self.make({"tv/1399/meta.toml": show, "tv/1399/s01/meta.toml": season,
                       "tv/1399/s01/e01.zh-Hans.ass": ASS, "tv/1399/s01/bd/e02.zh-Hans.ass": ASS})
        self.assertEqual(check.check_tree(d), [])

    def test_ass_without_sections(self):
        d = self.make({"movie/1/meta.toml": MOVIE_META, "movie/1/zh-Hans.ass": "hello"})
        errs = "\n".join(check.check_tree(d))
        self.assertIn("[Events]".lower(), errs.lower())
        self.assertIn("PlayResX", errs)


class Keys(unittest.TestCase):
    def test_titles(self):
        self.assertEqual(str(check.key_from_title("movie-11104 重庆森林")), "movie-11104")
        k = check.key_from_title("tv-1399 s01e01-05,07 权力的游戏")
        self.assertEqual((k.season, sorted(k.episodes)), (1, [1, 2, 3, 4, 5, 7]))
        self.assertEqual(str(k), "tv-1399 s01e01-05,07")
        self.assertIsNone(check.key_from_title("tv-1399 权力的游戏"))   # 剧集要有季
        self.assertIsNone(check.key_from_title("认领"))

    def test_overlap(self):
        whole = check.Key("tv", 1399, 1, None)
        e3 = check.Key("tv", 1399, 1, frozenset({3}))
        e4 = check.Key("tv", 1399, 1, frozenset({4}))
        self.assertTrue(whole.overlaps(e3))
        self.assertFalse(e3.overlaps(e4))
        self.assertFalse(e3.overlaps(check.Key("tv", 1399, 2, None)))
        self.assertFalse(check.Key("movie", 1399).overlaps(whole))   # 电影和剧是两套编号

    def test_form(self):
        body = ("### 类型\n\n剧集\n\n### TMDB 编号\n\nhttps://www.themoviedb.org/tv/1399-game-of-thrones\n\n"
                "### 片名\n\n权力的游戏\n\n### 季\n\n1\n\n### 集（留空 = 整季）\n\n1-3\n\n### 对哪个版本\n\n_No response_\n")
        k, name = check.key_from_form(check.form_fields(body))
        self.assertEqual((str(k), name), ("tv-1399 s01e01-03", "权力的游戏"))
        body2 = "### 类型\n\n电影\n\n### TMDB 编号\n\n11104\n\n### 片名\n\n重庆森林\n\n### 季\n\n_No response_\n"
        self.assertEqual(str(check.key_from_form(check.form_fields(body2))[0]), "movie-11104")
        with self.assertRaises(ValueError):
            check.key_from_form(check.form_fields("### 类型\n\n剧集\n\n### TMDB 编号\n\n1399\n"))

    def test_existing(self):
        ks = check.existing_keys(["movie/1/meta.toml", "tv/2/s01/e03.zh-Hans.ass", "tv/2/s01/bd/e04.zh-Hans.ass"])
        self.assertEqual([str(k) for k in ks], ["movie-1", "tv-2 s01e03", "tv-2 s01e04"])


if __name__ == "__main__":
    unittest.main()
