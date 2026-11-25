# reelcore-subs：特效字幕

大家一起做的特效字幕（ASS）都放这里。**先认领再动手**，避免两个人做同一部片。

## 流程

1. **查**：在 [Issues](../../issues?q=label%3A认领) 和下面的目录里按 TMDB 编号搜一下，确认没人做过、没人在做。
2. **认领**：点 New issue → 「认领字幕」，填类型、TMDB 编号、季 / 集。机器人会：
   - 把标题改成统一编号（如 `movie-11104 重庆森林`、`tv-1399 s01e01-e05 权力的游戏`），指派给你；
   - 发现已经有人认领或已经做完，就回复链接、打上「重复」并关掉。
3. **做**：按下面的目录和命名放文件，写好 `meta.toml`。
4. **提 PR**：描述里写 `认领 #<issue 号>`。检查会核对：格式、`meta.toml`、字体都列全了、这个 PR 新加的片子是你认领的。合并后认领 issue 自动关闭。
5. **不做了**：在认领 issue 里说一声，把它关掉（选 *Close as not planned*），别人就能认领。

修改已经合并的字幕（改错字、调时间轴）不用认领，直接提 PR。
有仓库写权限的人批量导入（比如压制机做过的字幕）不用一部部认领，但不能和别人开着的认领撞上。

## 编号

用 **TMDB 编号**，不用片名（片名中英文、译名不统一，按片名查容易漏）。
电影和剧集在 TMDB 是**两套编号**，同一个数字可能一个是电影一个是剧，所以一定带类型：

| 类型 | 编号 | 例子 |
|---|---|---|
| 电影 | `movie-<tmdb>` | `movie-11104`（themoviedb.org/movie/11104） |
| 剧集 | `tv-<tmdb>` + 季 + 集 | `tv-1399 s01e03`（themoviedb.org/tv/1399） |

剧集的季、集**以 TMDB 为准**。特别篇 / OVA 是第 0 季（`s00`）。原盘的卷号、绝对集数和 TMDB 对不上时，在季的 `meta.toml` 里写清楚对应关系。

## 目录

```
movie/11104/
  meta.toml
  zh-Hans.ass            简体中文
  zh-Hans+en.ass         中英双语（有就放）
tv/1399/
  meta.toml              剧名等公共信息、全剧共用的字体
  s01/
    meta.toml            这一季对应的视频版本
    e01.zh-Hans.ass
    e02.zh-Hans.ass
  s00/                   特别篇
fonts/                   只放可以公开分发的免费字体（附许可证）
```

文件名里的语言：`zh-Hans`（简体）、`zh-Hant`（繁体）、`ja`、`en`……双语用 `+` 连起来，中文在前：`zh-Hans+ja`。

同一部片有**不同剪辑版本**（导演剪辑版、电视版 / BD 版帧率不同）时，在下面再分一层：`movie/11104/directors-cut/`、`tv/1399/s01/bd/`，每层都有自己的 `meta.toml`。

## meta.toml

特效字幕是按帧对的，**一定要写清楚对的是哪个视频**，换个剪辑版本或帧率就错位。

电影 `movie/<tmdb>/meta.toml`：

```toml
title = "重庆森林"
original_title = "Chungking Express"
year = 1994
authors = ["你的 GitHub 用户名"]
fonts = ["方正兰亭黑_GBK", "Noto Sans CJK SC"]   # ASS 里用到的所有字体（检查会核对）

# [source] 这种表头要放最后：TOML 会把表头后面的键都算进这个表
[source]                          # 字幕对的视频
release = "Chungking Express 1994 1080p Blu-ray AVC DTS-HD MA 5.1"   # 原盘或片源的名字
fps = "24000/1001"
frames = 147997                   # 总帧数（mediainfo 的 Frame count），和时长二选一，最好都写
duration = "01:42:51.958"
crop = [0, 140, 0, 140]           # 可选：字幕画布对的是裁掉黑边后的画面（左、上、右、下，原盘像素）
```

**画布和裁边**：特效字幕的坐标（`\pos`、`\move`、`\clip`……）是相对 `PlayResX/PlayResY` 画布的。
在裁过黑边的视频上做的，写上 `crop`；在原盘整幅画面上做的，不写。压制机这次裁边不一样时，会按它换算画布和坐标。

**颜色**：按 SDR 调。HDR 成品由压制机统一降亮，不要自己把颜色调暗。

`origin`（可选）：字幕怎么来的，比如 `"reelcore-encode：原盘字幕 OCR + 机器翻译 / 配对"`。

剧集 `tv/<tmdb>/meta.toml` 写 `title`、`original_title`、`year`、全剧共用的 `fonts`；
每季 `tv/<tmdb>/sNN/meta.toml` 写 `authors`、`[source]`（`release`、`fps`），每集帧数不同的话写在 `[episodes]` 里：

```toml
authors = ["a", "b"]

[source]
release = "Game of Thrones S01 1080p Blu-ray"
fps = "24000/1001"

[episodes]
e01 = { frames = 89102 }
e02 = { frames = 80021 }
```

## 字体

- ASS 里用到的字体都要列在 `fonts`（电影的 `meta.toml`，或剧的 `meta.toml` / 季的 `meta.toml`）。
- **商业字体不要传进仓库**（这是公开仓库），只写名字，大家自己装。
- `fonts/` 只收能公开分发的字体（SIL OFL 等），同一个字体只放一份，旁边放许可证。单个文件不超过 20 MB。

## 压制机怎么用

reelcore-encode 做字幕那一步先按 TMDB 编号到这里找 `movie/<tmdb>/`（含剪辑版本子目录）：
`meta.toml` 的帧率和帧数（没写帧数就比时长，差 1 秒以内）和这张原盘对得上，就直接用这份 ASS，
不再 OCR / 机器翻译；对不上就照常机器做，并在任务记录里写原因。
语言挑 `zh-Hans+<原产地语言>` > `zh-Hans+en` > 其他 `zh-Hans+…` > `zh-Hans`。
ASS 里用到的字体会封进 mkv：先在本仓库 `fonts/`、再在压制机自己的字体目录找，找不到这一步会报错（缺字体特效会走样）。

## 检查（GitHub Actions）

- 目录和文件名格式、`meta.toml` 必填项；
- ASS 能解析（UTF-8，有 `[Script Info]`、`[V4+ Styles]`、`[Events]`，写了 `PlayResX/PlayResY`）；
- ASS 里用到的字体都列在 `fonts` 里；
- PR 新加的片子 / 剧集要有对应的认领 issue，并且是指派给 PR 作者的；
- 合并后，PR 描述里「认领 #号」的 issue 自动关闭。

本地跑：`python3 tools/check.py tree`。

## 许可

字幕按 [CC BY-NC-SA 4.0](LICENSE) 共享（署名、非商业、相同方式共享）。`fonts/` 里的字体按各自的许可证。
