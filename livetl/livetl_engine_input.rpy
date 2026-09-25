# =============================================================================
# LiveTL —— 引擎隔离层：面板输入框（鼠标定位光标、拖拽选区、撤销 / 重做）
#
# 这个文件是"输入框"这一组能力的适配层，规则与 livetl_engine.rpy 相同：
#   * 未文档化的引擎接口只能出现在三个适配层文件里：livetl_engine.rpy、
#     本文件、livetl_state.rpy；其它文件只调用 livetl_engine_* 函数。
#   * 每个函数遇到问题返回空值（None / [] / {}），原因记进
#     livetl_engine_note_error()（三个适配层共用一个错误出口）。
#   * 按能力拆文件，不按版本号拆：这里只放"输入框"这一件事。
#
# 为什么要单独一个文件：Ren'Py 的 Input 控件不带鼠标支持，要补上鼠标定位
# 光标与拖拽选区，就得读 Text 的排版内部（layout.lines[*].glyphs[*]），
# 适配代码比 livetl_engine.rpy 里那些小函数大得多；混在一起会让那份契约
# 文件不好读。门禁（tools/check_engine_seam.ps1、tools/check_renpy_api.ps1）
# 的适配层名单里有本文件。
# =============================================================================

init -90 python:
    # ---------------------------------------------------------------------
    # 契约层：面板输入框（鼠标定位光标、拖拽选区）
    #
    # 为什么要自己做：Ren'Py 的 Input 控件只认键盘 —— 8.1.1 与 8.5.3 的
    # Input.event() 都不看鼠标事件，类里也没有"选区"这个概念。对面板来说
    # 这是两个实际问题：
    #   * 鼠标点不进输入框，想在中间补一个字只能一路按方向键；
    #   * 点击不会被消费，会继续往下传给游戏：译者想点一下输入框，剧情反而
    #     往前推进一句，面板内容随即被新台词顶掉（拾取层当年踩过同一个坑）。
    #
    # 坐标换算是照引擎自己算超链接热区那几行写的（renpy/text/text.py 里
    # Text.render 的 layout.unscale_pair）：排版坐标是绘制分辨率，事件坐标是
    # 虚拟分辨率 —— 从鼠标算下标时乘 oversample、减排版偏移；把选区方块画回
    # 界面时除以 oversample、加排版偏移。
    # 依赖的内部结构：layout.oversample / xoffset / yoffset，
    # layout.lines[*].y / height / glyphs[*].x / advance / character。
    # 这些在 8.1.1 与 8.5.3 上一致，其中"一个字形对应一个字符"这条假设由
    # livetl_engine_input_probe() 每次运行自检一遍。
    #
    # 算不出来时（译文里有图片、表情文字这类"不是字的元素"）返回 None / []，
    # 调用方只挡住这一次点击、不动光标，原因记进 livetl_engine_note_error()。
    # ---------------------------------------------------------------------

    # 排版里表示"嵌入元素"的字符：光标就是这么插进文字里的
    _livetl_engine_input_object = 0xFFFC

    # 双击选词的分隔符：空白与中英标点。中文没有空格，靠标点切段，
    # 双击才会选到"一个短句"，而不是一整行。
    _livetl_engine_input_separators = (
        " \t\r\n\u3000"
        "，。、；：！？…—「」『』（）〈〉《》【】〔〕“”‘’·"
        ",.;:!?()[]{}<>\"'`~#$%^&*|\\/+=@"
    )

    def _livetl_engine_input_is_sep(ch):
        """这个字符算不算"词"的分界（双击选词用）。"""
        return ch in _livetl_engine_input_separators

    def _livetl_engine_input_color(spec):
        """把颜色写法换成 Render.fill() 要的四元组；写法不对时用兜底色。"""
        try:
            r, g, b, a = renpy.color.Color(spec)
            return (r, g, b, a)
        except Exception as e:
            livetl_engine_note_error("input/color", e)
            return (255, 204, 102, 96)

    def _livetl_engine_input_marks(widget):
        """把排版里的字逐个标上"第几个字符"。

        返回 [(行, [(内容下标, 字形), ...]), ...]；光标本身是插进排版里的
        一个 displayable，在排版里记成 U+FFFC，这里用 None 表示（它不对应
        任何字符，画选区时单独照顾）。

        字形总数与内容长度对不上时返回 None：说明译文里有排版认不出成
        "一个字"的东西（图片、表情文字），这时宁可不认，也不要点歪。
        """
        try:
            layout = widget.get_layout()
            content = widget.content
        except Exception as e:
            livetl_engine_note_error("input/marks", e)
            return None

        if layout is None:
            return None

        marks = []
        index = 0

        for line in (getattr(layout, "lines", None) or []):
            items = []

            for glyph in (getattr(line, "glyphs", None) or []):
                if getattr(glyph, "time", 0) == -1:
                    # 慢速打字（typewriter）还没显示出来的字：不算数
                    continue

                if getattr(glyph, "character", 0) == _livetl_engine_input_object:
                    items.append((None, glyph))
                    continue

                items.append((index, glyph))
                index += 1

            if items:
                marks.append((line, items))

        if index != len(content):
            livetl_engine_note_error(
                "input/marks",
                "glyphs={} chars={}".format(index, len(content)),
            )
            return None

        return marks

    def _livetl_engine_input_scale(layout):
        """排版坐标与虚拟坐标之间的倍数（引擎自己在用 oversample）。"""
        try:
            return float(getattr(layout, "oversample", 1.0) or 1.0)
        except Exception:
            return 1.0

    def _livetl_engine_input_to_virtual(layout, x, y):
        """排版坐标 → 虚拟坐标（窗口被放大时两者差一个倍数）。"""
        try:
            return layout.unscale_pair(x + layout.xoffset, y + layout.yoffset)
        except Exception:
            scale = _livetl_engine_input_scale(layout)
            xo = getattr(layout, "xoffset", 0)
            yo = getattr(layout, "yoffset", 0)
            return ((x + xo) / scale, (y + yo) / scale)

    def livetl_engine_input_index_at(widget, x, y):
        """鼠标点在第几个字符之间（0 = 最前，len(内容) = 最后）。

        `x` / `y` 是虚拟屏幕坐标里、相对输入框左上角的位置（事件给的就是
        这个）。认不出来时返回 None。
        """
        try:
            layout = widget.get_layout()
            content = widget.content
        except Exception as e:
            livetl_engine_note_error("input/index_at", e)
            return None

        if layout is None:
            return None

        length = len(content)

        if not length:
            # 空输入框：只有"最前面"一个位置
            return 0

        marks = _livetl_engine_input_marks(widget)

        if not marks:
            return None

        scale = _livetl_engine_input_scale(layout)
        lx = x * scale - getattr(layout, "xoffset", 0)
        ly = y * scale - getattr(layout, "yoffset", 0)

        # 先按纵向定行：点在最后一行下面时算最后一行
        target = marks[0]

        for line, items in marks:
            target = (line, items)

            if ly < (line.y + line.height):
                break

        # 再按横向定位置：落在某个字的中线左边就排到它前面
        index = None

        for item_index, glyph in target[1]:
            if item_index is None:
                continue

            middle = glyph.x + (getattr(glyph, "advance", 0) / 2.0)

            if lx < middle:
                return item_index

            index = item_index + 1

        if index is None:
            # 这一行只有光标占位符（例如正好折行）：按光标现在的位置算
            index = getattr(widget, "caret_pos", 0)

        return min(max(index, 0), length)

    def livetl_engine_input_selection_rects(widget, start, end):
        """选区在界面上的方块（虚拟坐标），多行时每行一块；没有则返回 []。

        布局与内容对不上（见 _livetl_engine_input_marks）时返回 []。
        """
        try:
            layout = widget.get_layout()
        except Exception as e:
            livetl_engine_note_error("input/rects", e)
            return []

        if layout is None:
            return []

        marks = _livetl_engine_input_marks(widget)

        if not marks:
            return []

        rects = []

        for line, items in marks:
            lefts = []
            rights = []

            for item_index, glyph in items:
                if item_index is None:
                    # 光标占位符：位置落在选区里时一起算上，免得中间留缝
                    inside = (start <= widget.caret_pos <= end)
                else:
                    inside = (start <= item_index < end)

                if not inside:
                    continue

                lefts.append(glyph.x)
                # 一个字的宽度用 advance（空格也算整格），没有就用 width
                rights.append(glyph.x + (getattr(glyph, "advance", 0) or getattr(glyph, "width", 0)))

            if not lefts:
                continue

            x0, y0 = _livetl_engine_input_to_virtual(layout, min(lefts), line.y)
            x1, y1 = _livetl_engine_input_to_virtual(
                layout, max(rights), line.y + line.height,
            )

            rects.append((x0, y0, x1 - x0, y1 - y0))

        return rects

    class LiveTLInput(renpy.display.behavior.Input):
        """面板输入框：官方 Input + 鼠标定位光标 + 拖拽选区 + 撤销 / 重做。

        官方 Input 只认键盘（8.1.1 / 8.5.3 都是）：鼠标点击既不会移动光标，
        也不会被消费 —— 于是"点输入框"等于"点游戏画面"，对话会被推进一句，
        面板内容随即被新台词顶掉。这里补上鼠标该有的行为；键盘、输入法、
        方向键、Ctrl+V 仍旧走官方实现，不重复实现引擎逻辑。

        撤销 / 重做（Ctrl+Z / Ctrl+Y）也是官方没有的：历史只记输入框自己的
        内容，不动已经写回 tl 的文件，也不动游戏回退。

        实例由 livetl_engine_input_widget() 创建并复用：控件带着光标位置与
        选区，界面每次刷新都重建的话光标会跳回末尾。
        """

        # 选区：内容里的下标。start <= end，end 不含；两者相等表示没有选区。
        sel_start = 0
        sel_end = 0

        # 拖拽时按住的那一端；None 表示当前没在拖
        drag_anchor = None

        # 连击判定（双击选词、三击全选）：上次按下的时间、位置与次数
        click_time = -10.0
        click_pos = (0, 0)
        click_count = 0

        # 自己占的那一行：宽取父容器给的宽度，高取排版高度。
        # 事件坐标是相对自己的，靠它判断"这一下点在不在输入框这一行里"，
        # 免得把面板别处（乃至游戏）的点击吃掉。
        row_size = (0, 0)

        # 选区底色（init 时从颜色写法转成 Render 要的四元组）
        select_rgba = (255, 204, 102, 96)

        # 让路判定：由快捷键那一层给的可调用对象，收到事件后返回真表示
        # "这一下绑成了快捷键"。None = 没有快捷键功能（照官方 Input 处理）。
        hotkey_filter = None

        def __init__(self, select_color=None, hotkey_filter=None, **kwargs):
            renpy.display.behavior.Input.__init__(self, **kwargs)

            self.hotkey_filter = hotkey_filter

            if select_color is None:
                try:
                    select_color = livetl_input_select_color
                except Exception:
                    select_color = ""

            self.select_rgba = _livetl_engine_input_color(select_color)

            # 撤销 / 重做历史：每个控件一份（面板上同时有语言与译文两个输入框）
            self.undo_stack = []
            self.redo_stack = []

            # 这一次事件开始前的状态，以及这次事件有没有真的改到内容
            self.edit_before = None
            self.edit_touched = False

            # 上一次"净效果是插入一个字符"的编辑（结束位置、时间），
            # 用来把连续打字合并成一步
            self.last_edit_end = None
            self.last_edit_time = -10.0

            # 正在恢复历史：恢复过程本身不再记进历史
            self.restoring = False

        # -----------------------------------------------------------------
        # 选区状态（供内部与自检使用）
        # -----------------------------------------------------------------

        def livetl_selected_text(self):
            """当前选中的文本；没有选区时是空串。"""
            if self.sel_end <= self.sel_start:
                return ""

            return self.content[self.sel_start:self.sel_end]

        def livetl_clear_selection(self):
            """收起选区（光标不动）。"""
            self.sel_start = 0
            self.sel_end = 0
            self.drag_anchor = None

        def _livetl_has_selection(self):
            return self.sel_end > self.sel_start

        # -----------------------------------------------------------------
        # 撤销与重做
        #
        # 官方 Input 没有撤销，这里自己记：每次"译者真的改了内容"之前存一份
        # 快照（内容 + 光标 + 选区），Ctrl+Z 恢复它；连续打字合并成一步，
        # 不然改一句话要按十几次。Ctrl+Y / Ctrl+Shift+Z 重做。
        #
        # 历史只属于"当前这一条"：内容被外面换掉（新台词、切到别的菜单条目）
        # 就清空，免得 Ctrl+Z 把上一条的译文撤进当前输入框。撤销只作用于
        # 输入框内容，不会去改已经写回 tl 的文件。
        # -----------------------------------------------------------------

        # 撤销栈上限（够来回改，又不至于一直占内存）
        _livetl_history_limit = 200

        # 连续打字合并的时间窗（秒）
        _livetl_merge_window = 1.0

        def livetl_clear_history(self):
            """清空撤销 / 重做历史。"""
            self.undo_stack = []
            self.redo_stack = []
            self.last_edit_end = None

        def _livetl_snapshot(self):
            """当前这一份内容的快照。"""
            return (self.content, self.caret_pos, self.sel_start, self.sel_end)

        def _livetl_record_edit(self, before, new_content):
            """一次事件改到了内容：把改动前的那一份记进撤销栈。

            单字符插入、且接着上一次插入的位置（一秒以内）时不另记一步 ——
            等于"刚才那一串打字算一步"。
            """
            content, caret, _sel_start, _sel_end = before
            pos = None

            if len(new_content) == len(content) + 1:
                candidate = caret

                if (new_content[:candidate] == content[:candidate]) and (new_content[candidate + 1:] == content[candidate:]):
                    pos = candidate

            merge = (
                (pos is not None)
                and (self.last_edit_end is not None)
                and (self.last_edit_end == pos)
                and ((self.st - self.last_edit_time) <= self._livetl_merge_window)
            )

            if not merge:
                self.undo_stack.append(before)

                if len(self.undo_stack) > self._livetl_history_limit:
                    del self.undo_stack[0]

            self.redo_stack = []

        def _livetl_finish_edit(self, st):
            """事件结束时记下它的"净效果"，供连续打字合并用。"""
            if not self.edit_touched:
                return

            content = self.edit_before[0]
            caret = self.edit_before[1]
            after = self.content

            if (len(after) == len(content) + 1) and (after[:caret] == content[:caret]) and (after[caret + 1:] == content[caret:]):
                self.last_edit_end = caret + 1
                self.last_edit_time = st
            else:
                self.last_edit_end = None

        def _livetl_restore(self, snapshot):
            """把控件恢复到某一份快照（内容、光标、选区）。"""
            content, caret, sel_start, sel_end = snapshot
            length = len(content)

            self.caret_pos = max(0, min(int(caret), length))
            self.old_caret_pos = self.caret_pos

            self.restoring = True
            try:
                # restoring 期间不记历史 —— 恢复本身不是一次编辑
                self.update_text(content, self.editable)
            finally:
                self.restoring = False

            # 内容一变，update_text 那侧会收起选区，这里按快照恢复
            self.sel_start = max(0, min(int(sel_start), length))
            self.sel_end = max(0, min(int(sel_end), length))

            renpy.redraw(self, 0)

        def _livetl_undo(self):
            """Ctrl+Z：撤销一步；没有历史可撤时返回 False。"""
            if not self.undo_stack:
                return False

            self.redo_stack.append(self._livetl_snapshot())
            self._livetl_restore(self.undo_stack.pop())
            self.last_edit_end = None

            return True

        def _livetl_redo(self):
            """Ctrl+Y / Ctrl+Shift+Z：重做一步；没有可重做的返回 False。"""
            if not self.redo_stack:
                return False

            self.undo_stack.append(self._livetl_snapshot())
            self._livetl_restore(self.redo_stack.pop())
            self.last_edit_end = None

            return True

        def _livetl_history_key(self, ev):
            """撤销 / 重做的按键；真的动了历史才返回 True（好决定要不要吃事件）。"""
            if renpy.map_event(ev, "ctrl_noshift_K_z") or renpy.map_event(ev, "meta_noshift_K_z"):
                return self._livetl_undo()

            if (
                renpy.map_event(ev, "ctrl_noshift_K_y")
                or renpy.map_event(ev, "meta_noshift_K_y")
                or renpy.map_event(ev, "ctrl_shift_K_z")
                or renpy.map_event(ev, "meta_shift_K_z")
            ):
                return self._livetl_redo()

            return False

        # -----------------------------------------------------------------
        # 内部：光标与选区
        # -----------------------------------------------------------------

        def _livetl_move_caret(self, index):
            """把光标放到第 index 个字符前（超出范围就夹到两端）。"""
            index = max(0, min(int(index), len(self.content)))

            if index != self.caret_pos:
                self.caret_pos = index
                self.old_caret_pos = index
                self.update_text(self.content, self.editable)
            else:
                renpy.redraw(self, 0)

        def _livetl_replace_selection(self, text):
            """用 text 换掉当前选区，光标落在替换内容之后。"""
            if not self._livetl_has_selection():
                return

            start = self.sel_start
            end = self.sel_end
            content = self.content[:start] + text + self.content[end:]

            self.sel_start = 0
            self.sel_end = 0
            self.drag_anchor = None
            self.caret_pos = start + len(text)
            self.old_caret_pos = self.caret_pos

            # 走本类的 update_text：写回 value（store 变量）、重绘，
            # 以及"记进撤销栈"都由它负责
            self.update_text(content, self.editable)

        def _livetl_copy_selection(self):
            """把选中的文本放进系统剪贴板。"""
            try:
                import pygame
                pygame.scrap.put(
                    pygame.scrap.SCRAP_TEXT,
                    self.livetl_selected_text().encode("utf-8"),
                )
            except Exception as e:
                livetl_engine_note_error("input/copy", e)

        def _livetl_word_range(self, index):
            """双击选中的范围：从这个字往两边扩到分隔符为止。"""
            content = self.content
            length = len(content)

            if not length:
                return (0, 0)

            index = max(0, min(int(index), length))

            # 光标夹在两字之间时，优先算左边那个字所在的一段（与常见编辑器一致）
            anchor = index - 1

            if (anchor < 0) or _livetl_engine_input_is_sep(content[anchor]):
                if (index < length) and not _livetl_engine_input_is_sep(content[index]):
                    anchor = index

            anchor = max(0, min(anchor, length - 1))
            sep = _livetl_engine_input_is_sep(content[anchor])

            start = anchor
            end = anchor + 1

            while (start > 0) and (_livetl_engine_input_is_sep(content[start - 1]) == sep):
                start -= 1

            while (end < length) and (_livetl_engine_input_is_sep(content[end]) == sep):
                end += 1

            return (start, end)

        def _livetl_click_count(self, st, x, y):
            """连击计数：同一位置、0.5 秒内再按一次算下一击。"""
            close = (abs(x - self.click_pos[0]) <= 4) and (abs(y - self.click_pos[1]) <= 4)

            if close and ((st - self.click_time) <= 0.5):
                self.click_count += 1
            else:
                self.click_count = 1

            self.click_time = st
            self.click_pos = (x, y)

            return self.click_count

        # -----------------------------------------------------------------
        # 内部：事件
        # -----------------------------------------------------------------

        def _livetl_inside(self, x, y):
            """这一下点在不在输入框这一行里。"""
            width, height = self.row_size

            return (0 <= x < width) and (0 <= y < height)

        def _livetl_hotkey_mode(self, ev):
            """这一下对输入框意味着什么："" / "live" / "bound" / "swallow"。

            判定由快捷键那层给（hotkey_filter），输入框只管照做：

            输入框在渲染树里排在面板 screen 的 key 语句后面，而事件是从后往前
            分发的 —— 真正先拿到按键的是输入框。引擎的 Input 一认"可打印键"
            就会当打字吃掉，带字母的快捷键于是永远轮不到 key 语句（实测：
            绑 Ctrl+S / Shift+R 之后，翻译时按下去一点反应都没有）。

            * "live"  —— 让路：事件继续往后传，最终落到 key 语句上执行动作；
            * "bound" —— 绑了但此刻不生效：吃掉，但只是"别打字"，不执行动作
                          （译者在设置页试一下自己刚绑的键是最自然不过的事）；
            * "swallow" —— 上面两种按键带出来的文本（含输入法的组合与上屏）：
                           吞掉，别让它落进输入框。
            """
            if self.hotkey_filter is None:
                return ""

            return self.hotkey_filter(ev)

        def _livetl_mouse(self, ev, x, y, st):
            """鼠标事件；返回 True 表示这一下归输入框，别再往下传。"""
            try:
                import pygame
            except Exception as e:
                livetl_engine_note_error("input/pygame", e)
                return False

            if (ev.type == pygame.MOUSEBUTTONDOWN) and (ev.button == 1):
                if not self._livetl_inside(x, y):
                    # 点到别处：像普通输入框那样收起选区，但这一下不归我们
                    self.livetl_clear_selection()
                    return False

                index = livetl_engine_input_index_at(self, x, y)

                if index is None:
                    # 排版里认不出第几个字：只挡住点击，不动光标
                    return True

                count = self._livetl_click_count(st, x, y)

                if count >= 3:
                    self.sel_start, self.sel_end = 0, len(self.content)
                    self._livetl_move_caret(len(self.content))
                elif count == 2:
                    self.sel_start, self.sel_end = self._livetl_word_range(index)
                    self._livetl_move_caret(index)
                else:
                    self.livetl_clear_selection()
                    self._livetl_move_caret(index)

                self.drag_anchor = index
                return True

            if (ev.type == pygame.MOUSEBUTTONUP) and (ev.button == 1):
                if self.drag_anchor is None:
                    return False

                self.drag_anchor = None
                return True

            if ev.type == pygame.MOUSEMOTION:
                if self.drag_anchor is None:
                    return False

                index = livetl_engine_input_index_at(self, x, y)

                if index is None:
                    return True

                # 拖到输入框外面时下标会被夹到两端，和常见输入框一致
                self.sel_start = min(self.drag_anchor, index)
                self.sel_end = max(self.drag_anchor, index)
                self._livetl_move_caret(index)
                return True

            return False

        def _livetl_deletes(self, ev):
            """这个事件是不是删除（退格 / Delete / 删词 / 删到最前）。"""
            for name in ("input_backspace", "input_delete", "input_delete_word", "input_delete_full"):
                if renpy.map_event(ev, name):
                    return True

            return False

        def _livetl_types(self, ev):
            """这个事件会不会往输入框里塞字（打字、粘贴、输入法上屏）。"""
            try:
                import pygame
            except Exception:
                return False

            if ev.type in (pygame.TEXTINPUT, pygame.TEXTEDITING):
                return True

            if renpy.map_event(ev, "input_paste"):
                return True

            return (ev.type == pygame.KEYDOWN) and bool(getattr(ev, "unicode", ""))

        def _livetl_edit_selection(self, ev):
            """选区存在时的编辑行为。

            * 打字 / 粘贴 / 输入法上屏 → 先删掉选区，官方实现再插入新内容；
            * 退格 / 删除 → 删掉选区，这一次按键就到此为止（不再多删一个字）；
            * 左右方向键 / Home / End → 收起到选区的一端；
            * 复制 → 复制选中的那一段（官方实现只会复制全文）；
            * 剪切 → 复制选中的那一段再删掉它。
            """
            if not self._livetl_has_selection():
                return

            if renpy.map_event(ev, "input_copy"):
                self._livetl_copy_selection()
                raise renpy.display.core.IgnoreEvent()

            if self._livetl_cut_selection(ev):
                raise renpy.display.core.IgnoreEvent()

            if self._livetl_deletes(ev):
                self._livetl_replace_selection("")
                raise renpy.display.core.IgnoreEvent()

            if renpy.map_event(ev, "input_left") or renpy.map_event(ev, "input_jump_word_left") or renpy.map_event(ev, "input_home"):
                start = self.sel_start
                self.livetl_clear_selection()
                self._livetl_move_caret(start)
                raise renpy.display.core.IgnoreEvent()

            if renpy.map_event(ev, "input_right") or renpy.map_event(ev, "input_jump_word_right") or renpy.map_event(ev, "input_end"):
                end = self.sel_end
                self.livetl_clear_selection()
                self._livetl_move_caret(end)
                raise renpy.display.core.IgnoreEvent()

            if self._livetl_types(ev):
                self._livetl_replace_selection("")

        def _livetl_select_all(self, ev):
            """Ctrl+A / Cmd+A：全选。

            官方 Input 连"全选"都没有。这里直接用按键写法判定，不改
            config.keymap —— 引擎自己的 map_event() 支持这种写法。
            """
            if not (renpy.map_event(ev, "ctrl_noshift_K_a") or renpy.map_event(ev, "meta_noshift_K_a")):
                return False

            self.sel_start = 0
            self.sel_end = len(self.content)
            self.drag_anchor = None
            self._livetl_move_caret(self.sel_end)

            return True

        def _livetl_cut_selection(self, ev):
            """Ctrl+X / Cmd+X：剪切（复制到剪贴板，再删掉选区）。

            官方 Input 连"复制"都只会复制全文，更没有剪切。没有选中内容时
            不动这个键：单行输入框里 Ctrl+X 空剪是没意义的，别把整条译文
            清掉。
            """
            if not (renpy.map_event(ev, "ctrl_noshift_K_x") or renpy.map_event(ev, "meta_noshift_K_x")):
                return False

            if not self._livetl_has_selection():
                return False

            self._livetl_copy_selection()
            self._livetl_replace_selection("")

            return True

        # -----------------------------------------------------------------
        # 引擎接口
        # -----------------------------------------------------------------

        def update_text(self, new_content, editable, check_size=False):
            """内容变了的统一入口，历史在这里记。

            * 译者在输入框里自己改的（事件处理中）→ 记进撤销栈；
            * 外面换的（新台词、清空、切到别的条目）→ 收起选区并清空历史，
              免得 Ctrl+Z 把上一条的译文撤进当前输入框。
            """
            if new_content != self.content:
                if self.restoring:
                    pass
                elif self.edit_before is not None:
                    # 一次事件只记一步：选区替换会连着改两次内容
                    if not self.edit_touched:
                        self._livetl_record_edit(self.edit_before, new_content)
                        self.edit_touched = True
                else:
                    self.livetl_clear_history()

                if self._livetl_has_selection():
                    self.livetl_clear_selection()

            renpy.display.behavior.Input.update_text(
                self, new_content, editable, check_size,
            )

        def render(self, width, height, st, at):
            rv = renpy.display.behavior.Input.render(self, width, height, st, at)

            # 记住自己占的那一行（宽用父容器给的宽度：面板里整行都能点）
            self.row_size = (width, rv.height)

            rects = livetl_engine_input_selection_rects(
                self, self.sel_start, self.sel_end,
            )

            if not rects:
                return rv

            # 底色垫在文字下面：先画几块纯色，再把文字叠上去
            out = renpy.display.render.Render(rv.width, rv.height)

            for rect_x, rect_y, rect_w, rect_h in rects:
                patch = renpy.display.render.Render(rect_w, rect_h)
                patch.fill(self.select_rgba)
                out.blit(patch, (rect_x, rect_y))

            out.blit(rv, (0, 0))

            return out

        def event(self, ev, x, y, st):
            # 记住这一次事件开始前的状态：撤销要的是"改动前"的那一份
            self.st = st
            self.edit_before = self._livetl_snapshot()
            self.edit_touched = False

            try:
                # 绑成快捷键的按键让给面板的 key 语句，它带出来的文本（含输入法的
                # 组合与上屏）一起吞掉；判定由快捷键那层给（见 _livetl_hotkey_mode）
                _livetl_hotkey_mode = self._livetl_hotkey_mode(ev)

                if _livetl_hotkey_mode == "live":
                    return None

                if _livetl_hotkey_mode in ("bound", "swallow"):
                    raise renpy.display.core.IgnoreEvent()

                if self.editable:
                    # Ctrl+Z / Ctrl+Y：撤销、重做（真的动了历史才吃掉这个键）
                    if self._livetl_history_key(ev):
                        raise renpy.display.core.IgnoreEvent()

                    # Ctrl+A：全选（官方 Input 没有这个功能）
                    if self._livetl_select_all(ev):
                        raise renpy.display.core.IgnoreEvent()

                    # 鼠标：点击定位光标、拖拽选区；落在输入框这一行的都吃掉
                    if self._livetl_mouse(ev, x, y, st):
                        raise renpy.display.core.IgnoreEvent()

                    # 选区存在时，编辑类按键先按"选中再打字"的规矩处理
                    self._livetl_edit_selection(ev)

                # 回车是"提交"，处理完别再让游戏把它当成"点击推进对话"
                enter = (self.value is not None) and renpy.map_event(ev, "input_enter")
                rv = renpy.display.behavior.Input.event(self, ev, x, y, st)

                if enter and (rv is None):
                    raise renpy.display.core.IgnoreEvent()

                return rv
            finally:
                self._livetl_finish_edit(st)
                self.edit_before = None

    # 面板输入框：同一个输入值只建一个控件（见 LiveTLInput 的说明）
    _livetl_engine_input_widgets = []

    def livetl_engine_input_text_input_stop():
        """关掉系统文本输入（输入法不再收按键）；成功返回 True。

        改键时用：关掉之后按键直接给游戏，中文输入法不会把 Shift+字母 收进候选条
        （那一步在引擎之前，插件拦不住，只能预防）。
        """
        try:
            import pygame

            pygame.key.stop_text_input()
        except Exception as e:
            livetl_engine_note_error("input/text_input_stop", e)
            return False

        return True

    def livetl_engine_input_text_input_start():
        """把系统文本输入开回来（改键结束、继续打中文用）；成功返回 True。

        引擎只在"输入框刚出现"时调用 start_text_input()，所以这一步得自己调。
        """
        try:
            import pygame

            pygame.key.start_text_input()
        except Exception as e:
            livetl_engine_note_error("input/text_input_start", e)
            return False

        return True

    def livetl_engine_input_widget(value, length, select_color=None, hotkey_filter=None, **properties):
        """拿面板输入框控件（第一次调用时创建，之后复用同一个）。

        `value` 是官方 InputValue（面板的 livetl_value / livetl_language_value），
        其余属性原样交给 Input（style / size 之类）。`hotkey_filter` 是快捷键
        那层给的判定函数：命中已绑定的快捷键时返回 "live"（让路给 key 语句）
        或 "bound"（绑了但此刻不生效，只吞掉按键），详见 LiveTLInput 的说明；
        不传就完全按官方 Input 的行为走。建不出来时返回 None，
        调用方按"没有输入框"处理（add None 是合法的）。
        """
        try:
            for cached_value, widget in _livetl_engine_input_widgets:
                if cached_value is value:
                    return widget

            # 官方 Input 的复制 / 粘贴受 copypaste 开关控制，默认是关的：
            # 不打开的话 Ctrl+V 根本走不到引擎那段粘贴逻辑（面板以前就是这样，
            # 只有插件自己实现的 Ctrl+C / Ctrl+X 能动剪贴板）。
            #
            # 粘贴时引擎会丢掉换行与制表符，这是有意的：面板上原文里的换行本来
            # 就显式显示成 \n，译者也照着显式写 \n（见 README 的"写换行"）。
            properties.setdefault("copypaste", True)

            widget = LiveTLInput(
                value=value, length=length, select_color=select_color,
                hotkey_filter=hotkey_filter, **properties
            )

            _livetl_engine_input_widgets.append((value, widget))
            return widget
        except Exception as e:
            livetl_engine_note_error("input/widget", e)
            return None

    # 面板输入框的排版假设自检：只在真的画过一次之后报一次
    _livetl_engine_input_probed = False

    def _livetl_engine_input_probe_sample(widget):
        """拿实际排版验一遍坐标换算：横向取几点，下标必须单调不减。"""
        layout = widget.get_layout()
        scale = _livetl_engine_input_scale(layout)
        width = float(layout.size[0]) / scale
        height = float(layout.size[1]) / scale
        y = height / 2.0

        samples = []

        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            samples.append(livetl_engine_input_index_at(widget, width * frac, y))

        length = len(widget.content or "")

        if samples[0] != 0:
            return "left={!r}".format(samples[0])

        if samples[-1] != length:
            return "right={!r}!=chars={}".format(samples[-1], length)

        for before, after in zip(samples, samples[1:]):
            if (before is None) or (after is None) or (after < before):
                return "not-monotonic={!r}".format(samples)

        return ""

    def livetl_engine_input_probe():
        """面板输入框的排版自检；每次运行只报一次，没画过时先不报。

        "一个字形对应一个字符"与"排版坐标 = 虚拟坐标 × oversample"是鼠标
        定位、拖拽选区都依赖的假设。引擎不报错、行为却变了的那类改动
        （语义漂移）只能靠这种自检发现，所以它写进 livetl.log。
        """
        global _livetl_engine_input_probed

        if _livetl_engine_input_probed:
            return []

        widget = None

        for _value, candidate in _livetl_engine_input_widgets:
            if candidate.get_layout() is not None:
                widget = candidate
                break

        if widget is None:
            return []

        _livetl_engine_input_probed = True

        try:
            reason = _livetl_engine_input_probe_sample(widget)
        except Exception as e:
            livetl_engine_note_error("input/probe", e)
            reason = repr(e)

        if reason:
            return [
                "engine seam runtime: input_map=no（{}：鼠标定位退回只挡点击，"
                "详见上一行 seam 错误）".format(reason),
            ]

        layout = widget.get_layout()

        return [
            "engine seam runtime: input_map=ok chars={} lines={} oversample={}".format(
                len(widget.content or ""),
                len(getattr(layout, "lines", None) or []),
                _livetl_engine_input_scale(layout),
            ),
        ]
