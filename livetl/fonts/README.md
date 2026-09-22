# 字体目录（自备）

这个目录**不包含任何字体文件**——中文字体需要你自己准备。

原因：常见的中文字体许可协议**禁止把字体文件随作品再分发**，
所以本仓库不附带字体。

## 怎么放

1. 下载一款免费可商用的中文字体，例如：
   - **思源黑体**（SIL OFL 许可，可自由分发和修改）：https://github.com/adobe-fonts/source-han-sans/releases
   - **Noto Sans SC**：https://fonts.google.com/noto/specimen/Noto+Sans+SC
   - 或你手头任意附和你需求的 `.ttf` / `.otf` / `.ttc` 字体
2. 把字体文件拷进这个目录，例如：

   ```
   livetl/fonts/SourceHanSansSC-Regular.otf
   livetl/fonts/SourceHanSansSC-Bold.otf
   ```

3. 打开 `livetl/livetl_config.rpy`，填上路径：

   ```renpy
   livetl_font_file = "livetl/fonts/SourceHanSansSC-Regular.otf"
   livetl_font_file_bold = "livetl/fonts/SourceHanSansSC-Bold.otf"
   ```

留空表示不做字体替换，游戏原本的字体照常使用。

## 注意

- 请使用**静态字重**（`.otf` / `.ttf`）。可变字体（文件名常带 `VF`）在 Ren'Py 里
  不会被正常渲染，中文会显示成方块。
