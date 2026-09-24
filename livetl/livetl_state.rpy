# =============================================================================
# LiveTL —— 运行时状态层
#
# 插件把"界面状态"（面板是否展开、拾取是否开着、菜单指纹、tl 索引缓存……）
# 放在 Ren'Py 的 session 里：它只在本次运行内存在，不进存档，也不会跟着
# "回退（Back）"一起回滚。放 store 变量会被回退带走，放 persistent 又会
# 跨项目残留，都不合适。
#
# 为什么要包一层：renpy.session 在 Ren'Py 文档里没有承诺（引擎自己的
# common 脚本在用，8.1.1 / 8.5.3 实测都在），属于"未文档化但可用"的接口。
# 按项目的引擎耦合规则，这类接口只能出现在适配层文件里 —— 就是本文件。
# 将来引擎把它改掉、或者我们想换状态载体，只改这里，调用点不用动。
#
# 错误统一记进 livetl_engine_note_error()：两个适配层共用一个错误出口，
# 排查时只需要看 livetl_engine_last_error()。
# =============================================================================

init -90 python:

    # 引擎 session 不可用时的兜底：普通字典，本次运行内有效（热重载会丢）
    _livetl_state_fallback = {}
    _livetl_state_store_cache = None

    def _livetl_state_store():
        """状态载体：引擎的 session；不可用时退回本地字典。"""
        global _livetl_state_store_cache

        if _livetl_state_store_cache is not None:
            return _livetl_state_store_cache

        try:
            # 真写一次再删掉：确认它是可读写的字典式对象，而不只是存在
            candidate = renpy.session
            candidate["_livetl_state_probe"] = True
            del candidate["_livetl_state_probe"]
            _livetl_state_store_cache = candidate
        except Exception as e:
            livetl_engine_note_error("state/session", e)
            _livetl_state_store_cache = _livetl_state_fallback

        return _livetl_state_store_cache

    def livetl_state_get(key, default=None):
        """读一个运行时状态；没有时返回 default。"""
        try:
            return _livetl_state_store().get(key, default)
        except Exception as e:
            livetl_engine_note_error("state/get", e)
            return default

    def livetl_state_set(key, value):
        """写一个运行时状态。"""
        try:
            _livetl_state_store()[key] = value
        except Exception as e:
            livetl_engine_note_error("state/set", e)

    def livetl_state_pop(key, default=None):
        """取出并删除一个运行时状态。"""
        try:
            return _livetl_state_store().pop(key, default)
        except Exception as e:
            livetl_engine_note_error("state/pop", e)
            return default

    def livetl_state_setdefault(key, default):
        """有就返回已有的值，没有就写入 default 并返回它。"""
        try:
            return _livetl_state_store().setdefault(key, default)
        except Exception as e:
            livetl_engine_note_error("state/setdefault", e)
            return default

    # ---------------------------------------------------------------------
    # 自检：状态载体到底是哪一个（语义漂移探针）
    #
    # 如果引擎哪天不再提供 session，插件会静默退到本地字典：功能都在，但
    # "热重载与回退不丢状态"这个假设就不成立了。所以这件事必须写进日志。
    # ---------------------------------------------------------------------

    _livetl_state_probed = False

    def livetl_state_probe():
        """状态载体自检：session=yes 表示用的是引擎 session，no 表示退到本地字典。"""
        global _livetl_state_probed

        if _livetl_state_probed:
            return []

        _livetl_state_probed = True

        store = _livetl_state_store()

        return [
            "state: session={}".format("yes" if store is not _livetl_state_fallback else "no"),
        ]
