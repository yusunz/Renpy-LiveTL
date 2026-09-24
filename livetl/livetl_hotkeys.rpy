# =============================================================================
# LiveTL —— 快捷键
#
# 五个动作可以绑快捷键，按"什么时候需要它"分成两类（screen 里的挂法不同）：
#   * 全局：显示 / 折叠面板、进入拾取 —— 面板折叠了也要能把面板叫回来，
#     所以挂在面板 screen 的顶层；
#   * 只在面板展开时：提交、重载、清空 —— 这三个只在写字时才有意义，
#     折叠后不绑，免得抢走游戏自己的按键。
#
# 译者在设置界面里改的绑定直接写回 livetl_config.rpy（改前先备份成 .bak），
# 所以按键设定跟着项目源码走、能提交、能回滚；打包后的游戏里配置只读，
# 那时只让本次运行生效，并在状态栏说明原因。
#
# 为什么不许绑裸字母：screen 的 key 会变成一个 Keymap displayable，它排在
# 输入框前面（实测面板 screen 的子树是 Keymap、Keymap、…、LiveTLInput），
# 事件按顺序分发，绑了字母键译者就打不出那个字了。
# =============================================================================

# 正在等译者按下一个键的动作名；"" = 不在捕获态
default livetl_hotkey_capture = ""


init -50 python:
    import pygame

    # 动作表：(动作名, 配置文件里的缺省键名, 界面上的说明)
    # 顺序就是设置界面里的显示顺序。
    livetl_hotkey_actions = [
        ("toggle", "livetl_hotkey", "显示 / 折叠面板"),
        ("pick", "livetl_pick_hotkey", "拾取模式"),
        ("submit", "livetl_submit_hotkey", "提交"),
        ("reload", "livetl_reload_hotkey", "重载"),
        ("clear", "livetl_clear_hotkey", "清空"),
    ]

    # keysym 里的修饰前缀，和引擎自己的 compile_event 用同一套名字
    _livetl_hotkey_modifiers = frozenset([
        "keydown", "keyup", "repeat",
        "alt", "meta", "shift", "noshift",
        "ctrl", "osctrl", "caps", "nocaps",
        "num", "nonum", "any", "anyrepeat", "anymod",
    ])

    # 输入框自己在用的组合键（见 livetl_engine_input.rpy）
    _livetl_hotkey_input_combo_keys = frozenset(["K_a", "K_x", "K_c", "K_v", "K_z", "K_y"])

    # 输入框要用、或者游戏几乎肯定会用的单键
    _livetl_hotkey_reserved_keys = frozenset([
        "K_RETURN", "K_KP_ENTER", "K_SPACE", "K_TAB",
        "K_BACKSPACE", "K_DELETE", "K_INSERT",
        "K_LEFT", "K_RIGHT", "K_UP", "K_DOWN",
        "K_HOME", "K_END", "K_PAGEUP", "K_PAGEDOWN",
        "K_ESCAPE",
    ])

    def livetl_hotkey_split(keysym):
        """"ctrl_K_s" → ({"ctrl"}, "K_s")；返回 (修饰集合, 主键)。"""
        parts = str(keysym or "").split("_")
        modifiers = set()

        while parts and parts[0] in _livetl_hotkey_modifiers:
            modifiers.add(parts.pop(0))

        return modifiers, "_".join(parts)

    def _livetl_hotkey_key_names():
        """pygame 常量值 → 键名（"K_s" 这种），给"按下的键 → keysym"用。"""
        rv = {}

        try:
            for name, value in vars(pygame.constants).items():
                if not name.startswith("K_") or not isinstance(value, int):
                    continue

                # 同一个值可能有多个名字（别名）：留最短的那个
                if value not in rv or len(name) < len(rv[value]):
                    rv[value] = name
        except Exception as e:
            livetl_engine_note_error("hotkey/key_names", e)

        return rv

    _livetl_hotkey_key_names_cache = None

    def livetl_hotkey_key_name(code):
        """按键常量值 → 键名；认不出来返回 ""。"""
        global _livetl_hotkey_key_names_cache

        if _livetl_hotkey_key_names_cache is None:
            _livetl_hotkey_key_names_cache = _livetl_hotkey_key_names()

        return _livetl_hotkey_key_names_cache.get(code, "")

    def livetl_hotkey_from_event(ev):
        """按键事件 → keysym（把 Ctrl / Alt / Shift 的状态一起带上）。"""
        key = livetl_hotkey_key_name(getattr(ev, "key", None))

        if not key:
            return ""

        mods = []

        try:
            if ev.mod & (pygame.KMOD_CTRL | pygame.KMOD_META):
                mods.append("ctrl")
            if ev.mod & pygame.KMOD_ALT:
                mods.append("alt")
            if ev.mod & pygame.KMOD_SHIFT:
                mods.append("shift")
        except Exception:
            pass

        return "_".join(mods + [key])

    def livetl_hotkey_label(keysym):
        """keysym → 界面上显示的名字："K_F8" → "F8"，"ctrl_K_s" → "Ctrl+S"。"""
        if not keysym:
            return "未绑定"

        modifiers, key = livetl_hotkey_split(keysym)
        names = []

        if modifiers & {"ctrl", "osctrl"}:
            names.append("Ctrl")
        if modifiers & {"alt"}:
            names.append("Alt")
        if modifiers & {"shift"}:
            names.append("Shift")

        name = key[2:] if key.startswith("K_") else key

        if len(name) == 1:
            name = name.upper()
        elif name.startswith("KP_"):
            name = "小键盘 " + name[3:]

        names.append(name)

        return "+".join(names)

    def livetl_hotkey_check(keysym):
        """这个键能不能绑；返回 (能不能用, 原因)。

        拒绝三类：引擎不认识的键名、输入框要用的键（裸字母数字、方向键、
        编辑键……）、输入框自己已经占用的组合（Ctrl+A/X/C/V/Z/Y）。
        """
        if not keysym:
            return False, "这一下没有按到键"

        if not isinstance(keysym, str):
            return False, "键名要写成字符串"

        modifiers, key = livetl_hotkey_split(keysym)

        if not key:
            return False, "只按住 Ctrl / Alt / Shift 不算一个键"

        if not hasattr(pygame.constants, key):
            return False, "引擎不认识这个键：{}".format(key)

        has_modifier = bool(modifiers & {"ctrl", "osctrl", "alt", "meta", "shift"})

        if not has_modifier:
            if key in _livetl_hotkey_reserved_keys:
                return False, "{} 要留给输入框和游戏，请换一个键".format(livetl_hotkey_label(keysym))

            if key.startswith("K_") and len(key) == 3 and key[2].isalnum():
                return False, "字母和数字要留给输入框打字，请用功能键，或者加上 Ctrl / Alt / Shift"

            if not key.startswith("K_"):
                return False, "这个键要留给输入框；要绑就得写成 K_ 开头的键名"

        if has_modifier and key in _livetl_hotkey_input_combo_keys:
            return False, "{} 已经给了输入框（复制 / 粘贴 / 撤销那一批）".format(livetl_hotkey_label(keysym))

        return True, ""

    def livetl_hotkey_config_name(action):
        """动作名 → 配置里那一行的变量名；未知动作返回 ""。"""
        for name, config_name, _label in livetl_hotkey_actions:
            if name == action:
                return config_name

        return ""

    def livetl_hotkey_bound(action):
        """动作当前生效的快捷键（就是配置里的值，"K_F8"）。"""
        return getattr(store, livetl_hotkey_config_name(action), "") or ""

    def livetl_hotkey_owner(keysym, skip=None):
        """这个键已经绑给哪个动作了；没人用返回 None。"""
        if not keysym:
            return None

        for name, _config_name, _label in livetl_hotkey_actions:
            if name == skip:
                continue

            if livetl_hotkey_bound(name) == keysym:
                return name

        return None

    def livetl_hotkey_action_label(action):
        """动作名 → 界面上的说明。"""
        for name, _config_name, label in livetl_hotkey_actions:
            if name == action:
                return label

        return action

    def livetl_hotkey_bind(action, keysym, path=None):
        """给动作绑一个键：写回 livetl_config.rpy 并立刻生效。

        返回 (是否成功, 提示)。绑定成功但配置没改成（打包后的游戏只读）
        时提示里会说明原因，这次运行仍然是生效的。
        `path` 是给测试用的口子，正常调用不用传。
        """
        ok, why = livetl_hotkey_check(keysym)

        if not ok:
            return False, why

        owner = livetl_hotkey_owner(keysym, skip=action)

        if owner:
            return False, "{} 已经给了【{}】".format(livetl_hotkey_label(keysym), livetl_hotkey_action_label(owner))

        config_name = livetl_hotkey_config_name(action)

        if not config_name:
            return False, "没有这个动作：{}".format(action)

        backup, error = livetl_config_set_value(config_name, '"{}"'.format(keysym), path=path)

        # 配置改不了（打包后的游戏里只剩 .rpyc）也让这次运行先用上
        setattr(store, config_name, keysym)

        if error:
            livetl_log("hotkey config not updated: {}".format(error))
            return True, "配置没改：{}".format(error)

        livetl_log("hotkey bind: {} -> {!r} (backup {})".format(action, keysym, backup))
        return True, ""

    def livetl_hotkey_clear(action, path=None):
        """清除绑定：把配置里那一行写成空串，并立刻生效。

        返回 (是否成功, 提示)。`path` 是给测试用的口子，正常调用不用传。
        """
        config_name = livetl_hotkey_config_name(action)

        if not config_name:
            return False, "没有这个动作：{}".format(action)

        backup, error = livetl_config_set_value(config_name, '""', path=path)

        # 同 livetl_hotkey_bind()：配置改不了也让这次运行生效
        setattr(store, config_name, "")

        if error:
            livetl_log("hotkey config not updated: {}".format(error))
            return True, "配置没改：{}".format(error)

        livetl_log("hotkey clear: {} (backup {})".format(action, backup))
        return True, ""

    # ---------------------------------------------------------------------
    # 设置界面用的一组包装：读行、进入捕获态、处理捕获到的按键
    # ---------------------------------------------------------------------

    def livetl_hotkey_rows():
        """设置界面要显示的行：[(动作名, 说明, 当前键的显示名), ...]。"""
        return [
            (name, label, livetl_hotkey_label(livetl_hotkey_bound(name)))
            for name, _config_name, label in livetl_hotkey_actions
        ]

    def livetl_hotkey_capture_start(action):
        """点【改键】：进入捕获态，等下一个按键。"""
        store.livetl_hotkey_capture = action
        livetl_set_status("请按下要绑给【{}】的键：Esc 取消，退格改成不绑定".format(
            livetl_hotkey_action_label(action)))
        livetl_log("hotkey capture start: {}".format(action))
        livetl_restart()

    def livetl_hotkey_clear_row(action):
        """设置界面里点【清除】：把这一行改成不绑定，结果写进状态栏。"""
        store.livetl_hotkey_capture = ""
        ok, note = livetl_hotkey_clear(action)

        if not ok:
            livetl_set_status("清除失败：{}".format(note))
        else:
            message = "【{}】已改成不绑定".format(livetl_hotkey_action_label(action))

            if note:
                message += "（{}）".format(note)

            livetl_set_status(message)

        livetl_restart()

    def livetl_hotkey_capture_key(ev):
        """捕获态收到一个事件；返回 True 表示这个事件已经用掉了。

        Esc 取消、退格 / 删除恢复缺省，其余按键交给 livetl_hotkey_bind()
        校验（裸字母数字、输入框占用的组合会被拒绝）。
        """
        action = store.livetl_hotkey_capture

        if not action or ev.type != pygame.KEYDOWN:
            return False

        keysym = livetl_hotkey_from_event(ev)

        if not keysym:
            # 认不出来的键：留在捕获态，也不让事件漏给游戏
            return True

        if keysym == "K_ESCAPE":
            store.livetl_hotkey_capture = ""
            livetl_set_status("已取消改键")
            livetl_restart()
            return True

        if keysym in ("K_BACKSPACE", "K_DELETE"):
            livetl_hotkey_clear_row(action)
            return True

        ok, note = livetl_hotkey_bind(action, keysym)

        if ok:
            store.livetl_hotkey_capture = ""
            message = "【{}】已绑到 {}".format(livetl_hotkey_action_label(action), livetl_hotkey_label(keysym))

            if note:
                message += "（{}）".format(note)

            livetl_set_status(message)
        else:
            # 绑失败时留在捕获态，译者可以直接再按一个键
            livetl_set_status("不能绑 {}：{}".format(livetl_hotkey_label(keysym), note))

        livetl_restart()
        return True
