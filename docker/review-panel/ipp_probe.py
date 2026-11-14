# Copyright (c) 2026 Carmine Gallina - https://github.com/carminegallina
"""Ask an IPP printer what it supports (Get-Printer-Attributes), stdlib only.

Usage: python3 ipp_probe.py <printer ip> [path]   (path defaults to /ipp/print)
"""
import struct
import sys
import urllib.request

CHARSET, LANGUAGE, URI, KEYWORD = 0x47, 0x48, 0x45, 0x44
TEXT_TAGS = {0x35, 0x36, 0x41, 0x42, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49}


def attribute(tag, name, value):
    name, value = name.encode(), value.encode()
    return struct.pack(">BH", tag, len(name)) + name + struct.pack(">H", len(value)) + value


def get_printer_attributes(uri):
    body = struct.pack(">BBHI", 2, 0, 0x000B, 1) + b"\x01"
    body += attribute(CHARSET, "attributes-charset", "utf-8")
    body += attribute(LANGUAGE, "attributes-natural-language", "en")
    body += attribute(URI, "printer-uri", uri)
    body += attribute(KEYWORD, "requested-attributes", "all")
    body += attribute(KEYWORD, "", "media-col-database")
    body += b"\x03"
    request = urllib.request.Request(uri.replace("ipp://", "http://", 1), data=body,
                                     headers={"Content-Type": "application/ipp"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read()


def decode_value(tag, raw):
    if tag in (0x21, 0x23) and len(raw) == 4:
        return struct.unpack(">i", raw)[0]
    if tag == 0x22 and len(raw) == 1:
        return bool(raw[0])
    if tag == 0x33 and len(raw) == 8:
        return struct.unpack(">ii", raw)
    if tag == 0x32 and len(raw) == 9:
        x, y, unit = struct.unpack(">iib", raw)
        return f"{x}x{y}{'dpi' if unit == 3 else 'dpcm'}"
    if tag in TEXT_TAGS:
        return raw.decode("utf-8", "replace")
    if 0x10 <= tag <= 0x1F:
        return {0x10: "unsupported", 0x12: "unknown", 0x13: "no-value"}.get(tag, f"oob-{tag:#x}")
    return raw.hex()


def parse(data):
    """Return (status code, {name: [values]}); collections become dicts."""
    status = struct.unpack(">H", data[2:4])[0]
    attributes = {}
    stack = []          # open collections: [dict, current member name]
    last_name = None    # an empty name adds a value to the previous attribute
    position = 8
    while position < len(data):
        tag = data[position]
        position += 1
        if tag == 0x03:
            break
        if tag < 0x10:  # group delimiter
            continue
        (length,) = struct.unpack(">H", data[position:position + 2])
        name = data[position + 2:position + 2 + length].decode()
        position += 2 + length
        (length,) = struct.unpack(">H", data[position:position + 2])
        raw = data[position + 2:position + 2 + length]
        position += 2 + length

        if tag == 0x4A:  # member name inside the open collection
            stack[-1][1] = raw.decode()
            continue
        if tag == 0x37:  # the innermost collection closes
            stack.pop()
            continue
        value = {} if tag == 0x34 else decode_value(tag, raw)
        if stack:
            collection, member = stack[-1]
            collection.setdefault(member, []).append(value)
        else:
            last_name = name or last_name
            attributes.setdefault(last_name, []).append(value)
        if tag == 0x34:
            stack.append([value, None])
    return status, attributes


if __name__ == "__main__":
    host = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else "/ipp/print"
    status, attributes = parse(get_printer_attributes(f"ipp://{host}:631{path}"))
    print(f"IPP status 0x{status:04x}")
    for key in sorted(attributes):
        if key != "media-col-database":
            print(f"{key}: {attributes[key]}")
    for entry in attributes.get("media-col-database", []):
        print("media-col:", entry)
