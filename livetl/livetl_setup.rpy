# =============================================================================
# LiveTL —— 启动引导
#
# 面板本身就是引导入口：这个项目还没为当前目标语言建过记录时，面板显示
# 语言输入框；确认后按 Ren'Py 官方格式生成翻译模板，并把选定的语言写回
# livetl_config.rpy（项目级，跟着项目走）。
# 判定用的都是项目自己的东西 —— 配置里的那一行与 tl/<语言>/ 下的
# .livetl_generated 标记，不用 persistent（它在存档目录里，换台机器就没了）。
# =============================================================================

init python:

    class LiveTLLanguageValue(VariableInputValue):
        """语言输入框的取值对象（继承官方实现，只改回车行为）。"""

        def enter(self):
            livetl_confirm_language()
            return None


# 设置界面里预填的语言：优先用 0.2.9 以前记在 persistent 里的那份
# （旧记录只在预填时用，点【开始翻译】会重新落到配置里），其次配置里的值
default livetl_language_input = persistent.livetl_language or livetl_language
default livetl_language_value = LiveTLLanguageValue("livetl_language_input")


init -20 python:

    # 本次运行是否要先显示设置界面。
    # 初值由配置决定；之后由译者点「开始翻译」置为 False。
    # 放在 session 里：热重载之后不会又弹回设置界面。
    livetl_setup_pending = livetl_state_setdefault("livetl_setup_pending", bool(livetl_show_setup_on_start))

    def livetl_need_setup():
        """是否显示语言设置界面。

        三种情况会显示：
          * 目标语言不合法（留空、写错、是引擎保留名 None）—— 无条件问，
            否则生成模板与写回会落到 tl/ 根目录，产出引擎解析不了的文件；
          * 这个项目还没为这个语言补全过（tl/<语言>/ 里没有标记文件）——
            第一次用这个语言，问一次；
          * livetl_show_setup_on_start = True —— 按配置每次启动都确认一次。
        其余时候直接进翻译界面，想换语言点面板上的【设置】。

        判断依据是项目自己的东西（tl 目录里的标记），不是 persistent：
        persistent 在存档目录里，换个机器、换个存档目录就没了，而"这个项目
        要翻成什么语言"本来就该跟着项目走。
        """
        # 体检界面要能盖住设置界面：否则在设置界面点【检查重复】
        # 只会切换状态，界面看起来毫无反应。
        if store.livetl_mode == "dup":
            return False

        if not livetl_language_valid(livetl_target_language()):
            return True

        if not livetl_project_setup_done():
            return True

        return bool(livetl_setup_pending)

    def livetl_confirm_language(path=None):
        """选定目标语言（写回配置），并增量补全一次翻译模板。

        `path` 是给测试用的口子（改配置那一步），正常调用不用传。
        """
        # 输入框留空就退回配置里的缺省语言，再解析成 (语言名, 目录, 说明)：
        # 语言名以 translate 语句里的为准，目录是译文实际所在的那个 tl 子目录
        language, directory, note = livetl_resolve_language(
            livetl_normalize_language(store.livetl_language_input or livetl_language),
        )

        if not directory:
            # 解析不了：名字不合法、是引擎保留名、或者磁盘上有大小写歧义
            livetl_set_status(note or livetl_language_hint())
            livetl_log("confirm_language rejected: {!r} ({})".format(
                store.livetl_language_input, note,
            ))
            return

        livetl_set_language(language)

        # 语言属于"这个项目在做什么"：写回配置那一行（项目级记录），
        # 换机器、换存档目录都还在。配置只读时本次运行照样生效，下面会说清。
        _backup, error = livetl_commit_language(language, path=path)

        # 输入框回填最终用的名字：译者看得见"我填的 chinese 变成了 tl/Chinese"
        store.livetl_language_input = language

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
            livetl_set_status("生成 tl/{}/ 失败：{}".format(directory, e))
            return

        livetl_mark_templates_done(language)

        notes = []

        if note:
            notes.append(note)

        if error:
            notes.append("配置没改：{}".format(error))

        suffix = "（{}）".format("；".join(notes)) if notes else ""

        if added > 0:
            livetl_set_status("tl/{}/ 已补全：新增 {} 条，按【重载】生效{}".format(directory, added, suffix))
        else:
            livetl_set_status("tl/{}/ 已是最新，没有要补的条目{}".format(directory, suffix))

        livetl_log("setup: incremental generate for {!r} (tl/{}/, {} files, {} new)".format(
            language, directory, count, added,
        ))

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
