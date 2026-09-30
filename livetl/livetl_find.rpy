# =============================================================================
# LiveTL —— 条目搜索
#
# 面板上的两个新状态：
#   * find       —— 搜索页：搜索框 + 结果列表（空搜索词 = 未翻清单）；
#   * find_edit  —— 点开一条结果后的编辑页（提交 / 清空写回这一条）。
#
# 数据来源是"引擎里的全部条目"，不是 tl 文件里已有的条目：
#   * 台词   —— 内存脚本里每个要翻译的标识符 + 原文 + 源码位置，
#               译文从 tl 文件批量解析（livetl_scan_tl_entry_texts）；
#   * 字符串 —— livetl_strings.rpy 的字符串索引（原文 / 译文 / 重复都在）。
# 所以还没生成模板的条目也搜得到（"找没翻的"能成立的前提）。
#
# 结果列表最多显示 _livetl_find_limit 条（上万条目一次全渲染会卡），命中
# 总数单独记一份给顶部提示；搜索词一变就把列表重新过滤一遍。
#
# 索引缓存在 session 里，键含语言与各 tl 文件的 (mtime, size)：外部改过 tl
# 会自动重建；插件自己写回后由 livetl_find_after_write() 只更新那一条，
# 不整表重建（"搜一条、改一条、再搜一条"的循环不卡）。
# =============================================================================

init -50 python:
    import time

    # 结果列表一次最多显示多少条（命中更多时顶部提示"共 N 条"）
    _livetl_find_limit = 200

    # 列表行里原文的截断长度（显示字符数）
    _livetl_find_row_chars = 34

    # 索引缓存：session 里存 (语言, tl 文件 stamp, 条目列表)
    _livetl_find_cache_key = "livetl_find_cache"

    def _livetl_find_stamp(language):
        """索引缓存键：这个语言的 tl 文件 (mtime, size) 清单。"""
        stamp = []

        for path in livetl_iter_tl_files(language):
            try:
                st = os.stat(path)
                stamp.append((path, int(st.st_mtime), st.st_size))
            except Exception:
                pass

        return stamp

    def _livetl_find_short_path(filename):
        """节点文件名 → 显示用的短路径（裁掉 game/ 之前的绝对路径）。"""
        path = str(filename or "").replace("\\", "/")

        if not path:
            return ""

        marker = "/game/"

        if marker in path:
            return path.rsplit(marker, 1)[-1]

        if path.startswith("game/"):
            return path[len("game/"):]

        return path

    def livetl_find_invalidate():
        """让搜索索引缓存作废（下次进搜索页时重建）。"""
        livetl_state_pop(_livetl_find_cache_key, None)

    # 搜索态的 session 载体：按 store 变量名存一份。
    #
    # 和面板可见性、设置页标记同一层。剧情回退（游戏 Back 按钮、滚轮、
    # PageUp、手柄 —— 都是引擎自己的回退）回滚的是 store 变量；
    # `livetl_ensure_panel` 每交互从这里回正，所以回退只退剧情，
    # 不会把搜索页 / 编辑搜索结果带走，也不会让提交写回错的条目
    # （和设置界面一个道理）。
    _livetl_find_state_key = "livetl_find_state"

    _livetl_find_state_names = (
        "livetl_mode",
        "livetl_find_input",
        "livetl_find_query",
        "livetl_find_results",
        "livetl_find_total",
        "livetl_find_loaded_index",
        "livetl_edit_origin",
        "livetl_find_tid",
        "livetl_current_kind",
        "livetl_current_key",
        "livetl_current_source",
    )

    def livetl_find_save():
        """把当前搜索态写进 session（回退 / 折叠都不丢）。"""
        state = {}

        for name in _livetl_find_state_names:
            state[name] = getattr(store, name, None)

        livetl_state_set(_livetl_find_state_key, state)

    def livetl_find_sync():
        """每交互把搜索态从 session 回正到 store（回退拿不走，像设置界面）。"""
        state = livetl_state_get(_livetl_find_state_key, None)

        if not state:
            return

        for name, value in state.items():
            if getattr(store, name, None) is not value:
                setattr(store, name, value)

    def livetl_find_exit():
        """完全离开搜索：清装载对象与 session 里的搜索态。"""
        livetl_find_leave()
        livetl_state_set(_livetl_find_state_key, None)

    def livetl_find_leave():
        """离开搜索编辑态时的清理：提交对象回到"剧情当前句"。

        回搜索列表（livetl_find_back）只走这一半，搜索态还留着；回菜单、
        进拾取、关搜索这些"完全离开"的路径走 livetl_find_exit()。
        """
        store.livetl_edit_origin = ""
        store.livetl_find_tid = None

    def livetl_find_entries(language=None, force=False):
        """搜索索引（会话内缓存）：[条目, ...]，按源码位置排序。

        条目是 dict：
          kind         "say" / "string"
          key          台词标识符 / 字符串条目的原文
          source       原文
          source_low   原文小写（匹配用，构建时算好，省得每次按键重算）
          target       当前译文（"" = 没有译文）
          target_low   译文小写（匹配用）
          translated   是否已有译文
          dup          同一个键在 tl 里出现多次
          rel, line    位置（台词 = 源码文件；字符串 = tl 文件）
        """
        if language is None:
            language = livetl_target_language()

        stamp = _livetl_find_stamp(language)
        cached = livetl_state_get(_livetl_find_cache_key)

        if (not force) and cached and (cached[0] == language) and (cached[1] == stamp):
            return cached[2]

        started = time.monotonic()
        texts = livetl_scan_tl_entry_texts(language)
        files_index = livetl_scan_tl_entry_files(language)
        entries = []
        says = 0

        for tid, _alternate in livetl_engine_all_translate_ids():
            if not tid:
                continue

            source = livetl_engine_source_text(tid) or ""
            target = texts.get(tid, "")
            filename, linenumber = livetl_engine_source_location(tid)

            entries.append({
                "kind": "say",
                "key": tid,
                "source": source,
                "source_low": source.lower(),
                "target": target,
                "target_low": target.lower(),
                "translated": bool(target),
                "dup": len(files_index.get(tid, [])) > 1,
                "rel": _livetl_find_short_path(filename),
                "line": linenumber or 0,
            })
            says += 1

        strings = 0

        for old, places in livetl_scan_string_index(language).items():
            rel, line, new = livetl_best_string_entry(old, places)

            # 生成的模板里未翻字符串条目的 new 是原文（占位），
            # 对译者来说等同于没翻（与菜单列表同一条规则）
            if new == old:
                new = ""

            target = new or ""

            entries.append({
                "kind": "string",
                "key": old,
                "source": old,
                "source_low": old.lower(),
                "target": target,
                "target_low": target.lower(),
                "translated": livetl_string_is_translated(old, new),
                "dup": len(places) > 1,
                "rel": rel,
                "line": line or 0,
            })
            strings += 1

        entries.sort(key=lambda e: ((e["rel"] or "\uffff"), e["line"]))

        livetl_state_set(_livetl_find_cache_key, (language, stamp, entries))
        livetl_log("find: index entries={} says={} strings={} ms={:.0f}".format(
            len(entries), says, strings, (time.monotonic() - started) * 1000.0,
        ))

        return entries

    def livetl_find_matching(query, entries=None):
        """按关键词过滤条目：原文或译文包含即命中；空词 = 未翻清单。"""
        if entries is None:
            entries = livetl_find_entries()

        text = (query or "").strip()
        matched = []

        if not text:
            for entry in entries:
                if not entry["translated"]:
                    matched.append(entry)
        else:
            needle = text.lower()

            for entry in entries:
                if (needle in entry["source_low"]) or (needle in entry["target_low"]):
                    matched.append(entry)

        return matched

    def livetl_find_refresh(force=False):
        """按搜索框当前内容重建结果列表（进入搜索页 / 输入变化时）。"""
        matched = livetl_find_matching(
            store.livetl_find_input, livetl_find_entries(force=force),
        )

        store.livetl_find_query = store.livetl_find_input
        store.livetl_find_total = len(matched)
        store.livetl_find_results = matched[:_livetl_find_limit]
        store.livetl_find_loaded_index = -1
        livetl_find_save()

    def livetl_find_open():
        """打开搜索页（折叠时先展开）。"""
        if livetl_need_setup():
            livetl_set_status("先选定目标语言，再用【搜索】")
            return

        if store.livetl_pick_active:
            return

        livetl_set_visible(True)
        store.livetl_mode = "find"
        livetl_find_leave()
        livetl_find_refresh()

    def livetl_find_close():
        """关闭搜索，回剧情当前条（唯一的"退出搜索"动作）。"""
        store.livetl_mode = "say"
        livetl_find_exit()
        store.livetl_find_loaded_index = -1

        # 强制刷新：搜索期间剧情可能已经推进，这里拉回最新的当前句
        livetl_sync(force=True)

    def livetl_find_back():
        """从编辑页回搜索页（搜索词与结果保留，接着挑下一条）。"""
        store.livetl_mode = "find"
        livetl_find_leave()
        store.livetl_find_loaded_index = -1
        livetl_find_save()

    def livetl_find_select(index):
        """点一条结果：装载到编辑页。"""
        results = store.livetl_find_results

        if not (0 <= index < len(results)):
            return

        entry = results[index]

        store.livetl_mode = "find_edit"
        store.livetl_edit_origin = "find"
        store.livetl_find_loaded_index = index
        store.livetl_current_kind = entry["kind"]
        store.livetl_current_key = entry["key"] if entry["kind"] == "string" else None
        store.livetl_find_tid = entry["key"] if entry["kind"] == "say" else None
        store.livetl_current_source = entry["source"]
        store.livetl_input = livetl_input_text(entry["target"] or "")
        livetl_find_save()

    def livetl_find_edit_where():
        """编辑搜索条目时的位置提示行；不在搜索编辑时返回 ""。"""
        if store.livetl_edit_origin != "find":
            return ""

        index = store.livetl_find_loaded_index
        results = store.livetl_find_results

        if not (0 <= index < len(results)):
            return ""

        entry = results[index]
        # 文件路径也可能带 { } [ ]（下载目录名、非 ASCII 路径……）：
        # 这一行会被 `text "[…]"` 解析，路径也要按字面转义
        rel = livetl_escape(entry["rel"] or "")
        line = entry["line"]
        prefix = "tl" if entry["kind"] == "string" else "源码"

        if rel and line:
            return "{}: {}:{}".format(prefix, rel, line)

        if rel:
            return "{}: {}".format(prefix, rel)

        return ""

    def livetl_find_row_text(index):
        """结果列表里某一行的显示文本（截断与转义都在这里做）。

        顺序很重要：**先按原文字符截断、再转义**。反过来的话，转义会把
        `{` 变成 `{{`，截断可能正好切在这对括号中间、留下一个裸 `{` ——
        Ren'Py 8.3.4 渲染这一行时直接抛 "Open text tag at end of string"，
        把游戏打崩（真实游戏实测：RoadsYetTraveled）。
        """
        results = store.livetl_find_results

        if not (0 <= index < len(results)):
            return ""

        entry = results[index]
        raw = entry["source"] or entry["key"]

        if len(raw) > _livetl_find_row_chars:
            raw = raw[:_livetl_find_row_chars] + "…"

        text = livetl_escape(raw)

        note = "已翻" if entry["translated"] else "未翻"

        if entry["dup"]:
            note += "（重复）"

        return "[[{}] {} — {}".format(index + 1, text, note)

    def livetl_find_hint_text():
        """搜索页顶部的提示行。"""
        query = (store.livetl_find_input or "").strip()
        total = store.livetl_find_total
        shown = len(store.livetl_find_results)

        if not query:
            if not total:
                return "没有未翻的条目"

            if shown < total:
                return "未翻 {} 条，显示前 {}".format(total, shown)

            return "未翻 {} 条".format(total)

        if not total:
            text = query

            if len(text) > 20:
                text = text[:20] + "…"

            # 与结果行同一条规则：先截断、再转义（截断切坏 {{ 会留下裸 {）
            return "没有匹配「{}」的条目".format(livetl_escape(text))

        if shown < total:
            return "共 {} 条，显示前 {}".format(total, shown)

        return "共 {} 条".format(total)

    def livetl_find_after_write():
        """提交 / 清空之后：把结果列表里装载的那条刷成最新（不重建整个索引）。

        写回会改 tl 文件，索引缓存的 stamp 已经过期；但译者通常是
        "搜一条、改一条、再搜一条"，这里只更新那一条。
        """
        if store.livetl_edit_origin != "find":
            return

        index = store.livetl_find_loaded_index
        results = store.livetl_find_results

        if not (0 <= index < len(results)):
            return

        entry = results[index]
        language = livetl_target_language()

        if entry["kind"] == "string":
            found = livetl_lookup_string(entry["key"], language)

            if found:
                rel, line, new = found

                if new == entry["key"]:
                    new = ""

                target = new or ""
                entry["rel"] = rel
                entry["line"] = line or 0
                entry["target"] = target
                entry["target_low"] = target.lower()
                entry["translated"] = livetl_string_is_translated(entry["key"], new)
            else:
                entry["target"] = ""
                entry["target_low"] = ""
                entry["translated"] = False
        else:
            target = livetl_read_entry(language, entry["key"]) or ""
            entry["target"] = target
            entry["target_low"] = target.lower()
            entry["translated"] = bool(target)

        # 结果列表与 session 里那份是同一个 list，这里的原地修改本来就已经
        # 落进搜索态；再存一次只是让"state 永远是最新的"这个心智模型成立。
        livetl_find_save()
