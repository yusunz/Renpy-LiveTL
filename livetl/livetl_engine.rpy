# =============================================================================
# LiveTL —— 引擎隔离层
#
# 本文件是唯一允许直接访问 Ren'Py 内部结构的文件。
#
# 插件要读台词原文、生成 tl 模板、查引擎的翻译表、在渲染树上做拾取，
# 这些能力 Ren'Py 没有全部提供公开 API，只能使用内部结构。
# 把这类调用集中在这里，引擎升级时的改动面就只有一个文件；
# 其它文件只认下面的函数名，名字与语义不随引擎版本变化。
#
# 结构约定（改动前先读）
#   1. 契约层：本文件的 livetl_engine_* 函数就是对外契约。
#      其它文件只调用它们，不关心内部怎么实现。
#   2. 适配层：版本差异、getattr 探测、引擎内部结构的访问只写在本文件里。
#      每个函数遇到问题一律返回空值（None / [] / {}），并把原因记进
#      livetl_engine_last_error()，不把异常抛给游戏。
#   3. 拆分规则：某组能力的适配代码超过约 50 行，或需要区分 3 个以上引擎
#      版本时，把这组函数整体拆到 livetl_engine_<能力>.rpy（例如
#      livetl_engine_pick.rpy），本文件保留同名函数转发过去。
#      按能力拆文件，不按版本号拆文件：Ren'Py 的差异是"某个接口从某版起
#      才有"，按版本号拆会让同一处逻辑散在两个文件里，改一次要动两处。
#   4. 门禁：其它文件里出现 renpy.game. / renpy.ast. / renpy.display.interface /
#      renpy.translation.generation / renpy.translation.scanstrings / translator.
#      会被 tools/check_engine_seam.ps1 拦下，提交前跑一次。
#
# 公开 API 不走这一层：renpy.get_screen / renpy.session / renpy.reload_script /
# renpy.config.* / config.* / persistent 等文档里有承诺的接口，直接调用即可。
# =============================================================================

init -90 python:
    import builtins
    import os

    # 最近一次适配层失败的描述，供日志排查（不参与任何判断逻辑）
    _livetl_engine_last_error = ""

    def livetl_engine_note_error(where, error):
        """记下适配层在哪里、因为什么失败。"""
        global _livetl_engine_last_error

        try:
            _livetl_engine_last_error = "{}: {!r}".format(where, error)
        except Exception:
            _livetl_engine_last_error = str(where)

    def livetl_engine_last_error():
        """最近一次适配层失败的描述；没有失败时是空串。"""
        return _livetl_engine_last_error

    # ---------------------------------------------------------------------
    # 适配层：引擎内部结构的基本入口
    #
    # 这几个函数只负责"拿到引擎对象"，判断逻辑留给下面的契约层。
    # ---------------------------------------------------------------------

    def _livetl_engine_ast_class(name):
        """取 renpy.ast 里的节点类（Say / TranslateSay 等）；取不到返回 None。"""
        try:
            return getattr(renpy.ast, name, None)
        except Exception:
            return None

    def _livetl_engine_translator():
        """引擎的脚本翻译器；取不到返回 None。"""
        try:
            return renpy.game.script.translator
        except Exception:
            return None

    def _livetl_engine_default_node(tid):
        """默认语言下这条 tid 对应的翻译节点；取不到返回 None。"""
        if not tid:
            return None

        translator = _livetl_engine_translator()

        if translator is None:
            return None

        try:
            return translator.default_translates.get(tid)
        except Exception:
            return None

    def _livetl_engine_block_nodes(node):
        """一个翻译块包含的 AST 节点。

        Ren'Py 8.5 起单句对话是 TranslateSay 节点（它是 Say 的子类），
        更早的版本是 Translate 节点包着一个 block。
        """
        if node is None:
            return []

        translate_say = _livetl_engine_ast_class("TranslateSay")

        if (translate_say is not None) and isinstance(node, translate_say):
            return [node]

        return list(getattr(node, "block", None) or [])

    def _livetl_engine_string_table(language):
        """引擎里这个语言的字符串翻译表；取不到返回 None。

        引擎用 defaultdict 存放，取值本身不会报错，但语言不存在时会顺带
        建出一张空表，所以调用方不要用它判断"语言是否存在"。
        """
        translator = _livetl_engine_translator()

        if translator is None:
            return None

        try:
            return translator.strings[language].translations
        except Exception:
            return None

    def _livetl_engine_shorten_filename(filename):
        """把绝对路径压成相对游戏目录的路径，返回 (文件名, 是否公共目录)。

        直接复用官方 generation.shorten_filename()：公共目录（renpy/common/）
        里的对话不生成翻译，这个判断必须与官方一致。
        """
        try:
            from renpy.translation import generation as gen
            return gen.shorten_filename(filename)
        except Exception as e:
            livetl_engine_note_error("shorten_filename", e)
            return None

    # ---------------------------------------------------------------------
    # 契约层：定位台词与翻译数据
    # ---------------------------------------------------------------------

    def livetl_engine_current_tid():
        """当前台词的翻译标识符；不在台词上时返回 None。"""
        try:
            return renpy.get_translation_identifier()
        except Exception as e:
            livetl_engine_note_error("current_tid", e)
            return None

    def livetl_engine_source_text(tid):
        """这条 tid 的原文；取不到返回 None。"""
        say = _livetl_engine_ast_class("Say")

        if say is None:
            return None

        for n in _livetl_engine_block_nodes(_livetl_engine_default_node(tid)):
            if isinstance(n, say):
                return n.what

        return None

    def livetl_engine_source_location(tid):
        """这条 tid 在源码里的位置 (文件名, 行号)；取不到返回 (None, None)。"""
        node = _livetl_engine_default_node(tid)

        if node is None:
            return (None, None)

        return (getattr(node, "filename", None), getattr(node, "linenumber", None))

    def livetl_engine_block_code(tid, text=None):
        """生成 translate 块里的代码行。

        text 为 None 时输出原文（写进 `#` 注释行），否则输出译文行。
        生成结果与 Ren'Py 官方 tl 格式一致。
        """
        say = _livetl_engine_ast_class("Say")
        rv = []

        for n in _livetl_engine_block_nodes(_livetl_engine_default_node(tid)):
            if (text is not None) and (say is not None) and isinstance(n, say):
                rv.append("    " + n.get_code(lambda s: text))
            else:
                rv.append("    " + n.get_code())

        return rv

    def livetl_engine_tl_path(language, tid):
        """这条译文应当写进哪个 tl 文件；定位不到时返回 None。"""
        node = _livetl_engine_default_node(tid)

        if node is None:
            return None

        filename = getattr(node, "filename", None)

        if not filename:
            return None

        shortened = _livetl_engine_shorten_filename(filename)

        if shortened is None:
            return None

        fn, common = shortened

        if common:
            return None

        # .rpym 的翻译按 .rpy 存放，与官方生成逻辑保持一致
        if fn.endswith("m"):
            fn = fn[:-1]

        try:
            return os.path.join(
                renpy.config.gamedir,
                renpy.config.tl_directory,
                language,
                fn,
            )
        except Exception as e:
            livetl_engine_note_error("tl_path", e)
            return None

    def livetl_engine_replay_label(tid):
        """当前语言下这一句实际执行到的块名；取不到返回 None。

        热重载后要靠这个名字跳回刚才那一句。
        Ren'Py 8.5 起 lookup_translate() 返回 (节点, 是否已有译文)，
        8.1 只返回节点，这里统一成节点。
        """
        translator = _livetl_engine_translator()

        if translator is None:
            return None

        try:
            rv = translator.lookup_translate(tid)
        except Exception as e:
            livetl_engine_note_error("replay_label", e)
            return None

        node = rv[0] if isinstance(rv, tuple) else rv
        return getattr(node, "name", None)

    # ---------------------------------------------------------------------
    # 契约层：官方生成器（模板与字符串）
    # ---------------------------------------------------------------------

    def livetl_engine_translate_files():
        """官方"要生成翻译的源文件"清单（去掉重复项）。

        config.translate_files 与自动扫描可能重叠，同一个文件出现两次时，
        一轮生成会把它的每个翻译块写两遍 —— 而重复条目会让游戏启动报错。
        """
        try:
            from renpy.translation import generation as gen
            filenames = gen.translate_list_files()
        except Exception as e:
            livetl_engine_note_error("translate_files", e)
            filenames = []

        rv = []
        seen = set()

        for filename in filenames:
            try:
                key = os.path.normpath(os.path.abspath(filename))
            except Exception:
                key = filename

            if key in seen:
                continue

            seen.add(key)
            rv.append(filename)

        return rv

    def livetl_engine_generate_templates(language):
        """调用官方生成器补全 tl/<语言>/ 模板，返回处理的源文件数。

        产出与 Launcher 的「生成翻译」一致：每个脚本一个文件、每句对话一个
        translate 块、原文写在 `#` 注释里；已经登记过的条目会跳过。
        界面字符串条目保留原文（空译文会让菜单项变成不可点的空按钮）。
        """
        from renpy.translation import generation as gen

        # `# TODO: Translation updated at ...` 由官方生成器写，官方默认开着；
        # 这里写明，免得被进程里别的调用改掉。
        gen.todo = True

        count = 0

        try:
            for filename in livetl_engine_translate_files():
                gen.write_translates(filename, language, gen.empty_filter)
                count += 1

            gen.write_strings(language, gen.null_filter, 0, 299, False, [])
        finally:
            gen.close_tl_files()

        return count

    def livetl_engine_string_file_map():
        """界面字符串 → 官方归属文件（Launcher 生成翻译时会写进的那个文件）。

        返回 {原文: 文件名}；引擎接口不可用时返回已扫描到的结果或空字典。
        """
        try:
            from renpy.translation import scanstrings, generation
        except Exception as e:
            livetl_engine_note_error("string_file_map/import", e)
            return {}

        rv = {}

        try:
            for s in scanstrings.scan(0, 299, False):
                if s.text not in rv:
                    rv[s.text] = generation.translation_filename(s)
        except Exception as e:
            livetl_engine_note_error("string_file_map/scan", e)

        return rv

    # ---------------------------------------------------------------------
    # 契约层：引擎翻译表（生成模板时的占位登记）
    #
    # 官方生成器判断"这条是不是已经有了"，看的是内存里的翻译表，而这张表
    # 只在游戏启动、脚本加载时由 tl 文件填充：本次运行中新写出来的 tl 文件
    # 不在表里，直接调用官方生成器会把它们当成新条目再写一遍 —— 已经翻好的
    # 内容会被空译文盖掉，还会留下让游戏启动报错的重复条目。
    # 所以生成前临时登记占位，生成后再撤掉。
    # ---------------------------------------------------------------------

    def livetl_engine_all_translate_ids():
        """全部台词条目 [(identifier, alternate), ...]；没有 alternate 时为 None。"""
        translator = _livetl_engine_translator()

        if translator is None:
            return []

        try:
            files = translator.file_translates
        except Exception as e:
            livetl_engine_note_error("all_translate_ids", e)
            return []

        rv = []

        for filename in livetl_engine_translate_files():
            try:
                entries = files[filename]
            except Exception:
                continue

            for _label, node in entries:
                identifier = getattr(node, "identifier", None)

                if identifier:
                    rv.append((identifier, getattr(node, "alternate", None)))

        return rv

    def livetl_engine_has_translation(identifier, language):
        """引擎的翻译表里有没有这条台词。"""
        translator = _livetl_engine_translator()

        if translator is None:
            return False

        try:
            return (identifier, language) in translator.language_translates
        except Exception:
            return False

    def livetl_engine_seed_translation(identifier, language):
        """临时登记一条占位台词译文（None 在引擎里就表示"还没有译文"）。"""
        translator = _livetl_engine_translator()

        if translator is None:
            return

        try:
            translator.language_translates[(identifier, language)] = None
        except Exception as e:
            livetl_engine_note_error("seed_translation", e)

    def livetl_engine_unseed_translation(identifier, language):
        """撤掉 livetl_engine_seed_translation() 塞进去的占位登记。"""
        translator = _livetl_engine_translator()

        if translator is None:
            return

        try:
            translator.language_translates.pop((identifier, language), None)
        except Exception:
            pass

    def livetl_engine_has_string_translation(old, language):
        """引擎的字符串翻译表里有没有这条。"""
        translations = _livetl_engine_string_table(language)

        if translations is None:
            return False

        return old in translations

    def livetl_engine_seed_string_translation(old, language):
        """临时登记一条占位字符串译文。"""
        translations = _livetl_engine_string_table(language)

        if translations is None:
            return

        try:
            translations[old] = None
        except Exception as e:
            livetl_engine_note_error("seed_string_translation", e)

    def livetl_engine_unseed_string_translation(old, language):
        """撤掉 livetl_engine_seed_string_translation() 塞进去的占位登记。"""
        translations = _livetl_engine_string_table(language)

        if translations is None:
            return

        try:
            translations.pop(old, None)
        except Exception:
            pass

    def livetl_engine_register_language(language):
        """让引擎把 <language> 当成已知语言。

        官方生成器（add_string_translation）内部也这么做，没有公开 API 可用。
        """
        translator = _livetl_engine_translator()

        if translator is None:
            return

        try:
            translator.languages.add(language)
        except Exception as e:
            livetl_engine_note_error("register_language", e)

    # ---------------------------------------------------------------------
    # 契约层：渲染层（拾取模式）
    # ---------------------------------------------------------------------

    def livetl_engine_displayables_at(x, y):
        """鼠标位置下的 displayable 链，每项是 (depth, w, h, displayable)。

        引擎自己的 Displayable Inspector 用的就是这个接口。
        拿不到渲染树时返回 []。
        """
        try:
            interface = renpy.display.interface
        except Exception:
            return []

        if interface is None:
            # 初始化阶段还没有界面对象（引擎是在 init 之后才创建它的）
            livetl_engine_note_error("displayables_at", "渲染接口尚未创建")
            return []

        tree = getattr(interface, "surftree", None)

        if tree is None:
            # 界面还没绘制过：例如交互刚重启、重载之后的瞬间
            livetl_engine_note_error("displayables_at", "当前没有渲染树")
            return []

        try:
            return tree.main_displayables_at_point(
                int(x), int(y), renpy.config.layers
            )
        except Exception as e:
            livetl_engine_note_error("displayables_at", e)
            return []

    def livetl_engine_is_text_displayable(d):
        """这个 displayable 是不是文本。"""
        return hasattr(d, "text_parameter")

    def livetl_engine_text_source(d):
        """文本 displayable 的原文（替换前的文本）；取不到返回 None。

        这里必须用 builtins.list / builtins.str 判断：Ren'Py 的 store 里
        list 被换成了可回滚版本，而 text_parameter 是引擎内部创建的内置
        list，用 store 的 list 判断会失败。
        """
        v = getattr(d, "text_parameter", None)

        if isinstance(v, (builtins.list, builtins.tuple)):
            v = "".join([i for i in v if isinstance(i, builtins.str)])

        if isinstance(v, builtins.str) and v.strip():
            return v

        return None

    def livetl_engine_displayable_location(d):
        """这个 displayable 在源码里的位置；取不到返回 None。"""
        return getattr(d, "_location", None)

    # ---------------------------------------------------------------------
    # 契约层：交互层
    # ---------------------------------------------------------------------

    def livetl_engine_underlay_suppressed():
        """引擎当前是否抑制 underlay。

        启动阶段的性能测试会同时抑制 underlay 与 overlay，插件要避开它，
        不能在那时显示面板。
        """
        try:
            return bool(renpy.display.interface.suppress_underlay)
        except Exception:
            return False

    # ---------------------------------------------------------------------
    # 契约层：启动自检
    # ---------------------------------------------------------------------

    def _livetl_engine_can_import(module_name):
        """这个引擎模块能不能导入（用于自检报告）。"""
        try:
            __import__(module_name)
            return True
        except Exception:
            return False

    def livetl_engine_probe():
        """把引擎版本与各内部接口的可用性写成几行文本。

        这几行会写进 livetl.log 的开头：用户报问题时要的第一份材料就是它，
        不用再逐个猜"这个引擎上哪个接口不存在"。

        注意：本函数在 init 阶段就会被调用，那时引擎还没创建界面对象，
        所以渲染相关的项只能报"初始化阶段：还没有"（pending），
        真正能不能用由 livetl_engine_displayables_at() 在运行时决定。
        """
        def flag(value):
            return "yes" if value else "no"

        interface = getattr(renpy.display, "interface", None)

        if interface is None:
            render = "pending"
        else:
            render = flag(getattr(interface, "surftree", None) is not None)

        return [
            "engine: {} | version_tuple={}".format(
                getattr(renpy, "version_string", "unknown"),
                getattr(renpy, "version_tuple", None),
            ),
            "engine seam: translator={} translate_say={} translation_info={}".format(
                flag(_livetl_engine_translator() is not None),
                flag(_livetl_engine_ast_class("TranslateSay") is not None),
                flag(hasattr(renpy, "get_translation_info")),
            ),
            "engine seam: generation={} scanstrings={} interface={}".format(
                flag(_livetl_engine_can_import("renpy.translation.generation")),
                flag(_livetl_engine_can_import("renpy.translation.scanstrings")),
                render,
            ),
        ]
