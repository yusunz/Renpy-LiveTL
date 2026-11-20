# =============================================================================
# LiveTL —— 拾取模式
#
# 面板点【拾取】后：面板收起，鼠标移到画面上任意文本上会实时显示它的原文，
# 点一下即可把这条文本交给面板翻译。适合翻译那些"跟着剧情走"抓不到的界面文本。
#
# 实现要点（都经过 8.1.1 / 8.5.3 实测）：
#   * 用渲染树接口取鼠标下的元素、从 Text 取替换前的文本（原文），
#     这两件事都在 livetl_engine.rpy 里，本文件只调用它；
#   * 拾取层要用 modal，并且 show/hide 之后必须 restart_interaction()，
#     否则事件树不更新，点击会穿透到游戏。
# =============================================================================

init -50 python:
    import os
    import re

    # 拾取模式是否开启（放 session：热重载与"回退"都不丢）
    livetl_pick_active = livetl_state_setdefault("livetl_pick_active", False)

    # 鼠标下的原文与预览框位置（拾取层读取）
    livetl_pick_preview = ""
    livetl_pick_px = 0
    livetl_pick_py = 0

    # 预览框宽度上限（1080p 设计稿像素），用于贴边时翻到鼠标另一侧
    _livetl_pick_preview_width = 440

    def livetl_pick_own(location):
        """这个 displayable 是不是插件自己的元素（面板、拾取层）。"""
        if not location:
            return False

        try:
            fn = str(location[0]).replace("\\", "/")
        except Exception:
            return False

        return ("/livetl/" in fn) or fn.startswith("livetl/")

    def livetl_pick_text_key(text):
        """比较用的文本键：去掉文本标签与首尾空白。

        画面上拾取到的是 Text 替换前的文本（参数里的原文，未翻译），目标语言下
        它已经是译文；而 say 的原文里还带着 {w=0.8} 这类标签。判断"是不是同一句"
        时去掉标签、比较可见文字即可。
        """
        try:
            text = re.sub(r"\{[^{}]*\}", "", str(text or ""))
        except Exception:
            text = str(text or "")

        return text.strip()

    def livetl_pick_same_text(a, b):
        """两段文本是不是同一句（原文 / 译文 / 画面文本之间比较用）。"""
        if not a or not b:
            return False

        if a == b:
            return True

        ka = livetl_pick_text_key(a)
        kb = livetl_pick_text_key(b)

        return bool(ka) and (ka == kb)

    def livetl_pick_resolve(text):
        """把画面上的文本解析成可翻译条目：返回 (kind, source, payload)。

        kind 为 "say"（payload = tid）或 "menu"（payload = 菜单下标）；认不出时返回
        None。画面显示的是目标语言文本，所以必须把**原文和当前语言译文**都拿来比：
        只比原文会让"拾取当前这句已翻译的对话"落进界面字符串分支，原文行被填成译文
        （8.5.3 / 8.6.1 实测的 bug）。菜单条目同理要比 caption 与已有译文。
        """
        if not text:
            return None

        tid = livetl_current_id()
        source = livetl_engine_source_text(tid)

        if source:
            translated = None
            language = livetl_engine_current_language()

            if language:
                translated = livetl_engine_translation_text(language, tid)

            if livetl_pick_same_text(source, text) or livetl_pick_same_text(translated, text):
                return ("say", source, tid)

        for i, item in enumerate(store.livetl_menu_items):
            if (livetl_pick_same_text(item.get("caption"), text)
                    or livetl_pick_same_text(item.get("new"), text)):
                return ("menu", item.get("caption") or text, i)

        return None

    def livetl_pick_raw(x, y):
        """鼠标下的原始元素链（未过滤），每项是 (depth, w, h, displayable)。"""
        return livetl_engine_displayables_at(x, y)

    def livetl_pick_probe(x=None, y=None):
        """鼠标下的文本：返回 (原文, 源码位置)；找不到返回 (None, None)。"""
        if (x is None) or (y is None):
            try:
                x, y = renpy.get_mouse_pos()
            except Exception:
                return (None, None)

        items = livetl_pick_raw(x, y)

        if not items:
            return (None, None)

        for item in items:
            if len(item) != 4:
                continue

            depth, w, h, d = item

            if not livetl_engine_is_text_displayable(d):
                continue

            location = livetl_engine_displayable_location(d)

            if livetl_pick_own(location):
                continue

            text = livetl_engine_text_source(d)

            if text:
                return (text, location)

        return (None, None)

    def livetl_pick_describe(x=None, y=None):
        """鼠标下都有什么（给人看的词），用于解释为什么拾取不到。

        典型情况：
          * 输入框（Input）—— 例如存档页的 "Page 1"，它是输入控件不是文本；
          * 按钮但没有文字 —— 图标/图片按钮；
          * 文本是动态生成的 —— 拿不到可翻译的原文。
        """
        if (x is None) or (y is None):
            try:
                x, y = renpy.get_mouse_pos()
            except Exception:
                return []

        kinds = []

        for item in livetl_pick_raw(x, y):
            if len(item) != 4:
                continue

            d = item[3]
            name = type(d).__name__

            if name == "Input":
                if "输入框" not in kinds:
                    kinds.append("输入框")
            elif name == "Button":
                if "按钮" not in kinds:
                    kinds.append("按钮")
            elif livetl_engine_is_text_displayable(d):
                if "文本" not in kinds:
                    kinds.append("文本")

        return kinds

    def livetl_pick_screen_sync():
        """显示/隐藏拾取层。

        show/hide 之后必须 restart_interaction()：实测不调用时
        screen 虽然存在（get_screen 能查到），但事件树与焦点还没更新，
        点击会穿透到游戏，modal 也拦不住。

        注意：只在真的改变了显示状态时才重启交互，
        否则每次交互回调都重启会变成死循环。
        """
        changed = False

        if store.livetl_pick_active:
            if renpy.get_screen("livetl_pick") is None:
                renpy.show_screen("livetl_pick")
                changed = True
        else:
            if renpy.get_screen("livetl_pick") is not None:
                renpy.hide_screen("livetl_pick")
                changed = True

        if changed:
            try:
                renpy.restart_interaction()
            except Exception:
                pass

    def livetl_pick_set_active(value):
        """开关拾取模式：收起/展开面板，并同步拾取层。"""
        livetl_state_set("livetl_pick_active", value)
        store.livetl_pick_active = value

        store.livetl_pick_preview = ""

        if value:
            store.livetl_visible = False
            livetl_state_set("livetl_visible", False)
        else:
            store.livetl_visible = True
            livetl_state_set("livetl_visible", True)

        livetl_pick_screen_sync()

    def livetl_pick_enter():
        """进入拾取模式。"""
        # 从搜索（编辑）态进拾取：完全离开搜索 —— 出来时编辑的是拾取到的
        # 东西，不再是装载条目，回退也不该把搜索界面翻回来
        livetl_find_exit()
        livetl_pick_set_active(True)
        livetl_set_status("拾取模式：点击要翻译的文本，Esc 退出")

    def livetl_pick_exit():
        """退出拾取模式（取消）。"""
        livetl_pick_set_active(False)

    def livetl_pick_confirm():
        """在拾取层上点击：取当前鼠标位置的文本并交给面板。"""
        text, location = livetl_pick_probe()

        if not text:
            # 说清为什么拾取不到，别让译者以为是插件坏了
            kinds = livetl_pick_describe()

            if "输入框" in kinds:
                livetl_set_status("这里是输入框（不可拾取）")
            elif "按钮" in kinds:
                livetl_set_status("这里没有文字，无法拾取")
            elif "文本" in kinds:
                livetl_set_status("此为动态生成文本，不可拾取")
            else:
                livetl_set_status("此处无可翻译的文本")

            return

        # 先判断是不是"当前这句对话 / 当前菜单里的某一条"：画面显示的是
        # 目标语言文本，原文/译文都要拿来比（见 livetl_pick_resolve）。
        resolved = livetl_pick_resolve(text)

        if resolved and (resolved[0] == "say"):
            livetl_pick_set_active(False)

            # 菜单还开着时别让菜单同步把面板抢回列表：
            # 否则刚拾到的这句对话立刻被菜单列表顶掉，看起来像"没拾到"。
            livetl_state_set("livetl_menu_hold", True)

            store.livetl_mode = "say"

            # 强制刷新：菜单列表刚把面板内容换成菜单项，
            # 只靠 tid 判断会以为"没变化"而跳过。
            livetl_sync(force=True)

            livetl_set_status("此为对话文本，已打开")
            return

        if resolved and (resolved[0] == "menu"):
            store.livetl_menu_index = resolved[2]
            store.livetl_mode = "menu"
            livetl_menu_fill()
            livetl_pick_set_active(False)
            livetl_set_status("已拾取菜单中的第 {} 条".format(resolved[2] + 1))
            return

        # 其它字符串条目：单条编辑模式
        index = livetl_scan_string_index()
        places = index.get(text)

        # 译文从引擎已加载的翻译表读（运行时真正显示的值），磁盘索引兜底：
        # tl 里写法特殊（.rpa / 续行 / 相邻字面量）时行扫描定位不到，但引擎
        # 认得这条，译文仍然要显示出来。
        translation = livetl_string_translation(text)
        known = bool(places) or livetl_string_known(text)

        # 菜单还开着时，别让菜单同步把面板抢回去
        livetl_state_set("livetl_menu_hold", True)

        store.livetl_mode = "say"
        store.livetl_current_kind = "string"
        store.livetl_current_key = text
        store.livetl_current_source = text
        store.livetl_input = ""

        if known:
            # 生成的模板里未翻译条目的 new 是原文（占位），对译者来说等同于没翻
            store.livetl_input = livetl_input_text("" if translation == text else (translation or ""))

            if places and (len(places) > 1):
                note = "已拾取字符串条目（已有译文，共 {} 处）".format(len(places))
            elif places:
                note = "已拾取字符串条目（已有译文）"
            else:
                note = "已拾取字符串条目（文件为只读，不可写）"
        elif text in livetl_string_file_map():
            note = "已拾取"
        else:
            note = "已拾取（非官方文本，写入strings.rpy）"

        livetl_pick_set_active(False)
        livetl_set_status(note)

    def livetl_pick_tick():
        """周期性刷新：鼠标下的原文 + 预览框位置（每秒 20 次）。"""
        if not store.livetl_pick_active:
            return

        try:
            x, y = renpy.get_mouse_pos()
        except Exception:
            return

        text, location = livetl_pick_probe(x, y)

        # 预览也显示"能翻译的那一面"：当前台词/菜单条目在目标语言下画面是译文，
        # 这里换回原文再显示，和拾取后落进面板的内容一致。
        resolved = livetl_pick_resolve(text)

        if resolved:
            text = resolved[1]

        text = text or ""

        if text != store.livetl_pick_preview:
            store.livetl_pick_preview = text

        # 预览框放在鼠标右下方；贴边时翻到另一侧（留白按 1080p 设计稿换算）
        px = x + livetl_px(16)
        py = y + livetl_px(16)

        if px > (renpy.config.screen_width - livetl_px(_livetl_pick_preview_width)):
            px = max(livetl_px(8), x - livetl_px(_livetl_pick_preview_width))

        if py > (renpy.config.screen_height - livetl_px(90)):
            py = max(livetl_px(8), y - livetl_px(90))

        store.livetl_pick_px = px
        store.livetl_pick_py = py

    if livetl_pick_tick not in config.periodic_callbacks:
        config.periodic_callbacks.append(livetl_pick_tick)


# -----------------------------------------------------------------------------
# 拾取层：Modal + 全屏点击捕获 + 鼠标附近的原文预览
# -----------------------------------------------------------------------------

screen livetl_pick():
    zorder 900
    modal True

    # Esc / 快捷键都可以退出
    key "game_menu" action Function(livetl_pick_exit)
    key livetl_pick_hotkey action Function(livetl_pick_exit)

    # 顶部提示条：显示拾取指引，以及"为什么拾取不到"的原因。
    # 拾取时面板是收起的，提示只能显示在这里，否则点了没反应。
    $ _livetl_pick_status = livetl_escape(livetl_status)

    frame:
        style "livetl_pick_tip"
        xalign 0.5
        ypos livetl_px(10)
        text _livetl_pick_status style "livetl_pick_tip_text"

    # 鼠标附近的原文预览
    if livetl_pick_preview:
        $ _livetl_pick_pv = livetl_escape(livetl_pick_preview)

        frame:
            style "livetl_pick_preview"
            xpos livetl_pick_px
            ypos livetl_pick_py
            xmaximum livetl_px(_livetl_pick_preview_width)
            text _livetl_pick_pv style "livetl_pick_preview_text"

    # 全屏点击捕获：点击 = 拾取当前鼠标下的文本
    button:
        xpos 0
        ypos 0
        xsize config.screen_width
        ysize config.screen_height
        background None
        action Function(livetl_pick_confirm)


style livetl_pick_tip is default:
    background "#000000c8"
    padding (livetl_px(14), livetl_px(8))

style livetl_pick_tip_text is default:
    size livetl_px(20)
    color "#ffcc66"

style livetl_pick_preview is default:
    background "#000000dd"
    padding (livetl_px(10), livetl_px(6))

style livetl_pick_preview_text is default:
    size livetl_px(18)
    color "#dfdfdf"
