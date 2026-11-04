# Profile 维护说明

`README.md` 保存个人介绍、教育经历、研究方向、技能分组与联系方式。`azusa.gif` 保留原始文件。

## Contribution Footprint

- `scripts/update_profile.py` 使用 GitHub GraphQL API 读取 `soMewheRetoFloat` 的真实数据。
- `scripts/render_footprint.py` 使用 `svgwrite` 绘制贡献图。
- `data/profile-data.json` 保存本次查询取得的数据。
- `assets/images/github-footprint.svg` 是 README 引用的图表。
- `scripts/validate_profile.py` 检查日期、数值、SVG 结构、文字边界及重复生成的一致性。

贡献日历与贡献类型覆盖最近 365 个完整 UTC 日期。雷达图使用 `log10(count + 1)` 刻度，并标注原始计数，其中 Repositories 表示该时期创建的仓库数量。日历总数采用 GitHub 返回值，其中可能包含用户已经选择公开展示的匿名私有贡献数量。

参与仓库来自 `repositoriesContributedTo`，查询条件为公开仓库、COMMIT 贡献、包含本人仓库，并遍历全部分页。GitHub 将这项查询定义为近期参与，未提供固定起止日期。Stars 和 Forks 是这些仓库的当前合计数；语言分布按照每个仓库的主要语言统计仓库数量。

## GitHub Actions

`.github/workflows/profile-data.yml` 每天在 UTC 18:17 运行，即日本时间次日 03:17、北京时间次日 02:17。GitHub 的计划运行可能排队。工作流支持手动运行，更新生成代码、依赖或工作流文件时也会运行。

工作流使用 GitHub 自带的 `GITHUB_TOKEN`，需要 `contents: write` 权限以提交生成文件。数据获取与验证全部成功后，仅提交 SVG 和数据文件。HTTP 请求失败、GraphQL 报错或校验失败时，程序立即终止。

## 本地运行

使用 Python 3.12 或更新版本，并安装 `requirements.txt` 中的依赖。本机优先使用 conda 的 `codex` 环境。`GH_TOKEN` 由调用环境提供。

```sh
python -m pip install -r requirements.txt
python scripts/update_profile.py
python scripts/validate_profile.py
```

使用仓库中保存的真实数据重新生成图片：

```sh
python scripts/update_profile.py --from-data data/profile-data.json
python scripts/validate_profile.py
```

`.build/` 与 `.work/` 保存检查结果和本地依赖，已被 `.gitignore` 忽略。

## 设计与数据来源

- 页面栏目组织与 Contribution Footprint 展示形式参考 [Xiao-ao-jiang-hu 的 profile](https://github.com/Xiao-ao-jiang-hu/Xiao-ao-jiang-hu)。
- 个人内容来自本仓库原有 README。
- 技能图标由 Skill Icons 提供，联系徽章由 Shields.io 提供。
- 贡献图使用本仓库的生成程序和 GitHub GraphQL API 数据。
