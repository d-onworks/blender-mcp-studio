"""`studio triposg …` — 이미지 → 3D 터미널 명령(MCP 도구 triposg_generate 와 같은 일).

  studio triposg config --mode local --python C:/triposg/python/python.exe \
        --triposg-src C:/triposg/src/TripoSG --weights C:/triposg/models/TripoSG --env HF_HOME=C:/triposg/models/hf
  studio triposg check                       # 설정·GPU 가 한가한지
  studio triposg generate frog.png --name frog_s1 --height-m 1.0
  studio triposg remote --config my_gpu.json --image frog.png --name frog_s1 --local-out out   # 받기만(블렌더 안 씀)

설정은 ~/.blender-mcp-studio/config.json 의 "triposg" 항목이다(docs/07_TripoSG.md 5절).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import config

KEYS = ("mode", "host", "shell", "remote_dir", "remote_python", "python", "triposg_src", "weights",
        "path_prepend", "busy_mb")


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def _add_conn(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", choices=["local", "remote"])
    p.add_argument("--host", help="원격 GPU PC 의 ssh 이름(~/.ssh/config 별칭 권장)")
    p.add_argument("--shell", choices=["powershell", "bash"], help="원격 셸(윈도우 = powershell)")
    p.add_argument("--remote-dir", help="원격 작업 폴더. 예: C:/triposg/out/demo")
    p.add_argument("--remote-python", help="원격 파이썬(TripoSG 의존성이 깔린 환경)")
    p.add_argument("--python", help="로컬 파이썬(TripoSG 의존성이 깔린 환경)")
    p.add_argument("--triposg-src", help="TripoSG 공식 저장소를 받은 폴더")
    p.add_argument("--weights", help="가중치 폴더 또는 VAST-AI/TripoSG")
    p.add_argument("--path-prepend", help="PATH 앞에 붙일 폴더(VC++ DLL 등)")
    p.add_argument("--env", action="append", help="환경변수 KEY=VALUE(여러 번). 예: HF_HOME=C:/triposg/models/hf")
    p.add_argument("--busy-mb", type=int, help="GPU 메모리가 이 값(MB)을 넘게 쓰이면 다른 작업 중으로 본다(기본 2500)")


def _conn_from(a) -> dict:
    d = {k: getattr(a, k) for k in KEYS if getattr(a, k, None) is not None}
    if getattr(a, "env", None):
        d["env"] = list(a.env)
    return d


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="studio triposg", description="그림 한 장 → TripoSG 3D 메시 → 블렌더")
    sub = ap.add_subparsers(dest="action", required=True)

    g = sub.add_parser("generate", help="생성하고 블렌더 장면에 넣기")
    g.add_argument("image")
    g.add_argument("--name")
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--depth", type=int, default=9, help="메시 격자 2^depth. 10GB GPU 는 9")
    g.add_argument("--steps", type=int, default=50)
    g.add_argument("--cfg", type=float, default=7.0)
    g.add_argument("--height-m", type=float, help="블렌더에서 맞출 키(미터)")
    g.add_argument("--keep-all", action="store_true", help="떠 있는 작은 조각도 남긴다")
    g.add_argument("--no-import", action="store_true", help="glb 만 만들고 블렌더에 넣지 않는다")
    g.add_argument("--blender-mode", choices=["auto", "gui", "headless"])
    g.add_argument("--crop", type=int, nargs=4, metavar=("X", "Y", "W", "H"), help="먼저 잘라낼 영역(맥)")
    g.add_argument("--no-cutout", action="store_true", help="맥 자동 배경 제거를 끈다")
    g.add_argument("--wait", type=int, default=0, help="GPU 가 바쁘면 최대 몇 초 기다릴지")
    _add_conn(g)

    c = sub.add_parser("config", help="설정 보기·저장(값을 주면 config.json 의 triposg 에 합친다)")
    _add_conn(c)
    c.add_argument("--from-json", help="설정 JSON 파일을 통째로 읽어 합치기(예: scripts/triposg/remote_config.example.json 꼴)")
    c.add_argument("--clear", action="store_true", help="triposg 설정을 지운다")

    k = sub.add_parser("check", help="설정과 GPU 가 한가한지 확인")
    _add_conn(k)

    r = sub.add_parser("remote", help="원격 GPU PC 에서 생성해 결과만 받아 오기(블렌더 안 씀)")
    r.add_argument("--config", help="설정 JSON(키 = 옵션 이름의 - 를 _ 로). 명령줄 값이 덮어쓴다")
    r.add_argument("--image", required=True)
    r.add_argument("--name", required=True)
    r.add_argument("--local-out", default="out")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--steps", type=int, default=50)
    r.add_argument("--cfg", type=float, default=7.0)
    r.add_argument("--depth", type=int, default=9)
    r.add_argument("--wait", type=int, default=0)
    _add_conn(r)
    return ap


def cli_main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    from .generate import default_mode, triposg_generate
    from .remote import TripoSGError, generate_remote, gpu_busy

    try:
        if a.action == "config":
            cur = dict(config.get("triposg") or {})
            if a.clear:
                cur = {}
            if a.from_json:
                cur.update(json.loads(Path(a.from_json).read_text(encoding="utf-8")))
            cur.update(_conn_from(a))
            if a.clear or a.from_json or _conn_from(a):
                config.set_value("triposg", cur or None)
            _print({"triposg": cur, "mode_used": default_mode(cur), "config_file": str(config.config_path())})
            return 0

        if a.action == "check":
            s = dict(config.get("triposg") or {})
            s.update(_conn_from(a))
            mode = default_mode(s)
            need = ("host", "remote_dir", "remote_python", "triposg_src") if mode == "remote" else ("triposg_src",)
            missing = [x for x in need if not s.get(x)]
            out = {"mode": mode, "missing": missing}
            if mode == "local":
                for x in ("python", "triposg_src", "weights"):
                    if s.get(x) and not s[x].startswith("VAST-AI/"):
                        out[f"{x}_exists"] = Path(s[x]).exists()
            try:
                busy = gpu_busy(s.get("host") if mode == "remote" else None, int(s.get("busy_mb") or 2500))
                out["gpu_busy"] = busy
                out["gpu_free"] = not busy
            except TripoSGError as e:
                out["gpu_error"] = str(e)
            out["ok"] = not missing and out.get("gpu_free", False)
            _print(out)
            return 0 if out["ok"] else 1

        if a.action == "remote":
            s = json.loads(Path(a.config).read_text(encoding="utf-8")) if a.config else {}
            s.update(_conn_from(a))
            s.setdefault("shell", "powershell")
            p = {"seed": a.seed, "steps": a.steps, "cfg": a.cfg, "depth": a.depth}
            info = generate_remote(s, Path(a.image).resolve(), a.name, p, Path(a.local_out), a.wait)
            _print(info)
            print(f"[완료] {Path(a.local_out) / (a.name + '.glb')}")
            return 0

        res = triposg_generate(a.image, name=a.name, seed=a.seed, depth=a.depth, steps=a.steps, cfg=a.cfg,
                               height_m=a.height_m, keep_largest=not a.keep_all, import_to_blender=not a.no_import,
                               blender_mode=a.blender_mode, crop=a.crop, auto_cutout=not a.no_cutout,
                               wait_sec=a.wait, settings=_conn_from(a) or None)
        _print(res)
        return 0
    except TripoSGError as e:
        print(f"[triposg] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(cli_main())
