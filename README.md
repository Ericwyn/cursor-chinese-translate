# Cursor Settings 页面汉化工具

## 工具简介

本工具用于将 Cursor IDE 的 Settings 页面（设置页面）从英文翻译为中文。
无论 Cursor 版本如何更新，只需重新运行脚本即可恢复汉化。

## 文件清单

| 文件 | 说明 |
|------|------|
| `CursorHanHua_GongJu.py` | Python 汉化注入主程序（核心脚本） |
| `QiDong_Cursor_ZhongWen.bat` | 一键启动批处理文件（自动注入 + 启动 Cursor） |
| `说明.md` | 本说明文档 |

## 使用方法

### 方法一：一键启动（推荐）

双击 `QiDong_Cursor_ZhongWen.bat`，它会自动检测汉化状态并注入，然后启动 Cursor。

### 方法二：手动注入

```bash
# 注入汉化
python CursorHanHua_GongJu.py

# 恢复原始英文
python CursorHanHua_GongJu.py --huifu
```

注入后需要 **重启 Cursor** 才能看到效果。

## 修改安装路径

打开 `CursorHanHua_GongJu.py`，找到文件开头的 **用户配置区域**：

```python
# ★★★ 用户配置区域 ★★★
CURSOR_AN_ZHUANG_LU_JING = r"D:\Tools\cursor"
```

将 `D:\Tools\cursor` 替换为您的 Cursor 实际安装路径即可。

同样，打开 `QiDong_Cursor_ZhongWen.bat`，修改顶部的配置变量：

```bat
set "CURSOR_EXE=D:\Tools\cursor\Cursor.exe"
set "CURSOR_USER_DIR=D:\Tools\cursor\user"
set "HANHUA_SCRIPT=e:\OPENCLAW\CursorHanHua_GongJu.py"
```

## 工作原理

### 整体流程

```
Python 脚本
  ├── 1. 备份 workbench.html → workbench.html.bak
  ├── 2. 备份 product.json → product.json.bak
  ├── 3. 生成 cursor_hanhua.js（翻译脚本）写入 Cursor 目录
  ├── 4. 在 workbench.html 中注入 <script> 标签引用翻译脚本
  └── 5. 重新计算 workbench.html 的 SHA256 哈希值并更新 product.json 中的 checksums
```

### 技术细节

1. **注入位置**：翻译脚本通过 `<script src="./cursor_hanhua.js">` 标签注入到 `workbench.html` 中，位于 `workbench.js` 之前加载。

2. **翻译机制**：`cursor_hanhua.js` 使用 JavaScript 的 `MutationObserver` API 监听 DOM 变化。当 Cursor Settings 页面渲染出英文文本时，脚本会实时将其替换为对应的中文翻译。

3. **翻译字典**：使用 `Map` 数据结构存储英文→中文的映射关系（500+ 条），查找效率为 O(1)。

4. **性能保障**：
   - 所有翻译操作通过 `requestAnimationFrame` 批量合并到下一帧执行，不阻塞 UI 线程
   - 只处理新增/变化的 DOM 节点（增量翻译），不做全量扫描
   - 自动跳过编辑器区域（`.monaco-editor` 等），不影响代码编辑
   - 跳过 `<textarea>`、`<input>`、`<code>`、`<pre>` 等不应翻译的元素

5. **版本兼容**：Cursor 更新时会覆盖 `workbench.html`，汉化注入会被清除。使用 `QiDong_Cursor_ZhongWen.bat` 启动时会自动检测并重新注入，因此无论版本如何更新都能保持汉化。

6. **幂等性**：脚本可重复运行，不会重复注入。如果检测到已注入，只会更新翻译 JS 文件内容（以便字典更新生效）。

7. **校验值同步**：Cursor 通过 `product.json` 中的 `checksums` 字段校验核心文件的 SHA256 哈希值。修改 `workbench.html` 后如不更新校验值，Cursor 启动时会提示 "Your Cursor installation appears to be corrupt. Please reinstall."。脚本会自动重新计算并更新校验值，避免此提示。

### 安全性

- 注入前自动创建 `workbench.html.bak` 和 `product.json.bak` 备份
- 可随时通过 `--huifu` 参数恢复全部原始文件（包括校验值）
- 翻译脚本仅修改文本节点的 `textContent`，不注入任何可执行代码
- 不修改 Cursor 的核心逻辑文件（`workbench.desktop.main.js` 等）

## 添加/修改翻译条目

翻译词典位于 `CursorHanHua_GongJu.py` 文件中的 `HAN_HUA_JS_NEI_RONG` 变量内。
格式为 JavaScript Map 条目：

```javascript
["English Text", "中文翻译"],
```

**注意事项**：
- 中文翻译文本中 **不能包含中文全角引号**（`""`），否则会导致 JS 语法错误
- 如需在翻译中使用引号，请使用方括号 `[]` 或半角引号 `'` 替代
- 修改后重新运行 `python CursorHanHua_GongJu.py` 并重启 Cursor 即可生效

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| 提示 "installation appears to be corrupt" | 重新运行 `python CursorHanHua_GongJu.py` 更新校验值 |
| 汉化完全无效 | 检查 JS 文件是否有语法错误：`node -c cursor_hanhua.js` |
| 部分文本未翻译 | 在字典中添加对应的英文→中文映射 |
| Cursor 启动异常 | 运行 `python CursorHanHua_GongJu.py --huifu` 恢复原始文件 |
| 更新后汉化消失 | 重新运行 `python CursorHanHua_GongJu.py` 或使用 bat 启动 |

原因：Cursor（基于 VS Code/Electron）在 product.json 的 checksums 字段中记录了核心文件的 SHA256 哈希值。我们修改了 workbench.html 注入翻译脚本后，文件哈希变了，但 product.json 中记录的仍是原始哈希值，所以 Cursor 启动时检测到不一致就报 "installation appears to be corrupt"。

修复：在 CursorHanHua_GongJu.py 中新增了 GengXin_JiaoYan_Zhi() 函数，在注入 HTML 后自动重新计算 workbench.html 的 SHA256 哈希值，并更新到 product.json 中。恢复时（--huifu）也会同步恢复 product.json 的原始值。
