"""
风格档案。

每个档案影响流水线中的六个环节：
  blueprint  蓝图策划的取向（要不要金手指、卖点、读者期待）
  director   场景调度的取向，以及按章节号给出的“节奏任务”
  character  角色扮演的口吻
  narrator   正文的写法、长度、结尾方式
  revise     润色时要保留 / 去掉什么
  topics     下一章选项的写法
角色在信息边界内自主行动、设定审校、状态回写这些“保证逻辑不崩”的环节对所有风格都一样。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# 所有风格都禁止的 AI 套话
AI_CLICHES = [
    "指尖微微收紧", "空气仿佛凝固", "空气中弥漫着", "嘴角勾起一抹", "眼底闪过一丝", "心中五味杂陈",
    "仿佛在诉说", "像是在克制某种", "不易察觉", "意味深长", "命运的齿轮", "时间仿佛静止",
    "目光交汇", "暗流涌动", "风暴即将来临", "一切才刚刚开始", "某种东西正在改变",
]
BASE_RULES = "通用要求：不替读者下结论，不写“他感到很痛苦”“这意味着”之类的解释；人物说话符合身份和当时情绪。\n禁止使用这些套话：" + "、".join(AI_CLICHES)


@dataclass
class StyleProfile:
    id: str
    name: str
    tagline: str
    blueprint: str
    director: str
    character: str
    narrator: str
    revise: str
    topics: str
    ending: str
    length: tuple = (1500, 3000)
    narrator_temperature: float = 0.8
    pacing: Optional[Callable[[int], str]] = None
    examples: List[str] = field(default_factory=list)

    def pacing_task(self, chapter_no: int) -> str:
        return self.pacing(chapter_no) if self.pacing else ""

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "tagline": self.tagline, "examples": self.examples}


def _webnovel_pacing(no: int) -> str:
    if no == 1:
        return "开篇：迅速交代主角处境和人设标签，让主角受到一次明显的压制或轻视，并在本章内亮出金手指的苗头。"
    if no in (2, 3):
        return "黄金三章：安排第一次小逆袭的条件——让对手的轻视公开化，给主角一个当众证明自己的机会。"
    phase = (no - 4) % 4
    return [
        "蓄压：对手出招或局势变坏，主角吃亏或受辱，同时埋下翻盘的伏笔。",
        "蓄压升级：压力加码，围观者站队，读者期待主角反击。",
        "爆发：安排能让主角兑现能力的局面，打脸、反转、揭晓要在本章发生的条件要齐备。",
        "收获与新期待：清点收获（地位、资源、关系变化），同时引出一个更强的对手或更大的悬念。",
    ][phase]


def _suspense_pacing(no: int) -> str:
    if no == 1:
        return "开篇：呈现一个具体的反常事件或案件，给出至少三条可供读者推理的线索。"
    return [
        "调查：让主角获得新线索，同时出现一个误导方向。",
        "反转：推翻一个此前看似成立的判断。",
        "逼近：嫌疑收窄，相关人物开始行动或掩盖。",
    ][(no - 2) % 3]


STYLES: Dict[str, StyleProfile] = {}


def _add(p: StyleProfile) -> None:
    STYLES[p.id] = p


_add(StyleProfile(
    id="realistic",
    name="写实文学",
    tagline="克制、可信、人物驱动，像严肃小说",
    blueprint=(
        "追求可信而不是戏剧化：不要给每个人都安排秘密或悲惨过去，只在剧情需要时才设置秘密；"
        "冲突来自目标之间的真实矛盾和资源约束，而不是误会和巧合；人物要有普通、日常的一面；现实题材严格遵守现实逻辑。"
    ),
    director="节奏自然，允许平静的过渡场景。",
    character="像真实的人一样：可能犹豫、搪塞、说错话、被情绪带偏，也可能只是做件平常的事。不要表演。",
    narrator=(
        "用具体的动作、对白和可感知的细节推进；不要每段结尾都升华或抒情；比喻少而准，一章不超过三处；"
        "不要堆砌意象和氛围描写；允许对白啰嗦、打断、答非所问，不要句句金句；平淡的事就平淡地写。"
    ),
    revise="删掉空泛的氛围句、解释人物情绪的句子、段尾升华、结尾总结；减少比喻和排比；把过于工整的对白改得像真人说话。",
    topics="三个选项走向不同（推进主线 / 转向某个配角 / 处理遗留问题），不要都是“危机升级”，用平实的语言。",
    ending="章节在最后一个事件处自然结束，不要额外制造悬念或做总结。",
    narrator_temperature=0.8,
    examples=["余华式的平静叙述", "契诃夫式的日常"],
))

_add(StyleProfile(
    id="webnovel",
    name="网文爽文",
    tagline="节奏快、先压后扬、打脸逆袭、章章有钩子",
    blueprint=(
        "这是一部追求“让人上瘾”的网络小说。主角需要一个清晰的金手指（独特能力、重生记忆、隐藏身份、系统等）"
        "和一句话能说清的人设标签；要有看轻主角的对手梯队（由弱到强），有负责被打脸、负责震惊、负责暧昧的配角；"
        "主线要能不断制造“读者在等的事”。世界逻辑仍要自洽，配角不能降智。"
    ),
    director=(
        "你要服务于追更体验：场景要能制造冲突和期待——让对手当众挑衅、让主角被低估、让有围观者见证。"
        "你可以安排这些局面，但不能替角色决定结果。每章要有一个清楚的增量（一个新信息、一次地位变化或一个新人物，选一个讲透）。"
    ),
    character="人物性格鲜明、反应直接：嚣张的就嚣张，护短的就护短，吃瘪了会恼羞成怒。主角有底气时可以从容，但不要无脑开挂。",
    narrator=(
        "网文写法：段落短（多为一到三句），节奏快，对话和动作、主角的吐槽或心理交替出现，不要整页都是对白；"
        "压抑的地方要让读者憋屈，爆发的地方要写足围观者的反应和对手的震惊；用词通俗有画面感，可以有口语和网感，但不油腻。"
    ),
    revise="保留爽点、反转和章末钩子；删掉拖沓的描写和重复的心理活动；长段落拆短；让对话更有冲击力；不要把结尾改平淡。",
    topics=(
        "选项要写成读者想追下去的“期待”，例如“他会不会当场亮出身份？”“那个嘲笑他的人下场如何？”；"
        "三个选项分别偏向：正面打脸 / 扮猪吃虎继续隐藏 / 开新地图或新感情线。"
    ),
    ending="章节结尾必须留钩子：断在反转、悬念、对手出招或“下一秒就要发生”的地方，让人想立刻点下一章。",
    length=(2000, 3000),
    narrator_temperature=0.85,
    pacing=_webnovel_pacing,
    examples=["扮猪吃虎", "重生复仇", "系统流", "种田经营"],
))

_add(StyleProfile(
    id="comedy",
    name="轻松喜剧",
    tagline="诙谐、吐槽、反差萌，读起来不累",
    blueprint="基调轻松：人物有反差萌和小毛病，冲突不必沉重，可以来自性格碰撞、误会和窘境；坏人也可以有点可笑。",
    director="多安排能产生笑点的局面：性格相冲的人凑在一起、计划赶不上变化、尴尬场合。",
    character="可以吐槽、拌嘴、嘴硬心软、一本正经地胡说八道；保持人物自己的逻辑，笑点来自性格而不是硬抖机灵。",
    narrator="语言轻快，善用反差和节奏制造笑点，叙述者可以带一点俏皮的旁白；笑点靠对白和旁白吐槽交替打出来，给包袱留铺垫和反应的空间，避免说教和煽情。",
    revise="保留包袱和反差；删掉解释笑点的句子和硬凹的梗；让节奏更利落。",
    topics="选项要有趣，让人想看“这下怎么收场”；三个方向风格各异。",
    ending="结尾可以落在一个小包袱上，或留一个让人忍不住想看的窘境。",
    narrator_temperature=0.9,
    examples=["欢喜冤家", "沙雕日常"],
))

_add(StyleProfile(
    id="suspense",
    name="悬疑推理",
    tagline="信息控制、公平线索、层层反转",
    blueprint="设计一个核心谜团，真相要在设定里定好（写在知情人物的秘密里）；线索对读者公平；每个嫌疑人都有动机和隐瞒。",
    director="控制信息释放：每章让主角获得部分线索，同时有人在掩盖或误导；场景要服务于调查和对峙。",
    character="知情者会隐瞒和说谎，但谎言要符合其动机；调查者会追问细节、注意矛盾。",
    narrator="冷静、精确的叙述，重要细节要写到但不点破；对话中藏信息；节奏张弛有度，不要提前泄露真相。",
    revise="保留所有线索细节和对话中的信息点；删掉提前解释推理的句子和多余的氛围渲染。",
    topics="选项是调查方向：追查哪条线索、怀疑谁、去哪里；不要直接透露答案。",
    ending="结尾落在一个新疑点、新发现或推翻之前判断的细节上。",
    narrator_temperature=0.75,
    pacing=_suspense_pacing,
    examples=["本格推理", "密室", "社会派"],
))

_add(StyleProfile(
    id="dark_epic",
    name="暗黑史诗",
    tagline="冷峻厚重、代价真实、权谋与命运",
    blueprint="世界残酷但有内在秩序；权力、信仰、生存是主要驱动力；每个选择都有代价；人物立场灰色，没有纯粹的好人坏人。",
    director="场景要承载权力博弈和生存压力；允许暴力和死亡，但要有因果和分量。",
    character="人物在残酷环境中做现实的选择：会妥协、背叛、牺牲他人，也会在关键时刻守住某条底线。",
    narrator="叙述冷峻克制，句子可以较长、有厚重感；暴力写得直接、不渲染；细节具体（器物、气味、天气、伤口）；不煽情，不感叹命运。",
    revise="删掉煽情、感叹、宿命论式的总结句；保留冷硬的细节和人物的残酷选择。",
    topics="选项围绕权力格局和代价：结盟、背叛、牺牲谁、保住什么。",
    ending="结尾落在一个改变局势的决定或后果上，不必刻意悬念。",
    length=(1800, 3200),
    narrator_temperature=0.8,
    examples=["冰与火之歌式权谋", "低魔中世纪"],
))

_add(StyleProfile(
    id="romance",
    name="言情心动",
    tagline="感情拉扯、心动细节、甜虐有度",
    blueprint="以情感线为主：男女主（或主要 CP）有鲜明反差和吸引力，有阻碍他们靠近的现实原因；配角助攻或搅局。",
    director="多安排两人独处、被迫合作、误会与澄清、第三者出现的场景；感情推进要有节奏，不要一章就确定关系。",
    character="感情表达要符合性格：嘴硬的人不会直接告白，害羞的人会转移话题；在意对方时会有具体的小动作。",
    narrator="重点写互动中的细节：眼神、距离、语气变化、没说出口的话；对话有来有回；心理描写只给视角人物，克制不腻。",
    revise="保留心动细节和拉扯感；删掉直白的“他喜欢她”式陈述和过量的形容词。",
    topics="选项围绕感情走向：更近一步 / 出现阻碍 / 一方隐瞒的事被发现。",
    ending="结尾停在一个让人心跳的瞬间或一句未完的话上。",
    narrator_temperature=0.85,
    examples=["先婚后爱", "欢喜冤家", "双向暗恋"],
))

DEFAULT_STYLE = "realistic"


def get_style(style_id: Optional[str]) -> StyleProfile:
    return STYLES.get(style_id or DEFAULT_STYLE) or STYLES[DEFAULT_STYLE]


def list_styles() -> List[dict]:
    return [p.public() for p in STYLES.values()]
