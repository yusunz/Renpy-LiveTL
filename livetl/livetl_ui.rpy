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
        """
        if not s:
            return ""
        return s.replace("{", "{{").replace("[", "[[")

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

    # 面板位置（右上角或右下角）
    $ _bottom = (livetl_position == "bottom-right")
    $ _yalign = 1.0 if _bottom else 0.0
    $ _yoffset = -150 if _bottom else 16

    if not livetl_visible:

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

    else:

        # 翻译状态：显示当前句原文，等待译者输入译文
        # （插值里不能用函数调用，先算好再显示，兼容 8.1）
        $ _source_display = livetl_escape(livetl_current_source)

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
                    textbutton "折叠" style "livetl_action" action Function(livetl_set_visible, False)

                if livetl_show_id:
                    text "id: [livetl_current_tid!q]" size 16

                # 原文（按字面显示，保留 {w} 之类的标签）
                text "原文: [_source_display]" style "livetl_source"

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
                    textbutton "重载" style "livetl_action" action Function(livetl_reload)
                    textbutton "设置" style "livetl_action" action Function(livetl_open_setup)

                # 最近一次操作的反馈
                if livetl_status:
                    text "[livetl_status]" style "livetl_status"


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

        # 面板显示状态以 session 为准：
        # 剧情回退会回滚 store 变量，这里每次交互都同步回来。
        store.livetl_visible = renpy.session.get("livetl_visible", True)

        if renpy.get_screen("livetl_panel") is None:
            renpy.show_screen("livetl_panel")

        # 新的一句开始时，把输入焦点放进输入框
        if store.livetl_focus_pending:
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
