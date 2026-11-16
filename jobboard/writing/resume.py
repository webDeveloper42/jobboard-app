"""Reading a resume file: .txt, .md, .docx and most .pdf files, with the standard library only.

PDFs are read best-effort: text drawn with fonts that carry a ToUnicode map (Word, Google Docs,
most resume builders) comes out fine. A scanned PDF has no text to find, so pasting is the way.
"""
import re
import unicodedata
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree

MAX_BYTES = 15 * 1024 * 1024


class ResumeError(ValueError):
    pass


def read(path):
    p = Path(path)
    if not p.is_file():
        raise ResumeError(f"there's no file at {p}")
    if p.stat().st_size > MAX_BYTES:
        raise ResumeError("that file is over 15 MB")
    suffix = p.suffix.lower()
    if suffix in (".txt", ".md", ".text", ""):
        out = p.read_text(errors="replace")
    elif suffix == ".docx":
        out = docx_text(p)
    elif suffix == ".pdf":
        out = pdf_text(p.read_bytes())
    else:
        raise ResumeError("use a .pdf, .docx, .txt or .md file, or paste the text")
    out = tidy(out)
    if len(re.findall(r"[A-Za-z]{3,}", out)) < 25:
        raise ResumeError("couldn't find readable text in that file. If it's a scanned PDF, paste the text instead")
    return out


def tidy(value):
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    value = re.sub(r"[ \t ]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def docx_text(path):
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(path) as z:
            root = ElementTree.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        raise ResumeError("that .docx file couldn't be opened") from None
    lines = []
    for para in root.iter(ns + "p"):
        bits = []
        for node in para.iter():
            if node.tag == ns + "t" and node.text:
                bits.append(node.text)
            elif node.tag == ns + "tab":
                bits.append("\t")
            elif node.tag in (ns + "br", ns + "cr"):
                bits.append("\n")
        bullet = para.find(f"{ns}pPr/{ns}numPr") is not None
        line = "".join(bits).strip()
        if line:
            lines.append(("• " if bullet else "") + line)
    return "\n".join(lines)


# ---------------------------------------------------------------- PDF

_OBJ = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)


def _inflate(raw, head):
    if b"FlateDecode" not in head:
        return raw if b"/Filter" not in head else b""
    for wbits in (15, -15):
        try:
            return zlib.decompress(raw, wbits)
        except zlib.error:
            continue
    try:
        return zlib.decompressobj().decompress(raw)
    except zlib.error:
        return b""


def _objects(data):
    objs = {}
    for m in _OBJ.finditer(data):
        body = m.group(3)
        sm = _STREAM.search(body)
        head = body[:sm.start()] if sm else body
        objs[int(m.group(1))] = (head, _inflate(sm.group(1), head) if sm else None)
    # Compressed object streams (PDF 1.5+) hold more objects inside them.
    for head, stream in list(objs.values()):
        if stream and b"/ObjStm" in head:
            n = re.search(rb"/N\s+(\d+)", head)
            first = re.search(rb"/First\s+(\d+)", head)
            if not (n and first):
                continue
            nums = list(map(int, stream[:int(first.group(1))].split()))
            pairs = list(zip(nums[0::2], nums[1::2]))
            for i, (num, off) in enumerate(pairs):
                start = int(first.group(1)) + off
                end = int(first.group(1)) + pairs[i + 1][1] if i + 1 < len(pairs) else len(stream)
                objs.setdefault(num, (stream[start:end], None))
    return objs


def _cmap(stream):
    """ToUnicode CMap: glyph code (hex) -> text."""
    out = {}

    def uni(hexs):
        try:
            return bytes.fromhex(hexs.decode()).decode("utf-16-be", "replace")
        except ValueError:
            return ""
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", stream, re.S):
        for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block):
            out[a.decode().upper().zfill(len(a))] = uni(b)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", stream, re.S):
        for a, b, rest in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]*>)", block):
            lo, hi, width = int(a, 16), int(b, 16), len(a)
            if hi - lo > 5000:
                continue
            if rest.startswith(b"["):
                for i, h in enumerate(re.findall(rb"<([0-9A-Fa-f]*)>", rest)):
                    out[format(lo + i, f"0{width}X")] = uni(h)
            else:
                base = int(rest.strip(b"<>") or b"0", 16)
                for i in range(hi - lo + 1):
                    try:
                        out[format(lo + i, f"0{width}X")] = chr(base + i)
                    except (ValueError, OverflowError):
                        pass
    return out


def _fonts(objs):
    """Font resource name (/F1) -> CMap, gathered from every font dictionary in the file."""
    by_obj = {}
    for num, (head, _) in objs.items():
        m = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", head)
        if m and b"/Font" in head:
            target = objs.get(int(m.group(1)))
            if target and target[1]:
                by_obj[num] = _cmap(target[1])
    names = {}
    for head, _ in objs.values():
        for block in re.findall(rb"/Font\s*<<(.*?)>>", head, re.S):
            for name, ref in re.findall(rb"/([\w.+-]+)\s+(\d+)\s+0\s+R", block):
                if int(ref) in by_obj:
                    names[name.decode()] = by_obj[int(ref)]
        m = re.search(rb"/Font\s+(\d+)\s+0\s+R", head)
        if m and int(m.group(1)) in objs:
            for name, ref in re.findall(rb"/([\w.+-]+)\s+(\d+)\s+0\s+R", objs[int(m.group(1))][0]):
                if int(ref) in by_obj:
                    names[name.decode()] = by_obj[int(ref)]
    return names


def _literal(s):
    out, i = bytearray(), 0
    esc = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f", b"(": b"(", b")": b")", b"\\": b"\\"}
    while i < len(s):
        c = s[i:i + 1]
        if c == b"\\" and i + 1 < len(s):
            n = s[i + 1:i + 2]
            if n in esc:
                out += esc[n]
                i += 2
                continue
            m = re.match(rb"[0-7]{1,3}", s[i + 1:i + 4])
            if m:
                out.append(int(m.group(), 8) & 255)
                i += 1 + len(m.group())
                continue
            i += 2 if n in (b"\n", b"\r") else 1
            continue
        out += c
        i += 1
    return bytes(out)


def _decode(raw, cmap):
    if not cmap:
        return raw.decode("latin-1")
    width = len(next(iter(cmap)))
    h = raw.hex().upper()
    step = width if width in (2, 4) else 2
    return "".join(cmap.get(h[i:i + step], "") for i in range(0, len(h), step))


_TOKEN = re.compile(rb"\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>|\[|\]|/[^\s/\[\]()<>]+|-?\d*\.?\d+|[A-Za-z'\"*]+", re.S)


def _content_text(stream, fonts):
    out, stack, cmap, arr = [], [], None, None
    size, last_y = 10.0, None
    for tok in _TOKEN.findall(stream):
        if tok == b"[":
            arr = []
            continue
        if tok == b"]":
            stack.append(("arr", arr or []))
            arr = None
            continue
        if tok[:1] == b"(" or tok[:1] == b"<":
            raw = _literal(tok[1:-1]) if tok[:1] == b"(" else bytes.fromhex(re.sub(rb"\s", b"", tok[1:-1]).decode() + ("0" if len(re.sub(rb"\s", b"", tok[1:-1])) % 2 else ""))
            (arr if arr is not None else stack).append(("str", raw))
            continue
        if arr is not None:
            try:
                if float(tok) < -180:
                    arr.append(("str", None))  # a wide gap inside TJ is a space
            except ValueError:
                pass
            continue
        op = tok.decode("latin-1")
        if op == "Tf" and len(stack) >= 2 and stack[-2][0] == "name":
            cmap = fonts.get(stack[-2][1])
            if stack[-1][0] == "num" and stack[-1][1] > 0:
                size = stack[-1][1]
        elif op in ("Tj", "'", '"') and stack and stack[-1][0] == "str":
            if op != "Tj":
                out.append("\n")
            out.append(_decode(stack[-1][1], cmap))
        elif op == "TJ" and stack and stack[-1][0] == "arr":
            out.append("".join(" " if raw is None else _decode(raw, cmap) for _, raw in stack[-1][1]))
        elif op == "T*":
            out.append("\n")
        elif op in ("Td", "TD") and len(stack) >= 2 and stack[-1][0] == stack[-2][0] == "num":
            # Some writers (Chrome, Skia) place every letter with its own move. Only a vertical move is a new line,
            # and only a horizontal jump wider than a letter is a gap between words.
            tx, ty = stack[-2][1], stack[-1][1]
            if abs(ty) > 0.5:
                out.append("\n")
            elif tx > size * 1.1:
                out.append(" ")
        elif op == "Tm" and len(stack) >= 6 and all(x[0] == "num" for x in stack[-6:]):
            y = stack[-1][1]
            out.append("\n" if last_y is None or abs(y - last_y) > 0.5 else " ")
            last_y = y
        elif op in ("Td", "TD", "Tm"):
            out.append("\n")
        elif op == "ET":
            out.append("\n")
        if tok[:1] == b"/":
            stack.append(("name", tok[1:].decode("latin-1")))
        else:
            try:
                stack.append(("num", float(tok)))
            except ValueError:
                stack = stack[-4:]
        if len(stack) > 50:
            stack = stack[-10:]
    return "".join(out)


def pdf_text(data):
    if not data.startswith(b"%PDF"):
        raise ResumeError("that isn't a PDF file")
    if b"/Encrypt" in data:
        raise ResumeError("that PDF is password-protected. Save an unlocked copy or paste the text")
    objs = _objects(data)
    fonts = _fonts(objs)
    pages = []
    for head, stream in objs.values():
        if stream and b"/Type" not in head[:200] and (b"BT" in stream and b"ET" in stream) and b"/ObjStm" not in head:
            pages.append(_content_text(stream, fonts))
    text = "\n".join(pages)
    text = unicodedata.normalize("NFKC", text)  # ligatures like "ﬁ" become "fi"
    text = "".join(ch for ch in text if ch == "\n" or ch.isprintable())
    return re.sub(r"[ ]{2,}", " ", text)
