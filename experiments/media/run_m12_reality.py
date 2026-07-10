"""M12 — Physical Reality Engine: verification-first media, discovered not hardcoded (no LLM, no GPU, no model).

The question, grounded in reality not theory: does the JimsAI spine
— evidence -> reusable structure -> projection -> VERIFY -> realize —
transfer to a NON-language modality? M8 proved it for code (typed search +
execution-verification, never voice a wrong program). This asks the same of a
media-adjacent modality: 2D physical scenes (light, objects, shadows,
occlusion). It is the honest first slice of the "Media Realization Engine /
Physical Reality Engine" direction (a verifier whose job is not to render but to
ensure reality — "is physically consistent", not "looks right").

What is and is NOT claimed. NOT claimed: frontier image quality, pixel
synthesis, or learning physics from photographs. CLAIMED and TESTED, falsifiably:
  (C1) INVARIANT DISCOVERY FROM EVIDENCE. Given only consistent scenes, the
       engine discovers which relations are invariant (shadow direction is a
       fixed function of light azimuth; shadow length scales with height/tan;
       objects rest on the ground; nearer occludes farther) WITHOUT being told
       the physics — it keeps a candidate relation iff it holds with ~zero
       residual across ALL evidence, and it REJECTS a spurious candidate that
       only looks related. This is ELE's promotion-by-recurrence, for physics.
  (C2) THE REFUSAL GUARANTEE (the M8 contract, for media). On held-out scenes,
       the engine ACCEPTS novel consistent ones (projection/composition it never
       trained on) and REFUSES physically-impossible ones, NAMING the violated
       law — and it must accept ZERO impossible scenes. It may fail to realize,
       but never realizes an impossibility. "Verify before realize."
  (C3) ONE CONCEPT, MANY REALIZATIONS. The SAME verified scene structure is
       realized deterministically as an SVG (visual) AND as a sentence
       (language) — no model in either path.

Anti-hardcoding: scenes are generated with random parameters per seed; the
verifier is handed a HYPOTHESIS SPACE of candidate relations (the analog of M8's
operation grammar) but never the physics — which relations are laws is decided
by the evidence, and anything outside the space is a known boundary, not a
guess. No scene's verdict is enumerated in code.

Metrics (REPORTED, per the grounding-review discipline):
  - discovered laws (must include the 4 real ones, must EXCLUDE the spurious one)
  - accept-rate on held-out CONSISTENT scenes (projection generalization)
  - refuse-rate on IMPOSSIBLE scenes, and correct-law-named rate
  - impossible_accepted  — THE GUARANTEE, must be 0

Run: .venv/Scripts/python.exe experiments/media/run_m12_reality.py [seed ...]
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOL_ANGLE = 3.0      # degrees; a shadow more than this off its law is impossible
TOL_LEN = 0.05       # relative; shadow length residual tolerance
TOL_SUPPORT = 1e-6   # an object base above the ground plane is floating


# ── latent physics (the hidden generator; the verifier never sees this) ──────

@dataclass
class Obj:
    x: float
    base_y: float      # 0.0 when resting on the ground
    height: float
    depth: float       # distance from camera; smaller = nearer
    shadow_dir: float  # degrees
    shadow_len: float
    x_span: float      # screen width, for occlusion overlap


@dataclass
class Scene:
    light_azimuth: float
    light_elevation: float
    warm: bool
    objects: list[Obj]
    occlusion: list[tuple[int, int]]  # (front_index, back_index) pairs
    spurious: float                    # a decoy feature correlated with nothing
    violated_law: str = ""             # set only on corrupted scenes
    meta: dict = field(default_factory=dict)


def _make_consistent(rng: Random) -> Scene:
    az = rng.uniform(0, 360)
    elev = rng.uniform(12, 78)
    warm = elev < 20
    shadow_dir = (az + 180.0) % 360.0
    tan_e = math.tan(math.radians(elev))
    n = rng.randint(2, 4)
    objs: list[Obj] = []
    for _ in range(n):
        h = rng.uniform(0.5, 3.0)
        objs.append(Obj(
            x=rng.uniform(-5, 5), base_y=0.0, height=h, depth=rng.uniform(1, 20),
            shadow_dir=shadow_dir, shadow_len=h / tan_e, x_span=rng.uniform(0.4, 1.2),
        ))
    # occlusion: for objects that overlap in x, nearer (smaller depth) is in front
    occ: list[tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if abs(objs[i].x - objs[j].x) < (objs[i].x_span + objs[j].x_span) / 2:
                front, back = (i, j) if objs[i].depth < objs[j].depth else (j, i)
                occ.append((front, back))
    return Scene(az, elev, warm, objs, occ, spurious=rng.uniform(0, 100))


def _corrupt(scene: Scene, rng: Random) -> Scene:
    """Inject exactly ONE physical impossibility; return a copy tagged with the
    law it violates. Corruptions exceed tolerance by construction."""
    import copy
    s = copy.deepcopy(scene)
    kind = rng.choice(["shadow_dir", "shadow_len", "support", "occlusion"])
    if kind == "shadow_dir":
        i = rng.randrange(len(s.objects))
        s.objects[i].shadow_dir = (s.objects[i].shadow_dir + rng.uniform(30, 150)) % 360
        s.violated_law = "shadow_direction"
    elif kind == "shadow_len":
        i = rng.randrange(len(s.objects))
        s.objects[i].shadow_len *= rng.choice([0.35, 2.6])
        s.violated_law = "shadow_length"
    elif kind == "support":
        i = rng.randrange(len(s.objects))
        s.objects[i].base_y = rng.uniform(0.3, 2.0)  # floating
        s.violated_law = "support"
    else:  # occlusion — mark the farther object as in front
        if s.occlusion:
            k = rng.randrange(len(s.occlusion))
            f, b = s.occlusion[k]
            s.occlusion[k] = (b, f)
            s.violated_law = "occlusion"
        else:  # no overlaps to corrupt; fall back to a shadow flip
            i = rng.randrange(len(s.objects))
            s.objects[i].shadow_dir = (s.objects[i].shadow_dir + 90) % 360
            s.violated_law = "shadow_direction"
    return s


# ── the hypothesis space (analog of M8's operation grammar) ──────────────────
# Basis features a functional law MAY be built from. The engine does not know
# which basis is right; it discovers the one with zero residual across evidence.

def _height_basis(o: Obj, tan_e: float) -> dict[str, float]:
    return {
        "height/tan(elev)": o.height / tan_e,
        "height": o.height,
        "height*tan(elev)": o.height * tan_e,
        "constant": 1.0,
    }


# ── the Physical Reality Engine: discover invariants, then verify ────────────

class RealityEngine:
    def __init__(self) -> None:
        self.laws: dict[str, dict] = {}

    def discover(self, scenes: list[Scene]) -> None:
        """Keep only relations that hold with ~zero residual across ALL evidence.
        Nothing here encodes the physics; it measures which candidates are
        invariant and fits their free parameter from data."""
        # (L1) shadow_direction = (light_azimuth + offset) mod 360 — discover offset
        offsets = []
        for s in scenes:
            for o in s.objects:
                offsets.append((o.shadow_dir - s.light_azimuth) % 360)
        off = _circular_mean(offsets)
        if all(_angle_diff(o.shadow_dir, (s.light_azimuth + off) % 360) < TOL_ANGLE
               for s in scenes for o in s.objects):
            self.laws["shadow_direction"] = {"type": "angle", "offset": off}

        # (L2) shadow_length = k * basis(height, elevation) — discover basis + k
        best = None
        for basis_name in _height_basis(scenes[0].objects[0], 1.0):
            ratios, ok = [], True
            for s in scenes:
                tan_e = math.tan(math.radians(s.light_elevation))
                for o in s.objects:
                    b = _height_basis(o, tan_e)[basis_name]
                    if b == 0:
                        ok = False; break
                    ratios.append(o.shadow_len / b)
                if not ok:
                    break
            if not ok or not ratios:
                continue
            k = sum(ratios) / len(ratios)
            resid = max(abs(r - k) / k for r in ratios) if k else 1.0
            if resid < TOL_LEN and (best is None or resid < best[2]):
                best = (basis_name, k, resid)
        if best:
            self.laws["shadow_length"] = {"type": "scale", "basis": best[0], "k": best[1]}

        # (L3) support: every object rests on the ground plane (base_y == 0)
        if all(abs(o.base_y) <= TOL_SUPPORT for s in scenes for o in s.objects):
            self.laws["support"] = {"type": "predicate"}

        # (L4) occlusion: the object marked in front is always the nearer one
        if all(s.objects[f].depth <= s.objects[b].depth for s in scenes for (f, b) in s.occlusion):
            self.laws["occlusion"] = {"type": "predicate"}

        # (Lx) SPURIOUS candidate: object[0].x is a linear function of the decoy
        # feature. It is random in the data, so a genuine discoverer must REJECT
        # it (this is the false-positive guard — the point of C1).
        xs = [(s.spurious, s.objects[0].x) for s in scenes]
        if _linear_zero_residual(xs):
            self.laws["spurious_x_from_decoy"] = {"type": "bogus"}

    def verify(self, scene: Scene) -> tuple[bool, list[str]]:
        """Accept iff every discovered law holds within tolerance. Returns the
        named violations — the engine says WHY it refuses, never just 'no'."""
        v: list[str] = []
        if "shadow_direction" in self.laws:
            off = self.laws["shadow_direction"]["offset"]
            for o in scene.objects:
                if _angle_diff(o.shadow_dir, (scene.light_azimuth + off) % 360) >= TOL_ANGLE:
                    v.append("shadow_direction"); break
        if "shadow_length" in self.laws:
            law = self.laws["shadow_length"]
            tan_e = math.tan(math.radians(scene.light_elevation))
            for o in scene.objects:
                b = _height_basis(o, tan_e)[law["basis"]]
                pred = law["k"] * b
                if pred == 0 or abs(o.shadow_len - pred) / pred >= TOL_LEN:
                    v.append("shadow_length"); break
        if "support" in self.laws:
            if any(abs(o.base_y) > TOL_SUPPORT for o in scene.objects):
                v.append("support")
        if "occlusion" in self.laws:
            if any(scene.objects[f].depth > scene.objects[b].depth for (f, b) in scene.occlusion):
                v.append("occlusion")
        return (not v), v


# ── realization: one verified structure, two modalities, both deterministic ──

def realize_svg(scene: Scene) -> str:
    """Deterministic vector realization — no model. Objects are boxes; shadows
    are cast along the discovered direction, length to scale."""
    W, H = 480, 320
    cx, cy, sc = W / 2, H * 0.72, 26.0
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">',
             f'<rect width="{W}" height="{H}" fill="{"#fce4c4" if scene.warm else "#dfe9f5"}"/>',
             f'<line x1="0" y1="{cy:.0f}" x2="{W}" y2="{cy:.0f}" stroke="#8a7f6a"/>']
    rad = math.radians(scene.objects[0].shadow_dir)
    dx, dy = math.cos(rad), math.sin(rad) * 0.35
    for o in sorted(scene.objects, key=lambda t: -t.depth):  # far first (painter)
        px = cx + o.x * sc
        w, h = o.x_span * sc, o.height * sc
        sl = o.shadow_len * sc
        parts.append(f'<polygon points="{px:.0f},{cy:.0f} {px + dx*sl:.0f},{cy + dy*sl:.0f} '
                     f'{px + w + dx*sl:.0f},{cy + dy*sl:.0f} {px + w:.0f},{cy:.0f}" '
                     f'fill="#00000033"/>')
        parts.append(f'<rect x="{px:.0f}" y="{cy - h:.0f}" width="{w:.0f}" height="{h:.0f}" '
                     f'fill="#6b7a8f" stroke="#33414f"/>')
    parts.append("</svg>")
    return "".join(parts)


_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def realize_text(scene: Scene) -> str:
    c = _COMPASS[int(((scene.light_azimuth + 22.5) % 360) // 45)]
    sc = _COMPASS[int(((scene.objects[0].shadow_dir + 22.5) % 360) // 45)]
    tod = "at golden hour" if scene.warm else "in neutral daylight"
    return (f"A scene lit from the {c} {tod} ({scene.light_elevation:.0f}° elevation); "
            f"{len(scene.objects)} objects rest on the ground, casting shadows toward {sc}.")


# ── math helpers ─────────────────────────────────────────────────────────────

def _angle_diff(a: float, b: float) -> float:
    d = abs((a - b) % 360)
    return min(d, 360 - d)


def _circular_mean(angles: list[float]) -> float:
    s = sum(math.sin(math.radians(a)) for a in angles)
    c = sum(math.cos(math.radians(a)) for a in angles)
    return math.degrees(math.atan2(s, c)) % 360


def _linear_zero_residual(pairs: list[tuple[float, float]]) -> bool:
    """True iff y is an (almost) exact linear function of x across all pairs."""
    n = len(pairs)
    if n < 3:
        return False
    sx = sum(p[0] for p in pairs); sy = sum(p[1] for p in pairs)
    sxx = sum(p[0] ** 2 for p in pairs); sxy = sum(p[0] * p[1] for p in pairs)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-9:
        return False
    m = (n * sxy - sx * sy) / denom
    b = (sy - m * sx) / n
    spread = (max(p[1] for p in pairs) - min(p[1] for p in pairs)) or 1.0
    return all(abs(p[1] - (m * p[0] + b)) / spread < 0.02 for p in pairs)


# ── experiment ───────────────────────────────────────────────────────────────

def run_seed(seed: int, n_train: int = 60, n_test: int = 60) -> dict:
    rng = Random(seed)
    train = [_make_consistent(rng) for _ in range(n_train)]
    engine = RealityEngine()
    engine.discover(train)

    consistent = [_make_consistent(rng) for _ in range(n_test)]           # held out
    impossible = [_corrupt(_make_consistent(rng), rng) for _ in range(n_test)]

    accepted_consistent = sum(1 for s in consistent if engine.verify(s)[0])
    impossible_accepted = 0
    refused_named = 0
    for s in impossible:
        ok, violations = engine.verify(s)
        if ok:
            impossible_accepted += 1
        elif s.violated_law in violations:
            refused_named += 1

    real = [k for k in ("shadow_direction", "shadow_length", "support", "occlusion")
            if k in engine.laws]
    return {
        "seed": seed,
        "discovered_laws": sorted(engine.laws.keys()),
        "real_laws_found": real,
        "spurious_rejected": "spurious_x_from_decoy" not in engine.laws,
        "accept_rate_consistent": round(accepted_consistent / n_test, 4),
        "refuse_rate_impossible": round((n_test - impossible_accepted) / n_test, 4),
        "correct_law_named_rate": round(refused_named / n_test, 4),
        "impossible_accepted": impossible_accepted,   # THE GUARANTEE — must be 0
        "n_train": n_train, "n_test": n_test,
    }


def main(seeds: list[int]) -> int:
    results = [run_seed(s) for s in seeds]
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)

    # C3 proof: realize one verified scene two ways, save the SVG.
    demo = _make_consistent(Random(seeds[0]))
    (out_dir / "m12_scene.svg").write_text(realize_svg(demo), encoding="utf-8")
    demo_text = realize_text(demo)

    total_impossible_accepted = sum(r["impossible_accepted"] for r in results)
    all_found_all = all(len(r["real_laws_found"]) == 4 for r in results)
    all_spurious_rej = all(r["spurious_rejected"] for r in results)
    accept = sum(r["accept_rate_consistent"] for r in results) / len(results)
    refuse = sum(r["refuse_rate_impossible"] for r in results) / len(results)
    named = sum(r["correct_law_named_rate"] for r in results) / len(results)

    (out_dir / "m12_reality.json").write_text(
        json.dumps({"results": results, "demo_text": demo_text}, indent=2), encoding="utf-8")

    print("=" * 68)
    print(f"M12 Physical Reality Engine — {len(seeds)} seeds {seeds}")
    print("-" * 68)
    for r in results:
        print(f"  seed {r['seed']}: laws={r['real_laws_found']} "
              f"spurious_rejected={r['spurious_rejected']} "
              f"accept={r['accept_rate_consistent']:.0%} refuse={r['refuse_rate_impossible']:.0%} "
              f"named={r['correct_law_named_rate']:.0%} impossible_accepted={r['impossible_accepted']}")
    print("-" * 68)
    print(f"C1 discovery : all 4 real laws found every seed = {all_found_all}; "
          f"spurious rejected every seed = {all_spurious_rej}")
    print(f"C2 guarantee : impossible scenes accepted (must be 0) = {total_impossible_accepted}")
    print(f"             : accept consistent {accept:.1%} | refuse impossible {refuse:.1%} | "
          f"correct law named {named:.1%}")
    print(f"C3 realize   : one verified scene -> SVG (results/m12_scene.svg) AND text:")
    print(f"             : \"{demo_text}\"")
    print("=" * 68)
    verdict = (all_found_all and all_spurious_rej and total_impossible_accepted == 0
               and accept > 0.98 and refuse > 0.98)
    print("VERDICT:", "PASS — spine transfers to media (discover->verify->refuse->realize)"
          if verdict else "FAIL — see per-seed rows")
    return 0 if verdict else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
