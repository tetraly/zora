# Taken with love from Dorkmaster Flek's SMRPG Randomizer

from typing import List, Dict
import hashlib


class Patch:
  """Class representing a patch for a specific seed that can be added to as we build it."""

  def __init__(self) -> None:
    self._data: Dict[int, bytes] = {}

  def __add__(self, other):
    """Add another patch to this patch and return a new Patch object."""
    if not isinstance(other, Patch):
      raise TypeError("Other object is not Patch type")

    patch = Patch()
    patch += self
    patch += other
    return patch

  def __iadd__(self, other):
    """Add another patch to this patch in place."""
    if not isinstance(other, Patch):
      raise TypeError("Other object is not Patch type")

    for addr in other.addresses:
      self.AddData(addr, other.GetData(addr))

    return self

  @property
  def addresses(self):
    """
        :return: List of all addresses in the patch.
        :rtype: list[int]
        """
    return list(self._data.keys())

  def GetAddresses(self) -> List[int]:
    """Returns a List of all addresses in the patch."""
    return list(self._data.keys())

  def GetData(self, addr: int) -> List[int]:
    """Get data in the patch for this address.  
       If the address is not present in the patch, returns empty bytes.
        :param addr: Address for the start of the data.
        :type addr: int
        :rtype: bytearray|bytes|list[int]
        """
    int_data: List[int] = []
    for byte in self._data[addr]:
      int_data.append(byte)
    return int_data

  def AddData(self, addr: int, data: List[int]) -> None:
    """Add data to the patch.
        :param addr: Address for the start of the data.
        :type addr: int
        :param data: Patch data as raw bytes.
        :type data: bytearray|bytes|list[int]|int|str
        """
    self._data[addr] = bytes(data)

  def AddDataFromHexString(self, addr: int, hex_string: str) -> None:
    """Add data to the patch from a hex string.
    
    :param addr: Address for the start of the data.
    :type addr: int
    :param hex_string: Hex string (spaces optional), e.g. "FF95 ACCAD0FB" or "FF95ACCAD0FB"
    :type hex_string: str
    """
    # Remove spaces and any other whitespace
    hex_string = hex_string.replace(" ", "").replace("\n", "").replace("\t", "")
    
    # Convert hex string to bytes
    data = bytes.fromhex(hex_string)
    
    self.AddData(addr, data)

  def RemoveData(self, addr: int) -> None:
    """Remove data from the patch.
        :param addr: Address the data was added to.
        :type addr: int
        """
    if addr in self._data:
      del self._data[addr]

  def for_json(self):
    """Return patch as a JSON serializable object.

        :rtype: list[dict]
        """
    patch = []
    addrs = list(self._data.keys())
    addrs.sort()

    for addr in addrs:
      patch.append({addr: self._data[addr]})

    return patch

  def AddFromIPS(self, ips_file_path: str) -> None:
    """Add patch data from an IPS file.

    IPS (International Patching System) format:
    - Header: "PATCH" (5 bytes)
    - Records: Each record contains:
      - Offset (3 bytes, big-endian)
      - Size (2 bytes, big-endian)
      - Data (size bytes)
      - Special case: If size is 0, it's an RLE record with count (2 bytes) and value (1 byte)
    - Footer: "EOF" (3 bytes)

    :param ips_file_path: Path to the IPS file
    :type ips_file_path: str
    """
    with open(ips_file_path, 'rb') as f:
      # Read and verify header
      header = f.read(5)
      if header != b'PATCH':
        raise ValueError(f"Invalid IPS file: {ips_file_path} (missing PATCH header)")

      while True:
        # Read offset (3 bytes)
        offset_bytes = f.read(3)
        if len(offset_bytes) < 3:
          break

        # Check for EOF marker
        if offset_bytes == b'EOF':
          break

        # Convert offset from big-endian
        offset = (offset_bytes[0] << 16) | (offset_bytes[1] << 8) | offset_bytes[2]

        # Read size (2 bytes)
        size_bytes = f.read(2)
        if len(size_bytes) < 2:
          break

        size = (size_bytes[0] << 8) | size_bytes[1]

        if size == 0:
          # RLE record: read count and value
          count_bytes = f.read(2)
          if len(count_bytes) < 2:
            break
          count = (count_bytes[0] << 8) | count_bytes[1]

          value_byte = f.read(1)
          if len(value_byte) < 1:
            break

          # Add repeated data
          data = [value_byte[0]] * count
          self.AddData(offset, data)
        else:
          # Normal record: read data
          data = f.read(size)
          if len(data) < size:
            break

          self.AddData(offset, list(data))

  def GetHashCode(self) -> bytes:
    to_be_returned = b''
    hash_string = hashlib.sha224()
    for address in self._data.keys():
      hash_string.update(str(address).encode('utf-8'))
      hash_string.update(self._data[address])
    for int_of_hash in hash_string.digest()[0:4]:
      val = int_of_hash & 0x1F
      if val == 0x0E: # Glitchy thing in Triforce of Power's slot -> Clock
        val = 0x21
      elif val == 0x02:  # White sword -> Heart
        val = 0x22
      elif val == 0x07:  # Red candle -> Fairy
        val = 0x23
      to_be_returned += bytes([val])
    return to_be_returned

