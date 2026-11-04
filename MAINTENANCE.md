# Profile 维护说明

`README.md` 保存原始 About Me、WakaTime、Tech Stack 与联系方式。`azusa.gif` 保留原始文件。

## WakaTime

- `scripts/update_wakatime.py` 使用 WakaTime API 读取本人最近七天的统计。
- `data/wakatime.json` 在成功获取数据后生成，保存语言、编辑器、操作系统和统计时间范围。
- README 中 `WAKATIME:START` 与 `WAKATIME:END` 之间的内容由程序更新。
- `scripts/check_profile.py` 检查 Markdown、图片引用、栏目、工作流与已获取的数据。

语言和编辑器各显示用时最多的五项，操作系统显示前三项。用时及百分比采用 WakaTime 返回值。起止日期按照 API 返回的时区显示，总用时包含 `Other`。

## 连接账号

1. 安装 WakaTime for Mac 或实际使用的编辑器插件，在应用中配置本人的 WakaTime API Key。
2. 在 WakaTime 的个人 OAuth 页面创建具有 `read_stats` 权限的 token。
3. 打开本仓库的 `Settings → Secrets and variables → Actions → New repository secret`，名称填写 `WAKATIME_TOKEN`，值填写该 OAuth token。
4. 在 `Actions → Update WakaTime Profile → Run workflow` 运行一次。

本机插件使用 API Key 上传活动；读取个人统计使用 OAuth token。工作流在尚未连接账号时仅检查页面结构，并在运行记录中说明连接状态。配置 token 后，后续运行将读取真实数据。

## GitHub Actions

`.github/workflows/profile-data.yml` 每天在 UTC 18:17 运行，即日本时间次日 03:17、北京时间次日 02:17。GitHub 的计划运行可能排队。工作流支持手动运行，更新 README、生成代码、依赖或工作流文件时也会运行。

GitHub 自带的 `GITHUB_TOKEN` 使用 `contents: write` 权限提交 README 和统计数据。WakaTime token 通过 Actions secret 注入。HTTP 请求失败、统计尚在计算或数据校验失败时，程序立即终止。

## 本地运行

使用 Python 3.12 或更新版本，并安装 `requirements.txt` 中的依赖。本机优先使用 conda 的 `codex` 环境。`WAKATIME_TOKEN` 由调用环境提供。

```sh
python -m pip install -r requirements.txt
python scripts/update_wakatime.py
python scripts/check_profile.py
```

使用成功获取的数据重新生成 WakaTime 内容：

```sh
python scripts/update_wakatime.py --from-data data/wakatime.json
python scripts/check_profile.py
```

`.build/` 与 `.work/` 保存检查结果和本地依赖，已被 `.gitignore` 忽略。

## 设计与数据来源

- 页面栏目与 Tech Stack 展示形式参考 [Xiao-ao-jiang-hu 的 profile](https://github.com/Xiao-ao-jiang-hu/Xiao-ao-jiang-hu)。
- 个人内容来自本仓库原有 README。
- 徽章由 Shields.io 提供，图标由 Skill Icons 和 techstack-generator 提供。
- WakaTime 内容使用本人的语言、编辑器和操作系统统计。
