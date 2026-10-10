"""A small 6502 interpreter for unit tests of patch routines
(tests/test_progressive_patches.py).

It runs one routine of a ROM image with chosen registers and memory and
reports the registers and memory afterwards, so a test can state what a
routine keeps and returns, which the emulator (tests/emulator.py) cannot
observe. Only the instructions the tested routines use are implemented
(an unknown opcode raises); no decimal mode, no V flag, no interrupts.

Memory: CPU RAM ($0000-$07FF, mirrored), work RAM ($6000-$7FFF) and the
switched bank at $8000 with the fixed bank 7 at $C000. Calls (JSR or JMP)
to an address in `stubs` run the stub instead and return, as RTS would.
"""
from collections.abc import Callable
from dataclasses import dataclass, field

NES_HEADER_SIZE = 0x10
BANK_SIZE = 0x4000
FIXED_BANK = 7
RAM_SIZE = 0x800
WORK_RAM_BASE, WORK_RAM_SIZE = 0x6000, 0x2000
SWITCHED_BASE, FIXED_BASE = 0x8000, 0xC000
STACK_BASE = 0x100
RETURN_SENTINEL = 0xFFFF            # a call() returns when an RTS lands here
STEP_LIMIT = 10_000

N_FLAG, Z_FLAG, C_FLAG = 0x80, 0x02, 0x01


@dataclass
class CPU:
    rom: bytes
    bank: int
    a: int = 0
    x: int = 0
    y: int = 0
    sp: int = 0xFF
    p: int = 0
    pc: int = 0
    ram: bytearray = field(default_factory=lambda: bytearray(RAM_SIZE))
    work_ram: bytearray = field(default_factory=lambda: bytearray(WORK_RAM_SIZE))
    stubs: dict[int, Callable[["CPU"], None]] = field(default_factory=dict)

    # --- memory ---------------------------------------------------------------

    def read(self, address: int) -> int:
        if address < 0x2000:
            return self.ram[address % RAM_SIZE]
        if WORK_RAM_BASE <= address < SWITCHED_BASE:
            return self.work_ram[address - WORK_RAM_BASE]
        bank, base = (self.bank, SWITCHED_BASE) if address < FIXED_BASE else (FIXED_BANK, FIXED_BASE)
        if address >= SWITCHED_BASE:
            return self.rom[NES_HEADER_SIZE + bank * BANK_SIZE + address - base]
        raise ValueError(f"read of ${address:04X}")

    def write(self, address: int, value: int) -> None:
        if address < 0x2000:
            self.ram[address % RAM_SIZE] = value
        elif WORK_RAM_BASE <= address < SWITCHED_BASE:
            self.work_ram[address - WORK_RAM_BASE] = value
        else:
            raise ValueError(f"write of ${address:04X}")

    def __getitem__(self, address: int) -> int:
        return self.read(address)

    def __setitem__(self, address: int, value: int) -> None:
        self.write(address, value)

    def load_work_ram(self, address: int, data: bytes) -> None:
        self.work_ram[address - WORK_RAM_BASE:address - WORK_RAM_BASE + len(data)] = data

    # --- flags and stack --------------------------------------------------------

    @property
    def carry(self) -> bool:
        return bool(self.p & C_FLAG)

    def _set_nz(self, value: int) -> int:
        value &= 0xFF
        self.p = self.p & ~(N_FLAG | Z_FLAG) | (value & N_FLAG) | (0 if value else Z_FLAG)
        return value

    def _set_carry(self, on: bool) -> None:
        self.p = self.p | C_FLAG if on else self.p & ~C_FLAG

    def _push(self, value: int) -> None:
        self.write(STACK_BASE + self.sp, value & 0xFF)
        self.sp = (self.sp - 1) & 0xFF

    def _pull(self) -> int:
        self.sp = (self.sp + 1) & 0xFF
        return self.read(STACK_BASE + self.sp)

    # --- running ----------------------------------------------------------------

    def call(self, address: int) -> None:
        """Run the routine at `address` until it returns."""
        self._push(RETURN_SENTINEL >> 8)
        self._push((RETURN_SENTINEL - 1) & 0xFF)
        self.pc = address
        for _ in range(STEP_LIMIT):
            if self.pc == RETURN_SENTINEL:
                return
            self.step()
        raise AssertionError(f"no return within {STEP_LIMIT} instructions")

    def _fetch(self) -> int:
        value = self.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def _operand_address(self, mode: str) -> int:
        if mode == "zp":
            return self._fetch()
        low = self._fetch()
        address = self._fetch() << 8 | low
        if mode == "abs":
            return address
        return (address + (self.x if mode == "absx" else self.y)) & 0xFFFF

    def _value(self, mode: str) -> int:
        return self._fetch() if mode == "imm" else self.read(self._operand_address(mode))

    def _compare(self, register: int, value: int) -> None:
        self._set_carry(register >= value)
        self._set_nz(register - value)

    def _add(self, value: int) -> None:
        total = self.a + value + (1 if self.carry else 0)
        self._set_carry(total > 0xFF)
        self.a = self._set_nz(total)

    def _return_from_stub(self, address: int) -> bool:
        stub = self.stubs.get(address)
        if stub is None:
            return False
        stub(self)
        return True

    def step(self) -> None:
        opcode = self._fetch()
        if opcode in LOADS_AND_ALU:
            op, mode = LOADS_AND_ALU[opcode]
            value = self._value(mode)
            if op == "LDA":
                self.a = self._set_nz(value)
            elif op == "LDX":
                self.x = self._set_nz(value)
            elif op == "LDY":
                self.y = self._set_nz(value)
            elif op == "AND":
                self.a = self._set_nz(self.a & value)
            elif op == "ORA":
                self.a = self._set_nz(self.a | value)
            elif op == "EOR":
                self.a = self._set_nz(self.a ^ value)
            elif op == "ADC":
                self._add(value)
            elif op == "SBC":
                self._add(value ^ 0xFF)
            elif op == "CMP":
                self._compare(self.a, value)
            elif op == "CPX":
                self._compare(self.x, value)
            elif op == "CPY":
                self._compare(self.y, value)
        elif opcode in STORES:
            register, mode = STORES[opcode]
            self.write(self._operand_address(mode), getattr(self, register))
        elif opcode in INCREMENTS:
            step, mode = INCREMENTS[opcode]
            address = self._operand_address(mode)
            self.write(address, self._set_nz(self.read(address) + step))
        elif opcode in BRANCHES:
            flag, taken_when = BRANCHES[opcode]
            offset = self._fetch()
            if bool(self.p & flag) == taken_when:
                self.pc = (self.pc + (offset - 0x100 if offset & 0x80 else offset)) & 0xFFFF
        elif opcode == 0x20:                                # JSR abs
            target = self._operand_address("abs")
            if not self._return_from_stub(target):
                return_address = (self.pc - 1) & 0xFFFF
                self._push(return_address >> 8)
                self._push(return_address & 0xFF)
                self.pc = target
        elif opcode == 0x4C:                                # JMP abs
            target = self._operand_address("abs")
            if self._return_from_stub(target):
                self._rts()
            else:
                self.pc = target
        elif opcode == 0x60:                                # RTS
            self._rts()
        elif opcode in IMPLIED:
            IMPLIED[opcode](self)
        else:
            raise NotImplementedError(f"opcode ${opcode:02X} at ${(self.pc - 1) & 0xFFFF:04X}")

    def _rts(self) -> None:
        low = self._pull()
        self.pc = ((self._pull() << 8 | low) + 1) & 0xFFFF


LOADS_AND_ALU: dict[int, tuple[str, str]] = {
    0xA9: ("LDA", "imm"), 0xA5: ("LDA", "zp"), 0xAD: ("LDA", "abs"), 0xBD: ("LDA", "absx"), 0xB9: ("LDA", "absy"),
    0xA2: ("LDX", "imm"), 0xA6: ("LDX", "zp"), 0xAE: ("LDX", "abs"),
    0xA0: ("LDY", "imm"), 0xA4: ("LDY", "zp"), 0xAC: ("LDY", "abs"), 0xBC: ("LDY", "absx"),
    0x29: ("AND", "imm"), 0x25: ("AND", "zp"), 0x2D: ("AND", "abs"), 0x3D: ("AND", "absx"), 0x39: ("AND", "absy"),
    0x09: ("ORA", "imm"), 0x05: ("ORA", "zp"), 0x0D: ("ORA", "abs"), 0x1D: ("ORA", "absx"), 0x19: ("ORA", "absy"),
    0x49: ("EOR", "imm"), 0x45: ("EOR", "zp"), 0x4D: ("EOR", "abs"),
    0x69: ("ADC", "imm"), 0x65: ("ADC", "zp"), 0x6D: ("ADC", "abs"), 0x7D: ("ADC", "absx"), 0x79: ("ADC", "absy"),
    0xE9: ("SBC", "imm"), 0xE5: ("SBC", "zp"), 0xED: ("SBC", "abs"),
    0xC9: ("CMP", "imm"), 0xC5: ("CMP", "zp"), 0xCD: ("CMP", "abs"), 0xDD: ("CMP", "absx"), 0xD9: ("CMP", "absy"),
    0xE0: ("CPX", "imm"), 0xC0: ("CPY", "imm"),
}
STORES: dict[int, tuple[str, str]] = {
    0x85: ("a", "zp"), 0x8D: ("a", "abs"), 0x9D: ("a", "absx"), 0x99: ("a", "absy"),
    0x86: ("x", "zp"), 0x8E: ("x", "abs"), 0x84: ("y", "zp"), 0x8C: ("y", "abs"),
}
# INC and DEC: (step, addressing mode).
INCREMENTS: dict[int, tuple[int, str]] = {0xE6: (1, "zp"), 0xEE: (1, "abs"), 0xC6: (-1, "zp"), 0xCE: (-1, "abs")}
BRANCHES: dict[int, tuple[int, bool]] = {
    0x10: (N_FLAG, False), 0x30: (N_FLAG, True), 0x90: (C_FLAG, False), 0xB0: (C_FLAG, True),
    0xD0: (Z_FLAG, False), 0xF0: (Z_FLAG, True),
}


def _tax(cpu: CPU) -> None:
    cpu.x = cpu._set_nz(cpu.a)


def _tay(cpu: CPU) -> None:
    cpu.y = cpu._set_nz(cpu.a)


def _txa(cpu: CPU) -> None:
    cpu.a = cpu._set_nz(cpu.x)


def _tya(cpu: CPU) -> None:
    cpu.a = cpu._set_nz(cpu.y)


def _inx(cpu: CPU) -> None:
    cpu.x = cpu._set_nz(cpu.x + 1)


def _iny(cpu: CPU) -> None:
    cpu.y = cpu._set_nz(cpu.y + 1)


def _dex(cpu: CPU) -> None:
    cpu.x = cpu._set_nz(cpu.x - 1)


def _dey(cpu: CPU) -> None:
    cpu.y = cpu._set_nz(cpu.y - 1)


def _pha(cpu: CPU) -> None:
    cpu._push(cpu.a)


def _pla(cpu: CPU) -> None:
    cpu.a = cpu._set_nz(cpu._pull())


def _clc(cpu: CPU) -> None:
    cpu._set_carry(False)


def _sec(cpu: CPU) -> None:
    cpu._set_carry(True)


def _nop(cpu: CPU) -> None:
    pass


IMPLIED: dict[int, Callable[[CPU], None]] = {
    0xAA: _tax, 0xA8: _tay, 0x8A: _txa, 0x98: _tya, 0xE8: _inx, 0xC8: _iny, 0xCA: _dex, 0x88: _dey,
    0x48: _pha, 0x68: _pla, 0x18: _clc, 0x38: _sec, 0xEA: _nop,
}
