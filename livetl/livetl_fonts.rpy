# =============================================================================
# LiveTL —— 字体
#
# 汉化后原文的字体往往不含中文字形（显示成方块）。
# 这里用 Ren'Py 自带的 config.font_replacement_map，
# 把游戏里用到的字体统一映射到 livetl_font（默认是随插件附带的思源黑体简体）。
#
# 译者换字体有两条路，两条都落在同一个地方（livetl_config.rpy 的 livetl_font）：
#   * 把字体文件拖进设置界面（拖放事件见本文件下半部分）
#   * 在设置界面点【选择字体】，从 livetl/fonts/ 里挑一个
# 改配置前会先把原文件备份成 .bak（只保留最近一次）
#
# 做法参考 KittyArk/Renpy_fonts_replacement（MIT 许可）。
#   原项目：https://github.com/KittyArk/Renpy_fonts_replacement
#   许可证：licenses/Renpy_fonts_replacement-LICENSE.txt
# =============================================================================

init -50 python:
    import hashlib
    import os
    import pygame
    import re
    import shutil

    # ---------------------------------------------------------------------
    # 拖放：引擎默认屏蔽标准之外的事件，config.pygame_events 是官方留的
    # 口子，不加的话 DROPFILE 根本到不了游戏里（见 Interface.post_init）。
    # ---------------------------------------------------------------------

    _livetl_drop_event = getattr(pygame, "DROPFILE", None)

    if _livetl_drop_event is not None and _livetl_drop_event not in config.pygame_events:
        config.pygame_events.append(_livetl_drop_event)

    def livetl_font_drop_event_type():
        """拖放事件类型；这个引擎上没有就返回 None。"""
        return _livetl_drop_event

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

    def livetl_font_display_name():
        """当前游戏字体的显示文本（设置界面用）。"""
        return livetl_font or "游戏原字体（没有替换）"

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

    # ---------------------------------------------------------------------
    # 字体库：livetl/fonts/ 里的字体文件
    # ---------------------------------------------------------------------

    # 字体目录（相对游戏目录）与认得的扩展名
    _livetl_fonts_dir = "livetl/fonts"
    _livetl_font_exts = (".ttf", ".otf", ".ttc")

    def _livetl_fonts_dir_path():
        """字体目录的绝对路径。"""
        return os.path.join(renpy.config.gamedir, "livetl", "fonts")

    def _livetl_font_rel(name):
        """字体文件名 → 相对游戏目录的路径（Ren'Py 里统一用 / 分隔）。"""
        return "{}/{}".format(_livetl_fonts_dir, name)

    def _livetl_font_digest(path):
        """文件内容摘要，用来判断两个字体是不是同一份；读不了返回 None。"""
        try:
            digest = hashlib.md5()

            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(block)

            return digest.hexdigest()
        except Exception:
            return None

    def livetl_font_is_variable(rel_path):
        """这个字体是不是可变字体（Ren'Py 渲染它会出方块，选中时要提醒）。

        先问引擎；8.1 的 renpy.variable_font_info() 对部分可变字体
        返回 None（文件里明明有 fvar 表），所以再按文件名兜一层 ——
        可变字体的文件名通常带 VF，这也是 fonts/README.md 里一直
        提醒译者的那个特征。
        """
        try:
            if renpy.variable_font_info(rel_path) is not None:
                return True
        except Exception:
            pass

        stem = os.path.splitext(os.path.basename(rel_path))[0].lower()

        if "variable" in stem:
            return True

        return re.search(r"(^|[^a-z])vf([^a-z]|$)", stem) is not None

    def livetl_font_list():
        """字体目录里可用的字体。

        返回 [{"path": 相对路径, "name": 文件名, "variable": 是否可变字体}]，
        按文件名排序。两个来源都看：磁盘目录（刚拖进来的还没进引擎清单）
        与引擎的文件清单（打包后字体可能在归档里）。
        """
        names = set()

        try:
            names.update(os.listdir(_livetl_fonts_dir_path()))
        except Exception:
            pass

        try:
            prefix = _livetl_fonts_dir + "/"

            for name in renpy.list_files():
                if name.startswith(prefix):
                    names.add(name[len(prefix):])
        except Exception:
            pass

        fonts = []

        for name in sorted(names):
            if not name.lower().endswith(_livetl_font_exts):
                continue

            rel = _livetl_font_rel(name)

            if not renpy.loadable(rel):
                continue

            fonts.append({
                "path": rel,
                "name": name,
                "variable": livetl_font_is_variable(rel),
            })

        return fonts

    def livetl_font_normalize_path(path):
        """把系统给的路径整理成 os 能用的形式。"""
        path = str(path or "").strip()

        if path.lower().startswith("file://"):
            path = path[7:]

        return path.replace("\\", "/")

    def livetl_font_import(source_path):
        """把外面拖进来的字体复制进字体目录。

        同一份文件（内容一致）重复拖入不会产生副本；同名但内容不同时
        自动加 -1、-2 后缀，不覆盖已有字体。
        返回 (相对路径, 错误信息)；出错时相对路径是 None。
        """
        source_path = livetl_font_normalize_path(source_path)

        if not source_path:
            return None, "没有拿到文件路径"

        if not source_path.lower().endswith(_livetl_font_exts):
            return None, "只认 .ttf / .otf / .ttc 字体文件"

        if not os.path.isfile(source_path):
            return None, "找不到文件：{}".format(source_path)

        name = os.path.basename(source_path)
        target_path = os.path.join(_livetl_fonts_dir_path(), name)
        digest = _livetl_font_digest(source_path)

        # 同一份字体已经在目录里了，直接用现成的
        if digest and os.path.isfile(target_path) and _livetl_font_digest(target_path) == digest:
            return _livetl_font_rel(name), ""

        # 同名但内容不同：加序号，别把已有字体盖掉
        stem, ext = os.path.splitext(name)
        index = 1

        while os.path.isfile(target_path):
            name = "{}-{}{}".format(stem, index, ext)
            target_path = os.path.join(_livetl_fonts_dir_path(), name)
            index += 1

        try:
            if not os.path.isdir(_livetl_fonts_dir_path()):
                os.makedirs(_livetl_fonts_dir_path())

            shutil.copyfile(source_path, target_path)
        except Exception as e:
            return None, "复制字体失败：{}".format(e)

        return _livetl_font_rel(name), ""

    # ---------------------------------------------------------------------
    # 配置文件：livetl_font 那一行
    # ---------------------------------------------------------------------

    # 只认 livetl_font 自己那一行（livetl_panel_font 不会被匹配到）
    _livetl_config_font_line = re.compile(r"^([ \t]*)livetl_font[ \t]*=[ \t]*.*$", re.MULTILINE)

    def livetl_config_path():
        """livetl_config.rpy 的绝对路径；找不到返回 None。

        插件一般放在 game/livetl/ 下，但目录名可能被改过：先问引擎要
        文件清单，再退回默认位置。打包后的游戏里往往只剩 .rpyc，
        这时改不了配置，调用方会把原因告诉译者。
        """
        gamedir = renpy.config.gamedir
        names = []

        try:
            names = [n for n in renpy.list_files() if n.endswith("livetl_config.rpy")]
        except Exception:
            pass

        names.append("livetl/livetl_config.rpy")

        for name in names:
            path = os.path.join(gamedir, name.replace("/", os.sep))

            if os.path.isfile(path):
                return path

        return None

    def _livetl_config_backup(path):
        """把配置文件备份成 xxx.bak，已有的直接覆盖。

        只留最近一次改动之前的版本：换字体是反复试的过程，
        每改一次攒一个备份很快就把目录堆满，而真要回退的通常
        就是上一个版本。
        """
        backup = path + ".bak"
        shutil.copyfile(path, backup)

        return backup

    def livetl_config_set_font(rel_path, path=None):
        """把配置文件里的 livetl_font 改成 rel_path（改之前先备份）。

        `path` 是给测试用的口子，正常调用不用传。
        返回 (备份文件名, 错误信息)；出错时备份文件名是 None。
        """
        if path is None:
            path = livetl_config_path()

        if not path:
            return None, "找不到 livetl_config.rpy"

        try:
            # newline="" —— 原样读、原样写，不动文件本来的换行符
            with open(path, "r", encoding="utf-8", newline="") as f:
                text = f.read()
        except Exception as e:
            return None, "读配置失败：{}".format(e)

        line = 'livetl_font = "{}"'.format(rel_path)
        new_text, count = _livetl_config_font_line.subn(lambda m: m.group(1) + line, text, count=1)

        if not count:
            return None, "配置里没有 livetl_font 这一行"

        try:
            backup = _livetl_config_backup(path)

            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new_text)
        except Exception as e:
            return None, "写配置失败：{}".format(e)

        return os.path.basename(backup), ""

    # ---------------------------------------------------------------------
    # 换字体：改配置 + 立即生效
    # ---------------------------------------------------------------------

    def livetl_font_apply_now():
        """让 livetl_font 立即生效：重建替换表、刷面板、清缓存、重绘。"""
        livetl_apply_font_replacement()

        # 面板样式（函数定义在界面文件里）
        livetl_apply_panel_font()

        # 字体与贴图缓存
        try:
            renpy.free_memory()
        except Exception:
            pass

        # 文本排版缓存：不清的话样式名没变，旧排版会被继续复用
        if not livetl_engine_clear_text_cache():
            livetl_log("clear_text_cache unavailable: {}".format(livetl_engine_last_error()))

        livetl_restart()

    def livetl_font_use(rel_path):
        """换字体：改配置（先备份）+ 立即生效，结果写进状态栏。"""
        if not rel_path:
            livetl_set_status("没有选中字体，未做改动")
            return False

        # 配置里是写成字符串的，这两种字符会让配置语法坏掉
        if '"' in rel_path or "\n" in rel_path or "\r" in rel_path:
            livetl_set_status("字体文件名里有引号或换行，写不进配置：{}".format(rel_path))
            return False

        if not renpy.loadable(rel_path):
            livetl_set_status("字体不可用：{}".format(rel_path))
            return False

        backup, error = livetl_config_set_font(rel_path)

        # 配置改不了也要让这次运行先用上新字体
        store.livetl_font = rel_path
        livetl_font_apply_now()

        notes = []

        if error:
            notes.append("配置没改：{}".format(error))
        elif backup:
            notes.append("已备份 {}".format(backup))

        if livetl_font_is_variable(rel_path):
            notes.append("可变字体，中文可能显示成方块")

        note = "（{}）".format("；".join(notes)) if notes else ""

        livetl_set_status("字体已换成 {}{}".format(rel_path, note))
        livetl_log("font switched: {!r} {}".format(rel_path, note))

        return True

    def livetl_font_drop(path):
        """拖进窗口的字体：先复制进字体目录，再切换。"""
        rel_path, error = livetl_font_import(path)

        if error:
            livetl_set_status("拖入的字体没用上：{}".format(error))
            livetl_log("font drop rejected: {} ({!r})".format(error, path))
            return False

        return livetl_font_use(rel_path)


init 100 python:

    # 脚本加载完成后执行一次替换
    livetl_apply_font_replacement()
