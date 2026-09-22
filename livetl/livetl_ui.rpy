# =============================================================================
# LiveTL —— 翻译面板
#
# 面板显示当前台词的原文与一个输入框：
#   [提交] 把输入框内容写回 tl 文件（不打断游戏）
#   [重载] 触发脚本热重载，让写回的译文立刻生效
#   [×]    折叠面板（快捷键可以重新打开）
# =============================================================================

init python:

    def livetl_set_visible(value):
        """展开 / 折叠面板。

        同时写 session 与 store：session 用于抵抗"回退"回滚，
        store 用于界面即时渲染。
        """
        renpy.session["livetl_visible"] = value
        store.livetl_visible = value

    def livetl_toggle_visible():
        livetl_set_visible(not renpy.session.get("livetl_visible", True))

    def livetl_escape(s):
        """把原文转义成可以按字面显示的文本。

        原文里的 {w}、[name] 是 Ren'Py 的文本标签与插值，
        直接显示会被解析掉，所以要转义成字面量。
        换行、制表符这类控制字符也还原成 \\n / \\t 的写法，
        这样译者看到的和源码里写的一致。
        """
        if not s:
            return ""

        s = s.replace("\r\n", "\\n")
        s = s.replace("\n", "\\n")
        s = s.replace("\r", "\\n")
        s = s.replace("\t", "\\t")

        return s.replace("{", "{{").replace("[", "[[")

    def livetl_input_text(s):
        """译文放进输入框时的显示形式。

        只处理控制字符（换行 → \\n），不动 { } [ ]：
        输入框里的内容会原样写回 tl，转义花括号会破坏译文。
        """
        if not s:
            return ""

        s = s.replace("\r\n", "\\n")
        s = s.replace("\n", "\\n")
        s = s.replace("\r", "\\n")
        s = s.replace("\t", "\\t")

        return s

    def livetl_unescape_input(s):
        """把输入框里的 \\n 等写法还原成实际字符。

        与上面两个函数对称：译者照着面板显示写 \\n，写回 tl 后
        就是真正的换行；想写字面反斜杠就写 \\\\，想写字面引号就写 \\"。
        """
        if not s:
            return ""

        rv = []
        i = 0

        while i < len(s):
            c = s[i]

            if (c == "\\") and (i + 1 < len(s)):
                n = s[i + 1]

                if n == "n":
                    rv.append("\n")
                    i += 2
                    continue
                if n == "t":
                    rv.append("\t")
                    i += 2
                    continue
                if n == "r":
                    rv.append("\r")
                    i += 2
                    continue
                if n == "\\":
                    rv.append("\\")
                    i += 2
                    continue
                if n == '"':
                    rv.append('"')
                    i += 2
                    continue

            rv.append(c)
            i += 1

        return "".join(rv)

    class LiveTLInputValue(VariableInputValue):
        """面板输入框的取值对象。

        直接继承官方的 VariableInputValue，保留它处理输入同步的全部细节
        （内容变化时写回 store 变量并刷新交互）；
        只把「回车」改成与「提交」按钮等效。

        这样写是为了同时兼容 Ren'Py 8.1 与 8.5：
        8.1 的 input 语句没有 action 参数，不能用它绑定回车。
        """

        def enter(self):
            livetl_submit()
            return None


default livetl_value = LiveTLInputValue("livetl_input")


init 10 python:

    # 每句台词开始时刷新面板内容
    def _livetl_character_callback(event, interact=True, **kwargs):
        if event == "begin":
            livetl_sync()

    if _livetl_character_callback not in config.all_character_callbacks:
        config.all_character_callbacks.append(_livetl_character_callback)


screen livetl_panel():
    zorder 500

    # 快捷键：显示 / 折叠面板
    key livetl_hotkey action Function(livetl_toggle_visible)

    # 快捷键：进入拾取模式（拾取状态下由拾取层自己处理退出）
    if not livetl_pick_active:
        key livetl_pick_hotkey action Function(livetl_pick_enter)

    # 面板位置（右上角或右下角）
    $ _bottom = (livetl_position == "bottom-right")
    $ _yalign = 1.0 if _bottom else 0.0
    $ _yoffset = -150 if _bottom else 16

    if livetl_pick_active:

        # 拾取模式下面板整体让位给拾取层
        pass

    elif not livetl_visible:

        # 折叠状态：只在角落留一个小按钮
        textbutton "TL":
            style "livetl_action"
            xalign 1.0
            yalign 0.0
            xoffset -8
            yoffset 8
            action Function(livetl_set_visible, True)

    elif livetl_need_setup():

        # 还没选定目标语言：在主界面里直接询问
        #
        frame:
            style_prefix "livetl"
            xalign 1.0
            yalign _yalign
            xoffset -16
            yoffset _yoffset
            xsize livetl_panel_width

            vbox:
                spacing 8

                hbox:
                    spacing 12
                    text "LiveTL 翻译模式" style "livetl_title"
                    textbutton "折叠" style "livetl_action" action Function(livetl_set_visible, False)

                text "目标语言（即 tl 目录名），例如 schinese、tchinese、japanese：" style "livetl_source"

                input:
                    id "livetl_language_input"
                    value livetl_language_value
                    length 40
                    size 22

                # 未翻译的句子怎么显示，交给译者选
                text "没翻过的句子在游戏里：" style "livetl_source"

                hbox:
                    spacing 10

                    textbutton "留空":
                        style "livetl_action"
                        action SetVariable("livetl_show_source_when_empty", False)
                        selected (not livetl_show_source_when_empty)

                    textbutton "显示原文":
                        style "livetl_action"
                        action SetVariable("livetl_show_source_when_empty", True)
                        selected (livetl_show_source_when_empty)

                hbox:
                    spacing 10
                    textbutton "开始翻译" style "livetl_action" action Function(livetl_confirm_language)
                    textbutton "检查重复" style "livetl_action" action Function(livetl_dup_open)

                # 设置界面也要有反馈：否则点【检查重复】之类的操作看不到结果
                if livetl_status:
                    text "[livetl_status]" style "livetl_status"

    else:

        frame:
            style_prefix "livetl"
            xalign 1.0
            yalign _yalign
            xoffset -16
            yoffset _yoffset
            xsize livetl_panel_width

            vbox:
                spacing 8

                # 标题栏
                hbox:
                    spacing 12
                    text "LiveTL":
                        style "livetl_title"
                    if livetl_mode == "menu":
                        text "菜单 · [livetl_menu_count] 条":
                            style "livetl_title"
                    elif livetl_mode == "dup":
                        text "查重体检":
                            style "livetl_title"
                    textbutton "折叠" style "livetl_action" action Function(livetl_set_visible, False)

                if livetl_mode == "dup":
                    use livetl_dup_body()
                else:
                    if livetl_mode == "menu":
                        use livetl_menu_body()

                    use livetl_edit_body()

                # 最近一次操作的反馈
                if livetl_status:
                    text "[livetl_status]" style "livetl_status"


# -----------------------------------------------------------------------------
# 编辑区：原文 + 输入框 + 操作按钮（对话与字符串条目共用）
# -----------------------------------------------------------------------------

screen livetl_edit_body():

    # 插值里不做函数调用，先算好再显示（兼容 8.1）
    $ _source_display = livetl_escape(livetl_current_source)

    if livetl_current_kind == "string":
        text "条目: [_source_display]" style "livetl_source"
    else:
        text "原文: [_source_display]" style "livetl_source"

    if livetl_show_id and livetl_current_tid:
        text "id: [livetl_current_tid!q]" size 16

    # 译文输入框：已保存过就填进去方便修改，否则留空
    input:
        id "livetl_input"
        value livetl_value
        length 2000
        size 22

    # 提交与重载分开，便于连续翻译
    hbox:
        spacing 10
        textbutton "提交" style "livetl_action" action Function(livetl_submit)
        textbutton "清空":
            style "livetl_action"
            action Confirm(
                "清空当前条目？\n对话只清掉译文；字符串条目会从 tl 里删除。",
                Function(livetl_clear_entry),
            )
        textbutton "重载" style "livetl_action" action Function(livetl_reload)
        textbutton "拾取" style "livetl_action" action Function(livetl_pick_enter)

        if (livetl_mode != "menu") and (renpy.get_screen("choice") is not None):
            textbutton "回菜单" style "livetl_action" action Function(livetl_menu_back)

        textbutton "设置" style "livetl_action" action Function(livetl_open_setup)


# -----------------------------------------------------------------------------
# 菜单列表：当前菜单的所有条目，点一下选中并编辑
# -----------------------------------------------------------------------------

screen livetl_menu_body():

    viewport:
        ymaximum livetl_menu_list_height
        scrollbars "vertical"
        mousewheel True

        vbox:
            spacing 2

            for _livetl_row in range(len(livetl_menu_items)):
                textbutton livetl_menu_row_text(_livetl_row):
                    style "livetl_menu_item"
                    selected (_livetl_row == livetl_menu_index)
                    action Function(livetl_menu_select, _livetl_row)


# -----------------------------------------------------------------------------
# 查重体检：列出重复的字符串条目，可一键清理
# -----------------------------------------------------------------------------

screen livetl_dup_body():

    if not livetl_dup_report:
        text "没有发现重复条目" style "livetl_source"
    else:
        text "同一语言下重复的字符串条目会让游戏启动报错，建议清理：" style "livetl_source"

        viewport:
            ymaximum livetl_menu_list_height
            scrollbars "vertical"
            mousewheel True

            vbox:
                spacing 2

                for _livetl_key, _livetl_places in livetl_dup_report:
                    $ _livetl_key_text = livetl_escape(_livetl_key)
                    text "[_livetl_key_text]" style "livetl_source"

                    for _livetl_rel, _livetl_line, _livetl_new in _livetl_places:
                        text "    [_livetl_rel]:[_livetl_line]" size 16

    hbox:
        spacing 10

        if livetl_dup_report:
            textbutton "清理（保留第一条）" style "livetl_action" action Function(livetl_dup_clean)

        textbutton "重新扫描" style "livetl_action" action Function(livetl_dup_rescan)
        textbutton "返回" style "livetl_action" action Function(livetl_dup_close)


style livetl_frame:
    background "#000000d0"
    padding (16, 12)

style livetl_action is default:
    background None
    hover_background "#ffffff30"
    selected_background "#ffcc6640"
    padding (10, 4)

style livetl_action_text is default:
    size 20
    color "#ffffff"
    hover_color "#ffcc66"
    selected_color "#ffcc66"

style livetl_title is default:
    size 20
    color "#ffcc66"

style livetl_source is default:
    size 20
    color "#dfdfdf"

style livetl_input is default:
    size 22
    color "#ffffff"

style livetl_status is default:
    size 17
    color "#a0d0a0"

style livetl_menu_item is default:
    background None
    hover_background "#ffffff30"
    selected_background "#ffcc6640"
    padding (8, 3)
    xfill True

style livetl_menu_item_text is default:
    size 18
    color "#ffffff"
    hover_color "#ffcc66"
    selected_color "#ffcc66"


init 500 python:

    # 面板字体：默认跟随游戏本身的字体；只有配置了 livetl_font
    # 才覆盖成指定字体（例如游戏字体不含中文时）。
    #
    # try/except 是为了兼容 lint：lint 阶段样式表尚未建立，
    # 直接赋值会中断检查。
    if livetl_font:
        try:
            style.livetl_title.font = livetl_font
            style.livetl_source.font = livetl_font
            style.livetl_input.font = livetl_font
            style.livetl_action_text.font = livetl_font
            style.livetl_status.font = livetl_font
            style.livetl_menu_item_text.font = livetl_font
            style.livetl_pick_tip_text.font = livetl_font
            style.livetl_pick_preview_text.font = livetl_font
        except Exception:
            pass


init python:

    # 面板挂载分两处：
    #   * 游戏进行中的每次交互：由 overlay_screens 自动显示
    #   * 主菜单：那里的交互会抑制 overlay，所以在交互开始时主动显示
    #
    # 启动阶段（GPU 性能测试等）既不在主菜单也不在游戏里，
    # 面板不会出现，不打扰游戏启动。
    if "livetl_panel" not in config.overlay_screens:
        config.overlay_screens.append("livetl_panel")

    def livetl_sync_input_collapse():
        """游戏自己弹输入框时自动折叠面板，输入完自动恢复。

        面板里的输入框会跟游戏的输入框抢键盘焦点（输入法候选与回车
        都会失效），所以这时把面板收成角落的小按钮；
        游戏输入结束后再展开回用户原来的显示状态。
        """
        game_input = livetl_game_input_active()
        collapsed = renpy.session.get("livetl_input_collapsed", False)

        if game_input and not collapsed:
            # 记下用户原本的显示状态，输入完还回去
            renpy.session["livetl_visible_before_input"] = store.livetl_visible
            renpy.session["livetl_input_collapsed"] = True

            store.livetl_visible = False
            renpy.session["livetl_visible"] = False
            # 这里不要 restart_interaction：重启会清空输入框列表，
            # 下一拍就检测不到游戏输入框，于是又恢复、再折叠，来回抖。
            # livetl_visible 是面板 screen 直接依赖的变量，改它就会重绘。

        elif (not game_input) and collapsed:
            renpy.session["livetl_input_collapsed"] = False

            restore = renpy.session.get("livetl_visible_before_input", True)
            store.livetl_visible = restore
            renpy.session["livetl_visible"] = restore

    def livetl_ensure_panel():
        """确保面板已显示。

        主菜单与游戏内的交互都会抑制 overlay，
        所以这里主动显示面板；启动阶段的 GPU 性能测试
        同时抑制 underlay 与 overlay，把它排除掉。
        """
        if renpy.display.interface.suppress_underlay:
            return

        # 目标语言选定后（含首次启动），补全 tl 模板
        livetl_ensure_templates()

        # 菜单出现时面板切成菜单列表；拾取模式下确保拾取层还在（例如热重载之后）
        if store.livetl_pick_active:
            livetl_pick_screen_sync()
        else:
            livetl_menu_sync()

        # 启动后的第一次交互做一次重复条目检查（只提示，不改文件）
        livetl_dup_check_startup()

        # 面板显示状态以 session 为准：
        # 剧情回退会回滚 store 变量，这里每次交互都同步回来。
        store.livetl_visible = renpy.session.get("livetl_visible", True)

        # 游戏自己在等输入（renpy.input）时自动折叠面板：
        # 面板里的输入框会跟游戏的输入框抢键盘焦点。
        # 输入结束后自动展开回原来的状态。
        livetl_sync_input_collapse()

        if renpy.get_screen("livetl_panel") is None:
            renpy.show_screen("livetl_panel")

        # 新的一句开始时，把输入焦点放进输入框
        if store.livetl_focus_pending:
            # 游戏在等输入时先不抢，等它输入完再给面板聚焦
            if not livetl_game_input_active():
                store.livetl_focus_pending = False
                renpy.set_focus("livetl_panel", "livetl_input")

        # 重载后的第一次交互：跳回刚才那一句，让新译文重新渲染
        tid = renpy.session.pop("livetl_replay_tid", None)

        if tid:
            node = livetl_lookup_node(tid)
            name = getattr(node, "name", None)
            livetl_log("replay after reload: tid={!r} name={!r}".format(tid, name))

            if name:
                renpy.jump(name)

    if livetl_ensure_panel not in config.interact_callbacks:
        config.interact_callbacks.append(livetl_ensure_panel)
