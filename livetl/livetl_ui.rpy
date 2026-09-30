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
        livetl_state_set("livetl_visible", value)
        store.livetl_visible = value

    def livetl_toggle_visible():
        livetl_set_visible(not livetl_state_get("livetl_visible", True))

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

    class LiveTLFindInputValue(LiveTLInputValue):
        """搜索框的取值对象：内容一变就按新关键词刷新结果。

        搜索是即时过滤：每敲一个字都重新过滤一遍索引（几万条在内存里
        跑子串匹配）。回车在搜索页没有别的动作。
        """

        def set_text(self, s):
            rv = LiveTLInputValue.set_text(self, s)
            livetl_find_refresh()
            return rv

        def enter(self):
            return None

    class LiveTLFontDropTarget(renpy.Displayable):
        """接住从系统里拖进来的字体文件。

        引擎只会把 DROPFILE 交给渲染树里的 displayable，所以设置界面要
        挂上这么一层（它自己不画东西）。注意事件的派发与坐标无关：
        拖到游戏窗口上就算数，界面里那个方框只是给译者瞄准的地方。
        """

        def __init__(self, **kwargs):
            renpy.Displayable.__init__(self, **kwargs)

        def render(self, width, height, st, at):
            return renpy.Render(1, 1)

        def event(self, ev, x, y, st):
            if ev.type == livetl_engine_file_drop_type():
                livetl_font_drop(getattr(ev, "file", None))

                # 列表开着的话（拖入时通常开着），把它刷成最新的
                if store.livetl_font_panel_open:
                    store.livetl_font_choices = livetl_font_list()

            return None

    livetl_font_drop_target = LiveTLFontDropTarget()

    class LiveTLHotkeyCapture(renpy.Displayable):
        """接住"改键"时按下的那一个键。

        和字体拖放层同一个套路：引擎只把事件交给渲染树里的 displayable，
        所以设置界面要挂上这一层（它自己不画东西）。不在捕获态时它什么都
        不做，事件照常往下走。

        吃事件要用 IgnoreEvent，不能 return 一个值：文档里写明"event() 返回
        非 None 时，这个值就是本次交互的返回值"—— 那样 say 会当场结束，
        剧情往前走一句（实测：改键时按 Ctrl 或字母，剧情自己跳行，按住
        Ctrl 更是连着跳好几句，看着就是快进）。
        """

        def __init__(self, **kwargs):
            renpy.Displayable.__init__(self, **kwargs)

        def render(self, width, height, st, at):
            return renpy.Render(1, 1)

        def event(self, ev, x, y, st):
            if livetl_hotkey_capture_key(ev):
                # 忽略这个事件、交互继续；返回值会把交互结束掉
                raise renpy.IgnoreEvent()

            return None

    livetl_hotkey_capture_target = LiveTLHotkeyCapture()

    # ---------------------------------------------------------------------
    # 设置界面里的字体操作
    # ---------------------------------------------------------------------

    def livetl_font_panel_toggle():
        """展开 / 收起字体列表（展开时重新扫一遍字体目录）。"""
        open_now = not bool(store.livetl_font_panel_open)
        store.livetl_font_panel_open = open_now

        if open_now:
            store.livetl_font_choices = livetl_font_list()

        livetl_restart()

    def livetl_font_choose(rel_path):
        """从列表里挑一个字体。"""
        store.livetl_font_panel_open = False
        livetl_font_use(rel_path)

    def livetl_font_choice_text(choice):
        """字体列表里一行的显示文字。"""
        text = choice["name"]

        if choice["variable"]:
            text += "（可变字体，中文可能显示方块）"

        if choice["path"] == livetl_font:
            text = "· " + text

        return text

    # 面板的临时状态：普通赋值，不用 default（原因见 livetl_setup.rpy 里的说明；
    # 这几项本来也不需要"存档 + 回退"）。
    livetl_value = LiveTLInputValue("livetl_input")

    # 搜索页 / 编辑搜索结果的状态（理由与上面相同；值是普通 Python 值，
    # 不写 default：这些是面板临时状态）。
    livetl_find_value = LiveTLFindInputValue("livetl_find_input")
    livetl_find_input = ""
    livetl_find_query = ""
    livetl_find_results = []
    livetl_find_total = 0
    livetl_find_loaded_index = -1
    livetl_edit_origin = ""
    livetl_find_tid = None

    livetl_font_panel_open = False
    livetl_font_choices = []


init 10 python:

    # 每句台词开始时刷新面板内容
    def _livetl_character_callback(event, interact=True, **kwargs):
        if event == "begin":
            livetl_sync()

    if _livetl_character_callback not in config.all_character_callbacks:
        config.all_character_callbacks.append(_livetl_character_callback)


screen livetl_panel():
    zorder 500

    # 快捷键：哪个动作此刻生效由 livetl_hotkey_live_keys() 决定（折叠后
    # 只留显示 / 折叠与拾取，写着译文时再加上提交 / 重载 / 清空）。
    #
    # 位置放在 screen 最前面：key 变成的 Keymap 在渲染树里排在输入框前面，
    # 而事件是从后往前分发的，所以它比输入框晚一步拿到按键 —— 输入框那边
    # 负责把快捷键的按键让出来（见 livetl_engine_input.rpy 的说明）。
    for _livetl_key_action, _livetl_key_sym in livetl_hotkey_live_keys():
        key _livetl_key_sym action livetl_hotkey_action(_livetl_key_action)

    # 面板位置（右上角或右下角）
    $ _bottom = (livetl_position == "bottom-right")
    $ _yalign = 1.0 if _bottom else 0.0
    $ _yoffset = -livetl_px(150) if _bottom else livetl_px(16)

    if livetl_pick_active:

        # 拾取模式下面板整体让位给拾取层
        pass

    elif not livetl_visible:

        # 折叠状态：只在角落留一个小按钮
        textbutton "TL":
            style "livetl_action"
            xalign 1.0
            yalign 0.0
            xoffset -livetl_px(8)
            yoffset livetl_px(8)
            action Function(livetl_set_visible, True)

    elif livetl_need_setup():

        # 还没选定目标语言：在主界面里直接询问
        #
        frame:
            style_prefix "livetl"
            xalign 1.0
            yalign _yalign
            xoffset -livetl_px(16)
            yoffset _yoffset
            xsize livetl_px(livetl_panel_width)

            # 面板范围内的事件不再往游戏传：否则"点一下输入框"会变成
            # "点一下游戏画面"，剧情往前推进一句（modal 是官方承诺的写法：
            # 鼠标在窗口内时事件不再穿透到下层）。
            modal True

            # 设置页比一屏长（语言列表、字体列表、快捷键都在这里）：整页可滚，
            # 窗口小的时候也不会有内容被切在屏幕外。
            viewport:
                ymaximum livetl_setup_panel_height()
                scrollbars "vertical"
                mousewheel True

                vbox:
                    spacing livetl_px(8)

                    hbox:
                        spacing livetl_px(12)
                        text "LiveTL 翻译模式" style "livetl_title"
                        textbutton "折叠" style "livetl_action" action Function(livetl_set_visible, False)

                    text "目标语言（就是 translate 语句里的语言名，例如 schinese、tchinese）：" style "livetl_source"

                    # 语言名是引擎身份，目录只是文件位置：填一个新名字会新建
                    # tl/<语言名>/，点下面已有的语言则翻译它们所在的那个目录。
                    text "填新名字 = 新建 tl/<语言名>/；点下面已有的语言 = 翻译它，写入它所在的目录。" style "livetl_hint"

                    # 语言输入框：和译文输入框用同一个控件（鼠标定位光标、
                    # 拖拽选区、点击不再穿透）；绑成快捷键的按键要让它过路
                    $ _livetl_language_widget = livetl_engine_input_widget(
                          livetl_language_value, 40, style="livetl_input", size=livetl_px(22),
                          hotkey_filter=livetl_hotkey_input_mode,
                          **livetl_panel_text_props())
                    add _livetl_language_widget id "livetl_language_input"

                    # 已有的语言列表（单独一个 screen，见 livetl_language_list）
                    use livetl_language_list()

                    hbox:
                        spacing livetl_px(10)
                        textbutton "开始翻译" style "livetl_action" action Function(livetl_confirm_language)
                        textbutton "切回默认" style "livetl_action" action Function(livetl_switch_to_default_language)
                        textbutton "检查重复" style "livetl_action" action Function(livetl_dup_open)

                    # 游戏当前语言与【切回默认】的说明：语言是引擎自己的偏好
                    # （persistent 的 _preferences.language），点过【切回默认】
                    # 之后，重启、甚至删掉插件，游戏都停在原文语言。
                    $ _livetl_game_language = livetl_game_language_text()
                    text "游戏当前语言：[_livetl_game_language]。翻译结束点【切回默认】：切回原文并记住，之后启动、删掉插件都保持原文；想继续翻译点【开始翻译】。" style "livetl_hint"

                    # 换字体：点按钮出字体列表；也可以把字体文件直接拖进窗口
                    $ _font_display = livetl_font_display_name()
                    text "游戏字体：[_font_display]" style "livetl_source"

                    hbox:
                        spacing livetl_px(10)

                        textbutton ("收起字体列表" if livetl_font_panel_open else "选择字体"):
                            style "livetl_action"
                            action Function(livetl_font_panel_toggle)

                    if livetl_font_panel_open:

                        if livetl_font_choices:
                            viewport:
                                ymaximum livetl_px(livetl_menu_list_height)
                                scrollbars "vertical"
                                mousewheel True

                                vbox:
                                    spacing livetl_px(2)

                                    for _livetl_font_choice in livetl_font_choices:
                                        $ _livetl_font_choice_text = livetl_font_choice_text(_livetl_font_choice)
                                        textbutton "[_livetl_font_choice_text]":
                                            style "livetl_menu_item"
                                            selected (_livetl_font_choice["path"] == livetl_font)
                                            action Function(livetl_font_choose, _livetl_font_choice["path"])
                        else:
                            text "livetl/fonts/ 里没有可用的字体文件" style "livetl_status"

                        # 拖放区：方框只是给译者瞄准用的，拖到窗口里就算数
                        frame:
                            background "#ffffff18"
                            padding (livetl_px(12), livetl_px(10))
                            xfill True

                            text "把字体文件拖到这里" style "livetl_source" xalign 0.5

                        add livetl_font_drop_target

                    # 快捷键：点【改键】再按一个键就能绑上
                    $ _livetl_capture_label = livetl_hotkey_capture_label()

                    if _livetl_capture_label:
                        text "按下要绑给【[_livetl_capture_label]】的键：Esc 取消，退格恢复缺省" style "livetl_status"
                    else:
                        text "快捷键" style "livetl_source"
                        text "字母和数字要留给输入框打字，绑的时候请用功能键，或者加 Ctrl / Alt / Shift" size livetl_px(16) style "livetl_source"

                        for _livetl_hotkey_row in livetl_hotkey_rows():
                            hbox:
                                spacing livetl_px(8)

                                text "    [_livetl_hotkey_row[1]]" style "livetl_source" xsize livetl_px(200)
                                text "[_livetl_hotkey_row[2]]" style "livetl_source" xsize livetl_px(90)
                                textbutton "改键":
                                    style "livetl_action"
                                    action Function(livetl_hotkey_capture_start, _livetl_hotkey_row[0])
                                textbutton "清除":
                                    style "livetl_action"
                                    action Function(livetl_hotkey_clear_row, _livetl_hotkey_row[0])

                    # 捕获层：点了【改键】之后由它接住下一个按键
                    add livetl_hotkey_capture_target

                    # 设置界面也要有反馈：否则点【检查重复】之类的操作看不到结果
                    if livetl_status:
                        $ _livetl_status_escaped = livetl_escape(livetl_status)
                        text "[_livetl_status_escaped]" style "livetl_status"

    else:

        frame:
            style_prefix "livetl"
            xalign 1.0
            yalign _yalign
            xoffset -livetl_px(16)
            yoffset _yoffset
            xsize livetl_px(livetl_panel_width)

            # 面板范围内的事件不再往游戏传（见设置界面里的说明）
            modal True

            vbox:
                spacing livetl_px(8)

                # 标题栏
                hbox:
                    spacing livetl_px(12)

                    if livetl_mode == "find":
                        text "搜索条目":
                            style "livetl_title"
                    elif livetl_mode == "find_edit":
                        text "搜索结果":
                            style "livetl_title"
                    else:
                        text "LiveTL":
                            style "livetl_title"
                        if livetl_mode == "menu":
                            text "菜单 · [livetl_menu_count] 条":
                                style "livetl_title"
                        elif livetl_mode == "dup":
                            text "查重体检":
                                style "livetl_title"

                    # 返回按钮挨着【折叠】放（标题栏右侧）
                    if livetl_mode == "find":
                        textbutton "回当前条" style "livetl_action" action Function(livetl_find_close)
                    elif livetl_mode == "find_edit":
                        textbutton "回搜索" style "livetl_action" action Function(livetl_find_back)

                    textbutton "折叠" style "livetl_action" action Function(livetl_set_visible, False)

                if livetl_mode == "dup":
                    use livetl_dup_body()
                elif livetl_mode == "find":
                    use livetl_find_body()
                else:
                    if livetl_mode == "menu":
                        use livetl_menu_body()

                    use livetl_edit_body()

                # 最近一次操作的反馈
                if livetl_status:
                    $ _livetl_status_escaped = livetl_escape(livetl_status)
                    text "[_livetl_status_escaped]" style "livetl_status"


# -----------------------------------------------------------------------------
# 编辑区：原文 + 输入框 + 操作按钮（对话与字符串条目共用）
# -----------------------------------------------------------------------------

screen livetl_language_list():
    # 设置页里的"tl 目录下已有"列表。
    #
    # 单独一个 screen：设置页本身已经很长（语言、字体、快捷键），列表再长一级
    # 会把缩进撑得很难读；`use` 进来以后设置页那一行只管位置。
    # 语言名取自 translate 语句，所以目录名与语言名不一致的游戏也会列对；
    # 点一行只把名字填进输入框，真正动手还是【开始翻译】。
    $ _livetl_language_rows = livetl_language_rows()

    if _livetl_language_rows:
        text "tl 目录下已有（点一下选它）：" style "livetl_hint"

        viewport:
            ymaximum livetl_px(livetl_menu_list_height)
            scrollbars "vertical"
            mousewheel True

            vbox:
                spacing livetl_px(2)

                for _livetl_language_row in _livetl_language_rows:
                    $ _livetl_language_text = _livetl_language_row["text"]
                    $ _livetl_language_name = _livetl_language_row["language"]
                    textbutton "[_livetl_language_text]":
                        style "livetl_menu_item"
                        action Function(livetl_language_pick, _livetl_language_name)
    else:
        text "tl 目录下还没有翻译。" style "livetl_hint"


# -----------------------------------------------------------------------------
# 搜索页：搜索框 + 结果列表（空搜索词 = 未翻清单）
# -----------------------------------------------------------------------------

screen livetl_find_body():

    # 搜索框：与译文框同一个控件（中文输入法、鼠标选词、快捷键让路都在）。
    # 内容一变就重新过滤一遍（见 LiveTLFindInputValue.set_text）。
    $ _livetl_find_widget = livetl_engine_input_widget(
          livetl_find_value, 60, style="livetl_input", size=livetl_px(22),
          hotkey_filter=livetl_hotkey_input_mode, **livetl_panel_text_props())
    add _livetl_find_widget id "livetl_find_input"

    # 命中统计（"未翻 N 条" / "共 N 条，显示前 M"）
    $ _livetl_find_hint = livetl_find_hint_text()
    text "[_livetl_find_hint]" style "livetl_hint"

    if livetl_find_results:
        viewport:
            ymaximum livetl_px(livetl_menu_list_height)
            scrollbars "vertical"
            mousewheel True

            vbox:
                spacing livetl_px(2)

                for _livetl_find_row_index in range(len(livetl_find_results)):
                    textbutton livetl_find_row_text(_livetl_find_row_index):
                        style "livetl_menu_item"
                        action Function(livetl_find_select, _livetl_find_row_index)


screen livetl_edit_body():

    # 原文行是只读控件：拖选、双击选词、三击全选、Ctrl+A 全选、Ctrl+C
    # 复制选中片段（没选中时不复制）。内容取"显示形态"——面板上看到什么
    # 就复制什么（见 livetl_input_text()）。
    # 插值里不做函数调用，先算好再显示（兼容 8.1）
    $ _source_display = livetl_input_text(livetl_current_source)
    $ _livetl_source_widget = livetl_engine_input_source_widget(
          _source_display, style="livetl_source", **livetl_panel_text_props())

    hbox:
        spacing livetl_px(4)

        if livetl_current_kind == "string":
            text "条目:" style "livetl_source"
        else:
            text "原文:" style "livetl_source"

        add _livetl_source_widget id "livetl_source"

    # 搜索装载的条目显示它的位置（源码 / tl），剧情当前句还是显示标识符
    if livetl_edit_origin == "find":
        $ _livetl_find_where = livetl_find_edit_where()
        if _livetl_find_where:
            text "[_livetl_find_where]" size livetl_px(16)
    elif livetl_show_id and livetl_current_tid:
        text "id: [livetl_current_tid!q]" size livetl_px(16)

    # 译文输入框：已保存过就填进去方便修改，否则留空。
    # 用自带鼠标支持的控件（官方 Input 点不进、也挡不住点击）：
    # 点一下定位光标、拖拽选词、双击选词、Ctrl+A 全选、Ctrl+X 剪切，
    # Ctrl+Z / Ctrl+Y 撤销与重做；绑成快捷键的按键要让给面板的 key 语句。
    # 原文行最后被点过时，Ctrl+A / Ctrl+C 归原文（见 livetl_engine_input.rpy）。
    $ _livetl_input_widget = livetl_engine_input_widget(
          livetl_value, 2000, style="livetl_input", size=livetl_px(22),
          hotkey_filter=livetl_hotkey_input_mode, **livetl_panel_text_props())
    add _livetl_input_widget id "livetl_input"

    # 提交与重载分开，便于连续翻译
    hbox:
        spacing livetl_px(10)
        textbutton "提交" style "livetl_action" action Function(livetl_submit)
        textbutton "清空":
            style "livetl_action"
            action livetl_clear_action()
        textbutton "重载" style "livetl_action" action Function(livetl_reload)
        textbutton "拾取" style "livetl_action" action Function(livetl_pick_enter)

        if livetl_mode != "find_edit":
            textbutton "搜索" style "livetl_action" action Function(livetl_find_open)

        if (livetl_mode != "menu") and (renpy.get_screen("choice") is not None):
            textbutton "回菜单" style "livetl_action" action Function(livetl_menu_back)

        textbutton "设置" style "livetl_action" action Function(livetl_open_setup)


# -----------------------------------------------------------------------------
# 菜单列表：当前菜单的所有条目，点一下选中并编辑
# -----------------------------------------------------------------------------

screen livetl_menu_body():

    viewport:
        ymaximum livetl_px(livetl_menu_list_height)
        scrollbars "vertical"
        mousewheel True

        vbox:
            spacing livetl_px(2)

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
            ymaximum livetl_px(livetl_menu_list_height)
            scrollbars "vertical"
            mousewheel True

            vbox:
                spacing livetl_px(2)

                for _livetl_key, _livetl_places in livetl_dup_report:
                    $ _livetl_key_text = livetl_escape(_livetl_key)
                    text "[_livetl_key_text]" style "livetl_source"

                    for _livetl_rel, _livetl_line, _livetl_new in _livetl_places:
                        text "    [_livetl_rel]:[_livetl_line]" size livetl_px(16)

    hbox:
        spacing livetl_px(10)

        if livetl_dup_report:
            textbutton "清理（保留第一条）" style "livetl_action" action Function(livetl_dup_clean)

        textbutton "重新扫描" style "livetl_action" action Function(livetl_dup_rescan)
        textbutton "返回" style "livetl_action" action Function(livetl_dup_close)


style livetl_frame:
    background "#000000d0"
    padding (livetl_px(16), livetl_px(12))

style livetl_action is default:
    background None
    hover_background "#ffffff30"
    selected_background "#ffcc6640"
    padding (livetl_px(10), livetl_px(4))

style livetl_action_text is default:
    size livetl_px(20)
    color "#ffffff"
    hover_color "#ffcc66"
    selected_color "#ffcc66"

style livetl_title is default:
    size livetl_px(20)
    color "#ffcc66"

style livetl_source is default:
    size livetl_px(20)
    color "#dfdfdf"

style livetl_hint is default:
    size livetl_px(16)
    color "#909090"

style livetl_input is default:
    size livetl_px(22)
    color "#ffffff"

style livetl_status is default:
    size livetl_px(17)
    color "#a0d0a0"

style livetl_menu_item is default:
    background None
    hover_background "#ffffff30"
    selected_background "#ffcc6640"
    padding (livetl_px(8), livetl_px(3))
    xfill True

style livetl_menu_item_text is default:
    size livetl_px(18)
    color "#ffffff"
    hover_color "#ffcc66"
    selected_color "#ffcc66"


init 500 python:

    # 面板上所有显示文字的样式（换字体时一起改）
    _livetl_panel_font_styles = [
        "livetl_title",
        "livetl_source",
        "livetl_input",
        "livetl_action_text",
        "livetl_status",
        "livetl_menu_item_text",
        "livetl_pick_tip_text",
        "livetl_pick_preview_text",
    ]

    def livetl_apply_panel_font():
        """把面板字体设成当前该用的那个（换完字体还会再调一次）。

        livetl_panel_font 优先，留空跟随游戏字体（livetl_font）；
        两个都留空时不覆盖样式，面板继承游戏自己的字体。
        字体文件不存在也退回不覆盖，免得面板渲染直接报错。
        """
        font = livetl_effective_panel_font()

        if font and not renpy.loadable(font):
            livetl_log("panel font skipped: {!r} not found".format(font))
            font = ""

        if not font:
            return

        # try/except 是为了兼容 lint：lint 阶段样式表尚未建立，
        # 直接赋值会中断检查。
        try:
            for name in _livetl_panel_font_styles:
                getattr(style, name).font = font
        except Exception:
            pass

    livetl_apply_panel_font()

    # 面板缩放的那一行日志：排查"面板太小 / 太大"这类问题时先看它。
    # 放在 init 500 而不是启动时：画布是 gui.init() 在 init -2 定下来的，
    # 这里读到的才是真实值（livetl_px 也是同样的道理，见配置文件的说明）。
    try:
        livetl_log("panel: scale={} screen={}x{} panel_width={} (livetl_ui_scale={})".format(
            livetl_ui_scale_value(), config.screen_width, config.screen_height,
            livetl_px(livetl_panel_width), livetl_ui_scale,
        ))
    except Exception:
        pass

    # 面板里的输入控件要用的排版参数：见 livetl_panel_text_props()
    _livetl_panel_text_props_cache = None

    def livetl_panel_text_props():
        """面板里的输入控件要用的排版参数（建控件时按实例传进去）。

        鼠标定位、拖拽选区依赖"一个字形 = 一个字符"（映射函数在引擎适配层里，
        见那里的说明）。Ren'Py 8 默认的 harfbuzz 排版会把 `fi` 这类连字合成
        一个字形（实测 Source Han Sans 的 "fi"：5 个字符只给 4 个字形），那样
        整行都对不上、选不中 —— 面板是译者逐字看原文、写译文的地方，字符
        一一对应比连字重要。

        为什么不在样式上设 shaper：实测运行期给样式属性赋值不生效（读回来还是
        原值），而且换语言重建样式之后init 期设的也会没。按实例传是唯一稳的
        办法（字体就是这么做的），代价是只有这两个控件是 freetype，面板其余
        文字照旧走引擎默认排版。

        8.1.1 没有 shaper 这个样式属性（那边也没有字形替换），返回空字典。
        """
        global _livetl_panel_text_props_cache

        if _livetl_panel_text_props_cache is None:
            try:
                known = hasattr(style.livetl_source, "shaper")
            except Exception:
                known = False

            _livetl_panel_text_props_cache = {"shaper": "freetype"} if known else {}

        return _livetl_panel_text_props_cache


init python:

    # 面板挂载分两处：
    #   * 游戏进行中的每次交互：由 overlay_screens 自动显示
    #   * 主菜单：那里的交互会抑制 overlay，所以在交互开始时主动显示
    #
    # 启动阶段（GPU 性能测试等）既不在主菜单也不在游戏里，
    # 面板不会出现，不打扰游戏启动。
    if "livetl_panel" not in config.overlay_screens:
        config.overlay_screens.append("livetl_panel")

    def livetl_setup_panel_height():
        """设置界面的最大高度：整屏减去上下留白，内容多了在面板里滚动。

        设置页里有语言列表、字体列表和各条快捷键，窗口小的时候会比一屏还长，
        被切在屏幕外的按钮就点不到了（实测：早期 720p 沙箱里加进语言列表后
        底部的快捷键行被切掉）。
        """
        try:
            return max(livetl_px(320), int(config.screen_height) - livetl_px(48))
        except Exception:
            return 640

    def livetl_sync_input_collapse():
        """游戏自己弹输入框时自动折叠面板，输入完自动恢复。

        面板里的输入框会跟游戏的输入框抢键盘焦点（输入法候选与回车
        都会失效），所以这时把面板收成角落的小按钮；
        游戏输入结束后再展开回用户原来的显示状态。
        """
        game_input = livetl_game_input_active()
        collapsed = livetl_state_get("livetl_input_collapsed", False)

        if game_input and not collapsed:
            # 记下用户原本的显示状态，输入完还回去
            livetl_state_set("livetl_visible_before_input", store.livetl_visible)
            livetl_state_set("livetl_input_collapsed", True)

            store.livetl_visible = False
            livetl_state_set("livetl_visible", False)
            # 这里不要 restart_interaction：重启会清空输入框列表，
            # 下一拍就检测不到游戏输入框，于是又恢复、再折叠，来回抖。
            # livetl_visible 是面板 screen 直接依赖的变量，改它就会重绘。

        elif (not game_input) and collapsed:
            livetl_state_set("livetl_input_collapsed", False)

            restore = livetl_state_get("livetl_visible_before_input", True)
            store.livetl_visible = restore
            livetl_state_set("livetl_visible", restore)

    def livetl_ensure_panel():
        """确保面板已显示。

        主菜单与游戏内的交互都会抑制 overlay，
        所以这里主动显示面板；启动阶段的 GPU 性能测试
        同时抑制 underlay 与 overlay，把它排除掉。
        """
        if livetl_engine_underlay_suppressed():
            return

        # 第一次真正交互时，把"只有跑起来才知道"的引擎事实写进日志：
        # 升级引擎后对比新旧日志，语义漂移（例如 lookup_translate 的返回值
        # 形态变了）一眼可见。每个探针每次运行只报一次，之后返回空列表。
        # 输入框那条要等到它被画过一遍（那才有排版可比），所以先返回空。
        for _livetl_probe_line in (
            livetl_engine_runtime_probe() + livetl_state_probe() + livetl_engine_input_probe()
        ):
            livetl_log(_livetl_probe_line)

        # 目标语言选定后（含首次启动），补全 tl 模板
        livetl_ensure_templates()

        # 菜单出现时面板切成菜单列表；拾取模式下确保拾取层还在（例如热重载之后）
        if store.livetl_pick_active:
            livetl_pick_screen_sync()
        else:
            # 搜索态以 session 为准先回正（回退只退剧情，不带走搜索界面），
            # 再让菜单同步决定要不要接管 —— 回正后 find / find_edit 的
            # 保护在 livetl_menu_sync 里生效。
            livetl_find_sync()
            livetl_menu_sync()

        # 启动后的第一次交互做一次重复条目检查（只提示，不改文件）
        livetl_dup_check_startup()

        # 面板显示状态以 session 为准：
        # 剧情回退会回滚 store 变量，这里每次交互都同步回来。
        store.livetl_visible = livetl_state_get("livetl_visible", True)

        # 译者在设置界面改过的东西（字体、显示方式、快捷键）同样每次交互回正，
        # 免得被"回退（Back）"带回旧值
        livetl_settings_sync()

        # 游戏自己在等输入（renpy.input）时自动折叠面板：
        # 面板里的输入框会跟游戏的输入框抢键盘焦点。
        # 输入结束后自动展开回原来的状态。
        livetl_sync_input_collapse()

        if renpy.get_screen("livetl_panel") is None:
            renpy.show_screen("livetl_panel")

        # 重载后的第一次交互：跳回刚才那一句，让新译文重新渲染
        tid = livetl_state_pop("livetl_replay_tid", None)

        if tid:
            name = livetl_engine_replay_label(tid)
            livetl_log("replay after reload: tid={!r} name={!r}".format(tid, name))

            if name:
                renpy.jump(name)

    if livetl_ensure_panel not in config.interact_callbacks:
        config.interact_callbacks.append(livetl_ensure_panel)

    def livetl_menu_poll():
        """每帧看一眼"面板该不该换形态"，该换就重画。

        为什么不能只在交互回调里做：菜单是在交互开始**之后**才显示的，
        而菜单一旦显示就会一直等玩家点，交互不会重新开始 —— 于是
        "交互开始时是台词、几帧后菜单才出现"这一种，回调永远补不上。
        每帧检查一次，形态真的变了才重启交互（不无条件重启：每次交互都重启
        会形成 "restart_interaction() was called 100 times" 的死循环）。
        """
        if livetl_engine_underlay_suppressed():
            return

        if store.livetl_pick_active:
            # 拾取模式有自己的同步逻辑（还要管拾取层的显示与隐藏）
            return

        mode_before = store.livetl_mode
        livetl_menu_sync()

        if store.livetl_mode != mode_before:
            livetl_restart()

    if livetl_menu_poll not in config.periodic_callbacks:
        config.periodic_callbacks.append(livetl_menu_poll)
