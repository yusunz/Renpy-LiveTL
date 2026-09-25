# =============================================================================
# LiveTL —— 核心逻辑
#
# 负责四件事：
#   1. 定位"当前正在显示的台词"，并读出它的原文
#   2. 在 tl/<语言>/ 下生成带原文注释的标准翻译模板
#   3. 把某一句的译文写回 tl 文件（只改这一条，其余内容不动）
#   4. 触发 Ren'Py 的脚本热重载，让新译文立刻生效
#
# 本文件不包含界面代码。
# =============================================================================

init -50 python:
    import os
    import re
    import time

    # ---------------------------------------------------------------------
    # 运行状态（界面会读取这些值）
    # ---------------------------------------------------------------------

    # 当前台词的信息
    livetl_current_tid = None       # 翻译标识符
    livetl_current_source = ""      # 原文

    # 面板当前的工作模式："say"（跟着台词）/"menu"（菜单条目列表）/"dup"（查重体检）
    livetl_mode = "say"

    # 当前编辑对象：对话（say）还是字符串条目（string）
    livetl_current_kind = "say"
    livetl_current_key = None       # string 模式下这条的原文，也就是翻译条目的 key

    # 当前菜单的条目列表：每项 {"caption", "new", "state", "dup"}
    livetl_menu_items = []
    livetl_menu_index = 0
    livetl_menu_count = 0

    # 重复条目体检的结果：[(key, [(文件, 行号, 译文), ...]), ...]
    livetl_dup_report = []
    livetl_dup_check_done = False

    # 面板输入框绑定的内容
    livetl_input = ""

    # 最近一次操作的反馈文字
    livetl_status = ""

    # 面板是否展开。
    # 放在 session 里：Ren'Py 的"回退（Back）"会回滚 store 变量，
    # 而面板的显示状态是界面状态，不应该跟着剧情一起回退。
    livetl_visible = livetl_state_setdefault("livetl_visible", True)

    # ---------------------------------------------------------------------
    # 基础工具
    # ---------------------------------------------------------------------

    def livetl_log(msg):
        """把调试信息追加到 game/livetl.log。"""
        if not livetl_debug:
            return

        try:
            path = os.path.join(renpy.config.gamedir, "livetl.log")
            with open(path, "a", encoding="utf-8") as f:
                f.write(str(msg) + "\n")
        except Exception:
            pass

    def livetl_log_init():
        """开始一次新的日志：清空旧内容，写下版本信息。

        每次启动游戏都从零开始写，避免日志无限增长；
        热重载会让 init 重跑，所以用 session 做标记，
        保证同一次运行只清一次（重载前的记录不会丢）。
        """
        if not livetl_debug:
            return

        if livetl_state_get("livetl_log_started"):
            return

        livetl_state_set("livetl_log_started", True)

        try:
            path = os.path.join(renpy.config.gamedir, "livetl.log")

            with open(path, "w", encoding="utf-8") as f:
                f.write("LiveTL {} | {} | game: {}\n".format(
                    livetl_version,
                    renpy.version_string,
                    renpy.config.name,
                ))

                # 引擎自检：这几行说明当前引擎上哪些内部接口可用，
                # 报问题时先看它们，省去逐个猜版本差异（见 livetl_engine.rpy）。
                for line in livetl_engine_probe():
                    f.write(line + "\n")

                f.write("-" * 60 + "\n")
        except Exception:
            pass

    # 在最早能写文件的时机开好这次运行的日志
    livetl_log_init()

    def livetl_set_status(msg):
        """更新面板上的反馈文字，并记入日志。"""
        store.livetl_status = msg
        livetl_log("status: " + msg)

    def livetl_settings_sync():
        """把译者改过的设置回正到 store。

        设置记在 session（见 livetl_config.rpy 的说明），界面读的却是 store
        变量；剧情"回退（Back）"会把 store 变量按检查点回滚，所以这里每次交互
        开始时再写一遍 —— 字体、快捷键就不会被回退带走。没改过的项
        不碰，保持配置里的缺省值。
        """
        for action, config_name, _label in livetl_hotkey_actions:
            keysym = livetl_setting_get("hotkey_" + action)

            if keysym is not None:
                setattr(store, config_name, keysym)

        language = livetl_setting_get("language")

        if language is not None:
            store.livetl_language = language

        font = livetl_setting_get("font")

        if font is not None:
            store.livetl_font = font

        # "要不要显示设置界面"本身也是 session 状态，store 里只是它的镜像
        store.livetl_setup_pending = livetl_state_get(
            "livetl_setup_pending", store.livetl_setup_pending,
        )

    def livetl_restart():
        """让界面重新渲染一次。

        screen 的变量依赖跟踪看不到函数内部读的 store 变量，
        所以切换面板形态（设置 / 菜单 / 体检）之后要主动重启一次交互，
        否则界面会停在旧的分支上。
        """
        try:
            renpy.restart_interaction()
        except Exception:
            pass

    def livetl_game_input_active():
        """游戏自己正在等玩家输入吗。

        判断依据是标准的 input screen（renpy.input() 与 input 语句都走它）。
        这种时候插件必须让出键盘，否则两个输入框会互相抢焦点，
        输入法候选与回车都会失效。

        注意：游戏自己写在别的 screen 里的输入框（例如图库的搜索框）
        检测不到，那种情况下按 F8 手动折叠面板即可。
        """
        try:
            return renpy.get_screen("input") is not None
        except Exception:
            return False

    # 目标语言（名字、目录、项目侧的记录）都在 livetl_language.rpy 里：
    # 语言名是引擎名（translate 语句里的那个），目录是译文实际所在的 tl
    # 子目录，两者可以不一样，所以读写都要按目录走。这里只管"当前台词"。

    # ---------------------------------------------------------------------
    # 定位当前台词
    #
    # 这里只留语义包装：所有对引擎内部结构的访问都在 livetl_engine.rpy 里，
    # 详见该文件开头的结构约定。
    # ---------------------------------------------------------------------

    def livetl_current_id():
        """当前台词的翻译标识符；不在台词上时返回 None。"""
        return livetl_engine_current_tid()

    def livetl_parse_quoted(code_line):
        """从一行台词代码里取出引号中的文本；取不到时返回 None。"""
        found = re.findall(r'"((?:[^"\\]|\\.)*)"', code_line)
        if not found:
            return None
        return found[-1].replace('\\"', '"')

    # ---------------------------------------------------------------------
    # tl 文件读写
    # ---------------------------------------------------------------------

    def _livetl_file_block_value(path, header):
        """一个文件里某个块头的译文："" 是"有这条但译文为空"，None 是没有这条。"""
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                lines = f.read().split("\n")
        except Exception:
            return None

        for i, line in enumerate(lines):
            if line.rstrip() != header:
                continue

            # 块里第一条不是空行、不是注释的行就是译文
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if not s or s.startswith("#"):
                    continue
                return livetl_parse_quoted(lines[j])

            return None

        return None

    def _livetl_file_has_block(path, header):
        """文件里有没有这个块头（文件不在、读不了都算没有）。"""
        try:
            with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                for line in f:
                    if line.rstrip() == header:
                        return True
        except Exception:
            return False

        return False

    def livetl_entry_files(language, tid):
        """这条 tid 的译文在哪些文件里（按加载顺序，最早的在前）。

        引擎按加载顺序覆盖，所以"最后那个文件"才是画面上生效的那一份。
        先按官方布局推（tl/<目录>/<源脚本名>，语言涉及的每个目录各一份），
        都没命中时退回扫描结果 —— 有的游戏把所有译文塞在一个文件里。
        """
        header = "translate {} {}:".format(language, tid.replace(".", "_"))

        # 引擎自己登记的那份最权威（后加载的覆盖先加载的，有探针钉着）
        registered = livetl_engine_translation_file(language, tid)

        if registered:
            parts = registered.split("/")[1:]
            path = os.path.join(livetl_engine_tl_root(), *parts) if parts else ""

            if path and os.path.isfile(path) and _livetl_file_has_block(path, header):
                return [path]

        rv = []
        # 语言还没有目录时按官方规则用语言名当目录（第一次生成时建出来）
        dirs = livetl_language_dirs_of(language) or [language]

        for directory in dirs:
            path = livetl_engine_tl_path(language, tid, directory=directory)

            if path and (path not in rv) and _livetl_file_has_block(path, header):
                rv.append(path)

        if not rv:
            rv = list(livetl_scan_tl_entry_files(language).get(tid, []))

        return sorted(rv)

    def livetl_read_entry(language, tid):
        """读取这一句已有的译文；文件或条目不存在时返回 None。

        同一个语言散在多个目录里时，引擎按加载顺序取最后一份，这里也一样。
        """
        resolved, _directory, _note = livetl_resolve_language(language)
        language = resolved or str(language or "")

        header = "translate {} {}:".format(language, tid.replace(".", "_"))
        value = None

        for path in livetl_entry_files(language, tid):
            got = _livetl_file_block_value(path, header)

            if got is not None:
                # 后加载的覆盖先加载的
                value = got

        return value

    def livetl_write_entry(language, tid, text):
        """把译文写回 tl 文件中的这一条；文件里其它内容保持原样。

        位置规则：这一条已经有块时，改在那个块所在的文件里（多个时改生效的
        那一份，否则会被后加载的那份盖住）；还没有这条时才在新语言的主目录里
        新建。语言名与目录名不一致（tl/out/ 里放着 translate chinese）时，
        靠的就是这条规则。
        """
        # 语言名可能来自调用方（设置界面刚确认时传的是输入框里的值），这里再
        # 解析一次：写进别人翻译文件这种代价，一次都不该发生。
        resolved, directory, _note = livetl_resolve_language(language)
        language = resolved or str(language or "")

        paths = livetl_entry_files(language, tid)

        if paths:
            # 已经有这一条：改生效的那一份
            path = paths[-1]
        else:
            path = livetl_engine_tl_path(language, tid, directory=directory or language)

        if path is None:
            return None

        if not paths:
            return livetl_append_block(path, language, tid, text)

        header = "translate {} {}:".format(language, tid.replace(".", "_"))
        new_lines = livetl_engine_block_code(tid, text)

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                lines = f.read().split("\n")
        except Exception as e:
            livetl_log("write_entry: 读取失败 {!r}".format(e))
            return None

        idx = None
        for i, line in enumerate(lines):
            if line.rstrip() == header:
                idx = i
                break

        if idx is None:
            return livetl_append_block(path, language, tid, text)

        # 只替换块里的译文行，其余保持原样
        j = idx + 1
        k = 0
        while j < len(lines) and k < len(new_lines):
            s = lines[j].strip()
            if not s or s.startswith("#"):
                j += 1
                continue
            lines[j] = new_lines[k]
            k += 1
            j += 1

        written = livetl_write_lines(path, lines)

        if written:
            livetl_log("write_entry: {} <- {!r}".format(tid, text))

        return written

    def livetl_write_lines(path, lines):
        """把行写回文件：父目录按需创建，收尾必须有换行。

        收尾不补换行的话，之后再往这个文件里追加内容时新内容会和最后一行挤在
        一起（Ren'Py 能解析，但格式就乱了）。
        """
        dirname = os.path.dirname(path)

        if dirname and not os.path.isdir(dirname):
            os.makedirs(dirname)

        content = "\n".join(lines)
        if not content.endswith("\n"):
            content += "\n"

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            livetl_log("write file {}: {!r}".format(path, e))
            return None

        return path

    def livetl_append_block(path, language, tid, text):
        """按官方格式往文件末尾追加一个 translate 块；写不了时返回 None。

        `# 源文件:行号` + `# 原文` + 译文，与官方生成器写出来的块一致。
        原文取不到（不是默认语言里的台词）时不写：那样只会留下一个空块，
        而空块会让 Ren'Py 直接报错。
        """
        if not path:
            return None

        block = livetl_engine_block_code(tid)

        if not block:
            livetl_log("append block: 拿不到 {} 的原文，跳过".format(tid))
            return None

        lines = []

        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    lines = f.read().split("\n")
            except Exception as e:
                livetl_log("append block: 读取失败 {!r}".format(e))
                return None

        filename, linenumber = livetl_engine_source_location(tid)

        lines.append("")

        if filename:
            lines.append("# {}:{}".format(filename, linenumber))

        lines.append("translate {} {}:".format(language, tid.replace(".", "_")))
        lines.append("")

        for code in block:
            lines.append("    # " + code.strip())

        lines.extend(livetl_engine_block_code(tid, text))

        written = livetl_write_lines(path, lines)

        if written:
            livetl_log("append block: {} <- {!r} ({})".format(tid, text, path))

        return written

    # ---------------------------------------------------------------------
    # 生成模板与热重载
    # ---------------------------------------------------------------------

    # tl 里除了台词块，还有这几种特殊的 translate 块（它们不是台词）
    _livetl_special_translates = ("strings", "python", "style")

    def livetl_scan_tl_entry_files(language=None, force=False):
        """扫描这个语言的 tl 文件：{标识符: [文件, ...]}（文件按加载顺序）。

        只认 `translate <语言> <标识符>:` 这种台词块，
        `strings` / `python` / `style` 这类特殊块不算（那些在
        livetl_strings.rpy 的索引里）。语言涉及的所有目录都扫，所以目录名与
        语言名不一致、或者同一个语言散在多个目录时也能看全。
        结果缓存在 session 里（键里带各文件的 mtime/size，外部改过会自动重建），
        插件写完文件后由 livetl_invalidate_tl_indexes() 作废。
        """
        if language is None:
            language = livetl_target_language()

        files = livetl_iter_tl_files(language)
        stamp = []

        for path in files:
            try:
                st = os.stat(path)
                stamp.append((path, int(st.st_mtime), st.st_size))
            except Exception:
                pass

        cached = livetl_state_get("livetl_tl_entry_files")

        if (not force) and cached and (cached[0] == language) and (cached[1] == stamp):
            return cached[2]

        pattern = re.compile(r"^\s*translate\s+" + re.escape(str(language)) + r"\s+(\S+)\s*:\s*$")
        rv = {}

        for path in files:
            try:
                # 用 utf-8 读、手动去掉 BOM：不依赖 utf-8-sig（部分环境没有）
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            if content.startswith("\ufeff"):
                content = content[1:]

            for line in content.split("\n"):
                m = pattern.match(line)

                if (m is None) or (m.group(1) in _livetl_special_translates):
                    continue

                places = rv.setdefault(m.group(1), [])

                if path not in places:
                    places.append(path)

        for places in rv.values():
            places.sort()

        livetl_state_set("livetl_tl_entry_files", (language, stamp, rv))
        return rv

    def livetl_scan_tl_identifiers(language=None):
        """这个语言已经写过的台词标识符（集合）。"""
        return set(livetl_scan_tl_entry_files(language).keys())

    def livetl_invalidate_tl_indexes():
        """写回 / 生成 / 清理之后把 tl 相关的缓存全部作废。

        语言索引（哪些语言在哪些目录里）、台词 → 文件、字符串索引，三份都是
        从 tl 文件读出来的，改了文件就必须重建。
        """
        livetl_invalidate_language_index()
        livetl_state_pop("livetl_tl_entry_files", None)
        livetl_invalidate_string_index()

    def livetl_count_tl_entries(language=None):
        """tl/<语言>/ 里现有的条目数：台词块 + 字符串条目。

        增量生成前后各数一次，差值就是"这次补了多少条"。
        字符串条目数从字符串索引里取（同一份解析逻辑，不重复实现）。
        """
        if language is None:
            language = livetl_target_language()

        strings = 0

        # 索引按各文件的 (mtime, size) 缓存，生成前后会自动重建，
        # 这里不用强制重扫。
        for places in livetl_scan_string_index(language).values():
            strings += len(places)

        return len(livetl_scan_tl_identifiers(language)) + strings

    def livetl_seed_existing_entries(language=None):
        """把"tl 文件里已经有的条目"临时登记进引擎的翻译表。

        官方生成器判断"这条是不是已经有了"，看的是内存里的翻译表
        （引擎侧怎么读怎么写见 livetl_engine.rpy），而这张表只在游戏
        启动、脚本加载时由 tl 文件填充。本次运行中新写出来的 tl 文件不在
        表里，直接调用官方生成器会把它们当成新条目再写一遍 —— 已经翻好的
        内容会被空译文盖掉，还会留下让游戏启动报错的重复条目。

        所以生成前按"文件里实际存在的条目"补上占位登记，生成后由
        livetl_unseed_existing_entries() 原样撤掉，运行期行为不变。

        占位值统一用 None：官方生成器只看"键在不在表里"，而这个值正好是
        引擎自己用来表示"没有译文"的，万一生成期间有人查表也只会退回原文。
        """
        if language is None:
            language = livetl_target_language()

        identifiers = livetl_scan_tl_identifiers(language)
        says = []

        for identifier, alternate in livetl_engine_all_translate_ids():
            if livetl_engine_has_translation(identifier, language):
                continue

            # 写进文件时点号会换成下划线，比对时按文件里的写法
            written = [identifier]

            if alternate is not None:
                written.append(alternate)

            if not any(i.replace(".", "_") in identifiers for i in written):
                continue

            livetl_engine_seed_translation(identifier, language)
            says.append((identifier, language))

        strings = []

        for old in livetl_scan_string_index(language, force=True):
            if livetl_engine_has_string_translation(old, language):
                continue

            livetl_engine_seed_string_translation(old, language)
            strings.append(old)

        if says or strings:
            livetl_log("seed: tl 里已有 {} 条台词、{} 条字符串".format(len(says), len(strings)))

        return {"language": language, "says": says, "strings": strings}

    def livetl_unseed_existing_entries(seeded):
        """撤掉 livetl_seed_existing_entries() 塞进去的占位登记。"""
        if not seeded:
            return

        for identifier, language in seeded["says"]:
            livetl_engine_unseed_translation(identifier, language)

        for old in seeded["strings"]:
            livetl_engine_unseed_string_translation(old, seeded["language"])

    def livetl_generate_templates(language=None):
        """增量生成（补全）目标语言的翻译模板，返回处理的文件数（manual 时是条目数）。

        位置规则：
          * 官方生成器（Launcher 的「生成翻译」用的就是它）只会写
            tl/<语言名>/<源脚本名>；只有那个路径恰好就是语言的生效目录时
            才用它，产出与 Launcher 完全一致；
          * 生效目录是别处时（实测有游戏把 translate chinese 放在 tl/out/），
            官方生成器写不对地方，改由插件按同一套格式补空条目 —— 判定
            "缺哪些"仍用官方那套条件（见 livetl_engine.rpy 的 missing_*）。
        两条路径都是增量的：任何文件里已经有的条目都不会再生成一遍。
        """
        if language is None:
            language = livetl_target_language()
        else:
            resolved, _directory, _note = livetl_resolve_language(language)
            language = resolved or str(language or "")

        directory = livetl_language_dir_of(language) or language

        if livetl_official_generator_usable(language, directory):
            count = livetl_generate_templates_official(language)
        else:
            count = livetl_generate_templates_manual(language, directory)

        # 文件变了：三份索引都要重建；顺便清掉"只有表头、没有条目"的
        # strings 块（这种块会让 Ren'Py 直接报 "expects a non-empty block"，
        # 整个语言都加载不了）。
        livetl_invalidate_tl_indexes()
        livetl_drop_empty_string_blocks(language)

        livetl_engine_register_language(language)

        livetl_log("generate_templates: {} for {!r} (tl/{}/)".format(count, language, directory))
        return count

    def livetl_official_generator_usable(language, directory):
        """官方生成器能不能用：它的目标路径是不是就是这个语言的生效目录。

        新建语言时两边指向同一个待建目录（相等）；NTFS 默认不区分大小写时
        `tl/chinese` 与 `tl/Chinese` 也是同一个物理目录，靠 livetl_same_dir()
        问文件系统判断 —— 不靠"Windows 一定不区分大小写"这个印象。
        """
        if (not language) or (not directory) or (directory == language):
            return True

        return livetl_same_dir(livetl_language_path(language), livetl_language_path(directory))

    def livetl_generate_templates_official(language):
        """官方生成器补全 tl/<语言>/（产出的文件与 Launcher 一致）。"""
        # 官方生成器只看内存里的翻译表，而本次运行新写出来的 tl 文件不在表里：
        # 先补登记，生成完再撤掉（见 livetl_seed_existing_entries）。
        seeded = livetl_seed_existing_entries(language)

        try:
            # 对话统一生成空字符串（等同 Launcher 的"为翻译生成空字符串"）：
            # "未翻译时显示原文"由显示层处理，不写进文件。
            return livetl_engine_generate_templates(language)
        finally:
            livetl_unseed_existing_entries(seeded)

    def _livetl_append_todo(path):
        """按官方生成器的样子，在文件末尾加一行 TODO 溯源标记。"""
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write("# TO" + "DO: Translation updated at {}\n\n".format(
                    time.strftime("%Y-%m-%d %H:%M"),
                ))
        except Exception as e:
            livetl_log("todo marker: {!r}".format(e))

    def livetl_generate_templates_manual(language, directory):
        """按官方格式把缺的条目补进 tl/<directory>/，返回补上的条目数。

        只补"哪个文件里都还没有"的条目：已经有的（哪怕在别的目录里、
        或者是驱动器里别的脚本刚写出来的）一律不动，与官方生成器的增量规则
        一致。格式对齐官方：`# 文件:行号` + `# 原文` + 空译文，
        新写到的文件在第一个新条目前面加一行 TODO。
        """
        existing = livetl_scan_tl_entry_files(language, force=True)
        touched = set()
        added = 0

        for tid in livetl_engine_missing_translates(language):
            if tid in existing:
                # 已经在别的目录里了（引擎没登记，例如本次运行刚写出来的）
                continue

            path = livetl_engine_tl_path(language, tid, directory=directory)

            if path is None:
                continue

            if path not in touched:
                touched.add(path)
                _livetl_append_todo(path)

            # 直接追加：不要走 livetl_write_entry（那会为每条重新解析一次位置，
            # 大项目上是平方级开销）
            if livetl_append_block(path, language, tid, "") is not None:
                added += 1

        for old in livetl_engine_missing_strings(language):
            if livetl_lookup_string(old, language) is not None:
                continue

            if livetl_write_string_entry(old, old) is not None:
                added += 1

        livetl_log("generate_templates manual: {} entries into tl/{}/".format(added, directory))
        return added

    def livetl_ensure_templates():
        """启动后的第一次交互：为已经选定的语言做一次增量补全。

        两道闸门：
          * livetl_autocomplete_on_start = False —— 启动不碰文件，
            只在设置界面点【开始翻译】时生成；
          * 这个项目还没为这个语言补全过 —— 说明译者还没确认过目标语言，
            这时一个字都不该写进项目（设置界面会先问一次）。
        它挂在每次交互的开始处，所以再加一道"每次运行只跑一次"的闸门，
        否则每句台词都会重扫一遍项目。
        """
        if not livetl_autocomplete_on_start:
            return

        if livetl_state_get("livetl_autocomplete_done"):
            return

        if livetl_need_setup():
            return

        language = livetl_target_language()

        if not livetl_project_setup_done(language):
            return

        livetl_state_set("livetl_autocomplete_done", True)

        try:
            count = livetl_generate_templates(language)
        except Exception as e:
            # 生成失败的原因通常不是"下次就好了"（目录只读、磁盘满……）：
            # 提示留给译者。这里不写标记 —— 标记是"译者确认过"的凭据，
            # 写下去就等于把设置界面也一并挡掉了。
            livetl_log("autocomplete failed: {!r}".format(e))
            livetl_set_status("自动补全 tl/{}/ 失败：{}".format(language, e))
            return

        livetl_log("autocomplete: {!r} ({} files)".format(language, count))

    def livetl_reload():
        """触发热重载：保存进度 → 重新加载脚本 → 读回存档。

        注意：读档只会恢复"已经显示的那句话"，不会重新执行当前语句，
        所以画面仍停在旧文本上。这里记下当前句，等重载后的第一次
        交互开始时跳回这一句，用新译文重新渲染。
        """
        livetl_state_set("livetl_replay_tid", livetl_current_id())
        livetl_log("reload_script() tid={!r}".format(livetl_state_get("livetl_replay_tid")))
        renpy.reload_script()

    # ---------------------------------------------------------------------
    # 面板状态同步
    # ---------------------------------------------------------------------

    def livetl_menu_captions():
        """当前菜单里的所有文本（原文）。没有菜单时返回 None。

        Ren'Py 的 choice screen 把菜单的标题行和所有选项都以
        items 的形式传来，每项的 caption 就是源码里的原文
        （翻译发生在显示层，这里拿到的始终是原文）。
        """
        screen = renpy.get_screen("choice")

        if screen is None:
            return None

        items = screen.scope.get("items")

        if not items:
            return None

        rv = []

        for entry in items:
            caption = getattr(entry, "caption", None)

            if isinstance(caption, str) and caption.strip():
                rv.append(caption)

        return rv or None

    def livetl_menu_entry_of(caption, index=None):
        """菜单里的一条：原文、已有译文、状态。"""
        if index is None:
            index = livetl_scan_string_index()

        places = index.get(caption)

        if places:
            best = livetl_best_string_entry(caption, places)
            new = best[2]
            duplicated = len(places) > 1
        else:
            new = ""
            duplicated = False

        # 生成的模板里未翻译条目的 new 是原文（占位），对译者来说等同于没翻
        if new == caption:
            new = ""

        translated = bool(new) and (new != caption)

        return {
            "caption": caption,
            "new": new,
            "state": "已翻" if translated else "未翻",
            "dup": duplicated,
        }

    def livetl_menu_fill():
        """把当前选中项的译文填进输入框。"""
        items = store.livetl_menu_items

        if not items:
            store.livetl_current_kind = "say"
            store.livetl_current_key = None
            store.livetl_current_source = ""
            store.livetl_input = ""
            return

        idx = max(0, min(store.livetl_menu_index, len(items) - 1))
        store.livetl_menu_index = idx

        item = items[idx]
        store.livetl_current_kind = "string"
        store.livetl_current_key = item["caption"]
        store.livetl_current_source = item["caption"]

        # 只在"刚进入菜单 / 换了选中项"时刷新输入框。
        #
        # 这个函数被 livetl_menu_sync 每帧调用，如果每次都写 livetl_input，
        # 译者打的字会在下一帧被 tl 里的旧值覆盖（表现就是"输入不进去"）。
        focus_key = (idx, item["caption"])

        if livetl_state_get("livetl_menu_focus_key") != focus_key:
            livetl_state_set("livetl_menu_focus_key", focus_key)

            store.livetl_input = livetl_input_text(item["new"] or "")

    def livetl_menu_sync():
        """菜单出现或换了一个菜单时刷新面板；返回是否处于菜单模式。

        用 caption 列表做指纹：同一个菜单只重建一次列表，
        避免每次交互都重新扫描 tl 文件。
        """
        # 体检界面正在接管面板时不要抢（否则点【检查重复】会被立刻弹回去）
        if store.livetl_mode == "dup":
            return False

        captions = livetl_menu_captions()

        if captions is None:
            livetl_state_set("livetl_menu_key", None)
            livetl_state_set("livetl_menu_hold", False)
            # 菜单关掉之后要重置，否则下次进同一个菜单时
            # 会因为 key 相同而不刷新输入框
            livetl_state_set("livetl_menu_focus_key", None)
            store.livetl_mode = "say"
            store.livetl_menu_items = []
            store.livetl_menu_index = 0
            store.livetl_menu_count = 0
            return False

        key = tuple(captions)

        if key != livetl_state_get("livetl_menu_key"):
            livetl_state_set("livetl_menu_key", key)

            index = livetl_scan_string_index()
            store.livetl_menu_items = [livetl_menu_entry_of(c, index) for c in captions]
            store.livetl_menu_index = 0

        store.livetl_menu_count = len(store.livetl_menu_items)

        # 正在编辑拾取到的界面文本时不抢面板（点【回菜单】恢复）
        if livetl_state_get("livetl_menu_hold"):
            return True

        store.livetl_mode = "menu"
        livetl_menu_fill()
        return True

    def livetl_menu_back():
        """从单条编辑回到当前菜单的列表。"""
        if livetl_menu_captions() is None:
            livetl_set_status("当前没有菜单")
            return

        livetl_state_set("livetl_menu_hold", False)
        store.livetl_mode = "menu"
        livetl_menu_sync()

    def livetl_menu_row_text(index):
        """菜单列表里某一行的显示文本（在这里转义，screen 里不做复杂表达式）。

        行首序号要写成 [[1]：引擎把 [1] 当成插值去取"第 1 个位置参数"，
        而位置参数永远是空的 —— 8.1 上抛 IndexError 把面板渲染打断，
        8.5.3 上不报错但会把方括号吃掉，显示成 "1 原文 — 未翻"。
        """
        items = store.livetl_menu_items

        if not (0 <= index < len(items)):
            return ""

        item = items[index]
        note = item["state"]

        if item["dup"]:
            note += "（重复）"

        return "[[{}] {} — {}".format(index + 1, livetl_escape(item["caption"]), note)

    def livetl_menu_select(index):
        """点击菜单列表里的某一条。"""
        store.livetl_menu_index = index
        livetl_menu_fill()

    def livetl_menu_refresh(key=None):
        """写回之后刷新菜单列表里的状态（不重建整个列表）。"""
        if key is None:
            key = store.livetl_current_key

        if not key:
            return

        index = livetl_scan_string_index(force=True)

        for item in store.livetl_menu_items:
            if item["caption"] == key:
                fresh = livetl_menu_entry_of(key, index)
                item["new"] = fresh["new"]
                item["state"] = fresh["state"]
                item["dup"] = fresh["dup"]

    # ---------------------------------------------------------------------
    # 重复条目体检
    # ---------------------------------------------------------------------

    def livetl_dup_scan(switch=True):
        """扫描重复条目；switch 为真时切到体检界面。"""
        report = livetl_find_duplicate_strings()

        store.livetl_dup_report = sorted(report.items())
        store.livetl_dup_check_done = True

        if switch:
            store.livetl_mode = "dup"

        if store.livetl_dup_report:
            livetl_set_status("发现 {} 处重复条目".format(len(store.livetl_dup_report)))
        else:
            livetl_set_status("没有发现重复条目")

        return len(store.livetl_dup_report)

    def livetl_dup_open():
        """从面板/设置界面进入体检界面。"""
        store.livetl_visible = True
        livetl_state_set("livetl_visible", True)
        livetl_dup_scan()
        livetl_restart()

    def livetl_dup_rescan():
        """【重新扫描】按钮用。

        注意：作为 action 的函数**不能有返回值** —— 非 None 的返回值会被
        Ren'Py 当成交互结果，主菜单收到之后会直接结束（表现为"点一下
        就开始游戏"）。所以这里包一层，把 livetl_dup_scan() 的结果丢掉。
        """
        livetl_dup_scan()

    def livetl_dup_close():
        """退出体检界面，回到对话模式。"""
        store.livetl_mode = "say"
        store.livetl_dup_report = []
        livetl_sync()
        livetl_restart()

    def livetl_dup_clean():
        """清理重复条目（保留第一条），清理前自动备份。"""
        count, backup = livetl_clean_duplicate_strings()

        if count:
            livetl_set_status("已清理 {} 条重复条目（备份：{}），按重载生效".format(
                count, os.path.basename(backup) if backup else "无"))
        else:
            livetl_set_status("没有需要清理的条目")

        livetl_dup_scan(switch=False)

        if not store.livetl_dup_report:
            livetl_set_status(livetl_status + "；列表已清空")

    def livetl_dup_check_startup():
        """启动后的第一次交互里做一次查重，发现重复就提示（不改文件）。"""
        if (not livetl_dup_check_on_start) or store.livetl_dup_check_done:
            return

        store.livetl_dup_check_done = True

        try:
            count = livetl_dup_scan(switch=False)
        except Exception as e:
            livetl_log("startup dup check failed: {!r}".format(e))
            return

        if count:
            livetl_set_status("发现 {} 处重复条目，点【设置】→【检查重复】处理".format(count))

    def livetl_sync(tid=None, force=False):
        """刷新面板内容：当前句的原文，以及已有的译文。

        force 为真时忽略"tid 没变"的短路：菜单列表会把面板内容换成
        菜单项，这时切回对话必须强制刷新一次。
        """
        if tid is None:
            tid = livetl_current_id()

        # 菜单列表 / 体检界面正在接管面板时不覆盖它的内容
        if store.livetl_mode != "say":
            return

        if (not force) and (tid == store.livetl_current_tid) and store.livetl_current_source:
            return

        store.livetl_current_kind = "say"
        store.livetl_current_key = None
        store.livetl_current_tid = tid
        store.livetl_current_source = livetl_engine_source_text(tid) or ""

        # 输入框：已经有译文就填进去方便修改，没有就留空。
        existing = None
        if tid:
            existing = livetl_read_entry(livetl_target_language(), tid)

        store.livetl_input = livetl_input_text(existing or "")

        livetl_log("sync: tid={!r} source={!r} existing={!r}".format(tid, store.livetl_current_source, existing))

        # 这里不碰"焦点"：官方 Input 不是 focusable，set_focus() 对它是空转
        # （还会顺手清掉游戏那边的焦点）。译者能直接打字，靠的是面板挂在
        # overlay 层、按键先经过面板，见 livetl_engine_input.rpy 的 event()。

    def livetl_submit():
        """把输入框内容写回 tl 文件（不重载）。"""
        # 输入框里写的是 \n 这样的转义写法，写回文件前还原成实际字符
        text = livetl_unescape_input(store.livetl_input)

        if not text.strip():
            livetl_set_status("输入框是空的，没有写入")
            return

        # 菜单 / 界面字符串：写进 translate <语言> strings 条目
        if (store.livetl_current_kind == "string") and store.livetl_current_key:
            rel = livetl_write_string_entry(store.livetl_current_key, text)

            if rel:
                livetl_set_status("已写入 tl/{}（按重载生效）".format(rel))
                livetl_menu_refresh()
            else:
                livetl_set_status("写入失败，详见 livetl.log")

            return

        # 对话：写进对应语句的 translate 块
        tid = livetl_current_id()

        if not tid:
            livetl_set_status("当前没有可翻译的台词")
            return

        path = livetl_write_entry(livetl_target_language(), tid, text)
        if path:
            livetl_invalidate_tl_indexes()
            livetl_set_status("已写入 tl/{}（按重载生效）".format(
                os.path.relpath(path, livetl_engine_tl_root()).replace("\\", "/"),
            ))
        else:
            livetl_set_status("写入失败，详见 livetl.log")

    def livetl_clear_action():
        """【清空】的 action：按钮与快捷键共用，确认文案只有一处。"""
        return Confirm(
            "清空当前条目？\n对话只清掉译文；字符串条目会从 tl 里删除。",
            Function(livetl_clear_entry),
        )

    def livetl_clear_entry():
        """清空当前条目。

        * 对话：把译文写成空串。translate 块的结构由源码决定，
          删不掉也不该删，能清掉的是里面的译文。
        * 字符串条目：从 tl 里整条删掉。字符串没有"空值"的安全写法
          （空译文会让菜单项变成不可点的空按钮）。
        """
        if (store.livetl_current_kind == "string") and store.livetl_current_key:
            rel = livetl_delete_string_entry(store.livetl_current_key)

            if rel:
                store.livetl_input = ""
                livetl_set_status("已删除字符串条目（{}）".format(rel))
                livetl_menu_refresh()
            else:
                livetl_set_status("没有找到可删除的条目")

            return

        tid = livetl_current_id()

        if not tid:
            livetl_set_status("当前没有可清空的台词")
            return

        path = livetl_write_entry(livetl_target_language(), tid, "")

        if path:
            livetl_invalidate_tl_indexes()
            store.livetl_input = ""
            livetl_set_status("已清空这一句的译文（按重载生效）")
        else:
            livetl_set_status("清空失败，详见 livetl.log")


init 10 python:

    # ---------------------------------------------------------------------
    # 显示层：未翻译的句子显示原文
    #
    # tl 文件里未翻译的条目一律是空串（干净、一眼可辨）。
    # 游戏里则照常读到原文：在这里于渲染阶段把空译文顶回原文 —— 不改动 tl 文件。
    # （以前这是个可选项"留空 / 显示原文"，0.5.0 起固定为显示原文：菜单选项与
    # 界面文本走的是 translate strings 条目，生成时写的就是原文，留空只把对白
    # 抹成空白，同一个场景里两套表现。）
    # ---------------------------------------------------------------------
    _livetl_prev_say_filter = config.say_menu_text_filter

    def _livetl_untranslated_filter(what):
        if _livetl_prev_say_filter is not None:
            what = _livetl_prev_say_filter(what)

        # 已经翻过（有内容）就原样显示
        if what and what.strip():
            return what

        # 没翻过：用原文顶上
        tid = livetl_current_id()
        if not tid:
            return what

        return livetl_engine_source_text(tid) or what

    config.say_menu_text_filter = _livetl_untranslated_filter
