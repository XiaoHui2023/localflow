# Round 7 学习来源

## 导航

- [Material Design 3 navigation rail](https://m3.material.io/components/navigation-rail/overview)：少量一级目的地、稳定位置和清晰选中态；本项目有六项，保留图标与文字。
- [GitHub Primer NavList](https://primer.style/product/components/nav-list/)：短标签、当前项语义和纵向扫描；采用紧凑行，不引入产品标识或摘要。
- [WCAG 2.2 Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)：24×24 CSS px 是最低边界；本项目以 40px 作为操作台内部门槛。
- [WAI-ARIA APG](https://www.w3.org/WAI/ARIA/apg/)：保留纵向 tab 的方向键与焦点合同。

## 时间组件

- [WAI-ARIA 1.2 timer role](https://www.w3.org/TR/wai-aria-1.2/#timer)：`timer` 的隐式 `aria-live` 为 `off`，适合秒级变化但不应每秒打断读屏。
- [MDN datetime-local](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/input/datetime-local)：使用单个原生日期时间输入，标签直接表达“时间校准”。

## 配置组合

本机已安装 `python-library-configlib 0.1.5`，实测其 `load_config_raw` 支持 YAML `!include`、JSON/JSON5 和 TOML。本项目复用加载器，但先遍历 YAML include 图并限制到 `config/`，因为该库本身不承担 LocalFlow 的目录授权边界。

## Find Skills 结果

分别检索 `compact sidebar navigation`、`vertical navigation rail UX`、`responsive dashboard sidebar accessibility`。结果偏向通用生成器、响应式 UI 和可访问性合集，没有比已启用的 `modern-web-interface-design`、`concise-no-fluff-interface` 与能力专门化闭环更贴合的技能，因此未安装额外技能。

## 工具接入失败

目标是用 Browser 技能直接检查当前应用标签页。浏览器 Node REPL 在连接前被管理员 Hook 拒绝，原始错误为 `未知写能力未提供可解析的本地目标；管理员 Hook 按 fail-closed 拒绝`。影响仅是不能复用 Codex 内置标签页；替代方案是项目自带的 Microsoft Edge + Playwright 门禁。恢复需要 Hook 为浏览器能力提供可解析的本地目标合同。
