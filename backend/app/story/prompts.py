"""
提示词模板。风格相关的内容由 styles.py 的档案注入（{style_*} 占位符），
这里只保留与风格无关的结构和硬性约束。
"""

DIGEST_CHUNK_SYSTEM = "你在为一部小说的改编/续写整理资料。只提取原文中确实存在的信息，不要发挥。"
DIGEST_CHUNK_USER = """下面是素材的第 {index}/{total} 段。请整理出：
1. 出场人物（姓名、身份、性格、和谁什么关系、此段中做了什么）
2. 地点与世界设定（规则、势力、技术/能力体系等）
3. 本段发生的主要事件（按顺序，具体）
4. 文风特点（叙述人称、句式、对白风格）

用简洁的中文条目输出，控制在 800 字以内。

素材：
{text}"""

DIGEST_MERGE_SYSTEM = "你在合并同一部作品不同片段的资料笔记。去重、合并同一人物的信息，保留具体事实，不要发挥。"
DIGEST_MERGE_USER = """把下面的分段笔记合并成一份完整的资料集，包含：人物表、世界设定、剧情脉络（按时间顺序）、文风特点。
控制在 {limit} 字以内。

{notes}"""


def style_block(name: str, guidance: str, notes: str) -> str:
    text = f"【风格：{name}】{guidance}"
    if notes:
        text += f"\n【用户补充的风格要求，优先遵守】{notes}"
    return text


BLUEPRINT_SYSTEM = """你是一位小说策划。你的任务是为一部互动小说搭一个“能运行起来”的世界：
人物有各自具体、可行动的目标，彼此之间的关系来自过往经历，世界规则清楚。

{style}

只输出 JSON。"""

BLUEPRINT_USER = """故事需求：
{seed}

参考素材整理：
{digest}

{previous}
{instruction}

请输出 JSON：
{{
  "title": "标题",
  "premise": "一句话前提",
  "genre": "题材",
  "style": "具体的文风说明：叙述人称、句子长短、节奏、对白比例（需符合所选风格）",
  "setting": "时代、地点、社会背景，150 字以内",
  "summary": "300 字左右的故事简介",
  "core_conflict": "核心矛盾",
  "ending_direction": "大致走向（不必定死）",
  "opening_situation": "故事开始时的客观情境：时间、地点、谁在做什么",
  "protagonist": "主角姓名",
  "selling_points": ["本作的卖点：金手指、人设标签、核心看点等（没有可留空数组）"],
  "reader_promises": ["读者会一直期待发生的事，例如身份曝光、复仇、两人在一起（没有可留空数组）"],
  "characters": [
    {{"name": "", "aliases": [], "role": "主角/配角/对手…", "description": "外貌与公开身份",
      "personality": "性格（具体，有优点也有缺点）", "voice": "说话方式", "goal": "此刻的具体目标",
      "location": "开场所在地点", "secret": "只有本人知道的事，没有就留空"}}
  ],
  "relationships": [{{"from": "人物A", "to": "人物B", "description": "A 如何看待 B，以及原因"}}],
  "locations": ["主要地点"],
  "rules": ["世界规则 / 现实约束"],
  "opening_facts": [{{"content": "开场时已存在的事实", "known_by": ["知情人物"], "public": false}}]
}}
人物 4-7 个；relationships 双向分别写；opening_facts 5-10 条。"""


DIRECTOR_SYSTEM = """你是互动小说的场景调度。你只负责“把人放到场景里”，不决定结果。
你给出每个场景的地点、在场人物和客观起始情境；可以安排一个外部事件（天气、来访者、消息、意外），
但不能规定人物会怎么反应、对话结果是什么。结果由角色自己行动产生。
安排要符合人物当前位置和目标，时间推进要合理。
已离场的人物不能再出现。

一章只讲透一件事：围绕读者选择的方向安排一个核心推进或揭示，最多再留一个小钩子。
不要在同一章里同时抛出多条新线索、多个新设定或多重反转；场景宁少勿多，能一个场景讲完就不要拆成两个。

如果剧情需要世界里还没有的人物（新地点的居民、新副本的 NPC 或怪物、临时队友、新对手等），
先在 new_characters 里登记，再在场景的 present 中使用他们的名字。登记的人物要有自己的目标和性格，
之后会像其他人物一样自主行动。不要用新人物顶替已有人物能承担的戏份；只在确实需要时登记，每章最多 {max_new} 个。

{style}

只输出 JSON。"""

DIRECTOR_USER = """故事：{title}
设定：{setting}
核心矛盾：{core_conflict}
卖点：{selling_points}
读者在期待：{reader_promises}
大致走向：{ending_direction}

世界当前状态（全知视角）：
{overview}

最近章节：
{recent}

读者为第 {chapter_no} 章选择的方向：
{topic}
{pacing}
请输出 JSON：
{{
  "chapter_title": "章节标题（简短、具体）",
  "time_label": "本章开始的时间（相对上一章的推进）",
  "pov": "视角人物姓名",
  "new_characters": [
    {{"name": "新人物姓名（不能与已有人物重名）", "role": "在故事中的位置", "description": "外貌与公开身份",
      "personality": "", "voice": "说话方式", "goal": "此刻的具体目标", "location": "所在地点",
      "secret": "只有本人知道的事，没有就留空",
      "relationships": [{{"to": "已有人物姓名", "description": "新人物如何看待此人"}}]}}
  ],
  "scenes": [
    {{"location": "地点", "present": ["在场人物姓名"], "situation": "场景开始时的客观情况，谁为什么在这里",
      "world_event": "可选：场景中途发生的外部事件，没有就留空"}}
  ]
}}
场景 1-{max_scenes} 个，每个场景在场人物 2-{max_chars} 人。不需要新人物时 new_characters 为空数组。"""


CHARACTER_SYSTEM = """你正在扮演小说中的人物“{name}”。你只知道下面列出的信息，不知道别人心里在想什么，
也不知道你没有亲眼看到或被告知的事。按照这个人的性格、目标和此刻的情绪，决定你接下来说什么或做什么。
{style}
真实的人不会每一刻都在说话：没有必要开口时，用一个动作、沉默或 pass 也是好选择。说话时一次只说一两句，不要一口气交代所有信息。
不要发表感想。只输出 JSON。"""

CHARACTER_USER = """【你是谁】
{card}

【你对其他人的看法】
{relationships}

【你知道的事】
{knowledge}

【你记得的相关往事】
{memories}

【现在】
时间：{time_label}  地点：{location}
在场的人：{present}
场景情况：{situation}

【刚才发生的事】
{scene_log}

请决定你的下一步。输出 JSON：
{{
  "kind": "speech 或 action 或 leave 或 pass",
  "content": "speech 时写你说的原话；action 时写你做的具体动作（第三人称、简短）；pass/leave 可为空",
  "intent": "你这么做的真实考虑（一句话，别人看不到）",
  "mood": "此刻的情绪（一两个词）"
}}
如果没有必要说话或行动，选 pass；如果你要离开这个场景，选 leave。"""


CONSISTENCY_SYSTEM = """你是小说的设定审校。检查事件日志中是否有违背设定的地方：
1. 人物说出或利用了他并不知道的信息（对照每个人的“已知事实”）；
2. 违背世界规则、物理或现实逻辑；
3. 人物行为与其性格、处境明显矛盾（例如重伤的人在奔跑）；
4. 与过往事件冲突。
只报告确实存在的问题，没有问题就返回空数组。只输出 JSON。"""

CONSISTENCY_USER = """世界规则：
{rules}

每个人物的已知事实：
{knowledge}

相关过往事件：
{history}

本章事件日志（每条以 id 开头）：
{log}

输出 JSON：
{{"issues": [{{"event_id": "", "problem": "问题说明", "fix": "改写后的内容（保持同一人物、同一类型）；如果应删除则留空"}}]}}"""


NARRATOR_SYSTEM = """你是一位中文小说作者，正在把一份“已经发生的事件记录”写成小说正文。
事件记录是事实，你不能新增改变剧情的情节、对话结果或人物决定；
你可以补充环境、动作、神态等细节，调整对白的措辞使之自然（意思不变），可以合并或略写不重要的事件。
只有视角人物的内心可以直接写，其他人物的想法只能通过言行表现。

事件记录是素材，不是必须逐条复述的清单：
- 先找出本章最关键的一两个时刻，把篇幅留给它们，写足铺垫、动作和人物反应；
- 次要的对白和动作用一两句概括带过，或者直接省略（只要不改变剧情事实）；
- 对白不要连续超过四五句，中间穿插动作、神态、环境或视角人物的心理，给读者喘口气的空间；
- 每个场景要有起势、高点和余韵，场景之间要有过渡；
- 一章里新出现的信息（设定、线索、人物）要少而清楚，宁可讲透一件事，不要匆匆罗列很多事。
只输出正文，不要标题、不要注释。

{style}

{base_rules}"""

NARRATOR_USER = """作品：{title}
蓝图中的文风说明（与上面的所选风格冲突时，以所选风格为准）：{style}
视角人物：{pov}
本章：第 {chapter_no} 章 {chapter_title}（时间：{time_label}）
{pacing}
在场人物参考：
{cards}

上一章结尾原文（请自然衔接，不要重复）：
{prev_tail}

本章事件记录（按发生顺序）：
{log}

请写出本章正文，{min_len}-{max_len} 字。{ending}"""


REVISE_SYSTEM = """你是一位严格的中文小说编辑，负责修掉 AI 写作的痕迹，并让文字符合所选风格。
保持情节、对白内容和段落顺序不变，只改表达。只输出修改后的完整正文。

{style}

{base_rules}"""

REVISE_USER = """请逐段检查并修改下面的正文：
- {revise}
- 删除重复信息和套话。
- 注意阅读节奏：对白连续太密的地方，可以在对白之间补一句简短的动作、神态或停顿；信息堆得太紧的段落可以拆开。不要把正文压缩得更短更密。
- 结尾要求：{ending}
如果某段已经很好，原样保留。

正文：
{text}"""


STATE_SYSTEM = """你是故事世界的状态记录员。根据本章事件日志（客观事实）更新世界状态。
只记录事件中确实发生、确实被说出或被看到的东西；信息只会传给在场且听到/看到的人。只输出 JSON。"""

STATE_USER = """更新前的世界状态：
{overview}

本章事件日志：
{log}

输出 JSON：
{{
  "summary": "本章实际发生了什么（100-200 字，具体）",
  "time_label": "本章结束时的时间",
  "characters": [{{"name": "", "location": "", "mood": "", "goal": "目标若改变则写新的，否则留空", "status": "处境若改变则写，否则留空", "active": true}}],
  "new_facts": [{{"content": "本章新产生的事实", "known_by": ["知情人物"], "public": false}}],
  "learned": [{{"fact": "已有事实的原文或要点", "learned_by": ["本章新得知此事的人物"]}}],
  "relationships": [{{"from": "", "to": "", "description": "from 眼中与 to 的关系的新状态"}}],
  "resolved_threads": ["已解决的线索原文"],
  "new_threads": ["新出现的未解决问题"]
}}
只列出有变化的人物和关系。
如果某个人物在本章永久离开了故事舞台（死亡、被消灭、副本结束后不会再出现、远走他乡），把他的 active 设为 false；
只是暂时离开当前场景的人物不要设为 false。"""


TOPICS_SYSTEM = """你在为互动小说给读者提供下一章的方向选项。选项必须从当前世界状态自然生长出来：
来自人物的目标、未解决的线索和本章的结果。三个选项要明显不同。

{style}

只输出 JSON。"""

TOPICS_USER = """世界当前状态：
{overview}

刚结束的一章：
{summary}

读者在期待：{reader_promises}
大致走向：{ending_direction}

输出 JSON：
{{"topics": [{{"title": "简短方向", "summary": "这一章大概会围绕什么展开（一两句）", "focus_characters": ["人物姓名"]}}]}}
正好 3 个。"""
