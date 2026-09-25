# =============================================================================
# LiveTL —— 目标语言
#
# 语言的身份是 `translate <语言> <id>:` / `translate <语言> strings:` 里的那个
# 名字：引擎按它登记和查找译文（translator.language_translates 的键、
# known_languages()、change_language() 用的都是它）。目录名只决定三件事：
# 官方生成器往哪写、资源覆盖（loader 的 tl/<语言>/ 前缀）、以及
# config.defer_tl_scripts 打开时的 tl 脚本加载过滤。
#
# 所以这里把两件事分开：
#   * 语言名 —— 引擎名：块头、读回、切换语言都用它；
#   * 目录   —— 译文实际所在的 tl 子目录：可能与语言名相同，也可能不同
#               （实测有游戏把 translate chinese 放在 tl/out/ 里）。
#
# 同一个语言出现在多个目录时，引擎按加载顺序取最后一份，插件照做
# （livetl_language_dir_of() 给的就是那个"生效目录"）。
#
# 本文件不包含界面代码，也不直接碰引擎内部结构（都走 livetl_engine_*）。
# =============================================================================

init -60 python:
    import os
    import re

    # 语言名同时是 tl/<语言>/ 的目录名与 translate 语句里的语言名。
    # 引擎的名字 token 规则是"字母或下划线开头，后面跟字母、数字、下划线"：
    # 实测连字符会让生成的文件解析不了（translate pt-br start_x: →
    # expected 'hash' not found），数字开头是 expected 'name' not found。
    _livetl_language_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    # 引擎保留名：`translate None <id>:` 是"默认语言"的写法，官方生成器也把
    # 字符串 "None" 当默认语言处理（generation.write_translates 里写明了），
    # 所以它不能当目标语言 —— 填了只会得到一堆语义不对的文件。
    _livetl_language_reserved = ("None",)

    # tl 文件里的 translate 块头：语言名 + 标识符（`strings` / `python` /
    # `style` 这些特殊块也长这样，它们同样说明"这个语言存在"）
    _livetl_block_pattern = re.compile(
        r"^\s*translate\s+([A-Za-z_][A-Za-z0-9_]*)\s+(\S+)\s*:\s*$", re.MULTILINE,
    )

    def livetl_language_valid(language):
        """这个语言名能不能当目标语言用。"""
        language = str(language or "")

        if (not language) or (language in _livetl_language_reserved):
            return False

        return _livetl_language_pattern.match(language) is not None

    def livetl_normalize_language(text):
        """界面上的输入 → 规范化的语言名；不合法时返回 ""。

        空格换成下划线（"simplified chinese" → "simplified_chinese"），
        其余原样交给 livetl_language_valid() 判断。
        """
        language = str(text or "").strip().replace(" ", "_")

        if not livetl_language_valid(language):
            return ""

        return language

    def livetl_language_hint():
        """语言名不合法时给译者看的一句话。"""
        return "目标语言只能用字母、数字、下划线，且不能以数字开头（例如 schinese）；None 是引擎保留名"

    # ---------------------------------------------------------------------
    # 磁盘上的事实：tl 下有哪些目录、哪些语言、各自出现在哪些目录里
    # ---------------------------------------------------------------------

    def livetl_language_path(directory):
        """tl/<目录> 的绝对路径（参数可以是语言名，也可以是别的目录名）。"""
        root = livetl_engine_tl_root()

        if (not root) or (not directory):
            return ""

        return os.path.join(root, str(directory))

    def _livetl_tl_files_in(directory_path):
        """一个 tl 子目录下的 .rpy / .rpym（跳过插件自己的备份目录前缀）。"""
        rv = []

        if not os.path.isdir(directory_path):
            return rv

        for dirpath, dirnames, filenames in os.walk(directory_path):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("_livetl_backup_"))

            for name in sorted(filenames):
                if name.endswith(".rpy") or name.endswith(".rpym"):
                    rv.append(os.path.join(dirpath, name))

        return rv

    def livetl_tl_dirs():
        """game/tl/ 下的目录名（原样大小写）；一个都没有时返回 []。

        tl 目录的位置由引擎隔离层负责（那是引擎事实），这里只负责列目录。
        里面可能有不是语言的目录（只放资源、或者人手建的），所以调用方要
        结合块扫描结果判断。
        """
        root = livetl_engine_tl_root()

        if not root or not os.path.isdir(root):
            return []

        try:
            names = os.listdir(root)
        except Exception as e:
            livetl_log("tl dirs: {!r}".format(e))
            return []

        return sorted(
            name for name in names
            if os.path.isdir(os.path.join(root, name))
        )

    def livetl_same_dir(a, b):
        """两个路径是不是同一个目录 —— 问文件系统，不看名字怎么写的。

        只比 realpath 不够稳（Windows 的 NTFS 默认不区分大小写，但"按目录开启
        大小写敏感"之后 Chinese/ 与 chinese/ 是两个真目录，实测同一个目录下
        可以同时存在），只比 samefile 也不够稳（ExFAT 之类不给文件索引的分区
        会误判成同一个）。所以两条都要成立：都在、且真实路径相同。
        """
        try:
            if not (os.path.isdir(a) and os.path.isdir(b)):
                return False

            return os.path.realpath(a) == os.path.realpath(b)
        except Exception:
            return False

    def _livetl_scan_language_index():
        """扫 tl 下的文件：{语言: {目录: 块数}}（默认语言 None 不计）。

        只看 translate 块头，所以和引擎一样不关心目录名。打包进 .rpa 的
        译文本地扫不到，那部分由 livetl_language_index() 用引擎的翻译表补。
        """
        rv = {}
        root = livetl_engine_tl_root()

        if not root or not os.path.isdir(root):
            return rv

        for directory in livetl_tl_dirs():
            for path in _livetl_tl_files_in(os.path.join(root, directory)):
                try:
                    with open(path, encoding="utf-8-sig", errors="ignore") as f:
                        text = f.read()
                except Exception as e:
                    livetl_log("language scan: 读取失败 {}: {!r}".format(path, e))
                    continue

                for m in _livetl_block_pattern.finditer(text):
                    language = m.group(1)

                    if language in _livetl_language_reserved:
                        continue

                    dirs = rv.setdefault(language, {})
                    dirs[directory] = dirs.get(directory, 0) + 1

        return rv

    def livetl_language_index(force=False):
        """{语言: {目录: 块数}}：磁盘上有哪些语言、各自出现在哪些 tl 目录里。

        两个来源：扫 tl 文件（覆盖目录名与语言名不一致的游戏），加上引擎的
        翻译表（覆盖打包进 .rpa、或 defer_tl_scripts 还没加载的语言）。
        session 缓存里带各 tl 文件的 (mtime, size)：外部改过 tl 会自动重建，
        插件自己写完文件调用 livetl_invalidate_language_index() 立即作废。
        """
        root = livetl_engine_tl_root()
        stamp = []

        if root and os.path.isdir(root):
            for directory in livetl_tl_dirs():
                for path in _livetl_tl_files_in(os.path.join(root, directory)):
                    try:
                        st = os.stat(path)
                        stamp.append((path, int(st.st_mtime), st.st_size))
                    except Exception:
                        pass

        cached = livetl_state_get("livetl_language_index")

        if (not force) and cached and (cached[0] == stamp):
            return cached[1]

        index = dict((language, dict(dirs)) for language, dirs in _livetl_scan_language_index().items())

        for language, paths in livetl_engine_translated_languages().items():
            if language in _livetl_language_reserved:
                continue

            for path in paths:
                parts = path.split("/")

                if len(parts) < 2 or not parts[1]:
                    continue

                # 引擎的翻译表只在"扫不到"时补一条目录记录（块数留 0，界面上
                # 只显示目录），这样打包在 .rpa 里的语言也能列出来
                index.setdefault(language, {}).setdefault(parts[1], 0)

        livetl_state_set("livetl_language_index", (stamp, index))
        return index

    def livetl_invalidate_language_index():
        """写回 / 生成 / 清理之后让语言索引失效，下次访问时重建。"""
        livetl_state_pop("livetl_language_index", None)

    def livetl_language_dirs_of(language):
        """这个语言出现在哪些 tl 目录里（按加载顺序，最早的在前）。"""
        dirs = livetl_language_index().get(str(language or ""), {})
        return sorted(dirs.keys())

    def livetl_language_dir_of(language):
        """这个语言的生效目录：加载顺序最后的那一个。

        同一个标识符出现在多个文件里时，引擎最后加载的那份胜出；目录名升序
        与 tl 脚本的加载顺序一致（路径字符串序，见 AGENTS.md 里的探针），
        所以最后那个目录就是"改了能看见"的那一个。语言还不存在时返回 ""。
        """
        dirs = livetl_language_dirs_of(language)
        return dirs[-1] if dirs else ""

    def livetl_language_exists(language):
        """磁盘上有没有这个语言的译文块。"""
        return bool(livetl_language_index().get(str(language or "")))

    def livetl_language_files(language):
        """这个语言涉及的 tl 文件（.rpy/.rpym），按加载顺序。"""
        root = livetl_engine_tl_root()
        rv = []

        if not root:
            return rv

        for directory in livetl_language_dirs_of(language):
            rv.extend(_livetl_tl_files_in(os.path.join(root, directory)))

        return sorted(rv)

    # ---------------------------------------------------------------------
    # 解析：译者填的名字 → (语言名, 目录, 说明)
    # ---------------------------------------------------------------------

    def livetl_resolve_language(name):
        """把译者填的名字解析成 (语言名, 目录, 说明)；解析不了时目录是空串。

        规则与 Ren'Py 自身的规则一致（translate 里的名字才是语言身份）：
          1. 磁盘上已经有这个语言 → 用它，文件位置取它的生效目录；
          2. 只差大小写命中一个语言 → 用磁盘上的写法；如果"你要建的那个目录"
             与"那个语言的目录"在这台机器上是同一处（NTFS 默认不区分大小写，
             tl/Chinese 与 tl/chinese 就是同一个目录），也不能另起名字 ——
             否则同一个文件里会出现两套 translate 块；
          3. 只差大小写命中多个写法 → 不猜（引擎把它们当不同语言），请译者选；
          4. 磁盘上没有这个语言 → 按官方规则新建 tl/<名字>/。
        说明是给译者看的一句话；没有要说明的事情时是空串。
        """
        name = str(name or "").strip()

        if not name:
            return "", "", ""

        if name in _livetl_language_reserved:
            return "", "", "None 是引擎的保留语言名（代表默认语言），不能当目标语言"

        if _livetl_language_pattern.match(name) is None:
            return "", "", livetl_language_hint()

        index = livetl_language_index()

        if name in index:
            return name, livetl_language_dir_of(name), ""

        lowered = name.lower()
        similar = sorted(lang for lang in index if lang.lower() == lowered)

        if len(similar) > 1:
            return "", "", "磁盘上同时存在 {}（引擎区分大小写，这是不同的语言），请在列表里选一个".format(
                "、".join(similar),
            )

        if len(similar) == 1:
            other = similar[0]
            other_dir = livetl_language_dir_of(other)

            if livetl_same_dir(livetl_language_path(name), livetl_language_path(other_dir)):
                return other, other_dir, "已有 tl/{}/（translate {}）；这台机器上它与 {} 是同一个目录，按已有的语言名用它".format(
                    other_dir, other, name,
                )

            # 大小写敏感的文件系统上它们能各自存在，那就按官方规则新建
            return name, name, "注意：磁盘上还有一个只差大小写的语言 {}（tl/{}/）".format(other, other_dir)

        if os.path.isdir(livetl_language_path(name)):
            # tl/<名字>/ 已经存在（可能是人手建的目录）：按官方规则，新译文就
            # 写进它；里面已经有别的语言的块时提醒一句
            others = sorted(
                lang for lang, dirs in index.items()
                if (name in dirs) and (lang != name)
            )
            note = ""

            if others:
                note = "tl/{}/ 里已经有 {} 的译文，会另起一套 translate {} 写进同一批文件".format(
                    name, "、".join(others), name,
                )

            return name, name, note

        return name, name, ""

    # ---------------------------------------------------------------------
    # 目标语言：本次运行选过的 ＞ 项目配置里的那一行
    # ---------------------------------------------------------------------

    def livetl_target_language():
        """当前目标语言（引擎名）。

        persistent 里那份是 0.2.9 以前的旧记录，只在设置界面里当预填值用。
        解析不了（例如磁盘上同时有两种大小写写法）时原样返回，交给
        livetl_resolve_language() 的调用方去提示。
        """
        raw = str(livetl_setting_get("language") or livetl_language or "").strip()
        language, _directory, _note = livetl_resolve_language(raw)
        return language or raw

    def livetl_target_dir():
        """当前目标语言的生效目录（读写落在哪个 tl 子目录里）。"""
        raw = str(livetl_setting_get("language") or livetl_language or "").strip()
        _language, directory, _note = livetl_resolve_language(raw)
        return directory or raw

    def livetl_set_language(language):
        """记下这次运行的目标语言（store 镜像 + session，不写文件）。

        落盘那一步在 livetl_commit_language()：只有译者点【开始翻译】才算是
        "选定这个项目的语言"。
        """
        store.livetl_language = language
        livetl_setting_set("language", language)
        livetl_log("language set to {!r}".format(language))

    def livetl_commit_language(language, path=None):
        """把目标语言写回 livetl_config.rpy 的 livetl_language 那一行。

        语言是"这个项目在做什么"，跟着项目走；配置改不了（打包后只剩 .rpyc）
        时本次运行仍然生效，由调用方在状态栏说明。
        返回 (备份文件名, 错误信息)。`path` 是给测试用的口子，正常调用不用传。
        """
        # 语言名已经过 livetl_language_valid()，只有字母数字下划线，
        # 当字面量写进配置文件是安全的
        backup, error = livetl_config_set_value(
            "livetl_language", '"{}"'.format(language), path=path,
        )

        if error:
            livetl_log("language config not updated: {}".format(error))
        else:
            livetl_log("language committed: {!r} (backup {})".format(language, backup))

        return backup, error

    # ---------------------------------------------------------------------
    # 项目侧记录：这个项目为哪个语言补过模板
    # ---------------------------------------------------------------------

    def livetl_mark_path(language=None, directory=None):
        """模板补全标记的位置（生效目录里的 .livetl_generated）。

        标记写在项目自己的 tl/<语言>/ 目录里，而不是 persistent：persistent
        是存档目录（多个项目可能共用），而 tl 目录是每个游戏独立的。
        拿不到目录时返回 ""，调用方会跳过写标记。

        `directory` 是给已经查过索引的调用方（例如候选列表）省一次查询的口子。
        """
        if language is None:
            language = livetl_target_language()

        if directory is None:
            directory = livetl_language_dir_of(language) or language

        root = livetl_language_path(directory)

        if not root:
            return ""

        return os.path.join(root, ".livetl_generated")

    def livetl_mark_templates_done(language):
        """记下"这个项目的这个语言已经补全过模板"。"""
        try:
            path = livetl_mark_path(language)

            if not path:
                return

            dirname = os.path.dirname(path)

            if not os.path.isdir(dirname):
                os.makedirs(dirname)

            with open(path, "w", encoding="utf-8") as f:
                f.write("LiveTL: translation templates generated for {}\n".format(language))
        except Exception:
            pass

    def livetl_project_setup_done(language=None):
        """这个项目是不是已经为这个语言补全过（生效目录里的标记文件）。

        这个标记就是"译者已经确认过目标语言"的项目侧记录：它跟着项目
        （tl 目录）走，不像 persistent 那样跟着机器走。语言不合法、拿不到
        目录、或者标记还没写时返回 False —— 那些情况本来就该再问一次。
        """
        if language is None:
            language = livetl_target_language()

        if not livetl_language_valid(language):
            return False

        mark = livetl_mark_path(language)
        return bool(mark) and os.path.exists(mark)

    # ---------------------------------------------------------------------
    # 设置界面用的候选列表
    # ---------------------------------------------------------------------

    def livetl_language_rows():
        """候选语言列表：每行 {language, dir, dirs, blocks, text}。

        屏幕只显示，不算逻辑（见 AGENTS.md 的面板约定）：这里把该说明的事情
        都拼成 text。
        """
        index = livetl_language_index()
        rows = []

        for language in sorted(index):
            # 只用这一次索引（livetl_language_dirs_of 之类每调一次都要重算一遍
            # tl 文件的时间戳，列表上十几行就会放大成几十次扫盘）
            dirs = sorted(index[language].keys())
            directory = dirs[-1] if dirs else ""
            blocks = sum(index[language].values())
            notes = []

            mark = livetl_mark_path(language, directory=directory)

            if mark and os.path.exists(mark):
                notes.append("插件生成过")

            if len(dirs) > 1:
                notes.append("有 {} 个目录，生效的是 tl/{}/".format(len(dirs), directory))
            elif directory != language:
                notes.append("目录名与语言名不同")

            if blocks:
                notes.append("{:,} 条".format(blocks))

            rows.append({
                "language": language,
                "dir": directory,
                "dirs": dirs,
                "blocks": blocks,
                "text": "{}    tl/{}/    {}".format(language, directory, "    ".join(notes)),
            })

        return rows

    def livetl_language_pick(language):
        """候选行点一下：填进输入框，并把"会写到哪里"说清楚（不写文件）。

        界面动作必须返回 None，否则返回值会被当成交互结果（见 AGENTS.md）。
        """
        resolved, directory, note = livetl_resolve_language(language)

        if not directory:
            livetl_set_status(note or livetl_language_hint())
            return None

        store.livetl_language_input = resolved

        message = "已选 {}：翻译将写入 tl/{}/，点【开始翻译】继续".format(resolved, directory)

        if note:
            message += "（{}）".format(note)

        livetl_set_status(message)
        return None
