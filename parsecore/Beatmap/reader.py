"""Byte-order-mark detection and BOM-aware line decoding for ``.osu`` files.

MIT License

Copyright (c) 2026-Present O!Lib Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import io
import typing

from enum import Enum


class Encoding(Enum):
    """Text encoding of a ``.osu`` file, detected from its byte-order mark."""

    Utf8 = "utf-8"
    Utf16BE = "utf-16-be"
    Utf16LE = "utf-16-le"

    @classmethod
    def from_bom(cls, bom: bytes) -> tuple["Encoding", int]:
        """Detect the encoding from a leading byte-order mark.

        Args:
            bom: The first few bytes of the file.

        Returns:
            A tuple of the detected encoding and the number of BOM bytes that
            should be skipped (``0`` when no BOM is present, defaulting to
            UTF-8).
        """
        if bom.startswith(b"\xef\xbb\xbf"):
            return cls.Utf8, 3
        elif bom.startswith(b"\xff\xfe"):
            return cls.Utf16LE, 2
        elif bom.startswith(b"\xfe\xff"):
            return cls.Utf16BE, 2

        return cls.Utf8, 0


class Decoder:
    """Reads a ``.osu`` byte stream line by line with BOM-aware decoding."""

    def __init__(self, stream: typing.BinaryIO | io.BytesIO):
        """Detect the stream's encoding from its BOM and seek past it.

        Args:
            stream: A binary stream positioned at the start of the file.
        """
        self.stream = stream

        start_pos = self.stream.tell()

        bom_candidate = self.stream.read(3)
        self.encoding, consumed = Encoding.from_bom(bom_candidate)

        self.stream.seek(start_pos + consumed)

    def read_line(self) -> str | None:
        """Read and decode the next line, or ``None`` at end of stream.

        Returns:
            The decoded line with trailing whitespace stripped, or ``None``
            when the stream is exhausted.
        """
        raw_line = self.stream.readline()

        if not raw_line:
            return None

        if self.encoding == Encoding.Utf16LE and raw_line.endswith(b"\n"):
            extra_byte = self.stream.read(1)
            raw_line += extra_byte

        decoded = raw_line.decode(self.encoding.value, errors="replace")

        return decoded.rstrip()
