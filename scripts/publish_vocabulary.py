#!/usr/bin/env python3
"""Publish verified vocabulary assets, then atomically advance the Raw manifest.

Only the Actions entry point writes remotely. Each attempt uses a temporary Git
worktree; the caller's files and uncommitted edits are never reset or staged.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import build_vocabulary as wire
from incremental_vocabulary import prepare_incremental_release


class CommandError(RuntimeError):
    pass


def command(arguments, cwd, input_text=None):
    result = subprocess.run(arguments, cwd=cwd, input=input_text, text=True, capture_output=True)
    if result.returncode:
        raise CommandError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


class Releases:
    def __init__(self, repository, cwd, run=command):
        self.repository, self.cwd, self.run = repository, cwd, run

    def get(self, tag):
        try:
            return json.loads(self.run(["gh", "api", f"repos/{self.repository}/releases/tags/{tag}"], self.cwd))
        except CommandError as error:
            if "HTTP 404" in str(error):
                # The tag endpoint omits drafts. Authenticated listing includes
                # them, which lets a later Actions run resume an interrupted upload.
                pages = json.loads(self.run(["gh", "api", f"repos/{self.repository}/releases?per_page=100",
                                             "--paginate", "--slurp"], self.cwd))
                matches = [release for page in pages for release in page if release["tag_name"] == tag]
                if len(matches) > 1:
                    raise ValueError(f"{tag} 存在多个草稿，请保留一份发布记录")
                return matches[0] if matches else None
            raise

    def api(self, endpoint, method, payload):
        return json.loads(self.run(["gh", "api", endpoint, "--method", method, "--input", "-"],
                                   self.cwd, json.dumps(payload, ensure_ascii=False)))

    def matches(self, release, output, manifest):
        names = ("manifest.json", Path(manifest["catalog"]["path"]).name, "terms.txt")
        listed = {asset["name"] for asset in release["assets"]}
        if not set(names) <= listed:
            return False
        with tempfile.TemporaryDirectory(prefix="force-vocab-verify-") as temporary:
            for name in names:
                self.run(["gh", "release", "download", release["tag_name"], "--repo", self.repository,
                          "--pattern", name, "--dir", temporary], self.cwd)
                local = output / (manifest["catalog"]["path"] if name.endswith(".json") and name != "manifest.json" else name)
                if (Path(temporary) / name).read_bytes() != local.read_bytes():
                    return False
        return True

    def publish(self, tag, existing, output, manifest, body, commit):
        if existing is not None and not existing["draft"]:
            if not self.matches(existing, output, manifest):
                raise ValueError(f"已发布的 {tag} 内容不同，不能覆盖")
            return
        metadata = {"name": f"词库 v{manifest['contentVersion']}", "body": body,
                    "draft": True, "prerelease": False, "make_latest": "false", "target_commitish": commit}
        if existing is None:
            release = self.api(f"repos/{self.repository}/releases", "POST", {"tag_name": tag, **metadata})
        else:
            release = self.api(f"repos/{self.repository}/releases/{existing['id']}", "PATCH", metadata)
        self.run(["gh", "release", "upload", tag, str(output / "manifest.json"),
                  str(output / manifest["catalog"]["path"]), str(output / "terms.txt"),
                  "--repo", self.repository, "--clobber"], self.cwd)
        release = json.loads(self.run(["gh", "api", f"repos/{self.repository}/releases/{release['id']}"], self.cwd))
        if not self.matches(release, output, manifest):
            raise ValueError(f"{tag} 的上传文件未通过回读校验；保留旧更新清单")
        self.api(f"repos/{self.repository}/releases/{release['id']}", "PATCH",
                 {"draft": False, "make_latest": "false"})


def release_notes(report, catalog, commit):
    words = {entry["id"]: entry["term"] for entry in catalog["entries"]}
    added = "、".join(words[entry_id] for entry_id in report["added"])
    return (f"新增或恢复 {len(report['added'])} 个词条，修改 {len(report['updated'])} 个词条，"
            f"归档 {len(report['archived'])} 个词条；当前共 {report['entryCount']} 个词条。\n\n"
            + (f"新增或恢复：{added}\n\n" if added else "")
            + f"源提交：{commit}\n\n完整 JSON、SHA-256 更新清单与主词索引见附件。")


def publish_repository(root, repository, run=command, release_factory=Releases):
    root = Path(root).resolve()
    for attempt in range(3):
        run(["git", "fetch", "origin", "main"], root)
        commit = run(["git", "rev-parse", "origin/main"], root).strip()
        with tempfile.TemporaryDirectory(prefix="force-vocab-publish-") as temporary:
            temporary = Path(temporary)
            checkout, output = temporary / "checkout", temporary / "output"
            run(["git", "worktree", "add", "--detach", str(checkout), commit], root)
            try:
                releases = release_factory(repository, checkout, run)
                minimum_version = 1
                for reservation in range(30):
                    report = prepare_incremental_release(checkout, output, minimum_version)
                    manifest = json.loads((output / "manifest.json").read_text())
                    tag = f"vocab-v{manifest['contentVersion']}"
                    existing = releases.get(tag)
                    if report["changed"] and existing is not None and not existing["draft"] and not releases.matches(existing, output, manifest):
                        # A previous run published assets but lost a race advancing main.
                        # Keep that release immutable, and use the next free version.
                        minimum_version = manifest["contentVersion"] + 1
                        continue
                    break
                else:
                    raise ValueError("连续 30 个版本已被其他内容占用，请检查发布历史")
                if report["changed"] or existing is not None:
                    catalog = json.loads((output / manifest["catalog"]["path"]).read_text())
                    releases.publish(tag, existing, output, manifest, release_notes(report, catalog, commit), commit)
                paths = ["terms.txt"]
                if report["changed"]:
                    paths += [manifest["catalog"]["path"], "manifest.json"]
                for relative in paths:
                    source, target = output / relative, checkout / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if relative.startswith("releases/") and target.exists() and target.read_bytes() != source.read_bytes():
                        raise ValueError(f"不能覆盖已发布快照：{relative}")
                    shutil.copyfile(source, target)
                run(["git", "add", "--", *paths], checkout)
                if run(["git", "diff", "--cached", "--name-only"], checkout).strip():
                    run(["git", "-c", "user.name=github-actions[bot]",
                         "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                         "commit", "-m", f"Publish vocabulary v{manifest['contentVersion']}"], checkout)
                    try:
                        run(["git", "push", "origin", "HEAD:main"], checkout)
                    except CommandError as error:
                        if attempt < 2 and any(message in str(error) for message in ("non-fast-forward", "fetch first", "[rejected]")):
                            continue
                        raise
                return report
            finally:
                run(["git", "worktree", "remove", "--force", str(checkout)], root)
    raise ValueError("main 持续更新，未切换更新清单；请重新运行发布")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=wire.ROOT)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" or not args.repository:
        parser.error("该命令仅在 GitHub Actions 中发布；本地请运行 build_vocabulary.py --check 或生成本地发布包")
    try:
        report = publish_repository(args.source_root, args.repository)
        print(wire.json_text(report), end="")
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a", encoding="utf-8") as stream:
                stream.write(f"词库 v{report['contentVersion']}：{report['entryCount']} 个词条；新增/恢复 {len(report['added'])}，修改 {len(report['updated'])}，归档 {len(report['archived'])}。\n")
    except (ValueError, OSError, CommandError) as error:
        parser.exit(1, f"发布失败：{error}\n")


if __name__ == "__main__":
    main()
