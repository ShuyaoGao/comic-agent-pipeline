/* =====================================================================
 * 成本档位（3–4 档）：只改“若用真实云端模型生产本片”估算用的示意单价与关键镜数量。
 * 所有单价都是教学示意值，不对应任何具体厂商的真实报价；离线 mock 实跑成本永远是 $0。
 * 单价一律写成小数（Python 侧是 float，f-string 里 0.1 与 1.0 的写法要一致）。
 * ===================================================================== */
(function (root) {
  "use strict";
  root.COST_PRESETS = [
    { key: "save", name: "省钱档", desc: "便宜文本模型 + 低价出图 + 本地配音；只给 1 个关键镜出真实视频",
      llm: { price_input_per_mtok_usd: 0.07, price_output_per_mtok_usd: 0.14 },
      image: { price_per_image_usd: 0.03 }, cost: { video_per_second_usd: 0.05, tts_per_1k_chars_usd: 0.0 },
      dispatch: { key_shot_max: 1 } },
    { key: "standard", name: "标准档", desc: "与 config.yaml 默认值相同：2 个关键镜出真实视频，其余用分镜图 + 轻动效",
      llm: {}, image: {}, cost: {}, dispatch: {} },
    { key: "premium", name: "高质量档", desc: "强文本模型 + 高清出图 + 云端配音；4 个关键镜出真实视频",
      llm: { price_input_per_mtok_usd: 0.55, price_output_per_mtok_usd: 2.19 },
      image: { price_per_image_usd: 0.15 }, cost: { video_per_second_usd: 0.3, tts_per_1k_chars_usd: 0.3 },
      dispatch: { key_shot_max: 4 } },
    { key: "all_real", name: "全量真实视频", desc: "标准单价，但每一镜都出真实视频——对照“调度能省多少”",
      llm: {}, image: {}, cost: {}, dispatch: { key_shot_max: 99 } },
  ];
  /* 在默认配置上叠加某一档 */
  root.applyCostPreset = function (config, key) {
    const p = root.COST_PRESETS.find(x => x.key === key) || root.COST_PRESETS[1];
    for (const sec of ["llm", "image", "cost", "dispatch"]) Object.assign(config[sec], p[sec]);
    return config;
  };
})(typeof window !== "undefined" ? window : globalThis);
