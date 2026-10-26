# 自动更新维护说明

## 正常运行

每月 **1 日 09:17，Europe/Brussels** 自动检查一次；夏令时由 GitHub 的时区调度处理。GitHub 可能延迟甚至丢弃定时运行，所以该时间不是实时服务保证。[GitHub 官方调度规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

先读取 ORCID 公开 works，确认 OpenAlex 作者仍绑定同一个 ORCID，分页读取其作品，再用 Crossref 的 ORCID 搜索及 DOI 查询补充、验证正式书目信息。姓名相同但无可靠身份标识的记录不会新增公开。正式期刊文章通过核验后，默认同时进入主页和 CV；人工排除规则优先。数据源尚未收录的成果不会凭空出现，只有 ResearchGate 收录的论文不保证被发现。ResearchGate 只保留普通链接。

同步成功后，只有公开内容指纹变化时才生成 HTML 和完整 PDF。每月检查没有变化时，PDF 的字节、修改时间和 Last updated 日期保持不变，也不会创建提交。版权年份由页面显示时更新，避免只为跨年创建提交。待审核区的实际变化可以形成可追踪记录，但不会改变公开内容日期。

工作流先验证、再上传明确的 Pages 文件白名单、显式部署、最后提交有效变化。不依赖机器人提交触发二次 Pages 构建，因为 GitHub 明确说明 `GITHUB_TOKEN` 提交不会触发分支式 Pages 构建。[官方说明](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)。

Last updated 的候选日期写入已测试的发布产物；只有产物部署成功后，它才会出现在正式站点。部署失败时不提交该批生成结果。首次候选版本在本地生成与实际发布间如果跨月，请在首次激活前重新生成候选日期并复核；不可把尚未发布的本地日期当作已经上线的证据。

## 首次启用：需要作者确认

1. 审核 PR、完整 CV 与网站截图。完成 PR 云端验证后，作者确认首次合并及发布。
2. 在仓库 Settings → Pages，将 Source 改为 **GitHub Actions**。保留原 GitHub Pages 站点和地址；这是为解决机器人提交不触发旧分支部署的机制限制。
3. Settings → Environments → `github-pages`，只允许默认分支部署。不要允许 PR 分支部署生产站点。
4. Settings → Secrets and variables → Actions → Variables，建立 `PUBLICATIONS_AUTOMATION_ENABLED`，值为 `true`。未设置或不是 `true` 时，本系统不执行正式部署，定时同步任务也不运行。
5. Actions → Update publications and CV → Run workflow，选择 `main`，保持 `sync=true`，勾选 `publish=true`。检查 prepare、deploy、monitor 结果与公开网页、固定 CV 链接，才能签收端到端部署。手动运行默认 `publish=false`，便于安全验证。
6. 检查 Actions 通知设置，启用失败通知。GitHub 原生通知能报告运行失败，不能报告根本没有发生的运行。
7. OpenAlex 本次匿名读取可用，但按共享 IP 配额限制；建议在 OpenAlex 免费账号获得自己的 API key，保存到仓库 Actions secret `OPENALEX_API_KEY`。如 ORCID 匿名访问受限，可自行注册免费只读 Public API 凭证并将 `/read-public` token 存为 `ORCID_READ_PUBLIC_TOKEN`。不要把任何 token 写入仓库或发到聊天。

自动工作流使用仓库内置的 `GITHUB_TOKEN`，不需要长期个人 token 执行正常更新。若以后主分支规则阻止机器人提交，运行会失败并保留诊断；需要重新评估 GitHub App 权限方案，不能静默绕过保护。

## 查看、手动运行和人工修正

- 在仓库 Actions 页面查看 **Update publications and CV**，查看步骤日志、Job summary 和 `sync-diagnostics` 下载物。诊断保留 30 天，不为日志创建仓库提交。
- 手动验证：Run workflow，`sync=true`、`publish=false`。这是检查数据源和构建的方式，不会发布。
- 手动正式更新：默认分支、发布开关已启用、`publish=true`。同一系统的运行通过并发组串行执行。
- 人工修正写入对应记录的 `manual` 对象，例如 `keywords`、`local_pdf`、`co_first_author`、`corresponding_author`、`contribution_note`、`show_on_homepage`、`show_in_cv`；不要直接修改生成的 HTML 或 PDF。
- `authors` 是按出版顺序排列的完整列表，`my_author_position` 从 1 开始。共同一作与通讯作者不从“第一作者”推断。
- 无 DOI 的候选保留在待审核区，不靠模糊标题匹配自动合并。预印本不自动作为正式期刊文章发布，也不会删除已有预印本。

## 出错时的行为

超时、限流、断网、空响应或异常格式会使同步失败，现有数据库和公开文件保持原样。短暂网络错误最多重试三次；失败日志不打印带 API key 的 URL。Crossref 的单条 404 会保留该条供审核，不会删掉已有记录。原有论文不因本次未出现在 ORCID/OpenAlex 中而消失。

内容校验失败则不部署。准备与部署间如果默认分支已变化，会拒绝部署旧版本。部署成功后若 Git 提交被规则或并发推送拒绝，工作流会失败；已部署产物和仓库可能暂时不一致，需要重跑并检查，不声称跨 GitHub 两个服务的操作具备原子事务。

## 长期可靠性与免费独立监测

GitHub 官方规定：公开仓库 60 天无活动可能自动停用定时工作流；定时运行只发生在默认分支，且可能延迟或遗漏。本系统不制造空提交保活，GitHub 原生机制也不能可靠监测自身停摆。[官方规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

可选配置分两层，两者都需要作者一次性在外部服务操作，当前未启用：

1. **缺运行通知：Healthchecks.io 免费检查。** 创建一个 check，周期设为 cron `17 9 1 * *`、时区 `Europe/Brussels`、宽限 24 小时，并配置邮箱通知。把该 check 的 ping URL 保存为仓库 secret `HEALTHCHECKS_URL`。工作流每次有效检查成功时 ping，失败时 `/fail`；只有状态变化才由该服务通知。只发送成功/失败信号，不发送论文或日志。免费档当前提供 20 个 checks，以服务最新条款为准。[服务说明](https://healthchecks.io/)、[配置文档](https://healthchecks.io/docs/configuring_checks/)。
2. **独立恢复：可选 Cloudflare Workers 免费层。** `monitor/worker.mjs` 每天 UTC 11:47 检查最近运行；33 天无成功检查时触发补跑，为最长月份、夏令时变化和宽限留出时间。对 `disabled_inactivity` 先通过 GitHub 官方接口重新启用，再手动 dispatch。不会覆盖 `disabled_manually`，不会在 24 小时内重复触发，也不会生成保活提交。步骤：创建免费 Cloudflare 账号/Worker；上传该模块；设置 daily cron `47 11 * * *`；设置 secret `GITHUB_ACTIONS_TOKEN` 为只限本仓库、`Actions: read and write` 的 fine-grained PAT，默认 Metadata: read；不要授予 Contents: write；设置 `ENABLED=true`。`monitor/wrangler.jsonc` 是等价的默认关闭配置。无需公开 HTTP 路由。使用 Worker 日志查看执行结果。

Cloudflare 调度使用 UTC，这与原生每月 1 日布鲁塞尔主调度是独立的兜底检查，不替代主调度。[Cron 文档](https://developers.cloudflare.com/workers/configuration/cron-triggers/)、[免费层限制](https://developers.cloudflare.com/workers/platform/pricing/)。GitHub 启用和 dispatch 接口要求 Actions 写权限。[官方接口权限](https://docs.github.com/en/rest/actions/workflows)。

外部 token 到期或撤销、Cloudflare/Healthchecks 服务变更、免费配额、API 策略和机构账户限制仍可能导致失效。建议选择可接受的 token 有效期并保留到期提醒；不能保证技术上永久零维护。没有配置外部监测时，系统仍能正常每月运行，但无法保证停摆后主动提醒。

## 回滚

停用仓库变量或将其设为 `false`，同时将外部 Worker `ENABLED=false`。保留或下载失败运行的诊断。

对需要撤回的更新使用 `git revert` 创建可追踪的恢复提交，审查后推送 `main`；显式部署工作流会部署已提交的恢复版本。若要恢复首次改造前状态，可从 `dd73d716fb3202e02d52d6c3105672ca71dc4aa5` 恢复 `index.html`，继续使用保留的原 CV，并把 Pages Source 恢复为原设置。避免 reset/force-push 删除历史。

Git bundle 可在新目录 `git clone original-repository.bundle recovered-homepage` 恢复原仓库；改造分支 bundle 则包含完整改造提交与历史。回滚流程在本地隔离副本中验证；生产回滚仍应经作者确认，不在尚未批准首次发布时更改线上设置。
