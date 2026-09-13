"""Build synthetic APKs (zip + APK Signing Block) for apk_cert.py tests.

Stdlib only. Constructs a real zip with a single entry, then splices an APK
Signing Block (v2/v3/v3.1 pairs, each carrying a bare X.509 DER certificate)
in between the local entries and the central directory, exactly where
apk_cert.py's `_signing_block` expects to find it.

Wire format (see plugins/appfactory-core/runtime/bin/apk_cert.py):

    [u64 size]                  <- excludes this field, includes everything below
    pair*  { u64 length; u32 id; bytes value }   <- length excludes itself, includes id+value
    [u64 size]                  (repeated)
    16 bytes  b"APK Sig Block 42"

Each pair's `value`, for the ids this suite cares about, is a signer block
walk: u32 signers_len, u32 signer_len, u32 signed_data_len, u32 digests_len
(kept 0 here), u32 certs_len, u32 cert_len, DER bytes. None of the length
fields except digests_len and cert_len are actually consulted by
first_cert_der() -- it walks them positionally -- so the first four u32s can
be zero.
"""
from __future__ import annotations

import io
import struct
import zipfile

MAGIC = b"APK Sig Block 42"


def _pair_value(der: bytes) -> bytes:
    """Wrap a bare X.509 DER cert in the signer-block layout apk_cert.py walks."""
    return (
        struct.pack("<4I", 0, 0, 0, 0)  # signers_len, signer_len, signed_data_len, digests_len
        + struct.pack("<I", 0)  # certs_len
        + struct.pack("<I", len(der))  # cert_len
        + der
    )


def _encode_pairs(certs: dict[int, bytes]) -> bytes:
    out = b""
    for pid, der in certs.items():
        value = _pair_value(der)
        length = 4 + len(value)  # id (4 bytes) + value
        out += struct.pack("<Q", length) + struct.pack("<I", pid) + value
    return out


def signing_block(certs: dict[int, bytes]) -> bytes:
    """The full APK Signing Block (leading size, pairs, trailing size, magic)."""
    pairs = _encode_pairs(certs)
    size = len(pairs) + 24  # trailing size (8) + magic (16), excluding the leading size field
    return struct.pack("<Q", size) + pairs + struct.pack("<Q", size) + MAGIC


def make_apk(path, certs: dict[int, bytes]) -> None:
    """Write a minimal zip at `path` carrying an APK Signing Block for `certs`.

    `certs` maps a scheme id (apk_cert.V2_ID / V3_ID / V31_ID) to a bare
    X.509 DER certificate.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("AndroidManifest.xml", b"not a real manifest, just an entry")
    data = bytearray(buf.getvalue())

    eocd_idx = data.rfind(b"PK\x05\x06")
    if eocd_idx < 0:
        raise AssertionError("zipfile did not produce an EOCD record")
    cd_offset = struct.unpack_from("<I", data, eocd_idx + 16)[0]

    block = signing_block(certs)
    new_data = bytearray(bytes(data[:cd_offset]) + block + bytes(data[cd_offset:]))

    new_eocd_idx = eocd_idx + len(block)
    new_cd_offset = cd_offset + len(block)
    struct.pack_into("<I", new_data, new_eocd_idx + 16, new_cd_offset)

    with open(path, "wb") as fh:
        fh.write(new_data)


def make_plain_zip(path) -> None:
    """A well-formed zip with no APK Signing Block at all."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("AndroidManifest.xml", b"not a real manifest, just an entry")
