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
    livetl_setup_pending = renpy.session.setdefault("livetl_setup_pending", True)

    def livetl_need_setup():
        """是否显示语言设置界面。

        每次启动游戏都先显示一次，让译者确认目标语言与
        "没翻过的句子怎么显示"；点「开始翻译」之后才切到翻译界面。
        """
        return bool(livetl_setup_pending) or (bool(livetl_ask_language) and not persistent.livetl_language)

    def livetl_confirm_language():
        """记下目标语言，并生成翻译模板。"""
        language = (store.livetl_language_input or "").strip() or livetl_language_default
        language = language.replace(" ", "_")

        livetl_set_language(language)

        # 设置完成，切到翻译界面
        store.livetl_setup_pending = False
        renpy.session["livetl_setup_pending"] = False

        # 把游戏强制切到目标语言。
        # 否则游戏界面仍然显示原文，"提交 / 重载"看起来就像没生效。
        try:
            renpy.change_language(language)
            livetl_log("change_language -> {!r}".format(language))
        except Exception as e:
            livetl_log("change_language failed for {!r}: {}".format(language, e))

        if os.path.exists(livetl_mark_path(language)):
            # 这个语言已经生成过：直接开工，不重复生成
            livetl_set_status("tl/{}/ 已存在，直接开始翻译".format(language))
            livetl_log("setup: {!r} already generated".format(language))
        else:
            count = livetl_generate_templates(language)
            livetl_mark_templates_done(language)
            livetl_set_status("已生成 tl/{}/ 翻译模板".format(language))
            livetl_log("setup: generated templates for {!r} ({} files)".format(language, count))

    def livetl_open_setup():
        """回到语言设置界面。

        换语言、或改"没翻过的句子怎么显示"时用。
        重新点「开始翻译」会按新的设置补全模板；
        已经翻好的条目不会被覆盖。
        """
        store.livetl_setup_pending = True
        renpy.session["livetl_setup_pending"] = True
        store.livetl_visible = True
        livetl_log("open setup")
