# Round 15：Case 单列与交互状态研究

研究日期：2026-08-28。

## 失败基线

旧实现用 `auto-fit` 在宽屏形成多列；旧 E2E 甚至要求至少两个不同横坐标，因此会把用户明确否定的布局判为通过。该问题归类为 `memory_escape + oracle_escape + ownership_escape`。

## 双轨检索

- Find Skills：`dense selection list interaction`、`react accessibility focus hover performance`。结果包含 desktop app design、linear design、react-performance 与 ui-ux-pro-max；它们未提供比本机 `modern-web-interface-design` 更精确的 Case 次数/框选合同，故不安装。
- 联网：W3C APG、Adobe React Aria ListBox/Virtualizer、Fluent 状态资料、GitHub 可访问拖放复盘及社区 hover/focus 反例。

## 候选比较

1. React Aria ListBox：成熟的垂直 stack、hover/focus/selected 状态和键盘模型，但点击 Case 是“次数 +1”而不是选择；直接采用会形成错误 ARIA 语义。
2. React Aria Virtualizer：适合数千项，只渲染可见行；当前框选按所有 DOM 行的几何求交，直接虚拟化会让屏外范围不完整，除非先重写为虚拟布局模型。
3. 原生按钮 + 单列 flex + 委托事件：保留正确动作语义和现有框选；以 `contain`、单个 wheel listener、短状态过渡和浏览器资源门控制成本。本轮采用。

## 来源

- [W3C APG Listbox Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/listbox/)
- [Adobe React Aria ListBox](https://react-aria.adobe.com/ListBox)
- [Adobe React Aria Virtualizer](https://react-aria.adobe.com/Virtualizer)
- [Fluent UI button interaction state specification](https://github.com/microsoft/fluentui/blob/master/specs/Button.md)
- [GitHub：accessible sortable list 的真实工程复盘](https://github.blog/engineering/user-experience/exploring-the-challenges-in-creating-an-accessible-sortable-list-drag-and-drop/)
- [React Spectrum discussion：hover 与 focused selection 的边界](https://github.com/adobe/react-spectrum/discussions/6260)

## 新门禁

- 1440px 宽屏仍恰好一列；每行宽/列表宽 ≥ 0.95。
- hover/focus 过渡 ≤ 100ms；DOM focus 改变边界但 Case 次数保持为零。
- 故障注入恢复多列、固定窄行、不可见焦点或慢过渡时门禁必须失败。
- 旧 click、wheel、marquee、批量相对/固定赋值、390px 溢出和资源预算继续通过。
