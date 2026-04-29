"""
User-facing dataset pipeline for author-style novel training projects.

Usage:
1. Create a project scaffold.
2. Put novel.txt and blueprint.txt into the project directory.
3. Split chapters and inspect outputs.
4. Build training samples after manual verification.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_author_training_samples import AuthorTrainingSampleBuilder, load_chapters
from scripts.split_novel_chapters import detect_and_read_text, normalize_text, split_into_chapters, write_outputs


PROJECTS_ROOT = Path("data_projects")
NOVEL_FILE_NAME = "novel.txt"
BLUEPRINT_FILE_NAME = "blueprint.txt"


README_TEMPLATE = """# {project_name}

把数据放在这个目录里，然后按两步执行。

必需文件：
1. `novel.txt`
   放原始小说全文 txt。
2. `blueprint.txt`
   放你人工撰写的全书蓝图。后续样本构造会优先使用它。

步骤 1：章节切分
`python backend/scripts/novel_dataset_pipeline.py split-chapters {project_name}`

检查输出：
- `outputs/chapters/chapters.json`
- `outputs/chapters/chapters/`

确认章节切分没问题后，再执行步骤 2。

步骤 2：构造样本
`python backend/scripts/novel_dataset_pipeline.py build-samples {project_name}`

样本输出到：
- `outputs/author_training_samples/`
"""


BLUEPRINT_TEMPLATE = """请在这里写这本小说的全书蓝图。

建议至少包含：
1. 故事一句话前提
2. 故事简介（200-500字）
3. 文风描述
4. 主题
5. 主角：姓名、核心欲望、弱点、人物弧线
6. 主要角色：各自欲望、压力、关系
7. 核心冲突
8. 长线悬念
9. 世界规则 / 题材边界
10. 结局方向
"""


def create_project(project_name: str, projects_root: Path) -> None:
    project_dir = projects_root / project_name
    outputs_dir = project_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    readme_path = project_dir / "README.txt"
    blueprint_path = project_dir / BLUEPRINT_FILE_NAME
    novel_path = project_dir / NOVEL_FILE_NAME

    if not readme_path.exists():
        readme_path.write_text(README_TEMPLATE.format(project_name=project_name), encoding="utf-8")
    if not blueprint_path.exists():
        blueprint_path.write_text(BLUEPRINT_TEMPLATE, encoding="utf-8")
    if not novel_path.exists():
        novel_path.write_text("", encoding="utf-8")

    print(f"Project created: {project_dir.resolve()}")
    print("Put files here:")
    print(f"  - {novel_path.name}")
    print(f"  - {blueprint_path.name}")
    print("Then run step 1:")
    print(f"  python backend/scripts/novel_dataset_pipeline.py split-chapters {project_name}")

def split_project_chapters(project_name: str, projects_root: Path, force: bool) -> None:
    project_dir = projects_root / project_name
    if not project_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_dir}")

    novel_path = project_dir / NOVEL_FILE_NAME
    outputs_dir = project_dir / "outputs"
    chapters_output_dir = outputs_dir / "chapters"

    if not novel_path.exists() or not novel_path.read_text(encoding="utf-8", errors="ignore").strip():
        raise FileNotFoundError(f"Novel file is missing or empty: {novel_path}")

    if chapters_output_dir.exists() and force:
        for child in chapters_output_dir.iterdir():
            if child.is_file():
                child.unlink()
            else:
                for nested in child.rglob("*"):
                    if nested.is_file():
                        nested.unlink()
                for nested_dir in sorted(child.rglob("*"), reverse=True):
                    if nested_dir.is_dir():
                        nested_dir.rmdir()
                child.rmdir()

    text, encoding = detect_and_read_text(novel_path)
    text = normalize_text(text)
    chapters = split_into_chapters(text)
    write_outputs(chapters, novel_path, chapters_output_dir, encoding)

    print(f"Chapter split complete for project: {project_name}")
    print(f"Detected encoding: {encoding}")
    print(f"Chapters: {len(chapters)}")
    print("Check these outputs before building samples:")
    print(f"  - {chapters_output_dir / 'chapters.json'}")
    print(f"  - {chapters_output_dir / 'chapters'}")
    print("Then run:")
    print(f"  python backend/scripts/novel_dataset_pipeline.py build-samples {project_name}")


def build_project_samples(project_name: str, projects_root: Path, recent_summary_window: int, force: bool) -> None:
    project_dir = projects_root / project_name
    if not project_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_dir}")

    blueprint_path = project_dir / BLUEPRINT_FILE_NAME
    outputs_dir = project_dir / "outputs"
    chapters_output_dir = outputs_dir / "chapters"
    author_output_dir = outputs_dir / "author_training_samples"

    if not blueprint_path.exists() or not blueprint_path.read_text(encoding="utf-8", errors="ignore").strip():
        raise FileNotFoundError(f"Blueprint file is missing or empty: {blueprint_path}")

    chapters_json_path = chapters_output_dir / "chapters.json"
    if not chapters_json_path.exists():
        raise FileNotFoundError(
            f"Chapters file not found: {chapters_json_path}. Run split-chapters first."
        )

    chapter_infos = load_chapters(chapters_json_path)
    builder = AuthorTrainingSampleBuilder(
        chapters=chapter_infos,
        output_dir=author_output_dir,
        recent_summary_window=recent_summary_window,
        blueprint_txt_path=blueprint_path,
    )
    builder.run(force=force)

    print(f"Sample build complete for project: {project_name}")
    print(f"Chapters: {len(chapter_infos)}")
    print("Outputs:")
    print(f"  - {author_output_dir / 'book_blueprint.json'}")
    print(f"  - {author_output_dir / 'chapter_training_samples.jsonl'}")
    print(f"  - {author_output_dir / 'planning_training_samples.jsonl'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Novel dataset pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-project", help="Create a new novel dataset project scaffold.")
    create_parser.add_argument("project_name", help="Project directory name.")
    create_parser.add_argument(
        "--projects-root",
        default=str(PROJECTS_ROOT),
        help="Root directory for all dataset projects.",
    )

    split_parser = subparsers.add_parser("split-chapters", help="Split novel.txt into chapter outputs.")
    split_parser.add_argument("project_name", help="Project directory name.")
    split_parser.add_argument(
        "--projects-root",
        default=str(PROJECTS_ROOT),
        help="Root directory for all dataset projects.",
    )
    split_parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild chapter outputs even if they already exist.",
    )

    build_parser = subparsers.add_parser("build-samples", help="Build training samples after chapter verification.")
    build_parser.add_argument("project_name", help="Project directory name.")
    build_parser.add_argument(
        "--projects-root",
        default=str(PROJECTS_ROOT),
        help="Root directory for all dataset projects.",
    )
    build_parser.add_argument(
        "--recent-summary-window",
        type=int,
        default=3,
        help="How many recent chapter summaries to include in chapter input reconstruction.",
    )
    build_parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild outputs even if cached files already exist.",
    )

    args = parser.parse_args()
    projects_root = Path(args.projects_root).resolve()
    projects_root.mkdir(parents=True, exist_ok=True)

    if args.command == "create-project":
        create_project(args.project_name, projects_root)
        return

    if args.command == "split-chapters":
        split_project_chapters(
            project_name=args.project_name,
            projects_root=projects_root,
            force=args.force,
        )
        return

    if args.command == "build-samples":
        build_project_samples(
            project_name=args.project_name,
            projects_root=projects_root,
            recent_summary_window=args.recent_summary_window,
            force=args.force,
        )
        return


if __name__ == "__main__":
    main()
