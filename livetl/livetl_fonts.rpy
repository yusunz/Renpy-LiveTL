# =============================================================================
# LiveTL —— 字体
#
# 汉化后原文的字体往往不含中文字形（显示成方块）。
# 这里用 Ren'Py 自带的 config.font_replacement_map，
# 把游戏里用到的字体统一映射到 livetl_font（默认是随插件附带的思源黑体简体）。
#
# 做法参考 KittyArk/Renpy_fonts_replacement（MIT 许可）。
#   原项目：https://github.com/KittyArk/Renpy_fonts_replacement
#   许可证：licenses/Renpy_fonts_replacement-LICENSE.txt
# =============================================================================

init -50 python:
    import re

    # 匹配脚本里出现的字体文件名，例如 "fonts/xxx.ttf"
    _livetl_font_pattern = re.compile(r'["\']([^"\']+\.(?:ttf|otf|ttc))["\']', re.IGNORECASE)

    def livetl_collect_fonts():
        """收集游戏脚本里用到的字体文件名。

        扫描参与翻译的脚本中出现过的 *.ttf / *.otf / *.ttc 字符串，
        和原项目里 extract_fonts.py 的思路一致。
        """
        fonts = set()

        for filename in livetl_engine_translate_files():
            try:
                with open(filename, "r", encoding="utf-8", errors="ignore") as f:
                    for m in _livetl_font_pattern.finditer(f.read()):
                        fonts.add(m.group(1))
            except Exception:
                pass

        return sorted(fonts)

    def livetl_effective_panel_font():
        """面板实际使用的字体。

        livetl_panel_font 留空时跟随游戏字体（livetl_font）；
        两个都留空时返回 ""，由面板样式继承游戏原字体。
        """
        return livetl_panel_font or livetl_font

    def livetl_apply_font_replacement():
        """把游戏用到的字体全部映射到 livetl_font。

        返回被替换的字体数量；livetl_font 留空、或字体文件不存在时不做替换。
        """
        target = livetl_font

        if not target:
            return 0

        # 字体文件不存在就跳过（不然游戏会因为找不到字体起不来）
        if not renpy.loadable(target):
            livetl_log("font replacement skipped: {!r} not found".format(target))
            return 0

        fonts = livetl_collect_fonts()

        count = 0

        for old_font in fonts:
            if old_font == target:
                continue

            # 常规 / 粗体 / 斜体 / 粗斜体 四种组合都要映射，
            # 否则文本加粗后又会落回原字体。
            #
            # 目标字体只有一个字重，加粗仍然交给 Ren'Py 自己处理
            # （按字号膨胀位图的伪粗体），所以 bold / italic 原样透传。
            for is_bold in (False, True):
                for italic in (False, True):
                    config.font_replacement_map[old_font, is_bold, italic] = (target, is_bold, italic)

            count += 1

        livetl_log("font replacement: {} fonts -> {!r}".format(count, target))
        return count


init 100 python:

    # 脚本加载完成后执行一次替换
    livetl_apply_font_replacement()
