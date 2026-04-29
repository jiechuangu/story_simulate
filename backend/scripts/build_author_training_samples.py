"""
Build chapter-level training samples for style-aware novel continuation.

Pipeline:
1. Read chapter records from chapters.json.
2. Summarize each chapter with an LLM.
3. Build one book-level blueprint from a user-provided blueprint.txt or chapter summaries.
4. Reconstruct chapter-generation inputs for each chapter.
5. Write chapter-level training samples to JSONL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.llm_client import LLMClient


@dataclass
class ChapterInfo:
    chapter_index: int
    chapter_id: str
    volume_title: str
    chapter_title: str
    text: str
    char_count: int
    paragraph_count: int


class AuthorTrainingSampleBuilder:
    def __init__(
        self,
        chapters: List[ChapterInfo],
        output_dir: Path,
        recent_summary_window: int = 3,
        blueprint_txt_path: Path | None = None,
    ):
        self.chapters = chapters
        self.output_dir = output_dir
        self.recent_summary_window = recent_summary_window
        self.blueprint_txt_path = blueprint_txt_path
        self.llm = LLMClient()

    def run(self, force: bool = False) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        chapter_summaries = self._build_or_load_chapter_summaries(force=force)
        blueprint = self._build_or_load_blueprint(chapter_summaries=chapter_summaries, force=force)
        chapter_samples, planning_samples = self._build_or_load_training_samples(
            blueprint=blueprint,
            chapter_summaries=chapter_summaries,
            force=force,
        )

        (self.output_dir / "chapter_summaries.json").write_text(
            json.dumps(chapter_summaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.output_dir / "book_blueprint.json").write_text(
            json.dumps(blueprint, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with open(self.output_dir / "chapter_training_samples.jsonl", "w", encoding="utf-8") as f:
            for sample in chapter_samples:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        with open(self.output_dir / "planning_training_samples.jsonl", "w", encoding="utf-8") as f:
            for sample in planning_samples:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")

        manifest = {
            "chapter_count": len(self.chapters),
            "chapter_sample_count": len(chapter_samples),
            "planning_sample_count": len(planning_samples),
            "recent_summary_window": self.recent_summary_window,
            "blueprint_txt_path": str(self.blueprint_txt_path) if self.blueprint_txt_path else None,
            "files": {
                "chapter_summaries": "chapter_summaries.json",
                "book_blueprint": "book_blueprint.json",
                "chapter_training_samples": "chapter_training_samples.jsonl",
                "planning_training_samples": "planning_training_samples.jsonl",
            },
        }
        (self.output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_or_load_chapter_summaries(self, force: bool) -> List[Dict[str, Any]]:
        path = self.output_dir / "chapter_summaries.json"
        if path.exists() and not force:
            return json.loads(path.read_text(encoding="utf-8"))

        records: List[Dict[str, Any]] = []
        for chapter in self.chapters:
            summary = self._summarize_chapter(chapter)
            records.append(summary)
            print(f"[chapter-summary] {chapter.chapter_id} {chapter.chapter_title}")
        return records

    def _build_or_load_blueprint(self, chapter_summaries: List[Dict[str, Any]], force: bool) -> Dict[str, Any]:
        path = self.output_dir / "book_blueprint.json"
        if path.exists() and not force:
            return json.loads(path.read_text(encoding="utf-8"))
        if self.blueprint_txt_path and self.blueprint_txt_path.exists():
            return self._build_book_blueprint_from_user_text(
                blueprint_text=self.blueprint_txt_path.read_text(encoding="utf-8"),
                chapter_summaries=chapter_summaries,
            )
        return self._build_book_blueprint(chapter_summaries)

    def _build_or_load_training_samples(
        self,
        blueprint: Dict[str, Any],
        chapter_summaries: List[Dict[str, Any]],
        force: bool,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        chapter_path = self.output_dir / "chapter_training_samples.jsonl"
        planning_path = self.output_dir / "planning_training_samples.jsonl"
        if chapter_path.exists() and planning_path.exists() and not force:
            chapter_samples: List[Dict[str, Any]] = []
            planning_samples: List[Dict[str, Any]] = []
            with open(chapter_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        chapter_samples.append(json.loads(line))
            with open(planning_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        planning_samples.append(json.loads(line))
            return chapter_samples, planning_samples

        chapter_samples: List[Dict[str, Any]] = []
        planning_samples: List[Dict[str, Any]] = []
        for idx, chapter in enumerate(self.chapters):
            recent_summaries = chapter_summaries[max(0, idx - self.recent_summary_window):idx]
            previous_chapter = chapter_summaries[idx - 1] if idx > 0 else None
            context = self._infer_chapter_context(
                blueprint=blueprint,
                chapter=chapter,
                chapter_summary=chapter_summaries[idx],
                recent_summaries=recent_summaries,
                previous_chapter=previous_chapter,
            )
            chapter_samples.append(
                {
                    "sample_id": f"{chapter.chapter_id}",
                    "chapter_index": chapter.chapter_index,
                    "chapter_id": chapter.chapter_id,
                    "volume_title": chapter.volume_title,
                    "chapter_title": chapter.chapter_title,
                    "input_payload": {
                        "book_blueprint": blueprint,
                        "recent_chapter_summaries": recent_summaries,
                        "previous_chapter_summary": previous_chapter,
                        "chapter_context": context,
                    },
                    "target_text": chapter.text,
                    "target_summary": chapter_summaries[idx],
                    "metadata": {
                        "char_count": chapter.char_count,
                        "paragraph_count": chapter.paragraph_count,
                    },
                }
            )
            planning_samples.append(
                {
                    "sample_id": f"{chapter.chapter_id}_plan",
                    "chapter_index": chapter.chapter_index,
                    "chapter_id": chapter.chapter_id,
                    "volume_title": chapter.volume_title,
                    "chapter_title": chapter.chapter_title,
                    "input_payload": {
                        "book_blueprint": blueprint,
                        "recent_chapter_summaries": recent_summaries,
                        "previous_chapter_summary": previous_chapter,
                        "target_chapter_summary": chapter_summaries[idx],
                    },
                    "target_plan": context,
                    "metadata": {
                        "char_count": chapter.char_count,
                        "paragraph_count": chapter.paragraph_count,
                    },
                }
            )
            print(f"[training-sample] {chapter.chapter_id} {chapter.chapter_title}")
        return chapter_samples, planning_samples

    def _summarize_chapter(self, chapter: ChapterInfo) -> Dict[str, Any]:
        system = (
            "你是小说章节分析器。"
            "请阅读一章小说正文，提取后续续写训练需要的结构化信息。"
            "只返回 JSON，不要解释。"
        )
        user = f"""
章节标题：{chapter.chapter_title}
所属卷/集：{chapter.volume_title}
章节正文：
{chapter.text}

请返回 JSON，字段必须包含：
- chapter_title
- one_line_summary：一句话概括本章发生了什么
- detailed_summary：120-220字，概括本章关键情节
- key_characters：数组，列出本章最关键角色
- pov：本章主要视角人物，如无法判断可留空
- scene_type：本章主要类型，例如 开场 / 冲突升级 / 试探对话 / 战斗 / 缓冲 / 揭秘
- emotional_tone：本章情绪底色
- relationship_tension：本章最关键的关系张力
- open_threads：数组，本章结束后仍未解决的线索或问题
- chapter_hook：本章结尾留给下一章的钩子
"""
        data = self.llm.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=1600,
        )
        return {
            "chapter_index": chapter.chapter_index,
            "chapter_id": chapter.chapter_id,
            "volume_title": chapter.volume_title,
            "chapter_title": data.get("chapter_title") or chapter.chapter_title,
            "one_line_summary": data.get("one_line_summary") or chapter.chapter_title,
            "detailed_summary": data.get("detailed_summary") or data.get("one_line_summary") or "",
            "key_characters": data.get("key_characters") or [],
            "pov": data.get("pov") or "",
            "scene_type": data.get("scene_type") or "",
            "emotional_tone": data.get("emotional_tone") or "",
            "relationship_tension": data.get("relationship_tension") or "",
            "open_threads": data.get("open_threads") or [],
            "chapter_hook": data.get("chapter_hook") or "",
        }

    def _build_book_blueprint(self, chapter_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        condensed = chapter_summaries[:4] + chapter_summaries[max(4, len(chapter_summaries) - 4):]
        if len(chapter_summaries) <= 8:
            condensed = chapter_summaries

        system = (
            "你是小说蓝图提炼器。"
            "请根据一本小说的章节摘要，提炼出适合续写训练使用的全书蓝图。"
            "蓝图要强调文风、人物、冲突、长期悬念和叙事方向。"
            "只返回 JSON，不要解释。"
        )
        user = f"""
书名：{self._guess_book_title()}
章节摘要列表：
{json.dumps(condensed, ensure_ascii=False)}

请返回 JSON，字段必须包含：
- title
- premise：一句话前提
- story_summary：180-320字，写成像小说简介而不是流水账
- style：文风概述
- theme：主题
- protagonist：对象，至少包含 name / description / desire / weakness
- major_characters：数组，每项至少包含 name / role / desire / pressure
- factions：数组，可为空
- core_conflict：长期主冲突
- world_rules：数组，列出世界设定或叙事规则
- long_term_mysteries：数组，列出长期悬念
- opening_topic：故事开篇会从什么方向切入
- ending_direction：故事整体会走向哪里
"""
        return self.llm.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.35,
            max_tokens=2200,
        )

    def _build_book_blueprint_from_user_text(
        self,
        blueprint_text: str,
        chapter_summaries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        condensed = chapter_summaries[:3] + chapter_summaries[max(3, len(chapter_summaries) - 3):]
        if len(chapter_summaries) <= 6:
            condensed = chapter_summaries

        system = (
            "你是小说训练数据的蓝图结构化器。"
            "用户已经提供了一份人工撰写的全书蓝图，你要以这份蓝图为最高优先级，"
            "将它整理成结构化 JSON，供后续章节样本构造使用。"
            "章节摘要只用于补全缺失信息，不能覆盖用户蓝图的核心判断。"
            "只返回 JSON，不要解释。"
        )
        user = f"""
书名：{self._guess_book_title()}

用户提供的 blueprint.txt：
{blueprint_text}

章节摘要样本（仅用于补充）：
{json.dumps(condensed, ensure_ascii=False)}

请返回 JSON，字段必须包含：
- title
- premise
- story_summary
- style
- theme
- protagonist：对象，至少包含 name / description / desire / weakness
- major_characters：数组，每项至少包含 name / role / desire / pressure
- factions：数组，可为空
- core_conflict
- world_rules：数组
- long_term_mysteries：数组
- opening_topic
- ending_direction
- source_note：固定说明这份蓝图来自用户提供的 blueprint.txt

要求：
1. 用户 blueprint.txt 是第一优先级。
2. 如果用户蓝图没有写明某个字段，再参考章节摘要补全。
3. 不要发明与用户蓝图冲突的设定。
4. 输出必须是合法 JSON。
"""
        data = self.llm.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=2200,
        )
        data["source_note"] = "user_blueprint_txt"
        data["raw_blueprint_text"] = blueprint_text
        return data

    def _infer_chapter_context(
        self,
        blueprint: Dict[str, Any],
        chapter: ChapterInfo,
        chapter_summary: Dict[str, Any],
        recent_summaries: List[Dict[str, Any]],
        previous_chapter: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        system = (
            "你是续写训练样本重建器。"
            "你的任务不是改写正文，而是反推出：在写出目标章节之前，生成模型应该拿到什么输入。"
            "只返回 JSON，不要解释。"
        )
        user = f"""
书籍蓝图：
{json.dumps(blueprint, ensure_ascii=False)}

最近章节摘要：
{json.dumps(recent_summaries, ensure_ascii=False)}

上一章摘要：
{json.dumps(previous_chapter, ensure_ascii=False) if previous_chapter else "无"}

目标章节标题：{chapter.chapter_title}
目标章节摘要：
{json.dumps(chapter_summary, ensure_ascii=False)}

请反推出“生成这一章之前”的输入状态，返回 JSON，字段必须包含：
- inferred_topic：对象，包含 title / summary / promise / focus_characters / tension_type
- active_characters：数组，本章生成前最应被放进上下文的人物
- chapter_goal：本章主要推进目标
- chapter_hook_seed：进入本章前，读者最期待被推进的钩子
- emotional_tone：本章应有的情绪底色
- relationship_tension：本章最关键的关系张力
- open_threads：数组，本章开写前仍应悬而未决的问题
- memory_cues：数组，列出生成本章时应该提醒模型记住的连续性要点
- scene_beats_seed：数组，每项包含 beat_title / tension / visible_action / subtext

要求：
1. inferred_topic 要像用户在上一章后点选的“下一章方向”。
2. 不要直接抄目标章节正文，要总结成生成前可用的控制信息。
3. active_characters 和 memory_cues 要尽量贴近续写时实际会用到的上下文。
"""
        return self.llm.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.3,
            max_tokens=2200,
        )

    def _guess_book_title(self) -> str:
        first = self.chapters[0].volume_title if self.chapters else ""
        if first:
            return first
        return self.chapters[0].chapter_title if self.chapters else "未命名小说"


def load_chapters(chapters_json_path: Path) -> List[ChapterInfo]:
    data = json.loads(chapters_json_path.read_text(encoding="utf-8"))
    chapters: List[ChapterInfo] = []
    for item in data.get("chapters") or []:
        chapters.append(
            ChapterInfo(
                chapter_index=int(item["chapter_index"]),
                chapter_id=item["chapter_id"],
                volume_title=item.get("volume_title", ""),
                chapter_title=item.get("chapter_title", ""),
                text=item.get("text", ""),
                char_count=int(item.get("char_count") or len(item.get("text", ""))),
                paragraph_count=int(item.get("paragraph_count") or 0),
            )
        )
    return chapters


def main() -> None:
    parser = argparse.ArgumentParser(description="Build chapter-level author training samples.")
    parser.add_argument("chapters_json", help="Path to chapters.json generated by split_novel_chapters.py")
    parser.add_argument(
        "--output-dir",
        help="Output directory. Defaults to <chapters_json_dir>/author_training_samples",
    )
    parser.add_argument(
        "--recent-summary-window",
        type=int,
        default=3,
        help="How many previous chapter summaries to include when reconstructing the next chapter input.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild outputs even if cached files already exist.",
    )
    parser.add_argument(
        "--blueprint-txt",
        help="Path to a user-provided blueprint.txt. Defaults to <chapters_json_dir>/blueprint.txt if present.",
    )
    args = parser.parse_args()

    chapters_json_path = Path(args.chapters_json).resolve()
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else chapters_json_path.parent / "author_training_samples"
    )
    default_blueprint_txt = chapters_json_path.parent / "blueprint.txt"
    blueprint_txt_path = (
        Path(args.blueprint_txt).resolve()
        if args.blueprint_txt
        else (default_blueprint_txt if default_blueprint_txt.exists() else None)
    )

    chapters = load_chapters(chapters_json_path)
    builder = AuthorTrainingSampleBuilder(
        chapters=chapters,
        output_dir=output_dir,
        recent_summary_window=args.recent_summary_window,
        blueprint_txt_path=blueprint_txt_path,
    )
    builder.run(force=args.force)

    print(f"Chapters loaded: {len(chapters)}")
    print(f"Output dir: {output_dir}")
    print(f"Blueprint txt: {blueprint_txt_path if blueprint_txt_path else 'None'}")
    print("Generated files:")
    print("  - chapter_summaries.json")
    print("  - book_blueprint.json")
    print("  - chapter_training_samples.jsonl")
    print("  - planning_training_samples.jsonl")
    print("  - manifest.json")


if __name__ == "__main__":
    main()
