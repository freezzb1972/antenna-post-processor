"""
EMQuest Merged CSV Parser
==========================
Streaming parser for the EMQuest "merged" CSV export format.

The merged CSV contains 4 sections:
  - Theta Log Magnitude (dB)
  - Theta Phase (deg)
  - Phi Log Magnitude (dB)
  - Phi Phase (deg)

Each section has 105 frequency blocks, each block is 362 lines:
  1 frequency+theta header + 1 phi+response header + 360 data rows (phi 0-359).
Data is 111 theta angles × 360 phi angles per frequency.

Memory strategy: Build a byte-offset index on first pass, then seek+read
individual frequency blocks on demand. Peak memory ~1.3 MB per frequency.
"""

import os
from typing import List, Tuple, Optional, Dict


class MergedCSVParser:
    """Parser for EMQuest merged CSV with byte-offset indexing."""

    SECTION_NAMES = [
        "Theta Log Magnitude",
        "Theta Phase",
        "Phi Log Magnitude",
        "Phi Phase",
    ]

    def __init__(self, path: str):
        self.path = path
        self._file_size = os.path.getsize(path)
        # Byte offsets: section_name -> list of file positions for each freq block
        self._section_offsets: Dict[str, List[int]] = {}
        self._frequencies: List[float] = []
        self._theta_angles: List[float] = []
        self._phi_angles: List[float] = []
        self._indexed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def frequencies(self) -> List[float]:
        """Return list of frequency values in MHz, in file order."""
        if not self._indexed:
            self._build_index()
        return self._frequencies

    @property
    def theta_angles(self) -> List[float]:
        """Return list of theta angles in degrees."""
        if not self._indexed:
            self._build_index()
        return self._theta_angles

    @property
    def phi_angles(self) -> List[float]:
        """Return list of phi angles in degrees."""
        if not self._indexed:
            self._build_index()
        return self._phi_angles

    @property
    def num_frequencies(self) -> int:
        if not self._indexed:
            self._build_index()
        return len(self._frequencies)

    @property
    def num_theta(self) -> int:
        if not self._indexed:
            self._build_index()
        return len(self._theta_angles)

    @property
    def num_phi(self) -> int:
        if not self._indexed:
            self._build_index()
        return len(self._phi_angles)

    def read_section_block(
        self, section_name: str, freq_index: int
    ) -> List[List[float]]:
        """
        Read one frequency block from a section.

        Args:
            section_name: One of 'Theta Log Magnitude', 'Theta Phase',
                          'Phi Log Magnitude', 'Phi Phase'.
            freq_index: 0-based index into the frequency list.

        Returns:
            2D list [phi_index][theta_index] of float values.
        """
        if not self._indexed:
            self._build_index()

        if section_name not in self._section_offsets:
            raise ValueError(
                f"Unknown section '{section_name}'. "
                f"Expected one of: {self.SECTION_NAMES}"
            )
        offsets = self._section_offsets[section_name]
        if freq_index < 0 or freq_index >= len(offsets):
            raise IndexError(
                f"Frequency index {freq_index} out of range "
                f"[0, {len(offsets)})"
            )

        return self._read_block_at_offset(
            offsets[freq_index], len(self._phi_angles), len(self._theta_angles)
        )

    def read_all_sections_for_freq(
        self, freq_index: int
    ) -> Dict[str, List[List[float]]]:
        """
        Read all 4 sections for a given frequency.

        Returns:
            Dict with keys 'theta_logmag', 'theta_phase',
            'phi_logmag', 'phi_phase', each mapping to a
            2D list [phi][theta].
        """
        key_map = {
            "Theta Log Magnitude": "theta_logmag",
            "Theta Phase": "theta_phase",
            "Phi Log Magnitude": "phi_logmag",
            "Phi Phase": "phi_phase",
        }
        result = {}
        for section_name, key in key_map.items():
            result[key] = self.read_section_block(section_name, freq_index)
        return result

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def _build_index(self):
        """Single-pass scan to find section boundaries and frequency blocks."""
        # Detect encoding (UTF-8 with or without BOM)
        encoding = self._ENCODING

        with open(self.path, "r", encoding=encoding, newline="") as f:
            # We use tell() after each readline to record byte offsets.
            # csv.reader would consume the iterator and lose positions,
            # so we use raw readline and minimal parsing.
            self._section_offsets = {name: [] for name in self.SECTION_NAMES}
            current_section: Optional[str] = None

            while True:
                pos = f.tell()
                line = f.readline()
                if not line:
                    break

                stripped = line.strip()

                # Detect section headers
                section_name = self._detect_section_header(stripped)
                if section_name:
                    current_section = section_name
                    continue

                # Detect frequency block start within a section
                if current_section and self._is_freq_block_start(stripped):
                    freq_val = self._parse_freq_from_line(stripped)
                    if freq_val is not None:
                        if current_section == "Theta Log Magnitude":
                            # Only add frequencies once (from first section)
                            self._frequencies.append(freq_val)
                            # Parse theta angles from first block
                            if not self._theta_angles:
                                self._theta_angles = self._parse_theta_angles(
                                    stripped
                                )
                        self._section_offsets[current_section].append(pos)

                        # Parse phi angles from first block of first section
                        if not self._phi_angles:
                            # Read the next line (phi header) and data lines
                            f.readline()  # skip phi/response header
                            phi_vals = []
                            for _ in range(360):
                                data_line = f.readline()
                                if not data_line:
                                    break
                                phi = self._parse_phi_from_line(data_line.strip())
                                if phi is not None:
                                    phi_vals.append(phi)
                            self._phi_angles = phi_vals

        self._indexed = True

    # ------------------------------------------------------------------
    # Block reading
    # ------------------------------------------------------------------

    def _read_block_at_offset(
        self, offset: int, n_phi: int, n_theta: int
    ) -> List[List[float]]:
        """Read a single frequency block from a given byte offset."""
        encoding = self._ENCODING
        with open(self.path, "r", encoding=encoding, newline="") as f:
            f.seek(offset)

            # Skip the frequency+theta header line
            f.readline()
            # Skip the phi+response header line
            f.readline()

            # Read phi data lines
            data = []
            for _ in range(n_phi):
                line = f.readline()
                if not line:
                    break
                values = self._parse_phi_data_line(line.strip(), n_theta)
                data.append(values)

        return data

    # ------------------------------------------------------------------
    # Line-level parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_section_header(line: str) -> Optional[str]:
        """Check if a line is a section header."""
        for name in MergedCSVParser.SECTION_NAMES:
            if line.startswith(name + ","):
                return name
        return None

    @staticmethod
    def _is_freq_block_start(line: str) -> bool:
        """Check if a line starts a frequency block: starts with ',<digits>,' followed by Theta Angle."""
        if not line.startswith(","):
            return False
        parts = line.split(",")
        if len(parts) < 3:
            return False
        freq_str = parts[1].strip()
        try:
            float(freq_str)
            return "Theta Angle" in line
        except (ValueError, IndexError):
            return False

    @staticmethod
    def _parse_freq_from_line(line: str) -> Optional[float]:
        """Extract frequency value from a block start line: ',<freq>,Theta Angle...'."""
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                return float(parts[1].strip())
            except (ValueError, IndexError):
                pass
        return None

    @staticmethod
    def _parse_theta_angles(line: str) -> List[float]:
        """Extract theta angles from a frequency header line.
        Format: ',<freq>,Theta Angle  (?,0,1,2,...,110,...'
        """
        parts = line.split(",")
        theta_vals = []
        # Skip first 3 parts: empty, freq, "Theta Angle  (?"
        for part in parts[3:]:
            part = part.strip()
            try:
                theta_vals.append(float(part))
            except (ValueError, IndexError):
                pass
        return theta_vals

    @staticmethod
    def _parse_phi_from_line(line: str) -> Optional[float]:
        """Extract phi angle from a data line: ',,<phi>,<val0>,...'."""
        parts = line.split(",")
        if len(parts) >= 3:
            try:
                return float(parts[2].strip())
            except (ValueError, IndexError):
                pass
        return None

    @staticmethod
    def _parse_phi_data_line(line: str, n_theta: int) -> List[float]:
        """Parse a phi data line into list of theta values.
        Format: ',,<phi>,<val0>,<val1>,...,<valN>,...'
        """
        parts = line.split(",")
        values = []
        # Data starts at index 3 (after empty, empty, phi)
        for part in parts[3 : 3 + n_theta]:
            try:
                values.append(float(part.strip()))
            except (ValueError, IndexError):
                values.append(0.0)
        # Pad if needed
        while len(values) < n_theta:
            values.append(0.0)
        return values

    _ENCODING = "utf-8-sig"  # EMQuest files are UTF-8-BOM
