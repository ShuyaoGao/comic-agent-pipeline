# 第三方依赖、素材与来源说明

## 浏览器页面（play/）

| 项目 | 位置 | 说明 | 许可证 |
|---|---|---|---|
| three.js r128 | `play/vendor/three/three.min.js` | 只用于 3D 导演台页面（`play/director.html`）。文件头：“Copyright 2010-2021 Three.js Authors / SPDX-License-Identifier: MIT”。随包附 MIT 许可证全文 `play/vendor/three/LICENSE`。说明：该文件取自作者本机已有的 r128 构建副本，与 npm `three@0.128.0` 官方构建是否逐字节相同未联网核实。 | MIT |
| 其余 HTML / CSS / JS | `play/` | 全部为本项目自写：离线流水线是 `src/manhua/` 的逐行 JS 移植；不引用 CDN，不联网，不调用任何 API。 | MIT（同本仓库） |
| 字体 | — | **不随包分发任何字体**。页面和 canvas 只按名字引用系统已安装的字体（Microsoft YaHei、PingFang SC 等），没有时由浏览器替换。 | — |
| 图片、声音 | — | 分镜卡、导演台俯视图、草样片都由 canvas 现场绘制；占位配音由 WebAudio 现场合成。仓库里没有外部图片或音频素材。 | — |

## 参考的公开算法（按公式 / 规范自写，没有复制代码）

| 用在哪里 | 出处 |
|---|---|
| `play/js/pyrt.js` 的伪随机数 | MT19937（Matsumoto & Nishimura, 1998）及其 `init_by_array` 播种；为与 Python 的 `random.Random(int)` 逐位一致，按 CPython 文档描述的行为实现（`choice` 走 `getrandbits` 拒绝采样） |
| `play/js/pyrt.js` 的 MD5 | RFC 1321 |
| 浮点舍入与格式化 | 与 Python 的 `round()`、`repr(float)`、`format(x, ".Nf")` 行为一致（按二进制精确值、银行家舍入），自写 |
| 分镜卡主色调 | HSV → RGB 转换（与 Python 标准库 `colorsys.hsv_to_rgb` 相同的公式） |

## Python 版依赖（`requirements.txt`，运行 `python main.py` 时才需要）

| 包 | 用途 | 许可证 |
|---|---|---|
| pydantic | 结构化数据校验 | MIT |
| Pillow | 离线占位图、导演台俯视图、草样片 GIF | MIT-CMU（HPND 类） |
| PyYAML | 读取 config.yaml | MIT |
| requests | 真实 API 模式的 HTTP 客户端（可选） | Apache-2.0 |
| python-dotenv | 从 .env 读取密钥（可选） | BSD-3-Clause |

Python 版在本机生成占位图时会调用系统里已安装的中文字体（如 Windows 的微软雅黑）绘制文字；这些图片是使用者本机生成的产物，不随本仓库分发。

## 测试与构建工具（不随 play/ 分发）

| 工具 | 用途 | 许可证 |
|---|---|---|
| Node.js | `tests/test_parity.py` 用它运行 JS 版流水线，与 Python 版逐字段比对 | MIT（本体） |
| 本机已安装的 Microsoft Edge / Google Chrome | 无头自检与截图（不下载任何浏览器） | 各自的许可 |
| Playwright（Python 包，可选） | `tools/browser_check.py`、`tools/mobile_check.py`、`tools/mobile_check_cap.py` 用它驱动本机已装的 Edge（channel "msedge"），通过 DevTools 协议模拟手机尺寸、DPR 和触屏；不下载浏览器 | Apache-2.0 |

## 名称与商标

- 页面上的模型名都是中性的“示例 ID”（如 `image-strong-example`），中文说明集中在 `play/names.js`。
- `config.yaml`、`.env.example` 与 `src/manhua/llm/`、`src/manhua/image/` 里的适配器代码提到的云端 / 本地模型和服务名称，
  只是**可配置示例**，表示“可以接这一类服务”，本项目与这些服务的提供方没有关联，也未获得其认可；接入前请到各自官网核对当前模型与价格。
- 离线编造器生成的角色名、剧情、台词均为程序按规则拼出的原创内容，与任何具体作品无关。
