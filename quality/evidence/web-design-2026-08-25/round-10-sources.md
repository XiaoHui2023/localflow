# 第十轮界面学习依据

## 学习目标

精简本地任务控制台的导航、资源树状态、操作文案与设置布局，同时保留可发现性、键盘操作和无障碍名称。

## 一手资料

- Carbon Design System, Button usage: https://carbondesignsystem.com/components/button/usage/
  - 只在含义已被广泛识别时使用纯图标按钮，并提供 tooltip；同组图标保持尺寸一致。
- Primer, Tooltip guidelines: https://primer.style/product/components/tooltip/guidelines/
  - 图标按钮需要可访问名称，tooltip 用于补充可见标签而不是承载必要信息。
- Atlassian Design System, Navigation layout: https://atlassian.design/components/navigation-system/layout/
  - 导航目的地应稳定、简短，并按任务优先级组织。
- USWDS, Time picker: https://designsystem.digital.gov/components/time-picker/
  - 时间输入需要明确标签、可键盘操作，并使用平台可理解的时间输入语义。

## 本轮采用

- “配置”导航改为“运行”并放到第二位，表达用户在该页的主要任务。
- 删除“插件”和“API”两个低频说明型目的地，完整说明保留在项目 Markdown 文档。
- 运行改为播放图标按钮，同时保留 `title` 与 `aria-label`。
- 文件状态仅通过文件图标的形状与错误色表达；文件名不着色，扩展名不显示。
- 设置合并成一个面板，两条设置使用同一栅格与控件高度。

## 未采用及原因

- 未把必要的错误信息仅放进 tooltip：诊断仍在打开错误配置后以内联内容显示。
- 未把自动校时改成额外“应用”按钮：用户已明确要求修改即设置，现有防抖提交保留。

本轮资料获取成功，没有网络、权限、登录或依赖失败。
