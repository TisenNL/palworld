#!/usr/bin/env python3
"""Aggregate .cache/timing/run-*.jsonl (+ benches) into report.md."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TIMING = ROOT / ".cache" / "timing"
REPORT = Path(__file__).resolve().parent / "report.md"


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def load_json(name: str):
    path = TIMING / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_run(path: Path) -> dict:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    start = next((e for e in events if e.get("type") == "run_start"), {})
    end = next((e for e in events if e.get("type") == "run_end"), {})
    ocrs = [e for e in events if e.get("type") == "ocr"]
    iters = [e for e in events if e.get("type") == "iteration"]
    sleeps = [e for e in events if e.get("type") == "sleep"]
    phases = [e for e in events if e.get("type") == "phase"]
    win32 = [e for e in events if e.get("type") == "win32"]
    focus = [e for e in events if e.get("type") == "focus"]
    locks = [e for e in events if e.get("type") == "lock"]

    capture = sum(e.get("capture_ms", 0) for e in ocrs)
    preproc = sum(e.get("preproc_ms", 0) for e in ocrs)
    infer = sum(e.get("inference_ms", 0) for e in ocrs)
    sleep_ms = sum(e.get("ms", 0) for e in sleeps)
    hold_ms = sum(e.get("action_duration_ms", 0) for e in iters)
    hold_ms += sum(e.get("hold_ms", 0) or 0 for e in win32 if e.get("op") == "keybd_event")
    # avoid double-counting hold if both present: prefer iteration durations
    hold_ms = sum(e.get("action_duration_ms", 0) for e in iters)
    confirm_ms = sum(e.get("ms", 0) for e in phases if e.get("name") == "confirm")
    focus_ms = sum(e.get("ms", 0) for e in focus) + sum(
        e.get("ms", 0) for e in phases if e.get("name") == "focus"
    )
    win32_ms = sum(float(e.get("call_ms") or 0) for e in win32)
    lock_ms = sum(e.get("wait_ms", 0) for e in locks)
    total = float(end.get("total_ms") or 0)
    ocr_total = capture + preproc + infer
    other = max(0.0, total - ocr_total - sleep_ms - hold_ms - confirm_ms - focus_ms)

    near = [i for i in iters if (i.get("norm") or 0) <= 12]
    near_ms = sum(i.get("iter_total_ms", 0) for i in near)
    cache_ocrs = [o for o in ocrs if str(o.get("reason", "")).startswith("cache_validate")]

    first_won = sum(1 for o in ocrs if o.get("first_variant_won"))
    return {
        "file": path.name,
        "initial_distance_m": start.get("initial_distance_m"),
        "target": start.get("target"),
        "initial": start.get("initial"),
        "total_ms": total,
        "status": end.get("status"),
        "ocr_reads": end.get("total_ocr_reads") or len(ocrs),
        "iterations": end.get("total_iterations") or len(iters),
        "iterations_within_12": end.get("iterations_within_12") or len(near),
        "exact_match": end.get("exact_match"),
        "ocr_cold_first_ms": end.get("ocr_cold_first_ms"),
        "breakdown_ms": {
            "ocr_capture": round(capture, 1),
            "ocr_preproc": round(preproc, 1),
            "ocr_inference": round(infer, 1),
            "ocr_total": round(ocr_total, 1),
            "sleep": round(sleep_ms, 1),
            "hold": round(hold_ms, 1),
            "confirm": round(confirm_ms, 1),
            "focus": round(focus_ms, 1),
            "win32_calls": round(win32_ms, 1),
            "locks": round(lock_ms, 1),
            "other": round(other, 1),
        },
        "near_field_ms": round(near_ms, 1),
        "near_field_ocrs": sum(i.get("ocr_count", 0) for i in near),
        "cache_validate_ocrs": len(cache_ocrs),
        "cache_validate_ms": round(sum(o.get("total_ms", 0) for o in cache_ocrs), 1),
        "first_variant_won_rate": round(first_won / max(1, len(ocrs)), 3),
        "ocr_events": ocrs,
        "phases": {p["name"]: p["ms"] for p in phases},
    }


def pct(part: float, total: float) -> float:
    return round(100.0 * part / total, 1) if total > 0 else 0.0


def main() -> None:
    TIMING.mkdir(parents=True, exist_ok=True)
    runs = [parse_run(p) for p in sorted(TIMING.glob("run-*.jsonl"))]
    # Ignore unit-test artifacts (injected no-op sleep → tiny wall time).
    real = [r for r in runs if (r["total_ms"] or 0) >= 500]
    env = load_json("env.json") or {}
    onnx = load_json("onnx_info.json") or {}
    capture = load_json("capture_bench.json")
    ocr_prof = load_json("ocr_profile.json")
    hud = load_json("hud_latency.json")
    phys = load_json("physics.json")
    fps = load_json("fps_hud.json")

    lines: list[str] = []
    lines.append("# Mark in game — relatório de medições\n")
    lines.append(f"Gerado por `aggregate_runs.py`. Runs JSONL encontrados: **{len(real)}**.\n")

    lines.append("## Parte B — Runs\n")
    if not real:
        lines.append("**PENDENTE:** rode 10 Marks com `PALWORLD_MARKER_TIMING=1` (5 longe, 5 perto, 1º cold).\n")
    else:
        lines.append("| Arquivo | Dist. inicial (m) | total_ms | OCRs | iters | iters≤12 | status |")
        lines.append("|---------|-------------------|----------|------|-------|----------|--------|")
        for r in real:
            lines.append(
                f"| `{r['file']}` | {r['initial_distance_m']} | {r['total_ms']:.0f} | "
                f"{r['ocr_reads']} | {r['iterations']} | {r['iterations_within_12']} | {r['status']} |"
            )
        totals = [r["total_ms"] for r in real if r["total_ms"]]
        if totals:
            lines.append("")
            lines.append(
                f"- p50 total: **{percentile(totals, 50):.0f} ms** · "
                f"p95: **{percentile(totals, 95):.0f} ms** · máx: **{max(totals):.0f} ms**"
            )
        # aggregate breakdown
        keys = [
            "ocr_capture",
            "ocr_preproc",
            "ocr_inference",
            "sleep",
            "hold",
            "confirm",
            "focus",
            "other",
        ]
        sums = {k: sum(r["breakdown_ms"].get(k, 0) for r in real) for k in keys}
        grand = sum(sums.values()) or 1.0
        lines.append("\n### Divisão percentual (soma de todos os runs)\n")
        lines.append("| Componente | ms | % |")
        lines.append("|------------|----|---|")
        ranked = sorted(sums.items(), key=lambda kv: -kv[1])
        for k, v in ranked:
            lines.append(f"| {k} | {v:.0f} | {pct(v, grand)} |")
        lines.append("\n### Top 5 consumidores\n")
        for i, (k, v) in enumerate(ranked[:5], 1):
            lines.append(f"{i}. **{k}** — {v:.0f} ms ({pct(v, grand)}%)")
        lines.append("")

    lines.append("## Parte C — Respostas\n")

    # C1
    lines.append("### 1. Custo de uma leitura OCR\n")
    if ocr_prof:
        lines.append(
            f"- total **{ocr_prof.get('total_ms')} ms** "
            f"(captura {ocr_prof.get('capture_ms')}, pré-proc {ocr_prof.get('preproc_ms')}, "
            f"inferência {ocr_prof.get('inference_ms')}); variantes={ocr_prof.get('variants_count')}"
        )
    elif real and any(r["ocr_events"] for r in real):
        all_o = [o for r in real for o in r["ocr_events"]]
        if all_o:
            lines.append(
                f"- média total_ms={statistics.fmean(o.get('total_ms',0) for o in all_o):.1f} · "
                f"captura={statistics.fmean(o.get('capture_ms',0) for o in all_o):.1f} · "
                f"pré={statistics.fmean(o.get('preproc_ms',0) for o in all_o):.1f} · "
                f"inf={statistics.fmean(o.get('inference_ms',0) for o in all_o):.1f} · "
                f"variantes médias={statistics.fmean(o.get('variants_count',0) for o in all_o):.1f}"
            )
        else:
            lines.append("**PENDENTE:** `py -3 tools/bench_mark_in_game/bench_ocr_profile.py`")
    else:
        lines.append("**PENDENTE:** `py -3 tools/bench_mark_in_game/bench_ocr_profile.py` (mapa aberto) ou 10 runs TIMING.")
    lines.append("")

    lines.append("### 2. Primeira variante já correta?\n")
    if real and any(r["ocr_events"] for r in real):
        all_o = [o for r in real for o in r["ocr_events"]]
        won = sum(1 for o in all_o if o.get("first_variant_won"))
        lines.append(f"- {won}/{len(all_o)} ({100*won/max(1,len(all_o)):.1f}%) first_variant_won")
    elif ocr_prof:
        lines.append(f"- perfil único: first_variant_won={ocr_prof.get('first_variant_won')}")
    else:
        lines.append("**PENDENTE:** precisa de eventos `ocr` nos JSONL.")
    lines.append("")

    lines.append("### 3. Score de confiança RapidOCR\n")
    all_o = [o for r in real for o in r["ocr_events"]]
    if all_o:
        correct = [o for o in all_o if o.get("consensus_count", 0) >= 2]
        lines.append(
            f"- leituras com consensus≥2: {len(correct)}; "
            "scores por variante estão em `variant_scores` nos JSONL."
        )
        lines.append("- limiar sem FP no conjunto: **avaliar após as 10 runs reais** (agregar scores vencedores vs perdedores).")
    else:
        lines.append("**PENDENTE:** coletar runs reais; RapidOCR retorna `item[2]` por caixa de texto.")
    lines.append("")

    lines.append("### 4. ONNX Runtime\n")
    ort = (onnx.get("onnxruntime") if onnx else None) or (env.get("onnxruntime") if env else None) or {}
    if ort:
        lines.append(f"- versão: {ort.get('version')} · providers: {ort.get('providers')}")
        lines.append(f"- CUDA: {ort.get('has_cuda')} · DirectML: {ort.get('has_directml')}")
        lines.append(f"- intra_op={ort.get('intra_op_num_threads')} inter_op={ort.get('inter_op_num_threads')}")
        for n in onnx.get("gil_contention") or []:
            lines.append(f"- {n}")
    else:
        lines.append("**PENDENTE:** `py -3 tools/bench_mark_in_game/bench_onnx_info.py`")
    lines.append("")

    lines.append("### 5. Captura ImageGrab vs mss vs dxcam\n")
    if capture:
        for eng in ("ImageGrab", "mss", "dxcam"):
            block = capture.get(eng) or {}
            if "error" in block:
                lines.append(f"- **{eng}**: erro — {block['error']}")
            else:
                lines.append(
                    f"- **{eng}**: mediana {block.get('median_ms')} ms · p95 {block.get('p95_ms')} ms (n={block.get('n')})"
                )
        if capture.get("roi"):
            lines.append(f"- ROI: {capture['roi']}")
    else:
        lines.append("**PENDENTE:** `py -3 tools/bench_mark_in_game/bench_capture.py` (+ venv mss/dxcam).")
    lines.append("")

    lines.append("### 6. Latência do HUD pós-tecla\n")
    if hud:
        for hold, data in hud.items():
            lines.append(f"- hold {hold}s → settled_at_ms={data.get('settled_at_ms')} samples={len(data.get('samples') or [])}")
    else:
        lines.append("**PENDENTE:** `py -3 tools/bench_mark_in_game/bench_hud_latency.py` (jogo aberto).")
    lines.append("")

    lines.append("### 7. Física do movimento\n")
    if phys:
        for key, kd in (phys.get("keys") or {}).items():
            r = (kd.get("0.06") or {}).get("units_per_sec_mean")
            s = (kd.get("0.06") or {}).get("units_per_sec_stdev")
            lines.append(f"- {key} @0.06s: {r} u/s (stdev {s})")
        lines.append(f"- linearidade: {phys.get('linearity')}")
    else:
        lines.append("**PENDENTE:** `py -3 tools/bench_mark_in_game/bench_physics.py`")
    lines.append("")

    lines.append("### 8. Near-field (‖erro‖≤12 → alvo exato)\n")
    if real:
        lines.append(
            f"- soma near_field_ms={sum(r['near_field_ms'] for r in real):.0f} · "
            f"OCRs near={sum(r['near_field_ocrs'] for r in real)}"
        )
    else:
        lines.append("**PENDENTE:** runs TIMING.")
    lines.append("")

    lines.append("### 9. Overhead validação de cache\n")
    if real:
        lines.append(
            f"- OCRs cache_validate={sum(r['cache_validate_ocrs'] for r in real)} · "
            f"ms={sum(r['cache_validate_ms'] for r in real):.0f}"
        )
    else:
        lines.append("**PENDENTE:** run quente com cache disco.")
    lines.append("")

    lines.append("### 10. Dataset OCR bench\n")
    crops = ROOT / ".cache" / "ocr-bench"
    n = len(list(crops.glob("*.png"))) if crops.is_dir() else 0
    if n >= 300:
        lines.append(f"- {n} PNGs em `.cache/ocr-bench/` (meta.json / labels.jsonl).")
    else:
        lines.append(f"**PENDENTE:** `{n}/300` — `py -3 tools/bench_mark_in_game/collect_ocr_crops.py`")
    lines.append("")

    lines.append("### 11. FPS jogo / HUD\n")
    if fps:
        lines.append(
            f"- sample_hz={fps.get('sample_hz')} · change_hz={fps.get('change_hz')} · "
            f"notas: {fps.get('notes')}"
        )
    else:
        lines.append("**PENDENTE:** `py -3 tools/bench_mark_in_game/bench_fps_hud.py` + anotar FPS do overlay do jogo.")
    lines.append("")

    lines.append("## Parte D — Ambiente\n")
    if env:
        lines.append(f"- CPU: {env.get('cpu')} ({env.get('cpu_cores')}c/{env.get('cpu_logical')}t)")
        lines.append(f"- GPU: {env.get('gpu')}")
        try:
            ram_gb = int(env.get("ram_bytes") or 0) / (1024**3)
            lines.append(f"- RAM: ~{ram_gb:.1f} GB")
        except Exception:
            lines.append(f"- RAM bytes: {env.get('ram_bytes')}")
        lines.append(f"- OS: {env.get('os')}")
        lines.append(f"- Python: {env.get('python','').split(chr(10))[0]}")
        ort = env.get("onnxruntime") or {}
        lines.append(f"- onnxruntime: {ort.get('version')} providers={ort.get('providers')}")
        lines.append(f"- rapidocr: {env.get('rapidocr')}")
        lines.append(f"- largest_monitor: {env.get('largest_monitor')} key={env.get('monitor_cache_key')}")
        notes = env.get("notes") or {}
        lines.append(f"- modo do jogo / Hz / nº monitores: {notes}")
    else:
        lines.append("**PENDENTE:** `py -3 tools/bench_mark_in_game/collect_env.py`")
        lines.append("- Pré-preenchido conhecido: i5-13400F / RTX 4060 Ti / ~32 GB / Win11 / Py3.14 / onnx 1.27 CPU+Azure")
    lines.append("")
    lines.append("## Como repetir\n")
    lines.append("Ver `tools/bench_mark_in_game/README.md`.\n")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {REPORT} ({len(real)} runs)")


if __name__ == "__main__":
    main()
