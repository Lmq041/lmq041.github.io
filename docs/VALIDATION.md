# 验证记录

本地验证日期：2026-10-26。此记录区分已完成验证与尚待授权的云端验收，不能据此声称已正式发布或永久无人值守。

| 验收项 | 本地结果 | 证据及限制 |
| --- | --- | --- |
| A 首次迁移 | 通过 | 原三篇 DOI、完整作者顺序与人数、本人位置、关键词、PDF 路径、共同一作和通讯标记；原 CV 12 个已有 DOI 均保留 |
| B 新增论文 | 通过 | 合成新论文同时进入主页与可搜索 CV；真实 API 还发现 10.1029/2026GL125062 |
| C 重复论文 | 通过 | DOI 大小写/URL 规范化、多来源合并、重复运行不重复添加 |
| D 作者匹配 | 通过 | 姓名独证、不同 ORCID、不同 given name、OpenAlex 身份或标题冲突不能新增公开 |
| E 特殊贡献 | 通过 | 本人加粗、共同一作 †、通讯 *、原人工字段不被覆盖 |
| F API 故障 | 通过 | 超时、429、空数据、异常 JSON、缺字段、DOI 不一致；失败不改现有数据 |
| G 无变化 | 通过 | 第二次构建不调用 PDF 生成器，PDF/HTML/日期字节与修改时间不变；PDF 重复生成逐字节一致 |
| H CV 完整性 | 通过本地检查 | 三页原 CV 全部渲染并逐页核对；新三页完整 PDF 已逐页目视检查，非论文每条内容及每篇 DOI/title 均做文字校验；原 PDF SHA-256 不变 |
| I 网页 | 通过本地与浏览器检查 | 原 CSS、Biography/Research/Education/Contact 内容完全一致；图片与本地链接均可用；1440×1000 与 390×844，图片加载正常，无横向溢出；远程外链的长期可用性不保证 |
| J Actions/部署 | 本地语法与 PR 云端检查通过；生产待验收 | actionlint 1.7.12 无错误；YAML 中时区、手动触发、固定 SHA、权限、分支及发布开关、先部署后提交有断言；PR CI 已实际安装依赖、读取正式 API 并验证构建。默认分支手动触发、生产部署及上线回滚仍需作者确认首次合并后验收 |

核心 Python 测试：30 项通过，另验证跨平台行尾差异不会触发重建。独立监测 Node 测试：6 项通过，包括健康无动作、停用恢复、尊重手动停用、避免重复触发和 HTTP 失败传播。

正式 API 已实际读取：ORCID public works、OpenAlex ORCID 作者及其作品、Crossref ORCID 搜索、已有 DOI 和新发现 DOI 的逐条元数据。已验证 OpenAlex 作者 `A5103046078` 的 ORCID 绑定。真实同步报告、无变化复跑日志和前后截图保留在本地交付的 verification 目录，未将完整 API 响应或任意本机材料上传。

## PR 云端证据

[PR #1](https://github.com/Lmq041/lmq041.github.io/pull/1) 的 [GitHub Actions 运行 40308384408](https://github.com/Lmq041/lmq041.github.io/actions/runs/40308384408) 已成功完成。prepare 成功，deploy 与 monitor 在 PR 环境按预期跳过。已下载云端 `sync-diagnostics`：`success=true`、`changed=false`、`pending_changed=false`。说明正式学术 API 在 GitHub 托管环境也已实际读取，并且再次运行没有数据库变化；没有据此声称已部署。

本地隔离工作区还验证了：从干净检出运行构建不会改变日期或文件；对全部改造提交执行 revert 后，仓库树与原始提交完全一致。原始 bundle 已通过 `git bundle verify`，包含完整历史。

网站“改造前”截图来自当时的正式站点；“改造后”截图来自本地候选版本。它们不是已部署前后对比。原 CV 与新 CV 均提供完整文件以及渲染对照。正式发布后仍需补一份线上网页与固定 CV 链接的核验结果。

外部 Cloudflare Worker 与 Healthchecks 尚未创建账号、发放 token 或部署。这里的 6 项监测测试是可注入模拟 GitHub 响应的单元测试，不能替代真正的外部调度测试。
