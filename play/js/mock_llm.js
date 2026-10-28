/* =====================================================================
 * mock_llm.js —— src/manhua/llm/mock.py + agents/writers.py 的逐行 JS 移植
 *
 * 离线“编造器”：不是真实模型，而是按上游结构化数据确定性地生成连贯内容。
 * 同一创意、同一 seed，输出与 Python 版逐字段一致（tests/test_parity.py 用 Node 比对）。
 * 对象的键顺序 = pydantic schema 的字段顺序（token 估算要用 model_dump_json() 的长度）。
 * ===================================================================== */
(function (root) {
  "use strict";
  const { md5Hex, PyRandom, cpLen, cpSlice, pyStrip, pyMod, pyFloorDiv, pyReprList, pyJson } = root.PyRT;

  const GENRE_MAP = [
    [["校园", "青春", "同学", "高中", "大学"],
     { genre: "校园情感", scene: "教学楼天台", tone: "青涩而炽热", wardrobe: "藏青校服" }],
    [["悬疑", "推理", "凶案", "真相", "失踪"],
     { genre: "都市悬疑", scene: "老旧公寓走廊", tone: "紧张压抑", wardrobe: "深色风衣" }],
    [["古风", "宫廷", "江湖", "侠", "王朝"],
     { genre: "古风权谋", scene: "雕花长廊", tone: "暗流涌动", wardrobe: "素色长袍" }],
    [["末日", "丧尸", "废土", "病毒", "幸存"],
     { genre: "末日科幻", scene: "地下实验室走廊", tone: "冷峻压抑", wardrobe: "战术夹克" }],
    [["赛博", "机甲", "黑客", "霓虹", "义体"],
     { genre: "赛博奇幻", scene: "霓虹雨夜街道", tone: "迷离冷艳", wardrobe: "发光风衣" }],
    [["豪门", "婚恋", "总裁", "联姻", "契约"],
     { genre: "豪门婚恋", scene: "落地窗会客厅", tone: "克制而暗涌", wardrobe: "剪裁西装" }],
    [["复仇", "重生", "逆袭", "打脸", "归来"],
     { genre: "都市复仇", scene: "高层写字楼", tone: "凌厉决绝", wardrobe: "黑色西装" }],
  ];
  const DEFAULT_GENRE = { genre: "都市情感", scene: "城市街角咖啡馆", tone: "温暖治愈", wardrobe: "米色风衣" };
  const SURNAMES = ["林", "沈", "江", "顾", "苏", "陆", "白", "云", "夜", "商", "温", "裴"];
  const GIVEN = ["未央", "知夏", "行舟", "时砚", "南乔", "听澜", "怀瑾", "向晚", "斯年", "晏清", "执初", "屿安"];
  const HAIR = ["黑色长发", "栗棕色短发", "银灰色束发", "墨色齐肩发", "深棕卷发"];
  const EYES = ["浅灰色瞳孔", "琥珀色眼眸", "深褐色眼睛", "冷蓝色瞳孔", "墨绿色眼眸"];
  const MARKS = ["左眼下方小痣", "右眉骨浅疤", "颈侧蝶形胎记", "无明显标记", "左耳银色耳骨钉"];
  const VOICES = ["清冷、低声、语速中等", "温润、偏低、语速偏慢", "明亮、轻快、语速偏快", "沙哑、磁性、语速沉稳"];
  const RED_FLAGS = ["同款", "复刻", "一模一样", "照搬", "模仿某博主", "抄", "翻拍", "原班"];
  const MODEL_NAME = "mock-llm-offline";

  class MockLLM {
    constructor(seed) { this.baseSeed = seed === undefined ? 20260529 : seed; this.name = MODEL_NAME; }

    _rng(...parts) {
      const h = md5Hex(parts.map(String).join("|"));
      return new PyRandom(pyMod(this.baseSeed + parseInt(h.slice(0, 8), 16), 2 ** 31));
    }
    static estTokens(text) { return Math.max(1, pyFloorDiv(cpLen(text), 2)); }
    _genreFor(text) {
      for (const [keys, info] of GENRE_MAP) if (keys.some(k => text.includes(k))) return info;
      return DEFAULT_GENRE;
    }

    /* 主入口：与 MockLLM.generate_structured 相同的计量 */
    generate({ task, system, user, context }) {
      const fab = { idea: this._fabIdea, script: this._fabScript, review: this._fabReview,
                    character: this._fabCharacter, storyboard: this._fabStoryboard }[task];
      if (!fab) throw new Error(`mock LLM 不认识的任务: ${task}`);
      const output = fab.call(this, context);
      const outText = pyJson(output, FLOAT_KEYS);
      return {
        output, model: this.name,
        prompt: cpSlice(system + "\n\n" + user, 0, 4000),
        input_tokens: MockLLM.estTokens(system + user),
        output_tokens: MockLLM.estTokens(outText),
        cost_usd: 0.0,
        params: { task, offline: true },
      };
    }

    _fabIdea(context) {
      const ideaText = context.idea_text !== undefined ? context.idea_text : "一个普通人意外卷入风波的故事";
      const g = this._genreFor(ideaText);
      const rng = this._rng("idea", ideaText);
      const roles = ["主角", "对手/反派", "关键配角"];
      const seeds = [];
      const used = new Set();
      for (const r of roles) {
        let name;
        while (true) {
          name = rng.choice(SURNAMES) + rng.choice(GIVEN);
          if (!used.has(name)) { used.add(name); break; }
        }
        const oneLine = {
          "主角": `在『${g.genre}』情境中被迫直面${g.tone}处境、逐步觉醒的核心人物`,
          "对手/反派": "手握资源、与主角立场对立、推动核心冲突升级的施压者",
          "关键配角": "串联信息、在转折点给主角关键助力或刺激的人物",
        }[r];
        seeds.push({ name, role: r, one_line: oneLine });
      }
      return {
        premise: `围绕『${pyStrip(ideaText)}』展开的${g.genre}短篇漫剧：${seeds[0].name}` +
                 `因一桩意外被卷入漩涡，与${seeds[1].name}展开博弈。`,
        genre: g.genre,
        target_audience: "18-30 岁短视频与漫剧受众",
        core_conflict: `${seeds[0].name} 的目标与 ${seeds[1].name} 的利益正面相撞，且时间紧迫。`,
        emotional_tone: g.tone,
        opening_hook: "前 3 秒抛出一个反常画面 + 一句悬念旁白，制造『这是怎么回事』的追看欲。",
        series_potential: "采用单元式悬念结构，每集留钩子，便于系列化扩展为多集漫剧。",
        type_structure_notes: [
          `${g.genre}类型常见节奏：钩子→冲突铺陈→中段反转→高潮对决→留白`,
          "只借鉴该类型的『节奏与结构规律』，不复制任何具体作品的剧情/台词/角色（合规）",
        ],
        character_seeds: seeds,
        candidate_directions: [
          `方向A（强冲突）：开篇即把 ${seeds[0].name} 推到绝境，靠反转翻盘。`,
          `方向B（强情感）：放慢节奏，突出 ${seeds[0].name} 与 ${seeds[2].name} 的羁绊。`,
          "方向C（强悬念）：以谜题驱动，每集揭一层真相。",
        ],
      };
    }

    _fabScript(context) {
      const idea = context.idea || {};
      const ideaText = context.idea_text || "";
      const g = this._genreFor(ideaText + (idea.genre || ""));
      const seeds = idea.character_seeds || [];
      const names = seeds.length ? seeds.map(s => s.name) : ["主角"];
      const hero = names[0];
      const rival = names.length > 1 ? names[1] : "对手";
      const ally = names.length > 2 ? names[2] : hero;
      const defs = [
        ["SC01", g.scene, "深夜", `${hero} 察觉异常，独自前往${g.scene}查探，气氛${g.tone}。`, [hero],
          [["旁白", "narration", "有些门，一旦推开就再也关不上。"],
           [hero, "action", `${hero} 屏住呼吸，缓步走向走廊尽头。`],
           [hero, "dialogue", "……这里到底发生过什么？"]]],
        ["SC02", g.scene, "紧接上场", `${rival} 现身，与 ${hero} 正面交锋，核心冲突点燃。`, [hero, rival],
          [[rival, "dialogue", "我劝你别再往前一步。"],
           [hero, "dialogue", "晚了。我已经看见了。"],
           [rival, "action", `${rival} 眼神骤冷，逼近一步。`]]],
        ["SC03", "转场·关键地点", "稍后", `${ally} 带来关键信息，${hero} 做出抉择，留下钩子。`, [hero, ally],
          [[ally, "dialogue", `${hero}，你要的证据，我找到了。`],
           [hero, "narration", "原来从一开始，我就站在棋盘里。"],
           [hero, "action", `${hero} 攥紧手中之物，转身走入夜色。`]]],
      ];
      const scenes = defs.map(([sid, loc, tod, summary, onStage, lines]) => ({
        scene_id: sid, location: loc, time_of_day: tod, summary, on_stage: onStage,
        script_lines: lines.map(([sp, kind, c]) => ({ speaker: sp, kind, content: c })),
      }));
      return {
        title: `《${cpSlice(g.scene, 0, 2)}夜·${hero}》`,
        logline: `${hero} 因一桩意外被卷入${g.genre}漩涡，与 ${rival} 展开博弈，最终被迫直面真相。`,
        synopsis: (idea.premise || "") + " 全片三场推进：察觉异常 → 正面交锋 → 抉择留钩。",
        target_platform: "主流短视频平台 · 竖屏",
        target_duration_seconds: 45,
        scenes,
      };
    }

    _fabReview(context) {
      const idea = context.idea || {}, script = context.script || {};
      // Python 用 str(idea) + str(script) 做子串扫描；命中词全是汉字，等价于扫描所有字符串值
      const blob = stringValues(idea).concat(stringValues(script)).join("\u0000");
      const hits = RED_FLAGS.filter(w => blob.includes(w));
      let status, notes;
      if (hits.length) {
        status = "warn";
        notes = [`检测到疑似『借用他作』关键词：${pyReprList(hits)}，请人工确认是否为原创表达。`];
      } else {
        status = "pass";
        notes = ["未检测到复刻具体作品/模仿在世创作者的红线词；内容为原创生成。"];
      }
      const dims = [
        ["剧情吸引力", 8.0, "钩子明确、三场递进，有反转动力。"],
        ["人物一致性", 7.5, "已用 character_id 绑定，待美术/视频阶段校验外观稳定。"],
        ["画风统一性", null, "待美术 Agent 出图后评估。"],
        ["镜头连贯性", 7.0, "分镜阶段再核对景别/机位衔接。"],
        ["动作自然度", null, "需视频生成阶段评估。"],
        ["音画同步", null, "需配音阶段评估。"],
        ["成片可用率", null, "需成片阶段评估。"],
        ["平台适配度", 8.0, "竖屏 45s 适配主流短视频平台节奏。"],
      ];
      return {
        logic_issues: ["第二场冲突动机可再前置一句，避免观众疑惑。"],
        pacing_notes: ["开场 3 秒钩子达标；建议第三场抉择再压缩，强化留白。"],
        continuity_notes: ["确认三场之间的时间线（深夜→紧接→稍后）连贯。"],
        compliance_status: status,
        compliance_notes: notes,
        quality_scores: dims.map(([d, s, c]) => ({ dimension: d, score: s, comment: c })),
        suggestions: ["进入角色设定前，确认主角的『不可变化项』，为后续一致性打基础。"],
        overall_pass: true,
      };
    }

    _fabCharacter(context) {
      const idea = context.idea || {};
      let seeds = idea.character_seeds || [];
      if (!seeds.length) seeds = [{ name: "主角", role: "主角", one_line: "核心人物" }];
      const genre = idea.genre !== undefined ? idea.genre : "都市";
      const identityByRole = { "主角": `${genre}主角`, "对手/反派": "主要对手/反派", "关键配角": "关键配角" };
      const characters = seeds.map((s, k) => {
        const i = k + 1;
        const rng = this._rng("char", s.name);
        const hair = rng.choice(HAIR), eyes = rng.choice(EYES), mark = rng.choice(MARKS);
        const voice = VOICES[(i - 1) % VOICES.length];
        return {
          character_id: `CHAR_${String(i).padStart(3, "0")}`,
          name: s.name,
          age: rng.choice([19, 22, 24, 26, 28, 31]),
          identity: Object.prototype.hasOwnProperty.call(identityByRole, s.role) ? identityByRole[s.role] : s.role,
          fixed_visual_features: [hair, eyes, mark],
          variable_features: ["表情", "动作", "光线", "景别"],
          forbidden_changes: ["不要改变发色", "不要改变瞳色", "不要更换主要服装", "不要改变标志性特征"],
          voice_profile: voice,
          reference_image: null,
          reference_seed: null,
        };
      });
      return {
        characters,
        consistency_strategy:
          "锁定每个角色专属 seed + 固定参考图（三视图），跨镜头复用同一参考图与 seed；" +
          "并把 fixed_visual_features 写入每镜 image_prompt、把 forbidden_changes 写入 negative_prompt，" +
          "从『提示词约束 + 视觉锚点』两侧抑制角色漂移（需求文档 4.5 一致性机制）。",
      };
    }

    _fabStoryboard(context) {
      const script = context.script || {};
      const charset = context.characters || {};
      const chars = {}, nameToId = {};
      for (const c of charset.characters || []) { chars[c.name] = c; nameToId[c.name] = c.character_id; }
      const shotSizes = ["中近景", "近景", "特写", "中景", "远景"];
      const angles = ["平视", "低机位", "俯视", "侧后方"];
      const moves = ["缓慢推进", "跟拍", "定镜", "环绕", "横移"];
      const shots = [];
      let n = 1;
      for (const scene of script.scenes || []) {
        const onStage = scene.on_stage || [];
        const onIds = onStage.filter(nm => nameToId[nm]).map(nm => nameToId[nm]);
        for (let j = 0; j < 2; j++) {
          const rng = this._rng("shot", scene.scene_id, j);
          const cam = { shot_size: shotSizes[(n + j) % shotSizes.length], angle: rng.choice(angles),
                        movement: rng.choice(moves) };
          const light = { key_light: "冷蓝侧光", rim_light: "弱白色轮廓光", intensity: "中等" };
          const featBits = [];
          for (const nm of onStage) {
            const c = chars[nm];
            if (c) featBits.push(`${nm}（${c.fixed_visual_features.join("、")}）`);
          }
          const featStr = featBits.length ? featBits.join("；") : "场景空镜";
          const action = scene.summary || "";
          const emotion = j === 1 ? "紧张悬疑" : "克制铺陈";
          let dialogue = "";
          for (const ln of scene.script_lines || []) {
            if (ln.kind === "dialogue" || ln.kind === "narration") { dialogue = `${ln.speaker}：${ln.content}`; break; }
          }
          const imagePrompt =
            `${scene.location || ""}，${cam.shot_size}${cam.angle}，` +
            `${light.key_light}+${light.rim_light}，人物：${featStr}；` +
            `动作：${action}；情绪：${emotion}；漫剧风格，竖屏构图，电影感打光`;
          const videoPrompt = `${imagePrompt}；镜头运动：${cam.movement}；时长 5s；保持人物外貌与服装一致，首帧=该镜分镜图`;
          shots.push({
            shot_id: `S${String(n).padStart(2, "0")}`, scene: scene.location || "", characters: onIds,
            camera: cam, lighting: light, action, duration: "5s",
            negative_prompt: "不要字幕,不要角色漂移,不要多出人物,不要手部畸形,不要改变发色瞳色服装",
            emotion, dialogue, image_prompt: imagePrompt, video_prompt: videoPrompt,
          });
          n++;
        }
      }
      return { shots };
    }
  }
  // schema 里是 float 的字段（model_dump_json 会输出 "8.0"）
  const FLOAT_KEYS = new Set(["score"]);

  function stringValues(v, out = []) {
    if (typeof v === "string") out.push(v);
    else if (Array.isArray(v)) v.forEach(x => stringValues(x, out));
    else if (v && typeof v === "object") Object.values(v).forEach(x => stringValues(x, out));
    return out;
  }

  /* ---------------- 5 个 LLM 型 Agent 的提示词（agents/writers.py 原文） ---------------- */
  const AGENTS = {
    idea: {
      key: "idea", name: "选题 Agent", task: "idea",
      prompt: st => [
        "你是漫剧『创意与选题 Agent』。把用户的一句话创意，发展为可生产的漫剧项目方向。" +
        "需给出题材类型、目标受众、核心冲突、情绪基调、开头钩子、系列化潜力，以及 2-4 个原创角色雏形与 2-3 个可选方向。" +
        "只做类型/节奏/结构层面的规律分析，严禁复制具体作品的剧情/台词/角色，严禁使用真实在世人物（需求文档第八章合规）。",
        `用户创意：${st.idea_text}`,
        { idea_text: st.idea_text }],
    },
    script: {
      key: "script", name: "编剧 Agent", task: "script",
      prompt: st => [
        "你是漫剧『编剧 Agent』。基于选题结果生成结构化剧本：标题、logline、大纲，以及按顺序的场景列表；" +
        "每个场景包含场景编号、地点、时间、概要、出场角色、镜头级台词/旁白/动作。台词要符合人物性格、适配竖屏短视频节奏。" +
        "保持原创，不要复制具体作品。",
        "请根据选题结果撰写一部 30-60 秒竖屏漫剧的结构化剧本。",
        { idea_text: st.idea_text, idea: st.idea }],
    },
    review: {
      key: "review", name: "审稿与合规 Agent", task: "review",
      prompt: st => [
        "你是漫剧『审稿与合规 Agent』。检查剧本的逻辑漏洞、动机不清、节奏拖沓与衔接桥段；" +
        "做合规判定（pass/warn/fail）：是否复制了具体作品剧情/台词/角色、是否高度模仿在世创作者、是否含低俗/暴力/侵权风险；" +
        "并对需求文档的八维质量指标打分（前期无法评估的维度 score 置空并说明『待后期』）。",
        "请审稿并给出合规判定与质量评分。",
        { idea: st.idea, script: st.script }],
    },
    characters: {
      key: "characters", name: "角色设定 Agent", task: "character",
      prompt: st => [
        "你是漫剧『角色设定 Agent』。为每个角色输出完整设定，字段严格对齐：" +
        "character_id、name、age、identity、fixed_visual_features（固定外貌，跨镜头不可变）、" +
        "variable_features（可变项）、forbidden_changes（不可变化项，一致性硬约束）、voice_profile（音色）。" +
        "并给出整体一致性策略（锁 seed + 固定参考图 + forbidden_changes 约束）。角色须原创。",
        "请基于选题与剧本生成全部角色的结构化设定。",
        { idea: st.idea, script: st.script }],
    },
    storyboard: {
      key: "storyboard", name: "分镜 Agent", task: "storyboard",
      prompt: st => [
        "你是漫剧『分镜 Agent』。把剧本拆解为镜头表，每个镜头字段严格对齐：" +
        "shot_id、scene、characters（用 character_id 绑定，避免角色混乱）、camera{shot_size,angle,movement}、" +
        "lighting{key_light,rim_light,intensity}、action、duration、negative_prompt，以及 emotion、dialogue、" +
        "image_prompt（分镜图提示词）、video_prompt（视频提示词）。" +
        "image_prompt 中务必带上出场角色的 fixed_visual_features，negative_prompt 中务必带上 forbidden_changes，" +
        "以从提示词侧抑制角色漂移（一致性）。",
        "请生成完整镜头表，含图像与视频提示词。",
        { script: st.script, characters: st.characters }],
    },
  };

  root.MockLLM = MockLLM;
  root.LLM_AGENTS = AGENTS;
  root.MOCK_TABLES = { GENRE_MAP, DEFAULT_GENRE, RED_FLAGS };
})(typeof window !== "undefined" ? window : globalThis);
