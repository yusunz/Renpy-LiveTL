# =============================================================================
# LiveTL —— 配置
#
# 所有可调参数集中在这里。需要修改时改本文件即可；
# 也可以在项目脚本中用更高优先级的 init 块覆盖。
# =============================================================================

init -100 python:
    import os
    import re
    import shutil

    # ---------------------------------------------------------------------
    # 版本
    # ---------------------------------------------------------------------

    # 插件版本：从同目录的 version.txt 读取，保证版本号只有一个出处。
    # 发版时改 livetl/version.txt 即可；它也会写进 game/livetl.log 开头。
    def _livetl_read_version():
        try:
            with renpy.file("livetl/version.txt") as f:
                return f.read().decode("utf-8").strip() or "unknown"
        except Exception:
            return "unknown"

    livetl_version = _livetl_read_version()

    # ---------------------------------------------------------------------
    # 目标语言
    # ---------------------------------------------------------------------

    # 缺省目标语言（tl 目录名），也是设置界面里预填的值。
    # 常见取值："schinese"（简体中文）、"tchinese"（繁体中文）、"japanese" 等。
    # 只能用字母、数字、下划线，且不能以数字开头：它同时是 tl/<语言>/
    # 的目录名与 translate 语句里的语言名，引擎那边就是这个规则。
    livetl_language = "schinese"

    # 是否每次启动都先显示语言设置界面。
    #   False（默认）—— 只在还没定过目标语言时问一次，之后直接进翻译界面
    #   True          —— 每次启动都先让译者确认一次
    # 想换语言随时点面板上的【设置】。语言名不合法时（留空、写错）
    # 无论这里怎么设都会显示一次，否则会生成引擎解析不了的文件。
    livetl_show_setup_on_start = False

    # 未翻译的句子在游戏里怎么显示（译者可在面板上改）：
    #   True  —— 显示原文（在渲染时替换，不改动 tl 文件）
    #   False —— 留空
    # 生成 tl 时统一写空字符串，这两种选择都不影响文件内容。
    livetl_show_source_when_empty = True

    # ---------------------------------------------------------------------
    # 界面
    # ---------------------------------------------------------------------

    # 快捷键（Ren'Py 的 keysym 名称，见 config.keymap）。
    # 译者可以在设置界面里改，改完记在 persistent 里；这里是缺省值，留空 = 不绑定。
    #
    # 前两个是全局的（面板折叠后也要能把面板叫回来），后三个只在面板展开时生效
    # ——它们只在写字时才有意义，折叠后不绑，免得抢走游戏自己的按键。
    #
    # 绑的时候要用功能键，或者带 Ctrl / Alt / Shift 的组合：
    # 裸的字母数字、方向键、回车空格这些要留给输入框打字。
    livetl_hotkey = "K_F8"

    # 拾取模式：进入后在画面上点选要翻译的文本。
    livetl_pick_hotkey = "K_F9"

    # 提交当前译文。
    livetl_submit_hotkey = ""

    # 重载脚本（保存 → 重载 → 回到同一句）。
    livetl_reload_hotkey = ""

    # 清空当前条目（和按钮一样会先确认）。
    livetl_clear_hotkey = ""

    # ---------------------------------------------------------------------
    # 字体
    # ---------------------------------------------------------------------

    # 游戏字体：把游戏里用到的字体统一替换成这个字体。
    # 汉化后原文的字体常常不含中文字形（显示成方块），填上就能解决。
    #   "" / None —— 用游戏原字体，不做替换
    #   "xxx.ttf" —— 使用指定字体文件（相对游戏目录）
    # 默认用随插件附带的开源字体（思源黑体简体，SIL OFL 许可，
    # 许可副本见 livetl/fonts/LICENSE.txt）。
    livetl_font = "livetl/fonts/SourceHanSansSC-Regular.otf"

    # 面板字体。
    #   "" / None —— 跟随游戏字体（即上面的 livetl_font；
    #                它也为空时，面板继承游戏原字体）
    #   "xxx.ttf" —— 面板单独使用指定字体
    livetl_panel_font = ""

    # 面板停靠位置："top-right" 或 "bottom-right"。
    livetl_position = "top-right"

    # 面板宽度（像素）。
    livetl_panel_width = 680

    # 输入框里选中文字时的底色（用于拖拽选词）。
    # 面板本身是深色底，用带透明度的浅色最清楚；写法与 Ren'Py 的
    # 颜色写法一致（#rgb / #rgba / #rrggbb / #rrggbbaa）。
    livetl_input_select_color = "#ffcc6666"

    # 是否显示当前句的翻译标识符（排查问题时有用）。
    livetl_show_id = True

    # 改键（等按键）期间要不要关掉系统文本输入。
    #   True （默认）—— 关掉后按键直接给游戏，输入法不会把 Shift+字母 收进候选条
    #                  （候选条出现 / 挂着都发生在引擎之前，插件只能这么预防）。
    #                  离开改键时会自动开回来，不影响之后打中文。
    #   False         —— 不关：改键时中文输入法仍可能弹候选条。
    # 如果发现自己的输入法被这样一关一开就会切回英文模式、要手动切回中文，
    # 把这项改成 False 即可。
    livetl_mute_ime_while_binding = True

    # 菜单列表在面板上的最大高度（像素），条目多了之后列表内滚动。
    livetl_menu_list_height = 260

    # 启动时是否自动检查 tl 目录里的重复字符串条目。
    # Ren'Py 对同一语言下重复的 old 会直接报错，发现后可在设置界面清理。
    livetl_dup_check_on_start = True

    # 是否把调试信息写入 game/livetl.log（排查问题时打开）。
    livetl_debug = True

    # ---------------------------------------------------------------------
    # 译者改过的设置：记在 session
    #
    # livetl_config.rpy 是"项目源码里的缺省值"（能提交、能给别人复用）；
    # 译者在界面上改过之后记进 session（见 livetl_state.rpy）：
    #   * 剧情"回退（Back）"回滚的是 store 变量，设置放 session 就不会被带走；
    #   * 不写 persistent：重开游戏回到配置里的缺省值，不会在机器上越积越多，
    #     也不会和项目源码里的那份打架。
    # store 里那几个同名变量是界面读的镜像，每次交互由 livetl_settings_sync()
    # 按这里记的值回正（见 livetl_core.rpy）。
    # ---------------------------------------------------------------------

    def livetl_setting_get(name, default=None):
        """读一条译者改过的设置；没改过时返回 default（调用方退回配置里的缺省值）。"""
        return livetl_state_get("livetl_setting_" + str(name), default)

    def livetl_setting_set(name, value):
        """记下译者改过的设置（放 session：回退与热重载都不受影响）。"""
        livetl_state_set("livetl_setting_" + str(name), value)

        return value

    def livetl_setting_clear(name):
        """把某条设置退回配置里的缺省值。"""
        livetl_state_pop("livetl_setting_" + str(name), None)

    def livetl_set_show_source(value):
        """设置"没翻过的句子在游戏里"显示原文还是留空。"""
        store.livetl_show_source_when_empty = bool(value)
        livetl_setting_set("show_source", bool(value))

    # ---------------------------------------------------------------------
    # 改写本文件用的工具
    #
    # 字体和快捷键都是"译者在界面上点一下，就在配置里改一行"，共用这几个
    # 函数。改之前先把原文件备份成 .bak（只留最近一次），改坏了能回头。
    # ---------------------------------------------------------------------

    def livetl_config_path():
        """livetl_config.rpy 的绝对路径；找不到返回 None。

        插件一般放在 game/livetl/ 下，但目录名可能被改过：先问引擎要文件
        清单，再退回默认位置。打包后的游戏里往往只剩 .rpyc，这时改不了
        配置，调用方会把原因告诉译者。
        """
        gamedir = renpy.config.gamedir
        names = []

        try:
            names = [n for n in renpy.list_files() if n.endswith("livetl_config.rpy")]
        except Exception:
            pass

        names.append("livetl/livetl_config.rpy")

        for name in names:
            path = os.path.join(gamedir, name.replace("/", os.sep))

            if os.path.isfile(path):
                return path

        return None

    def livetl_config_backup(path):
        """把配置文件备份成 xxx.bak，已有的直接覆盖。

        只留最近一次改动之前的版本：换字体、改快捷键都是反复试的过程，
        每改一次攒一个备份很快就把目录堆满，而真要回退的通常就是上一个版本。
        """
        backup = path + ".bak"
        shutil.copyfile(path, backup)

        return backup

    def livetl_config_set_value(name, literal, path=None):
        """把配置里 `<name> = ...` 那一行改成 `literal`（改之前先备份）。

        `literal` 是写进源码的字面量，已经带引号（例如 '"K_F8"'）。
        `path` 是给测试用的口子，正常调用不用传。
        返回 (备份文件名, 错误信息)；出错时备份文件名是 None。
        """
        name = str(name or "")

        if not name:
            return None, "没有给出要改的配置名"

        if path is None:
            path = livetl_config_path()

        if not path:
            return None, "找不到 livetl_config.rpy"

        try:
            # newline="" —— 原样读、原样写，不动文件本来的换行符
            with open(path, "r", encoding="utf-8", newline="") as f:
                text = f.read()
        except Exception as e:
            return None, "读配置失败：{}".format(e)

        pattern = re.compile(r"^([ \t]*)" + re.escape(name) + r"[ \t]*=[ \t]*.*$", re.MULTILINE)
        new_text, count = pattern.subn(lambda m: m.group(1) + name + " = " + literal, text, count=1)

        if not count:
            return None, "配置里没有 {} 这一行".format(name)

        try:
            backup = livetl_config_backup(path)

            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new_text)
        except Exception as e:
            return None, "写配置失败：{}".format(e)

        return os.path.basename(backup), ""
