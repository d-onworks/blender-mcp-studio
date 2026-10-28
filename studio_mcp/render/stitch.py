# -*- coding: utf-8 -*-
"""두 기계가 나눠 그린 PNG 를 한 영상으로 — ffmpeg.

프레임은 이름이 이어져 있으니(f_0000.png …) 같은 폴더에 모은 뒤 image2 로 한 번에 묶는다.
빠진 장이 있으면 영상 길이가 틀어지므로 기본은 멈춘다(--allow-missing 이면 앞 장을 복사해 메움).
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_frames(folder: Path, prefix: str):
    nums = []
    for p in folder.glob(f"{prefix}*.png"):
        tail = p.stem[len(prefix):]
        if tail.isdigit():
            nums.append(int(tail))
    return sorted(nums)


def stitch(folder, output, fps=24, prefix="f_", crf=16, codec="libx264", pix_fmt="yuv420p",
           audio=None, allow_missing=False, dry_run=False):
    folder, output = Path(folder), Path(output)
    nums = find_frames(folder, prefix)
    if not nums:
        sys.exit(f"[중단] {folder} 에 {prefix}####.png 가 없다")
    gaps = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums))
    if gaps and not allow_missing:
        sys.exit(f"[중단] 빠진 장 {len(gaps)}개: {gaps[:12]} — 다시 렌더하거나 --allow-missing")
    src_dir, tmp = folder, None
    if gaps:
        tmp = tempfile.mkdtemp(prefix="stitch_")
        src_dir = Path(tmp)
        last = None
        for f in range(nums[0], nums[-1] + 1):
            p = folder / f"{prefix}{f:04d}.png"
            last = p if p.exists() else last
            (src_dir / f"{prefix}{f:04d}.png").symlink_to(last.resolve())
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(fps),
           "-start_number", str(nums[0]), "-i", str(src_dir / f"{prefix}%04d.png")]
    if audio:
        cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "256k", "-shortest"]
    cmd += ["-c:v", codec, "-crf", str(crf), "-pix_fmt", pix_fmt, "-movflags", "+faststart", str(output)]
    print(f"[이어붙이기] {nums[0]}-{nums[-1]} ({nums[-1] - nums[0] + 1}장, {fps}fps"
          + (f", 메운 장 {len(gaps)}" if gaps else "") + f") → {output}")
    print("  " + " ".join(cmd))
    if dry_run:
        return cmd
    if not shutil.which("ffmpeg"):
        sys.exit("[중단] ffmpeg 가 없다")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return cmd
