# LiveTL

在 Ren'Py 游戏里直接做翻译：**边玩边译，写完立刻看到效果**。

不用在编辑器和游戏窗口之间来回切换——面板就在游戏里，显示当前台词的原文
（`{w}`、`{p}` 这类文本标签原样保留），输入译文、写回文件、一键重载，全程不离开游戏。

---

## 目录

- [安装](#安装)
- [使用方法](#使用方法)
- [配置](#配置)
- [字体替换](#字体替换)
- [工作原理](#工作原理)
- [兼容性](#兼容性)
- [已知限制](#已知限制)
- [参考与致谢](#参考与致谢)
- [许可](#许可)

## 安装

把 `livetl/` 目录整个放进游戏的 `game/` 目录即可，**不需要改动游戏原有的任何文件**：

```
<你的游戏>/
  game/
    livetl/
      livetl_config.rpy      配置
      livetl_core.rpy        核心逻辑（定位台词、写回、重载）
      livetl_setup.rpy       启动引导
      livetl_ui.rpy          悬浮面板
      livetl_fonts.rpy       字体替换
      fonts/
        MiSans-Regular.otf
        MiSans-Bold.otf
```

要求游戏是**脚本目录形式**（能读写 `game/tl/`）。打包进 `.rpa` 的游戏暂不支持写入。

## 使用方法

### 第一次使用

1. 启动游戏，右上角的悬浮框**默认显示设置界面**
2. 填写**目标语言**（就是 `tl` 目录名，例如 `schinese`、`tchinese`、`japanese`）
3. 选择**没翻过的句子在游戏里怎么显示**：
   - **留空**：显示为空白
   - **显示原文**：照常读到原文，便于边读边翻（默认）
4. 点【开始翻译】，插件会：
   - 在 `tl/<语言>/` 下按 **Ren'Py 官方格式**生成整套翻译模板
     （每个脚本一个文件、每句对话一个 `translate` 块、原文写在 `#` 注释里）
   - **自动把游戏切换到目标语言**（否则你会看到"提交了但没变化"）

### 日常翻译

面板会跟着剧情自动切换到当前台词。常用操作：

| 想做的事 | 怎么做 |
| --- | --- |
| 看原文 | 面板顶部显示当前台词原文，文本标签原样保留 |
| 输入译文 | **直接打字**——焦点会自动进入输入框，不需要用鼠标点它 |
| 确认输入法候选词 | 空格或回车 |
| 提交 | 点【提交】：把译文写回当前这一条 tl 条目 |
| 看效果 | 点【重载】：保存进度 → 重载脚本 → 回到同一句，画面即新译文 |
| 连续翻译 | 可以只提交不重载，翻完一段再统一重载 |
| 折叠 / 展开 | 点【折叠】，屏幕角落留一个小按钮；快捷键 `F8` |
| 改设置 | 点【设置】回到设置界面（换语言、改显示方式） |

**关于重载**：提交与重载是分开的两个动作。重载会让游戏短暂重建
（保存 → 重载脚本 → 读回存档），连续翻译时可以先不重载，感觉节奏更顺。

**关于输入法**：面板输入框正常支持中文输入法，候选框会自动定位到输入框下方。
写中文时先按空格/回车把候选词上屏，再点【提交】。

## 配置

所有可调项都在 `livetl/livetl_config.rpy`：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `livetl_language` | `"schinese"` | 缺省目标语言（`tl` 目录名） |
| `livetl_ask_language` | `True` | 启动时是否显示设置界面 |
| `livetl_language_default` | `"schinese"` | 设置界面预填的语言 |
| `livetl_show_source_when_empty` | `True` | 没翻过的句子显示原文（`False` 则留空） |
| `livetl_hotkey` | `"K_F8"` | 面板开关快捷键 |
| `livetl_position` | `"top-right"` | 面板位置：`top-right` / `bottom-right` |
| `livetl_panel_width` | `680` | 面板宽度（像素） |
| `livetl_font` | MiSans | 面板字体 |
| `livetl_replace_fonts` | `True` | 是否启用字体替换 |
| `livetl_font_file` | MiSans-Regular | 替换用的字体 |
| `livetl_font_file_bold` | MiSans-Bold | 粗体用的字体 |
| `livetl_scan_fonts` | `True` | 是否扫描脚本收集游戏用到的字体 |
| `livetl_show_id` | `False` | 显示当前句的翻译标识符（排查问题用） |
| `livetl_debug` | `True` | 是否写 `game/livetl.log` |

## 字体替换

汉化后原文的字体往往不含中文字形（显示成方块）。插件**自带 MiSans 字体**，
启动时会扫描游戏脚本里用到的字体文件，并通过 Ren'Py 自带的
`config.font_replacement_map` 把它们统一替换成 MiSans：

| 用途 | 字体 |
| --- | --- |
| 常规 | `livetl/fonts/MiSans-Regular.otf` |
| 粗体 | `livetl/fonts/MiSans-Bold.otf` |

> **注意**：请使用**静态字重**（`.otf` / `.ttf`）。
> MiSans 的可变字体（`MiSans VF.ttf`）在 Ren'Py 里不会渲染，中文会显示成方块。

## 工作原理

| 环节 | 用到的接口 |
| --- | --- |
| 定位当前台词 | `renpy.get_translation_identifier()` |
| 读取原文 | 默认语言节点 `translator.default_translates` |
| 生成 tl 模板 | `renpy.translation.generation.write_translates()` / `write_strings()`（官方生成逻辑） |
| 写回单条 | 按官方格式替换对应 `translate` 块里的译文行，文件其余内容不动 |
| 热重载 | `renpy.reload_script()`（保存 → 重载脚本 → 读回存档） |
| 重载后重绘当前句 | 读档只恢复"已显示的对话"，不会重跑当前语句，插件会跳回该句重新执行 |
| 未翻译时显示原文 | `config.say_menu_text_filter`（渲染阶段替换，不改动 tl 文件） |
| 字体替换 | `config.font_replacement_map` |

生成的 tl 文件里，**没翻过的条目一律是空字符串**——"空 = 没翻、有内容 = 翻了"，
进度一眼可辨，也不会出现"把原文当译文"的情况。

## 兼容性

- 在 Ren'Py **8.1.1** 与 **8.5.3** 上完整流程实测通过：
  主界面设置 → 生成模板 → 游戏内显示原文 → 中文输入 → 提交写回 → 热重载后立即生效
- 依赖游戏的 `game/tl/` 目录可写（脚本目录形式的游戏）

## 已知限制

- 目前只处理对话（`say`）；菜单选项、界面字符串、NVL 等留待后续版本
- 一条译文对应一句，暂不支持跨句合并或拆分
- 请勿用鼠标点击输入框——点击可能被游戏当成"继续对话"推进一步（焦点会自动进入输入框，直接打字即可）

## 参考与致谢

- **字体替换**的实现思路参考 **[KittyArk/Renpy_fonts_replacement](https://github.com/KittyArk/Renpy_fonts_replacement)**
  （MIT 许可，作者 KittyArk）。本项目使用了它的做法：用 Ren'Py 的
  `config.font_replacement_map` 批量映射字体，并在此基础上做了自动化
  （自动扫描游戏字体、自动执行）。
  许可证副本见 `licenses/Renpy_fonts_replacement-LICENSE.txt`。
- 翻译文件的生成、写回与重载均基于 **Ren'Py** 官方接口
  （`renpy.translation.generation`、`renpy.reload_script()`、
  `renpy.get_translation_identifier()` 等）。
- 内置字体为小米 **MiSans**。

## 许可

| 内容 | 许可 / 版权 |
| --- | --- |
| 本项目代码 | MIT，见 `LICENSE` |
| MiSans 字体 | 版权归小米科技所有，协议见 `licenses/MiSans-LICENSE.pdf` |
| 借鉴项目（Renpy_fonts_replacement） | MIT，见 `licenses/Renpy_fonts_replacement-LICENSE.txt` |

**关于 Ren'Py 本身**：本项目是第三方插件，**不包含也不分发 Ren'Py 引擎**
