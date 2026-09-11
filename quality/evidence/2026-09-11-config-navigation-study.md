# 配置局部导航层级研究

## 失败基线

已发布界面把“快捷”作为缩进按钮放在全局“配置”按钮下面。它同时使用全局导航的形状、选中边和纵向排列，却只切换配置面板内部的一块内容。这个不一致让界面看起来像二、三级菜单，缩进也缺少稳定含义。冻结截图为 `2026-09-11-navigation-hierarchy-failure.png`。

## 候选比较

| 方案 | 层级清晰 | 操作数 | 键盘 | 离线/旧浏览器 | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| 继续调整缩进 | 1/5 | 5/5 | 3/5 | 5/5 | 拒绝；没有修复所有权 |
| 全局侧栏分段控件 | 2/5 | 5/5 | 4/5 | 5/5 | 拒绝；窄栏仍承载局部选择 |
| 面板标题区下拉菜单 | 4/5 | 3/5 | 4/5 | 5/5 | 两项高频选择多一次操作 |
| 面板标题区同级标签页 | 5/5 | 5/5 | 5/5 | 5/5 | 采用 |
| 引入完整组件库 | 5/5 | 5/5 | 5/5 | 3/5 | 当前两项切换不值得新增依赖 |

## 依据与应用

- VS Code Activity Bar 只承载顶层 View Container；具体 Views 与动作归所属侧栏。
- Fluent 2 把少量、紧密相关、频繁访问的内容类别定义为 Tablist，并要求短且平行的标签。
- WAI-ARIA APG 要求 `tablist`、`tab`、`tabpanel`、唯一选中项、roving tabindex 及 Left/Right/Home/End 键盘行为。

因此采用一个全局“配置”折叠入口，加配置资源栏内部“资源 / 快捷”水平标签。视觉使用克制的底部选中线，不再依赖缩进、卡片或额外图标表达层级。

Find Skills 查询了 `sidebar nested navigation tabs UX`、`React accessible tabs sidebar` 和 `navigation rail local view switch`。找到 navigation-patterns、tab-navigation 与组件库候选，但未安装：现有用户根方案库、官方规范和项目浏览器门已经覆盖该决策，新依赖会扩大离线包、许可证审查和 Chrome 84/Firefox 78 兼容面。

## 可验证合同

- 全局 rail 中 `favorite-panel-toggle` 为零。
- 配置展开时资源栏内恰有“资源 / 快捷”两个 tab，且只选中一个；折叠时不可见。
- 左右方向键与 Home/End 改变选中项和焦点。
- 视图切换不卸载编辑器，不丢文件、草稿、模式或运行输入。
- 310px 资源栏和 390px 页面没有横向溢出，资源操作不被标签遮挡。

来源核对日期：2026-09-11。

- https://code.visualstudio.com/api/ux-guidelines/activity-bar
- https://code.visualstudio.com/api/ux-guidelines/views
- https://fluent2.microsoft.design/components/web/react/core/tablist/usage
- https://www.w3.org/WAI/ARIA/apg/patterns/tabs/
