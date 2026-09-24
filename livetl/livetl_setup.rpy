# =============================================================================
# LiveTL —— 启动引导
#
# 面板本身就是引导入口：还没有选定目标语言时，面板显示语言输入框；
# 确认后按 Ren'Py 官方格式生成翻译模板。
# 选择结果记在 persistent 里，之后启动不再重复询问。
# =============================================================================

init python:

    class LiveTLLanguageValue(VariableInputValue):
        """语言输入框的取值对象（继承官方实现，只改回车行为）。"""

        def enter(self):
            livetl_confirm_language()
            return None


# 设置界面里预填的语言：优先用上次选过的，方便直接确认
default livetl_language_input = persistent.livetl_language or livetl_language_default
default livetl_language_value = LiveTLLanguageValue("livetl_language_input")


init -20 python:

    # 本次运行是否要先显示设置界面。
    # 放在 session 里：热重载之后不会又弹回设置界面。
    livetl_setup_pending = livetl_state_setdefault("livetl_setup_pending", True)

    def livetl_need_setup():
        """是否显示语言设置界面。

        每次启动游戏都先显示一次，让译者确认目标语言与
        "没翻过的句子怎么显示"；点「开始翻译」之后才切到翻译界面。
        """
        # 体检界面要能盖住设置界面：否则在设置界面点【检查重复】
        # 只会切换状态，界面看起来毫无反应。
        if store.livetl_mode == "dup":
            return False

        return bool(livetl_setup_pending) or (bool(livetl_ask_language) and not persistent.livetl_language)

    def livetl_confirm_language():
        """记下目标语言，并增量补全一次翻译模板。"""
        language = (store.livetl_language_input or "").strip() or livetl_language_default
        language = language.replace(" ", "_")

        livetl_set_language(language)

        # 设置完成，切到翻译界面
        store.livetl_setup_pending = False
        livetl_state_set("livetl_setup_pending", False)

        # 把游戏强制切到目标语言。
        # 否则游戏界面仍然显示原文，"提交 / 重载"看起来就像没生效。
        try:
            renpy.change_language(language)
            livetl_log("change_language -> {!r}".format(language))
        except Exception as e:
            livetl_log("change_language failed for {!r}: {}".format(language, e))

        # 不管这个语言有没有生成过，都做一次增量补全 —— 与 Ren'Py SDK 的
        # 「生成翻译」一致：已经翻好的条目原样保留，只补新增的台词/字符串。
        # 有新增的文件里会留下 TODO 注释方便溯源（没有新增就不会有 TODO）。
        try:
            before = livetl_count_tl_entries(language)
            count = livetl_generate_templates(language)
            added = livetl_count_tl_entries(language) - before
        except Exception as e:
            # 生成失败不能把整个界面掀掉：报错留在状态栏，译者能看懂发生了什么
            livetl_log("setup: 生成失败 {!r}".format(e))
            livetl_set_status("生成 tl/{}/ 失败：{}".format(language, e))
            return

        livetl_mark_templates_done(language)

        if added > 0:
            livetl_set_status("tl/{}/ 已补全：新增 {} 条，按【重载】生效".format(language, added))
        else:
            livetl_set_status("tl/{}/ 已是最新，没有要补的条目".format(language))

        livetl_log("setup: incremental generate for {!r} ({} files, {} new)".format(language, count, added))

    def livetl_open_setup():
        """回到语言设置界面。

        换语言、或改"没翻过的句子怎么显示"时用。
        重新点「开始翻译」会按新的设置补全模板；
        已经翻好的条目不会被覆盖。
        """
        store.livetl_setup_pending = True
        livetl_state_set("livetl_setup_pending", True)
        store.livetl_visible = True
        livetl_log("open setup")
