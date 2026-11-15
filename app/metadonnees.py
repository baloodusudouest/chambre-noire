"""Date et tag écrits dans le JPEG (EXIF + XMP), portage exact de Scan Immich v3.9 (metadataSegments).

- EXIF : DateTimeOriginal, DateTimeDigitized, DateTime, OffsetTime*, logiciel.
- XMP : xmp:CreateDate, exif:DateTimeOriginal, digiKam:TagsList, lr:hierarchicalSubject (Immich lit les tags).
- Photos non datées : 1er janvier 1900 en heure « murale » UTC (+00:00), car Paris avait +00:09:21 en 1900.
"""
from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
LOGICIEL = "Chambre noire"


def _ascii(tag: int, s: str) -> dict:
    return {"tag": tag, "type": 2, "bytes": (s + "\0").encode("ascii")}


def _tiff(ifd0: list[dict], exif: list[dict]) -> bytes:
    taille = lambda n: 2 + n * 12 + 4
    donnees = lambda l: sum(len(e["bytes"]) + (len(e["bytes"]) & 1) for e in l if e.get("bytes") is not None and len(e["bytes"]) > 4)
    o0 = 8
    d0 = o0 + taille(len(ifd0))
    o1 = d0 + donnees(ifd0)
    d1 = o1 + taille(len(exif))
    fin = d1 + donnees(exif)
    buf = bytearray(fin)
    buf[0:4] = b"II*\x00"
    struct.pack_into("<I", buf, 4, o0)

    def ecrire(off, liste, dpos):
        struct.pack_into("<H", buf, off, len(liste))
        p = off + 2
        for e in liste:
            struct.pack_into("<HH", buf, p, e["tag"], e["type"])
            if e["type"] == 4:
                struct.pack_into("<II", buf, p + 4, 1, e["value"])
            elif e["type"] == 3:
                struct.pack_into("<IH", buf, p + 4, 1, e["value"])
            else:
                b = e["bytes"]
                struct.pack_into("<I", buf, p + 4, len(b))
                if len(b) <= 4:
                    buf[p + 8:p + 8 + len(b)] = b
                else:
                    struct.pack_into("<I", buf, p + 8, dpos)
                    buf[dpos:dpos + len(b)] = b
                    dpos += len(b) + (len(b) & 1)
            p += 12
        struct.pack_into("<I", buf, p, 0)

    ecrire(o0, [dict(e, value=o1) if e["tag"] == 0x8769 else e for e in ifd0], d0)
    ecrire(o1, exif, d1)
    return bytes(buf)


def _app1(prefixe: bytes, charge: bytes) -> bytes:
    longueur = 2 + len(prefixe) + len(charge)
    if longueur > 65535:
        raise ValueError("Segment de métadonnées trop long")
    return b"\xff\xe1" + struct.pack(">H", longueur) + prefixe + charge


def decalage(d: datetime) -> str:
    off = d.utcoffset() or timedelta(0)
    minutes = round(off.total_seconds() / 60)
    signe = "+" if minutes >= 0 else "-"
    a = abs(minutes)
    return f"{signe}{a // 60:02d}:{a % 60:02d}"


def segments(d: datetime, tag: str) -> tuple[bytes, bytes]:
    dt = d.strftime("%Y:%m:%d %H:%M:%S")
    off = decalage(d)
    tiff = _tiff(
        [_ascii(0x0131, LOGICIEL), _ascii(0x0132, dt), {"tag": 0x0213, "type": 3, "value": 1}, {"tag": 0x8769, "type": 4, "value": 0}],
        [{"tag": 0x9000, "type": 7, "bytes": b"0232"}, _ascii(0x9003, dt), _ascii(0x9004, dt),
         _ascii(0x9010, off), _ascii(0x9011, off), _ascii(0x9012, off), {"tag": 0xA001, "type": 3, "value": 1}],
    )
    iso = dt[:10].replace(":", "-") + "T" + dt[11:] + off
    xmp = (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about=""\n'
        '    xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
        '    xmlns:exif="http://ns.adobe.com/exif/1.0/"\n'
        '    xmlns:digiKam="http://www.digikam.org/ns/1.0/"\n'
        '    xmlns:lr="http://ns.adobe.com/lightroom/1.0/"\n'
        f'    xmp:CreatorTool="{LOGICIEL}"\n'
        f'    xmp:CreateDate="{iso}"\n'
        f'    exif:DateTimeOriginal="{iso}">\n'
        f'   <digiKam:TagsList><rdf:Seq><rdf:li>{escape(tag)}</rdf:li></rdf:Seq></digiKam:TagsList>\n'
        f'   <lr:hierarchicalSubject><rdf:Bag><rdf:li>{escape("|".join(tag.split("/")))}</rdf:li></rdf:Bag></lr:hierarchicalSubject>\n'
        '  </rdf:Description>\n'
        ' </rdf:RDF>\n'
        '</x:xmpmeta>\n'
        '<?xpacket end="w"?>'
    )
    return _app1(b"Exif\0\0", tiff), _app1(b"http://ns.adobe.com/xap/1.0/\0", xmp.encode("utf-8"))


def injecter(jpeg: bytes, d: datetime, tag: str) -> bytes:
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("Fichier JPEG invalide")
    pos = 2
    if jpeg[2:4] == b"\xff\xe0":                       # après l'en-tête JFIF
        pos = 4 + struct.unpack(">H", jpeg[4:6])[0]
    exif, xmp = segments(d, tag)
    return jpeg[:pos] + exif + xmp + jpeg[pos:]


def date_prise(annee: int, mois: int, non_datee: bool, secondes: int, heure: int = 12) -> datetime:
    """Date écrite pour une photo : 1er du mois (ou janvier) à l'heure donnée + n secondes ; non datée : 1900 en UTC."""
    if non_datee:
        return datetime(1900, 1, 1, heure, tzinfo=timezone.utc) + timedelta(seconds=secondes)
    base = datetime(annee, mois or 1, 1, heure)
    return (base + timedelta(seconds=secondes)).replace(tzinfo=PARIS)
