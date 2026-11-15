#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_teardown.py — 建出拆解教程的目录骨架（只建目录，不建空占位文件）。

做的事:
  * 建交付目录：00-项目综述 / 01-整体架构 / 02-技术栈 / 03-具体实现 / 04-面试与简历
  * 建 03-具体实现/00-项目准备/
  * 建 assets/ 并按章节一一镜像出子目录（图跟着章节走，找图不用翻扁平列表）
  * 建 .work/ 阶段工作区（中间产物，不交付、不进 README、审计会跳过）
  * 可选 --steps 一次建好 03-具体实现/NN-<能力主题>/ 与对应 assets 子目录

用法:
    python scaffold_teardown.py "知识库问答-拆解教程"
    python scaffold_teardown.py ./my-proj-拆解教程 --steps "工程可维护性,混合检索"
退出码 0。只依赖标准库。
"""
import argparse
import os
import re
import sys

TOP_DIRS = ["00-项目综述", "01-整体架构", "02-技术栈", "04-面试与简历"]
PREP_DIR = os.path.join("03-具体实现", "00-项目准备")
WORK_SUBDIRS = ["01-map", "02-arch", "03-deepdive", "freeze",
                "05-authoring", "06-review"]


def resolve_target(arg):
    """A bare name becomes <cwd>/<name>-拆解教程; anything path-like is used as-is."""
    looks_like_path = os.path.isabs(arg) or "/" in arg or "\\" in arg or arg.endswith("/")
    if looks_like_path:
        return os.path.abspath(arg)
    return os.path.abspath(arg if arg.endswith("-拆解教程") else arg + "-拆解教程")


def normalize_steps(raw):
    if not raw:
        return []
    steps = [s.strip().replace("/", "-").replace("\\", "-") for s in raw.split(",") if s.strip()]
    out, used = [], 0
    for s in steps:
        if re.match(r"^\d{1,3}-", s):
            out.append(s)
            used = max(used, int(re.match(r"^(\d+)", s).group(1)))
        else:
            used += 1
            out.append("%02d-%s" % (used, s))
    return out


def main():
    parser = argparse.ArgumentParser(description="拆解教程目录骨架")
    parser.add_argument("target", help="教程目录，或项目名（会自动补 -拆解教程）")
    parser.add_argument("--steps", default="", help="能力主题名，逗号分隔，如 \"工程可维护性,混合检索\"")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    root = resolve_target(args.target)
    steps = normalize_steps(args.steps)

    chapter_dirs = list(TOP_DIRS)
    chapter_dirs.insert(3, "03-具体实现")
    step_dirs = [os.path.join("03-具体实现", s) for s in steps]

    wanted = [root]
    wanted += [os.path.join(root, d) for d in chapter_dirs]
    wanted += [os.path.join(root, PREP_DIR)]
    wanted += [os.path.join(root, s) for s in step_dirs]
    wanted += [os.path.join(root, ".work")] + [os.path.join(root, ".work", d) for d in WORK_SUBDIRS]

    # assets mirrors chapters (and steps), same names, no numbering prefixes added
    asset_mirrors = chapter_dirs + [PREP_DIR] + step_dirs
    wanted += [os.path.join(root, "assets")] + [os.path.join(root, "assets", d) for d in asset_mirrors]

    created = []
    for d in wanted:
        if args.dry_run:
            print("会建:", os.path.relpath(d, root).replace("\\", "/") if d != root else root)
            continue
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
            created.append(d)

    if args.dry_run:
        return 0

    def rel(p):
        return os.path.relpath(p, root).replace("\\", "/") if p != root else "."

    print("教程目录: %s" % root)
    print("新建目录: %d 个" % len(created))
    for d in created:
        print("  + " + rel(d))

    print("\n目录骨架:")
    print(root.replace("\\", "/"))
    for d in chapter_dirs:
        print("   " + d + "/")
        if d == "03-具体实现":
            print("     00-项目准备/   01-外部服务.md / 02-搭建骨架.md")
            for s in steps:
                print("     " + s + "/   00-来龙去脉.md / 01-亮点难点.md / 02-功能流程与架构.md / 03-具体实现.md")
    print("   assets/<与章节同名的子目录>/")
    print("   .work/  （中间产物，不交付）")

    if not steps:
        print("\n提示: 能力主题还不确定时，实现目录可在 Phase 5 由主笔定稿后再补建；")
        print("      也可跑 --steps 一次建好，例如 --steps \"工程可维护性,混合检索\"")
    print("\n下一步: Phase 1 —— 派 senior-engineer 产出 .work/01-map/codemap.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
