"""Generate and cache dependency-free PNG artwork and WAV sound effects."""
from __future__ import annotations

import math
import random
import shutil
import struct
import wave
import zlib
from pathlib import Path

from .persistence import user_data_dir

ASSET_VERSION = "0.6.0"
SIDES = ("allied", "axis")
UNITS = ("rifle", "support", "scout", "mortar", "armour")
SIZES = (40, 56, 72)
RGBA = tuple[int, int, int, int]


class Image:
    def __init__(self, size: int) -> None:
        self.size = size
        self.pixels = bytearray(size * size * 4)

    def put(self, x: int, y: int, color: RGBA) -> None:
        if 0 <= x < self.size and 0 <= y < self.size:
            i = (y * self.size + x) * 4
            self.pixels[i:i + 4] = bytes(color)

    def rect(self, x1: float, y1: float, x2: float, y2: float, fill: RGBA, edge: RGBA | None = None) -> None:
        left, right = sorted((round(x1), round(x2)))
        top, bottom = sorted((round(y1), round(y2)))
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                self.put(x, y, edge if edge and (x in (left, right) or y in (top, bottom)) else fill)

    def circle(self, cx: float, cy: float, radius: float, fill: RGBA, edge: RGBA | None = None) -> None:
        r2, inner = radius * radius, max(0, radius - 1.5) ** 2
        for y in range(int(cy - radius - 1), int(cy + radius + 2)):
            for x in range(int(cx - radius - 1), int(cx + radius + 2)):
                d = (x - cx) ** 2 + (y - cy) ** 2
                if d <= r2:
                    self.put(x, y, edge if edge and d >= inner else fill)

    def line(self, x1: float, y1: float, x2: float, y2: float, fill: RGBA, width: int = 1) -> None:
        steps = max(1, int(max(abs(x2 - x1), abs(y2 - y1)) * 2))
        for step in range(steps + 1):
            t = step / steps
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            self.circle(x, y, max(0.5, width / 2), fill)

    def triangle(self, a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], fill: RGBA, edge: RGBA | None = None) -> None:
        points = (a, b, c)
        low, high = max(0, int(min(p[1] for p in points))), min(self.size - 1, int(max(p[1] for p in points)))
        for y in range(low, high + 1):
            hits: list[float] = []
            for p1, p2 in ((a, b), (b, c), (c, a)):
                if (p1[1] <= y < p2[1]) or (p2[1] <= y < p1[1]):
                    hits.append(p1[0] + (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1]))
            if len(hits) == 2:
                for x in range(round(min(hits)), round(max(hits)) + 1):
                    self.put(x, y, fill)
        if edge:
            self.line(*a, *b, edge, 1); self.line(*b, *c, edge, 1); self.line(*c, *a, edge, 1)

    def save(self, path: Path) -> None:
        rows = b"".join(b"\0" + self.pixels[y * self.size * 4:(y + 1) * self.size * 4] for y in range(self.size))
        def chunk(name: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.size, self.size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def _colors(side: str) -> tuple[RGBA, RGBA, RGBA, RGBA]:
    return ((48, 91, 143, 255), (116, 157, 201, 255), (22, 44, 69, 255), (230, 239, 248, 255)) if side == "allied" else ((145, 55, 49, 255), (199, 111, 94, 255), (68, 29, 27, 255), (248, 229, 219, 255))


def _unit_sprite(side: str, kind: str, size: int, path: Path) -> None:
    image = Image(size); s = size / 56; cx = cy = size / 2
    base, light, dark, white = _colors(side)
    image.circle(cx + 2*s, cy + 10*s, 17*s, (8, 12, 10, 120))
    if kind == "armour":
        image.rect(7*s, 18*s, 49*s, 39*s, (28, 33, 28, 255), (8, 10, 8, 255))
        for x in (12, 20, 28, 36, 44): image.circle(x*s, 36*s, 3*s, (66, 72, 62, 255), dark)
        image.rect(8*s, 20*s, 48*s, 34*s, base, dark)
        image.circle(29*s, 24*s, 9*s, light, dark)
        image.line(30*s, 23*s, 53*s, 15*s, dark, max(2, round(4*s)))
        image.line(31*s, 21*s, 52*s, 14*s, white, max(1, round(s)))
    else:
        image.circle(cx, cy, 19*s, base, white)
        image.circle(cx - 5*s, cy - 7*s, 10*s, light)
        if kind == "rifle":
            for ox, oy in ((-7, 3), (0, -6), (8, 4)): image.circle(cx+ox*s, cy+oy*s, 2.5*s, (232, 205, 170, 255), dark)
            image.line(cx-13*s, cy+12*s, cx+14*s, cy-12*s, (62, 42, 25, 255), max(1, round(2*s)))
        elif kind == "support":
            image.line(cx-14*s, cy+2*s, cx+15*s, cy-4*s, dark, max(2, round(4*s)))
            image.line(cx, cy, cx-10*s, cy+15*s, dark, max(1, round(2*s))); image.line(cx, cy, cx+10*s, cy+15*s, dark, max(1, round(2*s)))
        elif kind == "scout":
            image.triangle((cx,cy-14*s),(cx+14*s,cy),(cx,cy+14*s),white,dark); image.triangle((cx,cy-14*s),(cx-14*s,cy),(cx,cy+14*s),white,dark)
            image.circle(cx, cy, 4*s, dark, light)
        elif kind == "mortar":
            image.line(cx-2*s, cy+7*s, cx+8*s, cy-14*s, dark, max(2, round(5*s)))
            image.circle(cx+8*s, cy-14*s, 3*s, (55, 60, 52, 255), dark)
            image.line(cx, cy+5*s, cx-11*s, cy+16*s, dark, max(1, round(2*s))); image.line(cx, cy+5*s, cx+12*s, cy+16*s, dark, max(1, round(2*s)))
    image.circle(10*s, 10*s, 7*s, (239, 242, 232, 255), dark)
    insignia = (48, 77, 127, 255) if side == "allied" else (92, 31, 29, 255)
    if side == "allied": image.circle(10*s, 10*s, 4*s, insignia); image.circle(10*s, 10*s, 1.5*s, (235, 65, 55, 255))
    else: image.line(6*s,10*s,14*s,10*s,insignia,max(1,round(2*s))); image.line(10*s,6*s,10*s,14*s,insignia,max(1,round(2*s)))
    rng = random.Random(f"{side}{kind}{size}")
    for _ in range(size * 2): image.put(rng.randrange(size), rng.randrange(size), rng.choice(((255,255,255,18),(0,0,0,18))))
    image.save(path)


def _cursor(path: Path) -> None:
    image = Image(48)
    image.triangle((3,2),(3,37),(15,27),(225,250,255,255),(5,25,37,255))
    image.triangle((15,27),(24,46),(31,42),(225,250,255,255),(5,25,37,255))
    image.triangle((3,2),(35,23),(15,27),(225,250,255,255),(5,25,37,255))
    image.circle(8,8,5,(255,235,82,240),(5,25,37,255)); image.save(path)


def _objective(kind: str, path: Path) -> None:
    image = Image(44); white=(239,246,243,255); gold=(244,210,76,255); dark=(20,40,57,245)
    image.circle(22,22,19,dark,white); image.circle(22,22,14,(46,95,119,240),(104,210,235,255))
    if kind == "capture": image.line(16,32,16,11,white,2); image.triangle((17,11),(34,17),(17,23),gold,white)
    elif kind == "hold": image.triangle((10,18),(22,9),(34,18),gold,white); image.rect(13,18,31,33,gold,white); image.rect(19,23,25,33,dark,white)
    elif kind == "recon": image.circle(19,19,9,(0,0,0,0),white); image.line(26,26,35,35,gold,4)
    elif kind == "breakthrough": image.line(9,22,34,22,white,3); image.triangle((25,11),(38,22),(25,33),gold,white)
    elif kind == "preserve": image.circle(22,22,12,gold,white); image.line(15,22,20,28,dark,3); image.line(20,28,30,15,dark,3)
    else: image.rect(9,17,34,29,gold,white); image.circle(15,32,4,dark,white); image.circle(29,32,4,dark,white); image.line(26,17,38,12,white,3)
    image.save(path)


def _sample(name: str, t: float, rng: random.Random) -> float:
    if name == "ui_click": return math.sin(t*math.tau*880)*math.exp(-t*28)
    if name == "select": return (math.sin(t*math.tau*520)+.5*math.sin(t*math.tau*780))*math.exp(-t*13)
    if name == "order": return math.sin(t*math.tau*(390+190*t))*math.exp(-t*8)
    if name == "requisition": return sum(math.sin(t*math.tau*f) for f in (330,440,660))/2.6*math.exp(-t*3.8)
    if name == "objective": return sum(math.sin(t*math.tau*f) for f in (523,659,784))/2.7*min(1,t*10)*math.exp(-t*2.9)
    if name == "battle_start": return (math.sin(t*math.tau*110)*.6+math.sin(t*math.tau*220)*.35)*math.exp(-t*1.25)
    if name == "gunfire": return (rng.uniform(-1,1)*.82+math.sin(t*math.tau*95)*.25)*math.exp(-t*24)
    if name == "explosion": return (rng.uniform(-1,1)*.72+math.sin(t*math.tau*max(35,120-t*130))*.55)*math.exp(-t*5.2)
    if name in ("victory","defeat"):
        notes=(392,523,659,784) if name=="victory" else (330,277,220,165); return math.sin(t*math.tau*notes[min(3,int(t/.23))])*math.exp(-max(0,t-.8)*2.2)
    return (math.sin(t*math.tau*180)+rng.uniform(-.25,.25))*math.exp(-t*7)


def _sound(name: str, path: Path) -> None:
    rate=22050; duration={"ui_click":.12,"select":.20,"order":.28,"requisition":.72,"objective":.85,"battle_start":1.05,"gunfire":.24,"explosion":.74,"victory":1.15,"defeat":1.15,"error":.35}[name]
    rng=random.Random(name); frames=bytearray()
    for i in range(int(rate*duration)): frames.extend(struct.pack("<h",int(max(-1,min(1,_sample(name,i/rate,rng)))*14500)))
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),"wb") as audio: audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(rate); audio.writeframes(frames)


def ensure_assets() -> Path:
    root=user_data_dir()/f"assets_{ASSET_VERSION.replace('.','_')}"; marker=root/".complete"
    if marker.exists() and marker.read_text(encoding="utf-8",errors="ignore").strip()==ASSET_VERSION: return root
    if root.exists(): shutil.rmtree(root)
    for side in SIDES:
        for kind in UNITS:
            for size in SIZES: _unit_sprite(side,kind,size,root/"sprites"/f"{side}_{kind}_{size}.png")
    _cursor(root/"ui"/"neural_cursor.png")
    for kind in ("capture","hold","recon","breakthrough","preserve","destroy_armour"): _objective(kind,root/"ui"/f"objective_{kind}.png")
    for name in ("ui_click","select","order","requisition","objective","battle_start","gunfire","explosion","victory","defeat","error"): _sound(name,root/"sounds"/f"{name}.wav")
    marker.write_text(ASSET_VERSION,encoding="utf-8"); return root
