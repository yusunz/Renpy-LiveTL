# =============================================================================
# LiveTL —— 字符串条目（translate <语言> strings）
#
# 负责四件事：
#   1. 扫描 tl/<语言>/ 下的字符串条目，建立 old -> 位置/译文 的索引
#   2. 把某一条的译文写回（写前做跨文件全量查重，绝不产生重复条目）
#   3. 报告重复条目（Ren'Py 对同一语言下重复的 old 会直接报错）
#   4. 清理重复条目（保留第一条，清理前整目录备份）
#
# 本文件不包含界面代码。
# =============================================================================

init -50 python:
    import os
    import re

    # tl 文件里的 old / new 行
    _livetl_old_pattern = re.compile(r'^\s*old\s+"(.*)"\s*$')
    _livetl_new_pattern = re.compile(r'^\s*new\s+"(.*)"\s*$')

    # 清理重复条目时，这些文件先保留（与 Ren'Py 官方的归属习惯一致）
    _livetl_file_rank = ["common.rpy", "script.rpy", "options.rpy", "gui.rpy", "screens.rpy"]

    # 清理重复条目时的备份目录（放在 game/ 下，不能放 tl/ 里：
    # tl 的一级子目录会被 Ren'Py 当成语言）
    _livetl_backup_dir = "livetl_backup"

    # 扫描 tl 目录时跳过这个前缀的子目录（防御性处理）
    _livetl_backup_prefix = "_livetl_backup_"

    def livetl_quote(s):
        """把文本转义成 tl 文件里的字符串字面量（与官方 quote_unicode 一致）。"""
        s = s.replace("\\", "\\\\")
        s = s.replace('"', '\\"')
        s = s.replace("\a", "\\a")
        s = s.replace("\b", "\\b")
        s = s.replace("\f", "\\f")
        s = s.replace("\n", "\\n")
        s = s.replace("\r", "\\r")
        s = s.replace("\t", "\\t")
        s = s.replace("\v", "\\v")
        return s

    def livetl_unquote(s):
        """把 tl 文件里的字符串字面量还原成实际文本。"""
        mapping = {
            "n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
            "f": "\f", "v": "\v", "\\": "\\", '"': '"',
        }

        out = []
        i = 0

        while i < len(s):
            c = s[i]

            if (c == "\\") and (i + 1 < len(s)) and (s[i + 1] in mapping):
                out.append(mapping[s[i + 1]])
                i += 2
                continue

            out.append(c)
            i += 1

        return "".join(out)

    # ---------------------------------------------------------------------
    # 目录与文件
    # ---------------------------------------------------------------------

    def livetl_tl_language_dir(language=None):
        """目标语言的 tl 目录。"""
        if language is None:
            language = livetl_target_language()

        return os.path.join(renpy.config.gamedir, renpy.config.tl_directory, language)

    def livetl_iter_tl_files(language=None):
        """列出该语言 tl 目录下的翻译文件（.rpy / .rpym，跳过备份目录）。"""
        root = livetl_tl_language_dir(language)
        rv = []

        if not os.path.isdir(root):
            return rv

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted([d for d in dirnames if not d.startswith(_livetl_backup_prefix)])

            for name in sorted(filenames):
                if name.endswith(".rpy") or name.endswith(".rpym"):
                    rv.append(os.path.join(dirpath, name))

        return rv

    def livetl_string_file_rank(relpath):
        """重复条目清理时决定保留谁：数字越小越先保留。"""
        name = os.path.basename(relpath)

        if name in _livetl_file_rank:
            return (_livetl_file_rank.index(name), relpath)

        return (len(_livetl_file_rank), relpath)

    def livetl_drop_empty_string_blocks(language=None):
        """删掉"只有表头、没有条目"的 translate strings 块。

        这种块会让 Ren'Py 报 "translate strings statement expects a
        non-empty block"，整个语言都加载不了。

        生成模板、删条目、清理重复条目之后都会检查一遍：删掉一个块里
        最后一条 old/new 时，剩下的表头就会变成这种坏块。
        返回清理过的文件数。
        """
        if language is None:
            language = livetl_target_language()

        header = "translate {} strings:".format(language)
        cleaned = 0

        for path in livetl_iter_tl_files(language):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            # 文件开头可能有 BOM（官方生成器给新文件写的就是带 BOM 的）：
            # 扫描时去掉，写回时原样加回去，免得把 BOM 弄丢。
            bom = "\ufeff" if content.startswith("\ufeff") else ""
            lines = content[len(bom):].split("\n")

            out = []
            changed = False
            i = 0

            while i < len(lines):
                if lines[i].strip() != header:
                    out.append(lines[i])
                    i += 1
                    continue

                # 看这个块里有没有实际内容
                j = i + 1
                has_body = False

                while j < len(lines):
                    s = lines[j].strip()

                    if s.startswith("translate ") or s.startswith("label "):
                        break

                    if s.startswith("old ") or s.startswith("new "):
                        has_body = True
                        break

                    j += 1

                if has_body:
                    out.append(lines[i])
                    i += 1
                    continue

                # 空块：连同它上面刚写的 TODO 注释一起删掉
                while out and out[-1].strip().startswith("# TODO"):
                    out.pop()

                changed = True
                i += 1

                while (i < len(lines)) and (lines[i].strip() == ""):
                    i += 1

            if not changed:
                continue

            content = "\n".join(out)
            if not content.endswith("\n"):
                content += "\n"

            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(bom + content)
                cleaned += 1
            except Exception as e:
                livetl_log("drop empty strings block failed {}: {!r}".format(path, e))

        if cleaned:
            livetl_log("dropped empty strings blocks in {} file(s)".format(cleaned))

        return cleaned

    def livetl_string_is_translated(old, new):
        """这条条目是不是"真的翻译过"（而不是模板里写的原文占位）。"""
        return bool(new) and (new != old)

    def livetl_string_sort_key(old, place):
        """排在前面的条目更重要：优先保留有译文的，其次按文件优先级。"""
        rel, lineno, new = place
        return (0 if livetl_string_is_translated(old, new) else 1,) + livetl_string_file_rank(rel)

    def livetl_best_string_entry(old, places):
        """从同一个 old 的多条条目里挑一条（不会用占位原文盖掉真译文）。"""
        return sorted(places, key=lambda p: livetl_string_sort_key(old, p))[0]

    # ---------------------------------------------------------------------
    # 索引
    # ---------------------------------------------------------------------

    def livetl_scan_string_index(language=None, force=False):
        """扫描 tl/<语言>/ 下的字符串条目。

        返回 {old: [(相对文件名, 行号, 译文), ...]}。
        结果缓存在 session 里，缓存键包含各文件的 (mtime, size)，
        所以文件被外部改动（或用编辑器改过 tl）后会自动重建。
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

        cached = renpy.session.get("livetl_string_index")

        if (not force) and cached and (cached[0] == language) and (cached[1] == stamp):
            return cached[2]

        root = livetl_tl_language_dir(language)
        index = {}

        for path in files:
            rel = os.path.relpath(path, root).replace("\\", "/")

            try:
                with open(path, encoding="utf-8-sig") as f:
                    lines = f.read().split("\n")
            except Exception as e:
                livetl_log("string index: 读取失败 {}: {!r}".format(rel, e))
                continue

            pending = None

            for n, line in enumerate(lines, 1):
                m = _livetl_old_pattern.match(line)

                if m is not None:
                    pending = (livetl_unquote(m.group(1)), n)
                    continue

                m = _livetl_new_pattern.match(line)

                if (m is not None) and (pending is not None):
                    old, lineno = pending
                    index.setdefault(old, []).append((rel, lineno, livetl_unquote(m.group(1))))
                    pending = None

        renpy.session["livetl_string_index"] = (language, stamp, index)
        return index

    def livetl_invalidate_string_index():
        """写回或清理之后让索引失效，下次访问时重建。"""
        renpy.session.pop("livetl_string_index", None)
        renpy.session.pop("livetl_string_file_map", None)

    def livetl_lookup_string(key, language=None):
        """这条文本在 tl 里的条目；返回 (相对文件名, 行号, 译文) 或 None。"""
        index = livetl_scan_string_index(language)
        places = index.get(key)

        if not places:
            return None

        # 历史遗留重复时，取"清理时会保留"的那一条，保证读写一致
        return livetl_best_string_entry(key, places)

    # ---------------------------------------------------------------------
    # 归属文件（官方规则）
    # ---------------------------------------------------------------------

    def livetl_string_file_map(force=False):
        """源码里每个字符串的官方归属文件（懒加载 + 缓存）。

        沿用 Ren'Py 官方的 scanstrings + translation_filename 规则
        （在 livetl_engine.rpy 里），与 Launcher 的「生成翻译」写到同一个文件。
        """
        cached = renpy.session.get("livetl_string_file_map")

        if (cached is not None) and (not force):
            return cached

        rv = livetl_engine_string_file_map()

        if not rv and livetl_engine_last_error():
            livetl_log("string file map: 扫描失败 {}".format(livetl_engine_last_error()))

        renpy.session["livetl_string_file_map"] = rv
        return rv

    def livetl_string_file_for(key):
        """这条文本该写进哪个 tl 文件；源码里没有的运行时文本落到 strings.rpy。"""
        return livetl_string_file_map().get(key) or "strings.rpy"

    # ---------------------------------------------------------------------
    # 写回
    # ---------------------------------------------------------------------

    def livetl_write_string_entry(key, text):
        """把字符串条目的译文写回 tl 文件。

        规则（按顺序）：
          1. 先做跨文件全量查重：这条 old 已经存在就改它的 new；
          2. 不存在才按官方归属文件新增一条。

        返回写入的相对文件名；失败返回 None。
        """
        language = livetl_target_language()

        index = livetl_scan_string_index(language, force=True)
        existing = index.get(key)

        if existing:
            rel = livetl_best_string_entry(key, existing)[0]
        else:
            rel = livetl_string_file_for(key)

        path = os.path.join(livetl_tl_language_dir(language), rel)

        dirname = os.path.dirname(path)
        if dirname and not os.path.isdir(dirname):
            os.makedirs(dirname)

        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8-sig") as f:
                    lines = f.read().split("\n")
            except Exception as e:
                livetl_log("write string: 读取失败 {!r}: {!r}".format(rel, e))
                return None
        else:
            lines = ["translate {} strings:".format(language), ""]

        old_line = '    old "{}"'.format(livetl_quote(key))
        new_line = '    new "{}"'.format(livetl_quote(text))

        wrote = False

        for i, line in enumerate(lines):
            if line.strip() != old_line.strip():
                continue

            # 这条 old 下面就是它的 new：改掉
            j = i + 1
            while j < len(lines):
                if _livetl_new_pattern.match(lines[j]) is not None:
                    lines[j] = new_line
                    wrote = True
                    break

                s = lines[j].strip()
                if s.startswith("old ") or s.startswith("translate ") or (s == ""):
                    lines.insert(i + 1, new_line)
                    wrote = True
                    break

                j += 1

            break

        if not wrote:
            # 文件里还没有这条：追加到 strings 块末尾，没有块就新建
            header = "translate {} strings:".format(language)
            block_start = None

            for i, line in enumerate(lines):
                if line.strip() == header:
                    block_start = i
                    break

            if block_start is None:
                if lines and (lines[-1].strip() != ""):
                    lines.append("")

                lines.extend([header, "", old_line, new_line, ""])
            else:
                end = len(lines)

                for i in range(block_start + 1, len(lines)):
                    s = lines[i].strip()

                    if s.startswith("translate ") or s.startswith("label "):
                        end = i
                        break

                while (end > block_start + 1) and (lines[end - 1].strip() == ""):
                    end -= 1

                lines[end:end] = ["", old_line, new_line]

        content = "\n".join(lines)
        if not content.endswith("\n"):
            content += "\n"

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            livetl_log("write string: 写入失败 {!r}: {!r}".format(rel, e))
            return None

        livetl_invalidate_string_index()
        livetl_log("write string entry: {!r} -> {} ({!r})".format(key, rel, text))
        return rel

    # ---------------------------------------------------------------------
    # 查重体检
    # ---------------------------------------------------------------------

    def livetl_delete_string_entry(key, language=None):
        """删除某个字符串条目（old/new 整条删掉）。

        字符串条目没有"清空"的安全写法：空的 new 会让菜单项变成不可点的
        空按钮，所以清空字符串就等于删掉这一条。返回被删的文件名。
        """
        if language is None:
            language = livetl_target_language()

        index = livetl_scan_string_index(language, force=True)
        places = index.get(key)

        if not places:
            return None

        rel, lineno, _new = livetl_best_string_entry(key, places)
        path = os.path.join(livetl_tl_language_dir(language), rel)

        try:
            with open(path, encoding="utf-8-sig") as f:
                lines = f.read().split("\n")
        except Exception as e:
            livetl_log("delete string: 读取失败 {}: {!r}".format(rel, e))
            return None

        out = []
        i = 0

        while i < len(lines):
            if (i + 1) == lineno:
                # 顺带删掉紧贴它上面的注释行（例如 "# script.rpy:41"）
                if out and out[-1].strip().startswith("#"):
                    out.pop()

                i += 1

                # 跳到这条的 new 行
                while i < len(lines):
                    if _livetl_new_pattern.match(lines[i]) is not None:
                        i += 1
                        break

                    s = lines[i].strip()
                    if s.startswith("old ") or s.startswith("translate "):
                        break

                    i += 1

                if (i < len(lines)) and (lines[i].strip() == ""):
                    i += 1

                continue

            out.append(lines[i])
            i += 1

        content = "\n".join(out)
        if not content.endswith("\n"):
            content += "\n"

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            livetl_log("delete string: 写入失败 {}: {!r}".format(rel, e))
            return None

        livetl_invalidate_string_index()
        livetl_drop_empty_string_blocks(language)
        livetl_log("delete string entry: {!r} from {}".format(key, rel))
        return rel

    def livetl_find_duplicate_strings(language=None):
        """找出同一语言下重复出现的 old，返回 {old: [(文件, 行号, 译文), ...]}。"""
        index = livetl_scan_string_index(language, force=True)
        return dict((k, v) for k, v in index.items() if len(v) > 1)

    def livetl_backup_language_dir(language):
        """把整个 tl/<语言>/ 备份出来，返回备份目录（失败返回 None）。"""
        import shutil
        import time

        root = livetl_tl_language_dir(language)

        if not os.path.isdir(root):
            return None

        backup = os.path.join(
            renpy.config.gamedir,
            _livetl_backup_dir,
            "{}_{}".format(language, time.strftime("%Y%m%d_%H%M%S")),
        )

        try:
            shutil.copytree(root, backup)
        except Exception as e:
            livetl_log("backup failed: {!r}".format(e))
            return None

        return backup

    def livetl_clean_duplicate_strings(language=None, make_backup=True):
        """清理重复条目：每个 old 只保留一条。

        保留规则：common.rpy > script.rpy > options.rpy > gui.rpy > screens.rpy
        > 其它（文件名与行号排序）。删除时连同紧邻的注释行与空行一起删除。

        返回 (清理条数, 备份目录)。
        """
        if language is None:
            language = livetl_target_language()

        dups = livetl_find_duplicate_strings(language)

        if not dups:
            return (0, None)

        backup = livetl_backup_language_dir(language) if make_backup else None

        if make_backup and (backup is None):
            return (0, None)

        # 计算要删除的行号（1 起）
        drop = {}

        for old, places in dups.items():
            ordered = sorted(places, key=lambda p: livetl_string_sort_key(old, p))

            for rel, lineno, _new in ordered[1:]:
                drop.setdefault(rel, set()).add(lineno)

        removed = 0
        root = livetl_tl_language_dir(language)

        for rel, linenos in drop.items():
            path = os.path.join(root, rel)

            try:
                with open(path, encoding="utf-8-sig") as f:
                    lines = f.read().split("\n")
            except Exception as e:
                livetl_log("dup clean: 读取失败 {}: {!r}".format(rel, e))
                continue

            out = []
            i = 0

            while i < len(lines):
                if (i + 1) in linenos:
                    # 顺带删掉紧贴它上面的注释行（例如 "# script.rpy:41"）
                    if out and out[-1].strip().startswith("#"):
                        out.pop()

                    i += 1

                    # 跳到这条的 new 行
                    while i < len(lines):
                        if _livetl_new_pattern.match(lines[i]) is not None:
                            i += 1
                            break

                        s = lines[i].strip()
                        if s.startswith("old ") or s.startswith("translate "):
                            break

                        i += 1

                    if (i < len(lines)) and (lines[i].strip() == ""):
                        i += 1

                    removed += 1
                    continue

                out.append(lines[i])
                i += 1

            content = "\n".join(out)
            if not content.endswith("\n"):
                content += "\n"

            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                livetl_log("dup clean: 写入失败 {}: {!r}".format(rel, e))
                continue

        livetl_invalidate_string_index()
        livetl_drop_empty_string_blocks(language)
        livetl_log("dup clean: {} 条，备份 {!r}".format(removed, backup))
        return (removed, backup)
