# 字体目录

## 随插件附带

| 文件 | 说明 |
| --- | --- |
| `SourceHanSansSC-Regular.otf` | 思源黑体简体（Source Han Sans SC）Regular 字重 |
| `LICENSE.txt` | 该字体的 SIL Open Font License 1.1 许可 |

思源黑体采用 OFL 1.1：允许随软件打包、再分发和商用，
条件是**每一份副本都要带上版权声明和许可文件**。

> 分发本插件、或把字体打包进游戏发行时，请一并带上 `LICENSE.txt`。

## 换成别的字体

把字体文件放进这个目录，然后在 `livetl/livetl_config.rpy` 里填路径：

```renpy
livetl_font_file      = "livetl/fonts/你的字体-Regular.otf"
livetl_font_file_bold = "livetl/fonts/你的字体-Bold.otf"
```

这个目录默认被 `.gitignore` 忽略（只有上面附带的两个文件例外），
所以你自己加进来的字体不会被提交。

## 注意

- 请使用**静态字重**（`.otf` / `.ttf`）。可变字体（文件名常带 `VF`）在 Ren'Py 里
  不会被正常渲染，中文会显示成方块。
- Ren'Py 虽然支持 `.ttc` / `.otc` 字体集合，但只能用集合里的**第一个**字体。
