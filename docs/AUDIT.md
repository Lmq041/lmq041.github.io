# 仓库审查与实施记录

审查日期：2026-10-26。原始版本：`dd73d716fb3202e02d52d6c3105672ca71dc4aa5`。实施分支：`codex/academic-publication-automation`。完整原始 Git 历史另存为本地 bundle；原始提交仍在分支历史中。

## 原有仓库

- `index.html` 是包含内嵌 CSS 的静态单页，没有前端框架。三篇 Selected Publications 直接写在三个 `pub-card` 中。
- `README.md` 原来只有项目名称。不存在自定义 `.github/workflows`、结构化论文数据或可编辑 CV 模板。
- `assets/CV/260310_Mingqiang_Liang_CV.pdf` 共三页，是无可提取文字的 PDF。已将三页全部渲染并逐页阅读。原文件按字节保留，测试核对 SHA-256。
- CV 除主页三篇论文外，还包含其他论文及一项预印本，共 12 个已有 DOI 条目。另有原 CV 已公开的 In Preparation 条目，作为静态 CV 内容保留，不用于论文发现，也不发送给元数据 API。
- CV 非论文内容包括姓名、职位、机构、邮箱、网站、Research Interests、三段 Education 与论文题目及导师、三项 Awards、Funding Awards、五项口头报告、两项海报、三段 Research Experience、Technical Skills、Academic Service。均已重建在 `templates/cv-content.json`。
- 公开 Actions 历史显示原始版本由 GitHub 管理的 `dynamic/pages/pages-build-deployment` 工作流成功部署，运行 ID `22957173855`。认证后的 Pages API 已确认 `build_type=legacy`，来源为 `main` 分支根目录，状态 `built`。未认证时该接口返回 404，不能把该响应误判为没有 Pages。当前设置尚未修改。
- 2026-10-26 读取公开分支 API，`main.protected=false`。以后若启用分支保护或规则集，需重新验证机器人能否写入，不能默认保持可用。

## 三篇主页论文迁移

| DOI | 作者位置 | 贡献标记 | 本地 PDF |
| --- | --- | --- | --- |
| 10.1016/j.gloplacha.2025.105115 | 11 / 12 | Corresponding authors | Liang2025_midHocene.pdf |
| 10.1016/j.quascirev.2024.108946 | 1 / 8 | 原页面没有特殊标记，保持如此 | Liang2024_orbital_monsson.pdf |
| 10.1016/j.quascirev.2022.107420 | 2 / 5 | co-first author | Liang2022_enso_monsoon.pdf |

所有关键词、PDF 路径、DOI 链接和 ResearchGate 的 See all publications 链接均保留。作者顺序采用正式 Crossref 出版顺序，主页三篇的顺序与正式数据一致；仅统一姓名缩写，并修正原主页 2024 条目第二作者 `Qin` 为正式记录的 `Qiuzhen Yin`。此项是书目姓名纠错，不是调整作者位置。

## 书目差异的处理

1. 原 CV 的 2024 QSR 条目附有 `10.5194/egusphere-egu24-11517`，与期刊论文不一致，且作者列表缺项。统一数据库采用原主页对应的正式 QSR DOI `10.1016/j.quascirev.2024.108946` 及正式完整作者列表，原 CV 文件仍完整可查。没有把会议摘要额外计作期刊文章。
2. 原 CV 的 `10.1360/TB-2022-0833` 标为 2022；Crossref 的在线日期为 2022，卷期 68(12) 涉及出版年份差异。保留作者原有 2022 标注为人工字段，待作者复核后决定引用年份。自动程序不会擅自覆盖。
3. `10.5194/cp-2021-20` 的正式类型是 `posted-content`。保留已有成果，CV 单列为预印本及其他已有成果，不当作新期刊论文自动发布。
4. ORCID 中有无可用 DOI、格式不完整的 DOI，以及一个没有 Crossref 期刊元数据的 Zenodo DOI。进入待审核列表；不从标题猜 DOI，不把存储库对象当作期刊文章。
5. 首次真实同步新发现 `10.1029/2026GL125062`，ORCID 成果记录、ORCID 一致的 OpenAlex 作者、Crossref 期刊元数据共同支持归属，已进入本地主页和 CV 候选版本。新论文没有本地 PDF 或来源关键词时，不伪造下载链接或关键词。

## 身份与数据保护

已核实 OpenAlex 作者为 `https://openalex.org/A5103046078`，其 ORCID 与用户提供的标识一致。每次同步重新核验；身份变化会使同步失败。

数据库每条记录分为 `metadata` 与 `manual` 两层。显示时人工字段优先；原有贡献标记和人工确认的作者顺序被锁定。已收录记录不因来源缺失而删除。新条目仅有姓名匹配不够；要求 ORCID 成果归属、Crossref 作者 ORCID 或严格匹配的 OpenAlex 标识证据，同时核对作者与书目信息。类型冲突、作者冲突、来源标题冲突及撤稿/更正信号进入审核。

只使用现有公开仓库和正式公开元数据。没有读取本机其他研究材料，没有调用 ResearchGate 网页抓取，也没有向第三方上传论文 PDF。

## 实施文件

- `data/publications.json`：网站与 CV 的统一论文数据。
- `data/pending-publications.json`：独立待审核区，不包含于 Pages 发布包。
- `data/build-state.json`：有效公开内容指纹和日期，防止空重建。
- `scripts/publications.py`：数据模型、正式 API、身份校验、合并和保护规则。
- `scripts/sync_publications.py`：同步入口、失败报告与只在变化时写入。
- `scripts/build.py`：静态 HTML、完整 CV、内容完整性验证、Pages 文件白名单。
- `templates/index.html`：原 HTML 的模板，原 CSS 与无关内容保持不变。
- `templates/cv-content.json`、`templates/fonts/`：完整 CV 静态内容和有许可的可嵌入 DejaVu Serif 字体。
- `assets/CV/Mingqiang_Liang_CV.pdf`：长期固定地址的可搜索完整 CV。
- `.github/workflows/update-publications.yml`：每月、手动、PR 和主分支验证与显式 Pages 部署（作者于 2026-10-26 将定期检查从每周调整为每月一次）。
- `.github/dependabot.yml`、`requirements.txt`：依赖固定与更新提醒。
- `tests/`：迁移、身份、故障、幂等、CV、链接和工作流测试及原版对照。
- `monitor/`：可选免费独立监测及恢复程序，默认关闭。
- `README.md`、`docs/`：审查、验证与维护说明。

原 `assets/img/`、`assets/papers/` 和带日期的原 CV 均未修改。
