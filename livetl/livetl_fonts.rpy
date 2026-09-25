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
    import re
    import shutil

    # ---------------------------------------------------------------------
    # 拖放：登记引擎口子的事在 livetl_engine.rpy（那个配置项没有文档承诺，
    # 按规则只能待在那里）。这里在 init 阶段登记一次，界面层用
    # livetl_engine_file_drop_type() 查询；引擎不支持时它是 None。
    # ---------------------------------------------------------------------

    livetl_engine_file_drop_type()

    # 匹配脚本里出现的字体文件名。两种写法都要认：
    #   * 带引号的资源名：`"fonts/xxx.ttf"`（引号里允许空格，例如 "My Font.ttf"）
    #   * 文本标签里的写法：`{font=xxx.ttf}` —— 没有引号。实测不少游戏这样用
    #     （例如把某句台词写成 `{font=jempolfreak.ttf}...`），汉化后那句中文会因为
    #     这个字体没有中文字形变成方块，所以它必须进替换表。
    #     标签里的 `{font=` 与 `}` 都不是路径字符，按"路径字符 + 扩展名"就能认出来。
    # 带扩展名的系统字体 / register_font 家族名认不出来，那种只能靠译者换字体时
    # 看到的实际效果判断（表是按字体文件名建的）。
    _livetl_font_pattern = re.compile(
        r'["\']([^"\'\n]+\.(?:ttf|otf|ttc))["\']'
        r'|([A-Za-z0-9_\-./\\]+\.(?:ttf|otf|ttc))',
        re.IGNORECASE,
    )

    def livetl_collect_fonts():
        """收集会用到的字体文件名：游戏源码 + game/tl 下的全部脚本。

        扫描出现过的 *.ttf / *.otf / *.ttc 字符串，和原项目里 extract_fonts.py
        的思路一致。

        范围必须是"游戏源码 + **所有** tl 脚本"，不能只看游戏源码、也不能只看
        目标语言：译文脚本会给自己设字体（实测某游戏的中文翻译在
        tl/chinese/style.rpy 里把 gui.text_font / gui.name_text_font / 界面的
        gui.button_text_font … 整套换成了 tl/chinese/ 下的字体，tl/chinese/ 的
        screens.rpy 里还有 `{font=…}` 文本标签），而游戏切到哪个语言就会应用
        那个语言的脚本 —— 只扫一部分，译者选的字体就只覆盖一半文本（0.4.1 只扫
        目标语言，于是"目标语言和游戏实际在用的语言不是同一个"时就表现为
        "字体全局替换失效"）。

        每个文件的扫描结果按 (路径, mtime, 大小) 缓存，换字体时会重扫，
        但不会重复读没变过的文件。
        """
        files = list(livetl_engine_translate_files())
        files.extend(livetl_tl_files())

        cache = livetl_state_get("livetl_font_scan", {})
        new_cache = {}
        fonts = set()

        for filename in files:
            try:
                st = os.stat(filename)
                key = (filename, int(st.st_mtime), st.st_size)
            except Exception:
                key = (filename, None, None)

            found = cache.get(key)

            if found is None:
                found = set()

                try:
                    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
                        for m in _livetl_font_pattern.finditer(f.read()):
                            found.add(m.group(1) or m.group(2))
                except Exception:
                    pass

                found = tuple(sorted(found))

            new_cache[key] = found
            fonts.update(found)

        livetl_state_set("livetl_font_scan", new_cache)

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
        既不覆盖也不另存，回报错误让译者自己改名 —— 目录里同名文件
        只能有一个，攒副本和覆盖都容易把字体目录弄乱。
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

        if os.path.isfile(target_path):
            digest = _livetl_font_digest(source_path)

            # 同一份字体已经在目录里了，直接用现成的
            if digest and _livetl_font_digest(target_path) == digest:
                return _livetl_font_rel(name), ""

            return None, "fonts 目录里已经有一个同名的 {}（内容不同），请先改名再拖".format(name)

        try:
            if not os.path.isdir(_livetl_fonts_dir_path()):
                os.makedirs(_livetl_fonts_dir_path())

            shutil.copyfile(source_path, target_path)
        except Exception as e:
            return None, "复制字体失败：{}".format(e)

        return _livetl_font_rel(name), ""

    def livetl_config_set_font(rel_path, path=None):
        """把配置文件里的 livetl_font 改成 rel_path（改之前先备份）。

        `path` 是给测试用的口子，正常调用不用传。
        返回 (备份文件名, 错误信息)；出错时备份文件名是 None。
        """
        return livetl_config_set_value("livetl_font", '"{}"'.format(rel_path), path=path)

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
        # 译者的选择另外记一份：剧情"回退（Back）"不会把它带走
        livetl_setting_set("font", rel_path)
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
