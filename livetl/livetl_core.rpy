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

    # ---------------------------------------------------------------------
    # 运行状态（界面会读取这些值）
    # ---------------------------------------------------------------------

    # 当前台词的信息
    livetl_current_tid = None       # 翻译标识符
    livetl_current_source = ""      # 原文

    # 面板输入框绑定的内容
    livetl_input = ""

    # 最近一次操作的反馈文字
    livetl_status = ""

    # 面板是否展开。
    # 放在 session 里：Ren'Py 的"回退（Back）"会回滚 store 变量，
    # 而面板的显示状态是界面状态，不应该跟着剧情一起回退。
    livetl_visible = renpy.session.setdefault("livetl_visible", True)

    # 是否需要在下一个交互开始时把焦点放进输入框
    livetl_focus_pending = False

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

        if renpy.session.get("livetl_log_started"):
            return

        renpy.session["livetl_log_started"] = True

        try:
            path = os.path.join(renpy.config.gamedir, "livetl.log")

            with open(path, "w", encoding="utf-8") as f:
                f.write("LiveTL {} | {} | game: {}\n".format(
                    livetl_version,
                    renpy.version_string,
                    renpy.config.name,
                ))
                f.write("-" * 60 + "\n")
        except Exception:
            pass

    # 在最早能写文件的时机开好这次运行的日志
    livetl_log_init()

    def livetl_set_status(msg):
        """更新面板上的反馈文字，并记入日志。"""
        store.livetl_status = msg
        livetl_log("status: " + msg)

    def livetl_target_language():
        """当前选定的目标语言（优先取引导时保存的选择）。"""
        return persistent.livetl_language or livetl_language

    def livetl_set_language(language):
        """记录目标语言选择。"""
        persistent.livetl_language = language
        livetl_log("language set to {!r}".format(language))

    # ---------------------------------------------------------------------
    # 定位当前台词
    # ---------------------------------------------------------------------

    def livetl_current_id():
        """当前台词的翻译标识符；不在台词上时返回 None。"""
        try:
            return renpy.get_translation_identifier()
        except Exception:
            return None

    def livetl_lookup_node(tid):
        """当前语言下这一句实际执行的节点。

        Ren'Py 8.5 起 lookup_translate 返回 (节点, 是否已有译文)，
        8.1 只返回节点，这里统一成节点。
        """
        if not tid:
            return None

        rv = renpy.game.script.translator.lookup_translate(tid)
        if isinstance(rv, tuple):
            return rv[0]
        return rv

    def livetl_block_nodes(node):
        """取出一个翻译块包含的 AST 节点。

        Ren'Py 8.5 起单句对话是 TranslateSay 节点，
        更早的版本是 Translate 节点包着一个块。
        """
        translate_say = getattr(renpy.ast, "TranslateSay", None)
        if translate_say is not None and isinstance(node, translate_say):
            return [node]
        return node.block

    def livetl_find_source(tid):
        """从默认语言节点里读出这一句的原文。"""
        if not tid:
            return None

        node = renpy.game.script.translator.default_translates.get(tid)
        if node is None:
            return None

        for n in livetl_block_nodes(node):
            if isinstance(n, renpy.ast.Say):
                return n.what

        return None

    def livetl_block_code(node, text=None):
        """生成翻译块里的代码行。

        text 为 None 时输出原文（用作 # 注释行），否则输出译文行。
        生成结果与 Ren'Py 官方 tl 格式一致。
        """
        rv = []

        for n in livetl_block_nodes(node):
            if (text is not None) and isinstance(n, renpy.ast.Say):
                rv.append("    " + n.get_code(lambda s: text))
            else:
                rv.append("    " + n.get_code())

        return rv

    def livetl_parse_quoted(code_line):
        """从一行台词代码里取出引号中的文本；取不到时返回 None。"""
        found = re.findall(r'"((?:[^"\\]|\\.)*)"', code_line)
        if not found:
            return None
        return found[-1].replace('\\"', '"')

    # ---------------------------------------------------------------------
    # tl 文件读写
    # ---------------------------------------------------------------------

    def livetl_tl_path(language, tid):
        """这一句的译文应当写进哪个 tl 文件。"""
        from renpy.translation import generation as gen

        node = renpy.game.script.translator.default_translates.get(tid)
        if node is None:
            return None

        fn, common = gen.shorten_filename(node.filename)
        if common:
            return None

        # .rpym 的翻译按 .rpy 存放，与官方生成逻辑保持一致
        if fn.endswith("m"):
            fn = fn[:-1]

        return os.path.join(renpy.config.gamedir, renpy.config.tl_directory, language, fn)

    def livetl_read_entry(language, tid):
        """读取这一句已有的译文；文件或条目不存在时返回 None。"""
        path = livetl_tl_path(language, tid)
        if not path or not os.path.exists(path):
            return None

        header = "translate {} {}:".format(language, tid.replace(".", "_"))

        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.read().split("\n")

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

    def livetl_write_entry(language, tid, text):
        """把译文写回 tl 文件中的这一条；文件里其它内容保持原样。"""
        node = renpy.game.script.translator.default_translates.get(tid)
        if node is None:
            return None

        path = livetl_tl_path(language, tid)
        if path is None:
            return None

        new_lines = livetl_block_code(node, text)
        header = "translate {} {}:".format(language, tid.replace(".", "_"))

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                lines = f.read().split("\n")
        else:
            lines = []

        idx = None
        for i, line in enumerate(lines):
            if line.rstrip() == header:
                idx = i
                break

        if idx is None:
            # 文件里还没有这一条：按官方格式追加一个块
            lines.append("")
            lines.append("# {}:{}".format(node.filename, node.linenumber))
            lines.append(header)
            lines.append("")
            for code in livetl_block_code(node):
                lines.append("    # " + code.strip())
            lines.extend(new_lines)
        else:
            # 已经有了这一条：只替换块里的译文行
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

        dirname = os.path.dirname(path)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

        # 收尾必须是换行：否则之后再往这个文件里追加内容时，
        # 新内容会和最后一行挤在一起（Ren'Py 虽然能解析，但格式就乱了）。
        content = "\n".join(lines)
        if not content.endswith("\n"):
            content += "\n"

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        livetl_log("write_entry: {} <- {!r}".format(tid, text))
        return path

    # ---------------------------------------------------------------------
    # 生成模板与热重载
    # ---------------------------------------------------------------------

    def livetl_generate_templates(language=None):
        """生成（或补全）tl/<语言>/ 下的标准翻译模板。

        直接复用 Ren'Py 自带的翻译生成逻辑，
        所以产出的文件与 Launcher 里「生成翻译」完全一致：
        每个脚本一个文件、每句对话一个 translate 块、原文写在 # 注释里。
        """
        if language is None:
            language = livetl_target_language()

        from renpy.translation import generation as gen

        # 对话统一生成空字符串（等同 Launcher 的"为翻译生成空字符串"）：
        # "未翻译时显示原文"由显示层处理，不写进文件。
        count = 0
        for filename in gen.translate_list_files():
            gen.write_translates(filename, language, gen.empty_filter)
            count += 1

        # 界面字符串和菜单选项保留原文：
        # 它们如果也是空的，切到新语言后按钮会变成空白，译者没法操作。
        #
        # 只在还没有这个语言的字符串文件时才写：Ren'Py 对重复的字符串翻译
        # 会直接报错（"A translation for ... already exists"），
        # 而 tl 一旦生成过，文件里已经包含这些条目了。
        strings_path = os.path.join(
            renpy.config.gamedir,
            renpy.config.tl_directory,
            language,
            "common.rpy",
        )

        if not os.path.exists(strings_path):
            gen.write_strings(language, gen.null_filter, 0, 299, False, [])

        gen.close_tl_files()

        renpy.game.script.translator.languages.add(language)

        livetl_log("generate_templates: scanned {} files for {!r}".format(count, language))
        return count

    def livetl_mark_path(language):
        """模板补全标记的位置。

        标记写在项目自己的 tl/<语言>/ 目录里，而不是 persistent：
        persistent 是存档目录（多个项目可能共用），
        而 tl 目录是每个游戏独立的。
        """
        return os.path.join(
            renpy.config.gamedir,
            renpy.config.tl_directory,
            language,
            ".livetl_generated",
        )

    def livetl_mark_templates_done(language):
        """记下"这个项目的这个语言已经补全过模板"。"""
        try:
            path = livetl_mark_path(language)
            dirname = os.path.dirname(path)

            if not os.path.isdir(dirname):
                os.makedirs(dirname)

            with open(path, "w", encoding="utf-8") as f:
                f.write("LiveTL: translation templates generated for {}\n".format(language))
        except Exception:
            pass

    def livetl_ensure_templates():
        """确保当前项目里，目标语言的整套翻译模板已经生成过。

        每个项目只补全一次（靠 tl 目录里的标记文件判断）；
        官方生成逻辑本身是幂等的，已经翻好的条目不会被覆盖。
        想重新补全（例如剧本更新了）删掉那个标记文件即可。
        """
        language = livetl_target_language()

        if not language:
            return

        if os.path.exists(livetl_mark_path(language)):
            return

        count = livetl_generate_templates(language)
        livetl_mark_templates_done(language)
        livetl_log("ensure_templates: {!r} ({} files)".format(language, count))

    def livetl_reload():
        """触发热重载：保存进度 → 重新加载脚本 → 读回存档。

        注意：读档只会恢复"已经显示的那句话"，不会重新执行当前语句，
        所以画面仍停在旧文本上。这里记下当前句，等重载后的第一次
        交互开始时跳回这一句，用新译文重新渲染。
        """
        renpy.session["livetl_replay_tid"] = livetl_current_id()
        livetl_log("reload_script() tid={!r}".format(renpy.session["livetl_replay_tid"]))
        renpy.reload_script()

    # ---------------------------------------------------------------------
    # 面板状态同步
    # ---------------------------------------------------------------------

    def livetl_sync(tid=None):
        """刷新面板内容：当前句的原文，以及已有的译文。"""
        if tid is None:
            tid = livetl_current_id()

        if tid == livetl_current_tid and store.livetl_current_source:
            return

        store.livetl_current_tid = tid
        store.livetl_current_source = livetl_find_source(tid) or ""

        # 输入框：已经有译文就填进去方便修改，没有就留空。
        existing = None
        if tid:
            existing = livetl_read_entry(livetl_target_language(), tid)

        store.livetl_input = existing or ""

        livetl_log("sync: tid={!r} source={!r} existing={!r}".format(tid, store.livetl_current_source, existing))

        # 标记"下一次交互开始时聚焦输入框"。
        # 这里不能直接 set_focus：此刻面板还没显示，聚焦会失败；
        # 真正的聚焦在 livetl_ensure_panel 里做。
        # 这样译者可以直接打字，不必用鼠标点输入框
        # （点击输入框会穿透到游戏，把对话推进一句）。
        store.livetl_focus_pending = True

    def livetl_submit():
        """把输入框内容写回 tl 文件（不重载）。"""
        tid = livetl_current_id()
        if not tid:
            livetl_set_status("当前没有可翻译的台词")
            return

        text = store.livetl_input
        if not text.strip():
            livetl_set_status("输入框是空的，没有写入")
            return

        path = livetl_write_entry(livetl_target_language(), tid, text)
        if path:
            livetl_set_status("已写入 " + os.path.basename(path) + "（按重载生效）")
        else:
            livetl_set_status("写入失败，详见 livetl.log")


init 10 python:

    # ---------------------------------------------------------------------
    # 显示层：未翻译的句子怎么显示
    #
    # tl 文件里未翻译的条目一律是空串（干净、一眼可辨）。
    # 译者如果希望在游戏里照常读到原文，就在这里于渲染阶段
    # 把空译文顶回原文 —— 不改动 tl 文件。
    # ---------------------------------------------------------------------
    _livetl_prev_say_filter = config.say_menu_text_filter

    def _livetl_untranslated_filter(what):
        if _livetl_prev_say_filter is not None:
            what = _livetl_prev_say_filter(what)

        # 已经翻过（有内容）就原样显示
        if what and what.strip():
            return what

        if not livetl_show_source_when_empty:
            return what

        # 没翻过：用原文顶上
        tid = livetl_current_id()
        if not tid:
            return what

        return livetl_find_source(tid) or what

    config.say_menu_text_filter = _livetl_untranslated_filter
