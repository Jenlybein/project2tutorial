#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_teardown.py — 拆解教程交付物的机械审计。

两层检查：

**文件系统层**：断链、配图引用是否可达、图是否落在与章节同名的 assets 子目录、
alt 是否说清了内容、SVG 是否合法、全篇有无 Mermaid / 字符画 / 正文里的 SVG 源码、
README 导航是否覆盖每个文件、有没有孤立或空置的配图目录。

**文本层**（专治"看起来完整"）：唯一 H1、标题层级跳跃、附录倒置、自链接、
全角括号配对、单篇行数超限、跨文件重复代码块/表格、冻结词表 `_Avoid_` 命中、
中文夹多余空格、步骤编号断档。

用法:
    python audit_teardown.py "<教程目录>" [--json] [--no-readme-check]
                             [--glossary .work/28-authoring/glossary.md]
                             [--max-lines 600] [--max-lines-hard 900]

退出码: 有 error 时返回 1，否则 0。warn 不改变退出码。
只依赖标准库。
"""
import argparse
import hashlib
import json
import os
import re
import sys

SKIP_DIRS = {".work", ".git", "node_modules", ".obsidian"}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
H2_CN_NUM_RE = re.compile(r"^##\s*[一二三四五六七八九十]+、")
CJK = "\u4e00-\u9fa5"
CJK_SPACE_RE = re.compile(r"[%s][ \t]+[%s]" % (CJK, CJK))
STEP_RE = re.compile(r"^#{2,4}\s*步骤\s*(\d+)")
APPENDIX_H2_RE = re.compile(r"^##\s*(附|[一二三四五六七八九十]+、)")

IMG_RE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?\s*(?:\"[^\"]*\"|\'[^\']*\')?\s*\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(\s*<?([^)\s>]+)>?\s*(?:\"[^\"]*\"|\'[^\']*\')?\s*\)")
HTML_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
HTML_SRC_RE = re.compile(r'\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)
HTML_ALT_RE = re.compile(r'\balt\s*=\s*["\']([^"\']*)["\']', re.I)

BOX_CHARS = "├┌┐└┘┬┴┼┤┫┣━┃╔╗╚╝║═╠╣╦╩╬┏┓┗┛┳┻"
GENERIC_ALTS = {"图", "图1", "图一", "架构图", "示意图", "流程图", "配图", "image", "img", "pic"}
IMAGE_EXTS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}


def norm_target(target):
    t = target.strip().replace("\\", "/")
    if t.startswith("<") and t.endswith(">"):
        t = t[1:-1]
    t = t.split("#", 1)[0].split("?", 1)[0]
    return t


def is_remote(t):
    return t.lower().startswith(("http://", "https://", "mailto:", "data:", "ftp://"))


class Audit:
    def __init__(self, root, glossary=None, max_lines=600, max_lines_hard=900,
             profile="tutorial"):
        self.root = os.path.abspath(root)
        self.findings = []
        self.md_files = []
        self.asset_files = []
        self.asset_dirs = []
        self.refs_from_md = {}
        self.images_referenced = set()
        self.max_lines = max_lines
        self.max_lines_hard = max_lines_hard
        self.profile = profile
        self.glossary_path = glossary
        self.avoid_terms = self.load_glossary(glossary)
        # 跨文件重复检测：(kind, fingerprint) -> [(relpath, line), ...]
        self.blocks = {}

    def add(self, level, code, path, line, message):
        self.findings.append({
            "level": level, "code": code,
            "file": os.path.relpath(path, self.root).replace("\\", "/") if path else "",
            "line": line, "message": message,
        })

    # ---------------------------------------------------------------- inventory
    def walk(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIRS]
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                low = name.lower()
                if low.endswith(".md"):
                    self.md_files.append(full)
                elif os.path.splitext(low)[1] in IMAGE_EXTS and not low.endswith(".md"):
                    self.asset_files.append(full)
        for dirpath, dirnames, _ in os.walk(os.path.join(self.root, "assets")):
            dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIRS]
            self.asset_dirs.append(dirpath)

    # ------------------------------------------------------------------- helpers
    def chapter_key(self, md_path):
        """Return the tutorial-relative directory that owns this md file."""
        rel = os.path.relpath(md_path, self.root).replace("\\", "/")
        parts = rel.split("/")[:-1]
        return "/".join(parts)

    def resolve(self, md_path, target):
        base = os.path.dirname(md_path)
        return os.path.normpath(os.path.join(base, target))

    # ------------------------------------------------------------ text-level checks
    def load_glossary(self, path):
        """从 glossary.md 抽出 `_Avoid_` 词 → 正名 的映射。"""
        avoid = {}
        if not path or not os.path.exists(path):
            return avoid
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return avoid
        current = None
        for raw in text.splitlines():
            line = raw.strip()
            m = re.match(r"^\*\*(.+?)\*\*\s*[:：]?\s*$", line)
            if m:
                current = m.group(1).strip()
                continue
            m = re.match(r"^_Avoid_\s*[:：]\s*(.+)$", line)
            if m and current:
                for word in re.split(r"[,，、]", m.group(1)):
                    w = word.strip().strip("`").strip()
                    if w and len(w) >= 2:
                        avoid[w] = current
        return avoid

    def prose_lines(self, lines):
        """返回代码围栏之外的行 [(行号, 文本)]。

        markdown 正文里的 `# 标题` 与 Python 注释 `# app/xxx.py` 长得一样，
        不做围栏过滤会把代码注释当成 H1/H3，产生大量假阳性。
        """
        out, in_fence = [], False
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if s.startswith("```") or s.startswith("~~~"):
                in_fence = not in_fence
                continue
            if not in_fence:
                out.append((i, ln))
        return out

    def check_headings(self, path, prose):
        headings = []
        for i, ln in prose:
            m = HEADING_RE.match(ln)
            if m:
                headings.append((i, len(m.group(1)), m.group(2).strip()))
        if not headings:
            self.add("error", "no-heading", path, 0, "全文没有任何标题")
            return
        h1 = [h for h in headings if h[1] == 1]
        if not h1:
            self.add("error", "h1-missing", path, 0, "缺少 H1：每篇必须恰好一个 H1")
        elif len(h1) > 1:
            self.add("error", "h1-multiple", path, h1[1][0],
                     "出现 %d 个 H1（%s）：每篇只允许一个"
                     % (len(h1), "、".join(h[2] for h in h1)))

        prev = None
        for line_no, level, title in headings:
            if prev and level - prev[1] > 1:
                self.add("error", "heading-jump", path, line_no,
                         "标题层级跳跃：H%d「%s」之后直接是 H%d「%s」，应逐级下降"
                         % (prev[1], prev[2], level, title))
            prev = (line_no, level, title)

        seen = {}
        for line_no, level, title in headings:
            key = (level, title)
            if key in seen:
                self.add("warn", "heading-dup", path, line_no,
                         "同名同级标题重复：「%s」（L%d 已出现过）" % (title, seen[key]))
            else:
                seen[key] = line_no

        for idx in range(len(headings) - 1):
            a, b = headings[idx], headings[idx + 1]
            if a[1] == 3 and b[1] == 2 and ("附" in a[2] or "提示词" in a[2]):
                if H2_CN_NUM_RE.match("## " + b[2]) or b[2].startswith("附"):
                    self.add("error", "heading-inversion", path, b[0],
                             "附录倒置：H3「%s」下面挂编号式 H2「%s」。附件条目应为 H3/H4"
                             % (a[2], b[2]))

        numbered = [h for h in headings if h[1] == 2 and H2_CN_NUM_RE.match("## " + h[2])]
        appendix = [h for h in headings if h[1] == 2 and h[2].startswith("附")]
        if numbered and appendix:
            self.add("warn", "heading-cn-num", path, numbered[0][0],
                     "同篇并存两种附录风格：编号式 H2「%s」与「%s」。统一成一种（建议「附一 / 附二」）"
                     % (numbered[0][2], appendix[0][2]))
        elif numbered and not appendix:
            self.add("warn", "heading-cn-num", path, numbered[0][0],
                     "编号式 H2「%s」等 %d 处：若这些是从原素材拼进来的附件条目，统一改成「附一 / 附二」"
                     % (numbered[0][2], len(numbered)))

        steps = []
        for i, ln in prose:
            m = STEP_RE.match(ln)
            if m:
                steps.append((i, int(m.group(1))))
        if len(steps) >= 3:
            nums = [n for _, n in steps]
            expect = list(range(nums[0], nums[0] + len(nums)))
            if nums != expect:
                self.add("warn", "step-numbering", path, steps[0][0],
                         "步骤编号不连续或重复：%s（按顺序应为 %s）" % (nums, expect))

    def check_brackets(self, path, prose):
        open_n = close_n = 0
        for _i, ln in prose:
            # 把「1）」「**2）」「一）」这类列表序号标记剥掉，它是合法用法不是未闭合
            s = re.sub(r"^\s*(?:\*\*)?(?:\d+|[一二三四五六七八九十]+)\s*）", "", ln)
            s = re.sub(r"\*\*\s*(?:\d+|[一二三四五六七八九十]+)\s*）", "**", s)
            open_n += s.count("（")
            close_n += s.count("）")
        if open_n != close_n:
            self.add("error", "bracket-unbalanced", path, 0,
                     "正文全角括号不成对：「（」×%d，「）」×%d。批量替换最容易在这里出事"
                     % (open_n, close_n))

    def check_size(self, path, lines):
        n = len(lines)
        if n > self.max_lines_hard:
            self.add("error", "file-too-long", path, 0,
                     "单篇 %d 行，超过硬上限 %d：必须拆文件（按步骤或主题拆 2–3 篇）"
                     % (n, self.max_lines_hard))
        elif n > self.max_lines:
            self.add("warn", "file-long", path, 0,
                     "单篇 %d 行，超过建议上限 %d：至少补一张「本章怎么读」导航表"
                     % (n, self.max_lines))

    def check_terms(self, path, prose):
        if not self.avoid_terms:
            return
        # 纯 ASCII 词（chunk / Evidence Pack / app_id）要按词边界匹配，
        # 否则 `chunks` 表、`chunk_id` 这类标识符会被误判成避用词
        compiled = []
        for word, canonical in self.avoid_terms.items():
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9 _\-]*", word):
                rx = re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])"
                                % re.escape(word), re.I)
            else:
                rx = re.compile(re.escape(word))
            compiled.append((word, canonical, rx))
        for i, ln in prose:
            stripped = ln.strip()
            if stripped.startswith("    ") or stripped.startswith("_Avoid_"):
                continue
            scan = re.sub(r"`[^`]*`", "", ln)      # 行内代码里的标识符不算
            for word, canonical, rx in compiled:
                if rx.search(scan):
                    self.add("error", "avoid-term", path, i,
                             "用了冻结词表的避用词「%s」，应写作「%s」" % (word, canonical))
                    break

    def check_cjk_space(self, path, prose):
        hits, first = 0, 0
        # 「第 7 步 观测与评测」「第 3 章 多租户」这类编号分隔是合法写法，不算伤口
        skip_before = set("步章节条款项式页档阶段")
        for i, ln in prose:
            # 行内代码替换成占位符而不是删掉——直接删会把两侧空格挤到一起，造成假阳性
            scan = re.sub(r"`[^`]*`", "X", ln)
            for m in CJK_SPACE_RE.finditer(scan):
                if m.group(0)[0] in skip_before:
                    continue
                if hits == 0:
                    first = i
                hits += 1
        if hits:
            self.add("warn", "cjk-space", path, first,
                     "中文之间出现多余空格（共 %d 处）：机械替换的典型伤口，"
                     "如「一个 切片 到底」应写作「一个切片到底」" % hits)

    def collect_blocks(self, path, lines):
        rel = os.path.relpath(path, self.root).replace("\\", "/")
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith("```"):
                start = i + 1
                j = start
                while j < len(lines) and not lines[j].strip().startswith("```"):
                    j += 1
                body = "\n".join(lines[start:j])
                if body.count("\n") >= 2 and len(body.strip()) >= 80:
                    self.register_block("code", body, rel, i + 1)
                i = j + 1
                continue
            i += 1
        i = 0
        while i < len(lines):
            if lines[i].lstrip().startswith("|") and i + 1 < len(lines) \
                    and re.match(r"^\s*\|[\s:\-|]+\|\s*$", lines[i + 1]):
                start = i
                j = i
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    j += 1
                if j - start >= 3:
                    self.register_block("table", "\n".join(lines[start:j]), rel, start + 1)
                i = j
                continue
            i += 1

    def register_block(self, kind, body, rel, line):
        normalized = re.sub(r"\s+", " ", body).strip()
        fp = hashlib.sha1(("%s|%s" % (kind, normalized)).encode("utf-8")).hexdigest()
        self.blocks.setdefault((kind, fp), []).append((rel, line))

    def report_duplicates(self):
        for (kind, _fp), places in self.blocks.items():
            if len(places) < 2:
                continue
            if len({p[0] for p in places}) < 2:
                continue
            head = places[0]
            others = "、".join("%s:%d" % (p[0], p[1]) for p in places[1:])
            self.add("warn", "duplicate-block", os.path.join(self.root, head[0]), head[1],
                     "%s重复出现在多个文件（另有 %s）：按 ownership.md 只留一个 owner，其余改成指路"
                     % ("代码块" if kind == "code" else "表格", others))

    # --------------------------------------------------------------------- checks
    def check_md(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except UnicodeDecodeError:
            self.add("error", "encoding", path, 0, "文件不是 UTF-8，中文文档请统一用 UTF-8 保存")
            return
        rel = os.path.relpath(path, self.root).replace("\\", "/")
        lines = text.splitlines()
        self.refs_from_md[path] = rel

        chapter = self.chapter_key(path)

        # --- images
        # profile=skill 时只记录引用（不校验）：skill 的说明文里会出现 ![]() 模板示例，
        # 那是"教怎么引用图"，不是"交付物里贴图"。
        for m in IMG_RE.finditer(text):
            alt, target = m.group(1).strip(), norm_target(m.group(2))
            line_no = text[:m.start()].count("\n") + 1
            if target:
                self.images_referenced.add(os.path.normpath(os.path.join(os.path.dirname(path), target)))
            if self.profile != "skill":
                self.check_image_ref(path, line_no, alt, target, chapter)

        for m in HTML_IMG_RE.finditer(text):
            raw = m.group(0)
            line_no = text[:m.start()].count("\n") + 1
            src_m = HTML_SRC_RE.search(raw)
            alt_m = HTML_ALT_RE.search(raw)
            alt = (alt_m.group(1) if alt_m else "").strip()
            if src_m and self.profile != "skill":
                self.check_image_ref(path, line_no, alt, norm_target(src_m.group(1)), chapter)

        # --- links (image syntax also matches LINK_RE, so blank out images first;
        #     keep newlines so line numbers stay correct)
        def mask_image(m):
            return "!" + "".join("\n" if ch == "\n" else " " for ch in m.group(0)[1:])

        for m in LINK_RE.finditer(IMG_RE.sub(mask_image, text)):
            label, target = m.group(1).strip(), norm_target(m.group(2))
            if not target or is_remote(target):
                continue
            line_no = text[:m.start()].count("\n") + 1
            if "/" not in target and target == os.path.basename(path):
                self.add("error", "self-link", path, line_no,
                         "链接指向本篇自己（%s）：三件套导航应写「本篇（你在这里）」，不要做成链接" % target)
                continue
            full = self.resolve(path, target)
            if not os.path.exists(full):
                self.add("error", "broken-link", path, line_no,
                         "链接目标不存在: %s（相对路径或 ../ 层数写错了）" % target)

        # --- mermaid
        for i, ln in enumerate(lines, 1):
            if ln.strip().lower().startswith("```mermaid") or ln.strip().lower() == "``` mermaid":
                self.add("error", "mermaid", path, i, "出现了 Mermaid 代码块：本工坊禁用 Mermaid，图只能手写 SVG 文件")

        # --- svg source pasted into the body
        # profile=skill 时跳过：skill 文档里有大量"怎么手写 SVG"的示范源码
        if self.profile != "skill":
            for i, ln in enumerate(lines, 1):
                if "<svg" in ln.lower():
                    self.add("error", "svg-inline", path, i,
                             "正文里出现了 SVG 源码：图必须是 .svg 文件 + 相对路径引用，不能贴在正文代码块里")

        # --- ascii art (warn: a pure directory listing is legitimate)
        for i, ln in enumerate(lines, 1):
            if any(ch in ln for ch in BOX_CHARS) or "-->" in ln or "===>" in ln or ln.count("|--") > 0:
                self.add("warn", "charart", path, i,
                         "疑似字符画/目录树：仅当它是纯目录清单时可接受；若在表达模块关系或流程，必须换成 SVG")
                break

        # --- AI figure labelling
        if ".png" in text.lower() or ".jpg" in text.lower() or ".webp" in text.lower():
            if "示意图" not in text:
                self.add("warn", "ai-label", path, 0,
                         "本篇引用了 PNG/JPG 配图，但全文没有出现「示意图」标注；若其中含 AI 生图，必须标注「示意图，非真实界面 / 非真实数据」")

        # --- text-level checks（结构 / 术语 / 体量 / 重复）
        prose = self.prose_lines(lines)
        self.check_headings(path, prose)
        self.check_brackets(path, prose)
        self.check_size(path, lines)
        self.check_terms(path, prose)
        self.check_cjk_space(path, prose)
        self.collect_blocks(path, lines)

    def check_image_ref(self, path, line_no, alt, target, chapter):
        if not target:
            self.add("error", "image-empty", path, line_no, "图片引用没有路径")
            return
        if is_remote(target):
            return
        if not alt:
            self.add("error", "alt-missing", path, line_no,
                     "图片缺少 alt：%s（alt 要写清这张图说明了什么）" % target)
        elif len(alt) < 4 or alt.strip().lower() in GENERIC_ALTS:
            self.add("warn", "alt-generic", path, line_no,
                     "alt 过于笼统（%r）：写成「请求从网关进入后经过三跳落到检索表」这类说明" % alt)

        full = self.resolve(path, target)
        if not os.path.exists(full):
            self.add("error", "image-missing", path, line_no,
                     "配图文件不存在: %s（../ 层数按「引用文件相对教程根目录的层数」数一遍）" % target)
            return
        rel_img = os.path.relpath(full, self.root).replace("\\", "/")
        # 两种落盘形态都接受：全局 assets/<章节>/ 或 章节内 <章节>/assets/
        in_global_assets = rel_img.startswith("assets/")
        chapter_prefix = (chapter + "/assets/") if chapter else None
        in_chapter_assets = bool(chapter_prefix) and rel_img.startswith(chapter_prefix)
        if not (in_global_assets or in_chapter_assets):
            self.add("error", "image-location", path, line_no,
                     "配图既不在 assets/ 下、也不在本章 assets/ 下: %s" % rel_img)
            return
        if in_global_assets:
            expected = ("assets/" + chapter) if chapter else "assets"
            img_parts = rel_img.split("/")
            exp_parts = expected.split("/")
            if img_parts[:len(exp_parts)] != exp_parts:
                self.add("warn", "image-wrong-chapter", path, line_no,
                         "配图不在本章的 assets 子目录下: %s（有意跨章复用同一张图可接受；若是新图放错目录，按缺陷计）" % rel_img)

    def check_svg(self, path):
        rel = os.path.relpath(path, self.root).replace("\\", "/")
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except UnicodeDecodeError:
            self.add("error", "svg-encoding", path, 0, "SVG 不是 UTF-8")
            return
        low = text.lower()
        if "<svg" not in low:
            self.add("error", "svg-root", path, 0, "缺少 <svg> 根标签")
        if "xmlns" not in low:
            self.add("error", "svg-xmlns", path, 0, "缺少 xmlns 命名空间，浏览器可能不渲染")
        if "viewbox" not in low:
            self.add("error", "svg-viewbox", path, 0, "缺少 viewBox：宽度自适应靠它，不要写死 width/height 像素")
        if re.search(r'<svg[^>]*\bwidth\s*=\s*["\']?\d', low):
            self.add("warn", "svg-fixed-width", path, 0, "SVG 写死了 width 像素值：改用 viewBox 自适应")
        if len(text.strip()) < 40:
            self.add("error", "svg-empty", path, 0, "SVG 内容近乎为空")

    def check_assets(self):
        if not self.asset_files and not any("assets" in p.replace("\\", "/") for p in self.md_files):
            return
        for path in self.asset_files:
            if path.lower().endswith(".svg"):
                self.check_svg(path)
            ref = os.path.normpath(path)
            if ref not in self.images_referenced:
                self.add("warn", "asset-orphan",
                         path, 0,
                         "配图没有被任何正文引用（孤立文件）：要么补引用，要么删掉，别让它白生成")
        # empty chapter dirs
        for d in self.asset_dirs:
            rel = os.path.relpath(d, self.root).replace("\\", "/")
            if rel == "assets":
                continue
            entries = [e for e in os.listdir(d) if not e.startswith(".")]
            if not entries:
                self.add("warn", "asset-dir-empty", d, 0,
                         "空的配图子目录：建了却一张图都没有，说明这一章的图漏产了")

    def check_readme(self, strict=False):
        readme = os.path.join(self.root, "README.md")
        if not os.path.exists(readme):
            self.add("error", "readme-missing", readme, 0,
                     "缺少 README.md 总索引（Phase 6 必产出：导航表要链到每一个文件）")
            return
        text = open(readme, encoding="utf-8", errors="replace").read()
        missing, folder_level = [], []
        for md in self.md_files:
            if os.path.abspath(md) == os.path.abspath(readme):
                continue
            rel = os.path.relpath(md, self.root).replace("\\", "/")
            if rel in text:
                continue
            folder = os.path.dirname(rel)
            # 目录级链接也算"能被读者顺着找到"：该目录路径在 README 里出现过
            if folder and (folder + "/") in text:
                folder_level.append(rel)
            else:
                missing.append(rel)
        if missing:
            self.add("error", "readme-coverage", readme, 0,
                     "README 导航既没链到这些文件、也没链到它们所在目录: " + "、".join(missing))
        if folder_level and strict:
            self.add("error", "readme-folder-level", readme, 0,
                     "README 只链到目录、没有链到这些文件（strict 模式不允许）: " + "、".join(folder_level))
        elif folder_level:
            self.add("warn", "readme-folder-level", readme, 0,
                     "README 只链到目录（%d 个文件靠目录链接间接可达）：如果章节内部有导航，可接受；"
                     "若读者需要从 README 直达每一篇，补全链接" % len(folder_level))

    # ---------------------------------------------------------------------- run
    def run(self, readme_check=True, readme_strict=False):
        if not os.path.isdir(self.root):
            raise SystemExit("目录不存在: %s" % self.root)
        if self.glossary_path and not os.path.exists(self.glossary_path):
            self.add("warn", "glossary-missing", self.root, 0,
                     "指定了词表但文件不存在：%s（Phase 2.8 没做，术语检查已跳过）"
                     % self.glossary_path)
        self.walk()
        if not self.md_files:
            raise SystemExit("目录里没有 Markdown 文件: %s" % self.root)
        for md in self.md_files:
            self.check_md(md)
        self.report_duplicates()
        self.check_assets()
        if readme_check:
            self.check_readme(strict=readme_strict)
        return self.findings


def main():
    parser = argparse.ArgumentParser(description="拆解教程交付物机械审计")
    parser.add_argument("root", help="教程目录，如 ./项目名-拆解教程")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--no-readme-check", action="store_true", help="跳过 README 导航覆盖检查")
    parser.add_argument("--glossary", default=None,
                        help="冻结词表路径（.work/28-authoring/glossary.md），给了才做术语避用词检查")
    parser.add_argument("--max-lines", type=int, default=600, help="单篇行数建议上限，默认 600")
    parser.add_argument("--max-lines-hard", type=int, default=900, help="单篇行数硬上限，默认 900")
    parser.add_argument("--readme-strict", action="store_true",
                        help="README 必须直接链到每一个文件；默认允许目录级链接（只报 warn）")
    parser.add_argument("--profile", choices=["tutorial", "skill"], default="tutorial",
                        help="tutorial（默认）＝检查教程交付物；skill＝检查 skill 说明仓库"
                             "（跳过 SVG 源码示例与图片模板示例这两类专属检查）")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    findings = Audit(args.root, glossary=args.glossary, profile=args.profile,
                     max_lines=args.max_lines,
                     max_lines_hard=args.max_lines_hard).run(
        readme_check=not args.no_readme_check,
        readme_strict=args.readme_strict)
    errors = [f for f in findings if f["level"] == "error"]
    warns = [f for f in findings if f["level"] == "warn"]

    if args.json:
        print(json.dumps({"root": args.root, "errors": errors, "warnings": warns,
                          "error_count": len(errors), "warning_count": len(warns)},
                         ensure_ascii=False, indent=2))
        return 1 if errors else 0

    def show(title, items):
        print("\n== %s (%d) ==" % (title, len(items)))
        for f in items:
            loc = "%s:%d" % (f["file"], f["line"]) if f["line"] else (f["file"] or "-")
            print(" [%s] %-18s %s" % (f["code"], loc, f["message"]))
        if not items:
            print(" 无")

    show("ERROR", errors)
    show("WARN", warns)
    print("\n结论: %d error, %d warn  →  %s" % (
        len(errors), len(warns), "未通过，先修 error" if errors else "机械检查通过（warn 需人眼确认）"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
