/**
 * ZORA — Zelda One Randomizer App
 * Vanilla JS frontend. No build step required.
 *
 * Flag encoding matches flags_generated.py exactly:
 *   - Base64 alphabet: A-Z0-9!@a-z
 *   - LSB-first bit packing, 6 bits per character
 *   - Each flag placed at its permanent bit_offset (main) or cosmetic_bit_offset (cosmetic)
 *   - Cosmetic flags are encoded in a separate string that does not affect the seed hash
 *   - No version prefix
 */

// ---------------------------------------------------------------------------
// Flag codec — must stay in sync with flags_generated.py
// ---------------------------------------------------------------------------

const BASE64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@abcdefghijklmnopqrstuvwxyz'

// Set once from the /flags API response.
let flagStringLength = null
let cosmeticFlagStringLength = null

/**
 * Encode flag state to a flag string.
 * flagDefs: array of {id, bit_offset OR cosmetic_bit_offset, bits, type, values}
 * state: {flagId: value} where value is:
 *   tristate: 0 (off) | 1 (on) | 2 (random)
 *   item/enum: integer index
 *   bool:     0 | 1
 * length: total number of characters in the output string
 * offsetField: 'bit_offset' for main flags, 'cosmetic_bit_offset' for cosmetic flags
 */
function encodeFlags(flagDefs, state, length, offsetField) {
  let bitfield = BigInt(0)
  for (const def of flagDefs) {
    const raw = BigInt(state[def.id] ?? 0)
    const mask = (BigInt(1) << BigInt(def.bits)) - BigInt(1)
    bitfield |= (raw & mask) << BigInt(def[offsetField])
  }
  const chars = []
  for (let i = 0; i < length; i++) {
    chars.push(BASE64[Number(bitfield & BigInt(63))])
    bitfield >>= BigInt(6)
  }
  return chars.join('')
}

/**
 * Decode a flag string to flag state.
 * Returns null if the string contains invalid characters or is too long.
 * Short strings are right-padded with 'A' (vanilla defaults).
 * offsetField: 'bit_offset' for main flags, 'cosmetic_bit_offset' for cosmetic flags
 */
function decodeFlags(flagDefs, str, length, offsetField) {
  str = str.padEnd(length, 'A')
  if (str.length > length) return null

  let bitfield = BigInt(0)
  for (let i = 0; i < length; i++) {
    const idx = BASE64.indexOf(str[i])
    if (idx < 0) return null
    bitfield |= BigInt(idx) << BigInt(i * 6)
  }

  const state = {}
  for (const def of flagDefs) {
    const mask = (BigInt(1) << BigInt(def.bits)) - BigInt(1)
    const raw = Number((bitfield >> BigInt(def[offsetField])) & mask)
    if (def.type === 'tristate') {
      state[def.id] = Math.min(raw, 2)  // clamp; 3 is invalid → 0 (off)
    } else if (def.type === 'item' || def.type === 'enum') {
      state[def.id] = raw
    } else if (def.type === 'color') {
      state[def.id] = raw  // raw 6-bit value
    } else {
      state[def.id] = raw ? 1 : 0
    }
  }
  return state
}

function defaultState(flagDefs) {
  const state = {}
  for (const def of flagDefs) {
    if (def.type === 'tristate') {
      state[def.id] = 0
    } else if (def.type === 'item' || def.type === 'enum') {
      // Both item and enum flags use v.index (always present in API response)
      const found = (def.values ?? []).find(v => v.id === def.default)
      state[def.id] = found ? found.index : 0
    } else if (def.type === 'color') {
      state[def.id] = typeof def.default === 'number' ? def.default : 0
    } else {
      state[def.id] = 0
    }
  }
  return state
}

// ---------------------------------------------------------------------------
// IPS patcher
// ---------------------------------------------------------------------------

function applyIpsPatch(rom, patch) {
  const MAGIC = [0x50, 0x41, 0x54, 0x43, 0x48] // "PATCH"
  const EOF_MARKER = 0x454f46

  for (let i = 0; i < 5; i++) {
    if (patch[i] !== MAGIC[i]) throw new Error('Invalid IPS patch: bad header magic')
  }

  const result = new Uint8Array(rom)
  let pos = 5

  while (pos + 3 <= patch.length) {
    const offset = (patch[pos] << 16) | (patch[pos + 1] << 8) | patch[pos + 2]
    pos += 3
    if (offset === EOF_MARKER) break
    if (pos + 2 > patch.length) break

    const size = (patch[pos] << 8) | patch[pos + 1]
    pos += 2

    if (size === 0) {
      // RLE record
      if (pos + 3 > patch.length) break
      const rleSize = (patch[pos] << 8) | patch[pos + 1]
      const rleByte = patch[pos + 2]
      pos += 3
      result.fill(rleByte, offset, offset + rleSize)
    } else {
      const data = patch.slice(pos, pos + size)
      pos += size
      result.set(data, offset)
    }
  }
  return result
}

// ---------------------------------------------------------------------------
// Dark mode
// ---------------------------------------------------------------------------

function initDarkMode() {
  const saved = localStorage.getItem('zora-theme')
  if (saved) document.documentElement.setAttribute('data-theme', saved)
  // If no saved pref, prefers-color-scheme CSS handles it automatically

  document.getElementById('dark-mode-btn').addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme')
    // Determine actual current mode (accounting for system pref)
    const isDark = current === 'dark' ||
      (!current && window.matchMedia('(prefers-color-scheme: dark)').matches)
    const next = isDark ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', next)
    localStorage.setItem('zora-theme', next)
    document.getElementById('dark-mode-btn').textContent = next === 'dark' ? '☀️' : '🌙'
  })

  // Set initial icon
  const saved2 = localStorage.getItem('zora-theme')
  const isDark = saved2 === 'dark' ||
    (!saved2 && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.getElementById('dark-mode-btn').textContent = isDark ? '☀️' : '🌙'

  // Highlight Z, O, R, A in the subtitle
  const subtitle = document.getElementById('header-subtitle')
  const text = subtitle.textContent
  const targets = { Z: 0, O: 0, R: 0, A: 0 }
  subtitle.textContent = ''
  for (const ch of text) {
    if (ch in targets && targets[ch] === 0) {
      targets[ch]++
      const s = document.createElement('span')
      s.style.color = 'var(--color-accent)'
      s.textContent = ch
      subtitle.appendChild(s)
    } else {
      subtitle.appendChild(document.createTextNode(ch))
    }
  }
}

// ---------------------------------------------------------------------------
// IndexedDB ROM persistence
// ---------------------------------------------------------------------------

const ROM_DB_NAME    = 'zora-db'
const ROM_DB_VERSION = 1
const ROM_STORE      = 'rom'
const ROM_KEY        = 'last'

function openRomDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(ROM_DB_NAME, ROM_DB_VERSION)
    req.onupgradeneeded = (e) => e.target.result.createObjectStore(ROM_STORE)
    req.onsuccess = (e) => resolve(e.target.result)
    req.onerror   = (e) => reject(e.target.error)
  })
}

async function saveRomToDb(file) {
  try {
    const bytes = new Uint8Array(await file.arrayBuffer())
    const db = await openRomDb()
    const tx = db.transaction(ROM_STORE, 'readwrite')
    tx.objectStore(ROM_STORE).put({ name: file.name, bytes }, ROM_KEY)
    await new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = (e) => rej(e.target.error) })
    db.close()
  } catch (err) {
    console.warn('[ZORA] Could not save ROM to IndexedDB:', err)
  }
}

async function loadRomFromDb() {
  try {
    const db = await openRomDb()
    const tx = db.transaction(ROM_STORE, 'readonly')
    const record = await new Promise((res, rej) => {
      const req = tx.objectStore(ROM_STORE).get(ROM_KEY)
      req.onsuccess = (e) => res(e.target.result)
      req.onerror   = (e) => rej(e.target.error)
    })
    db.close()
    if (!record) return null
    return new File([record.bytes], record.name)
  } catch (err) {
    console.warn('[ZORA] Could not load ROM from IndexedDB:', err)
    return null
  }
}

async function clearRomFromDb() {
  try {
    const db = await openRomDb()
    const tx = db.transaction(ROM_STORE, 'readwrite')
    tx.objectStore(ROM_STORE).delete(ROM_KEY)
    db.close()
  } catch (err) {
    console.warn('[ZORA] Could not clear ROM from IndexedDB:', err)
  }
}

// ---------------------------------------------------------------------------
// localStorage persistence
// ---------------------------------------------------------------------------

const STORAGE_KEYS = {
  flagString:          'zora-flag-string',
  cosmeticFlagString:  'zora-cosmetic-flag-string',
  seed:                'zora-seed',
  activeTab:           'zora-active-tab',
}

/**
 * Save the current ROM filename, flag string, and seed to localStorage.
 * Call this any time one of those values changes.
 */
function saveSession() {
  const flagString         = document.getElementById('flag-string-input')?.value ?? ''
  const cosmeticFlagString = document.getElementById('cosmetic-flag-string-input')?.value ?? ''
  const seed               = document.getElementById('seed-input')?.value ?? ''

  if (flagString) {
    localStorage.setItem(STORAGE_KEYS.flagString, flagString)
  }
  if (cosmeticFlagString) {
    localStorage.setItem(STORAGE_KEYS.cosmeticFlagString, cosmeticFlagString)
  }
  if (seed) {
    localStorage.setItem(STORAGE_KEYS.seed, seed)
  }
}

/**
 * Restore the seed from localStorage and auto-load the last ROM from
 * IndexedDB (flag string is applied later, after the flags section finishes
 * loading its schema).
 * Returns the saved flag strings (or null) so initFlagsSection() can apply them.
 */
async function loadSession() {
  // Restore seed right away — the element already exists at DOMContentLoaded
  const savedSeed = localStorage.getItem(STORAGE_KEYS.seed)
  if (savedSeed) {
    const seedInput = document.getElementById('seed-input')
    if (seedInput) seedInput.value = savedSeed
  }

  // Try to auto-load the last ROM from IndexedDB
  const savedFile = await loadRomFromDb()
  if (savedFile) {
    await setRomFile(savedFile)
  }

  // Return saved flag strings so initFlagsSection() can apply them after schema loads
  return {
    flagString:         localStorage.getItem(STORAGE_KEYS.flagString),
    cosmeticFlagString: localStorage.getItem(STORAGE_KEYS.cosmeticFlagString),
  }
}

// ---------------------------------------------------------------------------
// ROM section / version detection
// ---------------------------------------------------------------------------

// Graphics data lives at these file offsets (iNES header included).
// Zeroing this region before hashing allows custom-graphics ROMs to
// match the same version fingerprint as a vanilla ROM.
const GRAPHICS_REGION_START = 0xC12A
const GRAPHICS_REGION_END   = 0x10000  // exclusive

// iNES header size. Hashing starts after this to match No-Intro "ROM SHA-1".
const NES_HEADER_SIZE = 0x10

// File offset and encoded bytes for the "RANDOMIZER" string written by ZORA
// to the title screen.  Used to identify pre-randomized ROMs for re-randomization.
const TITLE_VERSION_OFFSET  = 0x1AB19
const RANDOMIZER_MAGIC      = new Uint8Array([0x1B, 0x0A, 0x17, 0x0D, 0x18, 0x16, 0x12, 0x23, 0x0E, 0x1B])

// Returns true if romBytes contains the RANDOMIZER_MAGIC at TITLE_VERSION_OFFSET.
function isRandomizerRom(romBytes) {
  if (romBytes.length < TITLE_VERSION_OFFSET + RANDOMIZER_MAGIC.length) return false
  for (let i = 0; i < RANDOMIZER_MAGIC.length; i++) {
    if (romBytes[TITLE_VERSION_OFFSET + i] !== RANDOMIZER_MAGIC[i]) return false
  }
  return true
}

// Known ROM versions, identified by two SHA-1 hashes of the PRG data
// (bytes after the 16-byte iNES header):
//   intact_sha1  — hash of the unmodified PRG (matches No-Intro ROM SHA-1)
//   zeroed_sha1  — hash after zeroing GRAPHICS_REGION_START..GRAPHICS_REGION_END
//                  (matches custom-graphics ROMs whose program data is unchanged)
//
// To add a new version: run detectRomVersion() on a known-good ROM and log
// both hashes, then append an entry here with the next integer version index.
const KNOWN_ROM_VERSIONS = [
  {
    version: 0,
    label: 'PRG0',
    intact_sha1: 'A12D74C73A0481599A5D832361D168F4737BBCF6',
    zeroed_sha1: 'B6268D665E22DCD2A0B416C48F7EEA92A75515F4',
  },
  {
    version: 1,
    label: 'PRG1',
    intact_sha1: 'BE2F5DC8C5BA8EC1A344A71F9FB204750AF24FE7',
    zeroed_sha1: '97937BADCC7853E21256496D1FF0CE0750FFEC2F',
  },
]

// Hex-encode a Uint8Array as an uppercase hex string.
function toHex(bytes) {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0').toUpperCase()).join('')
}

// Compute SHA-1 of a Uint8Array. Returns an uppercase hex string.
async function sha1Hex(bytes) {
  // Use .buffer directly only if bytes owns the full ArrayBuffer (no offset/length).
  // slice() always returns an independent ArrayBuffer, avoiding the shared-buffer pitfall.
  const buf = bytes.buffer.byteLength === bytes.byteLength && bytes.byteOffset === 0
    ? bytes.buffer
    : bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  const digest = await crypto.subtle.digest('SHA-1', buf)
  return toHex(new Uint8Array(digest))
}

// Detect PRG version from raw file bytes (including iNES header).
// Strategy:
//   1. Hash the intact PRG data — matches standard (unmodified) ROMs.
//   2. Zero the graphics region and hash again — matches custom-graphics ROMs
//      whose program data is otherwise identical to a known version.
// Returns {version: int, label: string} or null if unrecognised.
async function detectRomVersion(romBytes) {
  const prg = romBytes.subarray(NES_HEADER_SIZE)
  const intactHash = await sha1Hex(prg)

  // Always compute zeroed hash so we can log it for populating zeroed_sha1 entries
  const copy = new Uint8Array(romBytes)
  copy.fill(0, GRAPHICS_REGION_START, GRAPHICS_REGION_END)
  const zeroedHash = await sha1Hex(copy.subarray(NES_HEADER_SIZE))

  for (const entry of KNOWN_ROM_VERSIONS) {
    if (entry.intact_sha1 && entry.intact_sha1 === intactHash) {
      if (!entry.zeroed_sha1) {
        console.info(`[ZORA] ${entry.label} zeroed_sha1: ${zeroedHash}`)
      }
      return entry
    }
  }

  for (const entry of KNOWN_ROM_VERSIONS) {
    if (entry.zeroed_sha1 && entry.zeroed_sha1 === zeroedHash) return entry
  }

  console.warn(`[ZORA] Unknown ROM. intact_sha1=${intactHash} zeroed_sha1=${zeroedHash}`)
  return null
}

let romFile = null
let romVersion = null    // integer (0 = PRG0, 1 = PRG1) or null if not yet detected
let romIsCustom = false  // true when the ROM was identified as a ZORA-randomized ROM

async function setRomFile(file) {
  romFile = file
  romVersion = null
  romIsCustom = false

  const hint = document.getElementById('rom-dropzone-hint')
  const label = document.getElementById('rom-file-label')
  const dropzone = document.getElementById('rom-dropzone')
  const versionRow = document.getElementById('rom-version-row')
  const versionBadge = document.getElementById('rom-version-badge')
  const versionError = document.getElementById('rom-version-error')

  if (file) {
    hint.style.display = 'none'
    label.textContent = file.name
    label.style.display = ''
    dropzone.classList.add('rom-dropzone--filled')

    // Reset version display while we detect
    versionRow.style.display = ''
    versionBadge.style.display = 'none'
    versionBadge.textContent = ''
    versionBadge.className = 'rom-version-badge'
    versionError.style.display = 'none'
    versionError.textContent = ''

    const romBytes = new Uint8Array(await file.arrayBuffer())
    const detected = await detectRomVersion(romBytes)

    if (detected) {
      romVersion = detected.version
      versionBadge.textContent = detected.label
      versionBadge.style.display = ''
    } else if (isRandomizerRom(romBytes)) {
      romIsCustom = true
      versionBadge.textContent = 'Custom'
      versionBadge.className = 'rom-version-badge rom-version-badge--custom'
      versionBadge.style.display = ''
    } else {
      versionError.textContent =
        'This does not appear to be a valid LoZ ROM. ' +
        'If you believe this is incorrect, please ask for help in the ZORA Discord.'
      versionError.style.display = ''
    }

    // Persist the ROM binary for auto-load on next page visit
    saveRomToDb(file)
  } else {
    hint.style.display = ''
    label.style.display = 'none'
    label.textContent = ''
    dropzone.classList.remove('rom-dropzone--filled')
    versionRow.style.display = 'none'
    clearRomFromDb()
  }

  updateGenerateButton()
}

function initRomSection() {
  const input = document.getElementById('rom-input')
  const dropzone = document.getElementById('rom-dropzone')
  const dropText = document.getElementById('rom-dropzone-text')

  // Click anywhere on the drop zone opens the file picker
  dropzone.addEventListener('click', () => input.click())
  dropzone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') input.click()
  })

  input.addEventListener('change', async () => {
    await setRomFile(input.files[0] ?? null)
    input.value = ''
  })

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault()
    dropzone.classList.add('rom-dropzone--active')
    dropText.textContent = 'Drop to select'
  })

  dropzone.addEventListener('dragleave', (e) => {
    if (!dropzone.contains(e.relatedTarget)) {
      dropzone.classList.remove('rom-dropzone--active')
      dropText.textContent = 'Drop ROM here'
    }
  })

  dropzone.addEventListener('drop', async (e) => {
    e.preventDefault()
    dropzone.classList.remove('rom-dropzone--active')
    dropText.textContent = 'Drop ROM here'
    await setRomFile(e.dataTransfer.files[0] ?? null)
  })
}

// ---------------------------------------------------------------------------
// Flags section
// ---------------------------------------------------------------------------

let flagDefs = []            // all flag definitions from /flags (main + cosmetic)
let mainFlagDefs = []        // non-cosmetic flags only (packed into flag_string)
let cosmeticFlagDefs = []    // cosmetic flags only (packed into cosmetic_flag_string)
let itemEnum = []            // [{id, index, label}, ...]
let nesColorPalette = []     // [{index, hex, label, excluded?}, ...] from /flags
let flagState = {}           // {flagId: raw int value} — covers both main and cosmetic
let coercedFlags = new Set()

// Convert a raw integer flag value to its string id for constraint comparison.
function flagValueToId(def, raw) {
  if (def.type === 'tristate' || def.type === 'bool') {
    return raw === 0 ? 'off' : raw === 1 ? 'on' : 'random'
  }
  if (def.type === 'item') {
    return itemEnum.find(e => e.index === raw)?.id ?? 'random'
  }
  if (def.type === 'enum') {
    return def.values?.find(v => v.index === raw)?.id ?? def.values?.[0]?.id ?? ''
  }
  if (def.type === 'color') {
    return String(raw)  // color flags use raw integer values
  }
  return String(raw)
}

// Convert a string id back to a raw integer for constraint coercion.
function flagValueFromId(def, id) {
  if (def.type === 'tristate') return id === 'on' ? 1 : id === 'random' ? 2 : 0
  if (def.type === 'bool') return id === 'on' ? 1 : 0
  if (def.type === 'item') return itemEnum.find(e => e.id === id)?.index ?? 0
  if (def.type === 'enum') return def.values?.find(v => v.id === id)?.index ?? 0
  if (def.type === 'color') return parseInt(id, 10) || 0
  return 0
}

/**
 * Apply constraints from the schema.
 * constraints: array from /flags response
 * Returns {state, coerced: Set<string>}
 */
function applyConstraints(constraints, state) {
  const next = { ...state }
  const coerced = new Set()

  for (const constraint of constraints) {
    const triggered = (constraint.when ?? []).every(cond => {
      const def = flagDefs.find(f => f.id === cond.flag)
      if (!def) return false
      const strVal = flagValueToId(def, next[cond.flag] ?? 0)
      if ('equals' in cond) return strVal === cond.equals
      if ('not_equals' in cond) return strVal !== cond.not_equals
      return false
    })

    if (!triggered) continue

    for (const action of constraint.then ?? []) {
      if (!action.flag || !action.must_be) continue
      const def = flagDefs.find(f => f.id === action.flag)
      if (!def) continue
      const desired = action.must_be
      if (flagValueToId(def, next[action.flag] ?? 0) !== desired) {
        next[action.flag] = flagValueFromId(def, desired)
        coerced.add(action.flag)
      }
    }
  }

  return { state: next, coerced }
}

function setFlagValue(id, raw, constraints) {
  flagState[id] = raw
  const result = applyConstraints(constraints, flagState)
  flagState = result.state
  coercedFlags = result.coerced
  syncFlagStringFromState()
  renderFlagRows()
  saveSession()  // persist after every flag change
}

function syncFlagStringFromState() {
  const mainEncoded     = encodeFlags(mainFlagDefs, flagState, flagStringLength, 'bit_offset')
  const cosmeticEncoded = encodeFlags(cosmeticFlagDefs, flagState, cosmeticFlagStringLength, 'cosmetic_bit_offset')

  const input = document.getElementById('flag-string-input')
  if (input.value !== mainEncoded) input.value = mainEncoded
  input.classList.remove('flag-string-input--error')
  document.getElementById('flag-string-error').textContent = ''

  const cosmeticInput = document.getElementById('cosmetic-flag-string-input')
  if (cosmeticInput && cosmeticInput.value !== cosmeticEncoded) cosmeticInput.value = cosmeticEncoded
}

function syncStateFromFlagString(str, constraints) {
  const decoded = decodeFlags(mainFlagDefs, str, flagStringLength, 'bit_offset')
  if (!decoded) {
    document.getElementById('flag-string-error').textContent = 'Invalid flag string'
    document.getElementById('flag-string-input').classList.add('flag-string-input--error')
    return
  }
  document.getElementById('flag-string-input').classList.remove('flag-string-input--error')
  document.getElementById('flag-string-error').textContent = ''
  // Merge decoded main flags into full state (preserving cosmetic flags)
  const merged = { ...flagState, ...decoded }
  const result = applyConstraints(constraints, merged)
  flagState = result.state
  coercedFlags = result.coerced
  // Re-encode normalised value back to input
  const encoded = encodeFlags(mainFlagDefs, flagState, flagStringLength, 'bit_offset')
  document.getElementById('flag-string-input').value = encoded
  renderFlagRows()
  saveSession()  // persist after manual flag string edits
}

function syncStateFromCosmeticFlagString(str) {
  const decoded = decodeFlags(cosmeticFlagDefs, str, cosmeticFlagStringLength, 'cosmetic_bit_offset')
  if (!decoded) {
    const input = document.getElementById('cosmetic-flag-string-input')
    if (input) input.classList.add('flag-string-input--error')
    return
  }
  const input = document.getElementById('cosmetic-flag-string-input')
  if (input) input.classList.remove('flag-string-input--error')
  // Merge decoded cosmetic flags into full state (preserving main flags)
  flagState = { ...flagState, ...decoded }
  // Re-encode normalised value back to input
  const encoded = encodeFlags(cosmeticFlagDefs, flagState, cosmeticFlagStringLength, 'cosmetic_bit_offset')
  if (input && input.value !== encoded) input.value = encoded
  renderFlagRows()
  saveSession()
}

function renderFlagCheckbox(def, raw, coerced) {
  // tristate: cycles off → on → random → off
  const isOn = raw === 1
  const isRandom = raw === 2
  let cls = 'flag-checkbox'
  if (isOn) cls += ' flag-checkbox--on'
  else if (isRandom) cls += ' flag-checkbox--random'

  const btn = document.createElement('button')
  btn.type = 'button'
  btn.className = cls
  btn.setAttribute('role', 'checkbox')
  btn.setAttribute('aria-checked', isRandom ? 'mixed' : String(isOn))
  btn.setAttribute('aria-label', def.label)
  btn.textContent = isOn ? '✓' : isRandom ? '?' : ''
  return btn
}

function renderFlagSelect(def, raw) {
  const sel = document.createElement('select')
  sel.className = 'flag-enum-select'
  sel.setAttribute('aria-label', def.label)
  for (const v of def.values ?? []) {
    const opt = document.createElement('option')
    opt.value = String(v.index)
    opt.textContent = v.label
    if (v.index === raw) opt.selected = true
    sel.appendChild(opt)
  }
  return sel
}

/**
 * Build the flag-value-to-NES-index mapping from the palette data.
 * Value 0 = vanilla, value 14 = random, values 1-13 and 15-63 = NES colors.
 * Excludes NES 0x0D and 0x0E.
 */
function colorFlagToNesIndex(flagValue) {
  if (flagValue === 0 || flagValue === 14) return null
  // Values 1-13: NES 0x00-0x0C
  if (flagValue >= 1 && flagValue <= 13) return flagValue - 1
  // Values 15-63: NES 0x0F-0x3F
  if (flagValue >= 15 && flagValue <= 63) return flagValue - 15 + 0x0F
  return null
}

function nesIndexToFlagValue(nesIndex) {
  // NES 0x00-0x0C → flag values 1-13
  if (nesIndex >= 0x00 && nesIndex <= 0x0C) return nesIndex + 1
  // NES 0x0F-0x3F → flag values 15-63
  if (nesIndex >= 0x0F && nesIndex <= 0x3F) return nesIndex - 0x0F + 15
  return 0 // excluded colors → vanilla
}

function renderColorPicker(def, raw, constraints) {
  const wrapper = document.createElement('div')
  wrapper.className = 'flag-color-picker'

  // Current selection display + toggle button
  const toggle = document.createElement('button')
  toggle.type = 'button'
  toggle.className = 'color-picker-toggle'
  toggle.setAttribute('aria-label', `${def.label}: click to change`)

  function updateToggle(value) {
    if (value === 0) {
      toggle.style.backgroundColor = ''
      toggle.textContent = 'Default'
      toggle.className = 'color-picker-toggle color-picker-toggle--vanilla'
    } else if (value === 14) {
      toggle.style.backgroundColor = ''
      toggle.textContent = 'Random'
      toggle.className = 'color-picker-toggle color-picker-toggle--random'
    } else {
      const nesIdx = colorFlagToNesIndex(value)
      const entry = nesColorPalette.find(e => e.index === nesIdx)
      toggle.style.backgroundColor = entry ? entry.hex : '#000'
      toggle.textContent = ''
      toggle.className = 'color-picker-toggle color-picker-toggle--color'
    }
  }
  updateToggle(raw)

  // Dropdown panel (hidden by default)
  const panel = document.createElement('div')
  panel.className = 'color-picker-panel'
  panel.setAttribute('hidden', '')

  // Special buttons row
  const specials = document.createElement('div')
  specials.className = 'color-picker-specials'

  const vanillaBtn = document.createElement('button')
  vanillaBtn.type = 'button'
  vanillaBtn.className = 'color-picker-special-btn' + (raw === 0 ? ' color-picker-special-btn--selected' : '')
  vanillaBtn.textContent = 'Default'
  vanillaBtn.addEventListener('click', () => {
    setFlagValue(def.id, 0, constraints)
    updateToggle(0)
    updateSelection(0)
  })
  specials.appendChild(vanillaBtn)

  const randomBtn = document.createElement('button')
  randomBtn.type = 'button'
  randomBtn.className = 'color-picker-special-btn' + (raw === 14 ? ' color-picker-special-btn--selected' : '')
  randomBtn.textContent = 'Random'
  randomBtn.addEventListener('click', () => {
    setFlagValue(def.id, 14, constraints)
    updateToggle(14)
    updateSelection(14)
  })
  specials.appendChild(randomBtn)
  panel.appendChild(specials)

  // 4x16 NES palette grid
  const grid = document.createElement('div')
  grid.className = 'color-picker-grid'

  const swatches = []
  for (let row = 0; row < 4; row++) {
    for (let col = 0; col < 16; col++) {
      const nesIdx = row * 16 + col
      const entry = nesColorPalette.find(e => e.index === nesIdx)
      const swatch = document.createElement('button')
      swatch.type = 'button'
      swatch.className = 'color-swatch'

      if (!entry || entry.excluded) {
        swatch.className += ' color-swatch--excluded'
        swatch.disabled = true
        swatch.style.backgroundColor = '#000'
        swatch.title = entry ? entry.label : `0x${nesIdx.toString(16).toUpperCase().padStart(2, '0')}`
      } else {
        swatch.style.backgroundColor = entry.hex
        swatch.title = `${entry.label} (0x${nesIdx.toString(16).toUpperCase().padStart(2, '0')})`
        const flagVal = nesIndexToFlagValue(nesIdx)

        if (flagVal === raw) {
          swatch.className += ' color-swatch--selected'
        }

        swatch.addEventListener('click', () => {
          setFlagValue(def.id, flagVal, constraints)
          updateToggle(flagVal)
          updateSelection(flagVal)
        })
      }
      swatches.push({ swatch, nesIdx })
      grid.appendChild(swatch)
    }
  }
  panel.appendChild(grid)

  function updateSelection(value) {
    vanillaBtn.className = 'color-picker-special-btn' + (value === 0 ? ' color-picker-special-btn--selected' : '')
    randomBtn.className = 'color-picker-special-btn' + (value === 14 ? ' color-picker-special-btn--selected' : '')
    for (const { swatch, nesIdx } of swatches) {
      const entry = nesColorPalette.find(e => e.index === nesIdx)
      if (!entry || entry.excluded) continue
      const flagVal = nesIndexToFlagValue(nesIdx)
      if (flagVal === value) {
        swatch.classList.add('color-swatch--selected')
      } else {
        swatch.classList.remove('color-swatch--selected')
      }
    }
  }

  // Toggle panel visibility on click
  toggle.addEventListener('click', (e) => {
    e.stopPropagation()
    const isOpen = !panel.hasAttribute('hidden')
    // Close all other open color pickers first
    document.querySelectorAll('.color-picker-panel:not([hidden])').forEach(p => {
      if (p !== panel) p.setAttribute('hidden', '')
    })
    if (isOpen) {
      panel.setAttribute('hidden', '')
    } else {
      panel.removeAttribute('hidden')
    }
  })

  // Store update function for renderFlagRows
  wrapper._updateColorPicker = (value) => {
    updateToggle(value)
    updateSelection(value)
  }

  wrapper.appendChild(toggle)
  wrapper.appendChild(panel)
  return wrapper
}

function buildFlagRow(def, raw, coerced, constraints) {
  const row = document.createElement('div')
  row.className = 'flag-row' + (coerced ? ' flag-row--coerced' : '')
  row.dataset.flagId = def.id

  if (def.type === 'color') {
    const picker = renderColorPicker(def, raw, constraints)
    row.appendChild(picker)
  } else if (def.type === 'tristate' || def.type === 'bool') {
    const cb = renderFlagCheckbox(def, raw, coerced)
    cb.addEventListener('click', () => {
      // cycle: 0 → 1 → 2 (tristate) or 0 → 1 (bool)
      const cur = flagState[def.id] ?? 0
      let next
      if (def.type === 'tristate') {
        next = cur === 0 ? 1 : cur === 1 ? 2 : 0
      } else {
        next = cur === 0 ? 1 : 0
      }
      setFlagValue(def.id, next, constraints)
    })
    row.appendChild(cb)
  } else {
    // item enum
    const sel = renderFlagSelect(def, raw)
    sel.addEventListener('change', () => {
      setFlagValue(def.id, Number(sel.value), constraints)
    })
    row.appendChild(sel)
  }

  const ctrl = row.firstChild
  const labelSpan = document.createElement('span')
  labelSpan.className = 'flag-label'
  labelSpan.textContent = def.label
  labelSpan.style.cursor = 'pointer'
  labelSpan.addEventListener('click', () => {
    if (def.type === 'color') {
      const toggle = ctrl.querySelector('.color-picker-toggle')
      if (toggle) toggle.click()
    } else if (def.type === 'tristate' || def.type === 'bool') ctrl.click()
    else ctrl.focus()
  })
  if (coerced) {
    const lock = document.createElement('span')
    lock.className = 'flag-lock'
    lock.title = 'Coerced by constraint'
    lock.textContent = '🔒'
    labelSpan.appendChild(lock)
  }
  row.appendChild(labelSpan)

  // Tooltip
  if (def.description) {
    const wrapper = document.createElement('span')
    wrapper.className = 'tooltip-wrapper'
    const trigger = document.createElement('span')
    trigger.className = 'tooltip-trigger'
    trigger.setAttribute('tabindex', '0')
    trigger.textContent = 'i'
    const popup = document.createElement('span')
    popup.className = 'tooltip-popup'
    popup.textContent = def.description.trim()
    wrapper.appendChild(trigger)
    wrapper.appendChild(popup)
    row.appendChild(wrapper)
  }

  return row
}

function renderFlagRows() {
  // Re-render only the flag rows in each column, preserving tab structure
  const allRows = document.querySelectorAll('[data-flag-id]')
  for (const row of allRows) {
    const id = row.dataset.flagId
    const def = flagDefs.find(f => f.id === id)
    if (!def) continue
    const raw = flagState[id] ?? 0
    const coerced = coercedFlags.has(id)
    row.className = 'flag-row' + (coerced ? ' flag-row--coerced' : '')

    // Update control
    const ctrl = row.firstChild
    if (def.type === 'color') {
      if (ctrl._updateColorPicker) ctrl._updateColorPicker(raw)
    } else if (def.type === 'tristate' || def.type === 'bool') {
      const isOn = raw === 1
      const isRandom = raw === 2
      let cls = 'flag-checkbox'
      if (isOn) cls += ' flag-checkbox--on'
      else if (isRandom) cls += ' flag-checkbox--random'
      ctrl.className = cls
      ctrl.setAttribute('aria-checked', isRandom ? 'mixed' : String(isOn))
      ctrl.textContent = isOn ? '✓' : isRandom ? '?' : ''
    } else {
      ctrl.value = String(raw)
    }

    // Update label coercion indicator
    const labelSpan = row.querySelector('.flag-label')
    const existingLock = labelSpan.querySelector('.flag-lock')
    if (coerced && !existingLock) {
      const lock = document.createElement('span')
      lock.className = 'flag-lock'
      lock.title = 'Coerced by constraint'
      lock.textContent = '🔒'
      labelSpan.appendChild(lock)
    } else if (!coerced && existingLock) {
      existingLock.remove()
    }
  }
}

async function initFlagsSection() {
  const container = document.getElementById('flags-container')
  container.innerHTML = '<div class="flags-loading">Loading flags…</div>'

  let schema
  try {
    const res = await fetch('/flags')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    schema = await res.json()
  } catch (e) {
    container.innerHTML = `<div class="inline-error">Failed to load flags: ${e.message}</div>`
    return
  }

  // Update header version from API
  if (schema.version) {
    const versionEl = document.querySelector('.header-version')
    if (versionEl) versionEl.textContent = `v${schema.version}`
  }

  // Store schema data
  flagStringLength = schema.string_length
  cosmeticFlagStringLength = schema.cosmetic_string_length ?? 2
  itemEnum = schema.item_enum ?? []
  nesColorPalette = schema.nes_color_palette ?? []
  const allDefs = (schema.flags ?? []).filter(f => f.enabled !== false)
  flagDefs = allDefs  // all defs (used by renderFlagRows)
  mainFlagDefs = allDefs.filter(f => !f.cosmetic)
  cosmeticFlagDefs = allDefs.filter(f => f.cosmetic)

  // Add item values array to item-type flags (sorted by index)
  for (const def of allDefs) {
    if (def.type === 'item') {
      def.values = [...itemEnum].sort((a, b) => a.index - b.index)
    }
  }

  const constraints = schema.constraints ?? []

  // Start from schema defaults, then overlay any saved strings
  flagState = defaultState(allDefs)
  const savedFlagString = localStorage.getItem(STORAGE_KEYS.flagString)
  if (savedFlagString) {
    const decoded = decodeFlags(mainFlagDefs, savedFlagString, flagStringLength, 'bit_offset')
    if (decoded) Object.assign(flagState, decoded)
  }
  const savedCosmeticFlagString = localStorage.getItem(STORAGE_KEYS.cosmeticFlagString)
  if (savedCosmeticFlagString) {
    const decoded = decodeFlags(cosmeticFlagDefs, savedCosmeticFlagString, cosmeticFlagStringLength, 'cosmetic_bit_offset')
    if (decoded) Object.assign(flagState, decoded)
  }
  const result = applyConstraints(constraints, flagState)
  flagState = result.state
  coercedFlags = result.coerced

  // Build group → flags map, preserving declaration order
  const groupOrder = []
  const groupMap = {}
  for (const def of allDefs) {
    if (!groupMap[def.group]) {
      groupMap[def.group] = []
      groupOrder.push(def.group)
    }
    groupMap[def.group].push(def)
  }

  // Build tab UI
  container.innerHTML = ''

  const tabBar = document.createElement('div')
  tabBar.className = 'flags-tabs'
  tabBar.setAttribute('role', 'tablist')
  container.appendChild(tabBar)

  const panels = []
  const savedTab = localStorage.getItem(STORAGE_KEYS.activeTab)
  const activeIdx = savedTab !== null && groupOrder.includes(savedTab)
    ? groupOrder.indexOf(savedTab)
    : 0

  groupOrder.forEach((group, idx) => {
    // Tab button
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.className = 'flags-tab-btn' + (idx === activeIdx ? ' flags-tab-btn--active' : '')
    btn.setAttribute('role', 'tab')
    btn.setAttribute('aria-selected', String(idx === activeIdx))
    btn.setAttribute('aria-controls', `flag-panel-${idx}`)
    btn.textContent = group
    btn.addEventListener('click', () => {
      document.querySelectorAll('.flags-tab-btn').forEach(b => {
        b.classList.remove('flags-tab-btn--active')
        b.setAttribute('aria-selected', 'false')
      })
      btn.classList.add('flags-tab-btn--active')
      btn.setAttribute('aria-selected', 'true')
      panels.forEach(p => p.setAttribute('hidden', ''))
      panels[idx].removeAttribute('hidden')
      localStorage.setItem(STORAGE_KEYS.activeTab, group)
    })
    tabBar.appendChild(btn)

    // Panel
    const panel = document.createElement('div')
    panel.id = `flag-panel-${idx}`
    panel.setAttribute('role', 'tabpanel')
    if (idx !== activeIdx) panel.setAttribute('hidden', '')

    const flags = groupMap[group]
    const allOrdered = [...flags].sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0))
    const hasDisplayOrder = flags.some(f => f.display_order != null)
    const cols = hasDisplayOrder ? [
      allOrdered.filter(f => f.display_order < 100),
      allOrdered.filter(f => f.display_order >= 100 && f.display_order < 200),
      allOrdered.filter(f => f.display_order >= 200),
    ] : (() => {
      const colSize = Math.ceil(flags.length / 3)
      return [flags.slice(0, colSize), flags.slice(colSize, colSize * 2), flags.slice(colSize * 2)]
    })()

    const tabContent = document.createElement('div')
    tabContent.className = 'flag-tab'

    cols.forEach((colFlags, i) => {
      if (i > 0) {
        const divider = document.createElement('div')
        divider.className = 'flag-col-divider'
        tabContent.appendChild(divider)
      }
      const col = document.createElement('div')
      col.className = 'flag-col'
      for (const def of colFlags) {
        col.appendChild(buildFlagRow(def, flagState[def.id] ?? 0, coercedFlags.has(def.id), constraints))
      }
      tabContent.appendChild(col)
    })

    panel.appendChild(tabContent)
    container.appendChild(panel)
    panels.push(panel)
  })

  // Wire up flag string input
  const flagStringInput = document.getElementById('flag-string-input')
  flagStringInput.addEventListener('input', () => {
    syncStateFromFlagString(flagStringInput.value, constraints)
  })

  // Wire up cosmetic flag string input
  const cosmeticFlagStringInput = document.getElementById('cosmetic-flag-string-input')
  if (cosmeticFlagStringInput) {
    cosmeticFlagStringInput.addEventListener('input', () => {
      syncStateFromCosmeticFlagString(cosmeticFlagStringInput.value)
    })
  }

  // Close color picker panels when clicking outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.flag-color-picker')) {
      document.querySelectorAll('.color-picker-panel:not([hidden])').forEach(p => {
        p.setAttribute('hidden', '')
      })
    }
  })

  // Set initial flag strings (will reflect saved state if restored above)
  syncFlagStringFromState()
}

// ---------------------------------------------------------------------------
// Seed section
// ---------------------------------------------------------------------------

function newSeed() {
  // Random 32-bit unsigned int
  return Math.floor(Math.random() * 0x100000000)
}

function initSeedSection() {
  const input = document.getElementById('seed-input')

  // loadSession() may have already restored a saved seed; only set a new one
  // if the field is still empty.
  if (!input.value) {
    input.value = newSeed()
  }

  // Persist seed whenever the user edits it manually
  input.addEventListener('input', () => saveSession())

  document.getElementById('new-seed-btn').addEventListener('click', () => {
    input.value = newSeed()
    saveSession()
  })
}

// ---------------------------------------------------------------------------
// Generate section
// ---------------------------------------------------------------------------

function updateGenerateButton() {
  const btn = document.getElementById('generate-btn')
  btn.disabled = !romFile || (romVersion === null && !romIsCustom)
}

function initGenerateSection() {
  updateGenerateButton()

  document.getElementById('generate-btn').addEventListener('click', async () => {
    if (!romFile) return

    const btn = document.getElementById('generate-btn')
    const resultArea = document.getElementById('generate-result')
    const errorArea = document.getElementById('generate-error')

    btn.disabled = true
    btn.innerHTML = '<span class="spinner" aria-hidden="true"></span> Generating…'
    resultArea.hidden = true
    errorArea.hidden = true
    errorArea.replaceChildren()

    const dot = document.getElementById('status-dot')
    dot.className = 'status-dot'
    document.getElementById('rom-download-btn').disabled = true
    document.getElementById('spoiler-download-btn').disabled = true
    document.getElementById('visualizer-btn').disabled = true

    const seed = document.getElementById('seed-input').value || String(newSeed())
    const flagString = document.getElementById('flag-string-input').value
    const cosmeticFlagString = document.getElementById('cosmetic-flag-string-input')?.value ?? ''

    const tStart = Date.now()

    try {
      let res
      if (romIsCustom) {
        const form = new FormData()
        form.append('rom', romFile)
        form.append('flag_string', flagString)
        form.append('cosmetic_flag_string', cosmeticFlagString)
        form.append('seed', seed)
        if (romVersion !== null) form.append('rom_version', String(romVersion))
        res = await fetch('/generate/rerandomize', { method: 'POST', body: form })
      } else {
        res = await fetch('/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ flag_string: flagString, cosmetic_flag_string: cosmeticFlagString, seed: Number(seed), rom_version: romVersion }),
        })
      }

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const message = body.message ?? `Server error ${res.status}`
        const details = Array.isArray(body.details) ? body.details : []
        errorArea.textContent = message
        if (details.length > 0) {
          const ul = document.createElement('ul')
          ul.className = 'error-details'
          for (const d of details) {
            const li = document.createElement('li')
            li.textContent = d
            ul.appendChild(li)
          }
          errorArea.appendChild(ul)
        }
        dot.className = 'status-dot status-dot--error'
        errorArea.hidden = false
        return
      }

      const data = await res.json()
      const elapsed = Date.now() - tStart

      // Decode base64 patch
      const patchBin = Uint8Array.from(atob(data.patch), c => c.charCodeAt(0))

      // Read ROM locally
      const romBuf = await romFile.arrayBuffer()
      const romBytes = new Uint8Array(romBuf)

      // Apply patch client-side
      const patched = applyIpsPatch(romBytes, patchBin)

      // Build filenames from the uploaded ROM name
      const romBase = (romFile.name ?? 'zelda1').replace(/\.nes$/i, '')
        .replace(/-/g, '!').replace(/_/g, '@')
      const romFilename = `${romBase}-zora-${data.seed}-${data.flag_string}.nes`
      const spoilerFilename = `${romBase}-spoilers-${data.seed}-${data.flag_string}.txt`
      const spoilerText = typeof data.spoiler_log === 'string' ? data.spoiler_log : ''

      // Wire download buttons
      const romBtn = document.getElementById('rom-download-btn')
      romBtn.onclick = () => {
        const blob = new Blob([patched.buffer], { type: 'application/octet-stream' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = romFilename
        a.click()
        URL.revokeObjectURL(url)
      }

      const spoilerBtn = document.getElementById('spoiler-download-btn')
      spoilerBtn.onclick = () => {
        const blob = new Blob([spoilerText], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = spoilerFilename
        a.click()
        URL.revokeObjectURL(url)
      }

      // Enable download buttons and show success dot
      document.getElementById('rom-download-btn').disabled = false
      document.getElementById('spoiler-download-btn').disabled = false
      dot.className = 'status-dot status-dot--ready'

      // Wire visualizer button (opens in new tab)
      const vizBtn = document.getElementById('visualizer-btn')
      vizBtn.disabled = false
      const spoilerData = data.spoiler_data
      vizBtn.onclick = () => {
        if (!spoilerData) return
        const html = buildVisualizerHTML(spoilerData)
        const w = window.open('', '_blank')
        if (w) {
          w.document.write(html)
          w.document.close()
        }
      }

      // Show result
      document.getElementById('gen-time').textContent = `(${elapsed.toLocaleString()} ms)`

      const hashCodeEl = document.getElementById('hash-code')
      const hashCodeItems = document.getElementById('hash-code-items')
      if (data.hash_code && data.hash_code.length === 4) {
        hashCodeItems.textContent = data.hash_code.join(' · ')
        hashCodeEl.hidden = false
      } else {
        hashCodeEl.hidden = true
      }

      resultArea.hidden = false

    } catch (err) {
      dot.className = 'status-dot status-dot--error'
      errorArea.textContent = String(err)
      errorArea.hidden = false
    } finally {
      btn.disabled = !romFile
      btn.innerHTML = 'Generate Random Game'
    }
  })
}

// ---------------------------------------------------------------------------
// Visualizer (opens in a new browser tab)
// ---------------------------------------------------------------------------

const ROOM_TYPE_ABBREV = {
  PLAIN_ROOM: 'Plain', SPIKE_TRAP_ROOM: 'Spike Trap', FOUR_SHORT_ROOM: 'Four Short',
  FOUR_TALL_ROOM: 'Four Tall', AQUAMENTUS_ROOM: 'Aquamentus', GLEEOK_ROOM: 'Gleeok',
  GOHMA_ROOM: 'Gohma', THREE_ROWS: 'Three Rows', REVERSE_C: 'Reverse C',
  CIRCLE_WALL: 'Circle Wall', DOUBLE_BLOCK: 'Double Block', LAVA_MOAT: 'Lava Moat',
  MAZE_ROOM: 'Maze', GRID_ROOM: 'Grid', VERTICAL_CHUTE_ROOM: 'Vert. Chute',
  HORIZONTAL_CHUTE_ROOM: 'Horiz. Chute', VERTICAL_ROWS: 'Vert. Rows',
  ZIGZAG_ROOM: 'Zigzag', T_ROOM: 'T Room', VERTICAL_MOAT_ROOM: 'Vert. Moat',
  CIRCLE_MOAT_ROOM: 'Circle Moat', POINTLESS_MOAT_ROOM: 'Pointless Moat',
  CHEVY_ROOM: 'Chevy', NSU: 'NSU', HORIZONTAL_MOAT_ROOM: 'Horiz. Moat',
  DOUBLE_MOAT_ROOM: 'Double Moat', DIAMOND_STAIR_ROOM: 'Diamond Stair',
  NARROW_STAIR_ROOM: 'Narrow Stair', SPIRAL_STAIR_ROOM: 'Spiral Stair',
  DOUBLE_SIX_BLOCK_ROOM: 'Double Six', SINGLE_SIX_BLOCK_ROOM: 'Single Six',
  FIVE_PAIR_ROOM: 'Five Pair', TURNSTILE_ROOM: 'Turnstile',
  ENTRANCE_ROOM: 'Entrance Room', SINGLE_BLOCK_ROOM: 'Single Block',
  TWO_FIREBALL_ROOM: 'Two Fireball', FOUR_FIREBALL_ROOM: 'Four Fireball',
  DESERT_ROOM: 'Desert', BLACK_ROOM: 'Black Room', ZELDA_ROOM: 'Zelda',
  GANNON_ROOM: 'Ganon', TRIFORCE_ROOM: 'Triforce Room',
  TRANSPORT_STAIRCASE: 'Transport', ITEM_STAIRCASE: 'Item Stair',
}

const ENEMY_ABBREV = {
  NOTHING: '', BLUE_LYNEL: 'Blue Lynel', RED_LYNEL: 'Red Lynel',
  BLUE_MOBLIN: 'Blue Moblin', RED_MOBLIN: 'Red Moblin',
  BLUE_GORIYA: 'Blue Goriya', RED_GORIYA: 'Red Goriya',
  RED_OCTOROK_1: 'Red Octorok', RED_OCTOROK_2: 'Red Octorok',
  BLUE_OCTOROK_1: 'Blue Octorok', BLUE_OCTOROK_2: 'Blue Octorok',
  RED_DARKNUT: 'Red Darknut', BLUE_DARKNUT: 'Blue Darknut',
  BLUE_TEKTITE: 'Blue Tektite', RED_TEKTITE: 'Red Tektite',
  BLUE_LEEVER: 'Blue Leever', RED_LEEVER: 'Red Leever',
  ZOLA: 'Zola', VIRE: 'Vire', ZOL: 'Zol',
  GEL_1: 'Gel', GEL_2: 'Gel', POLS_VOICE: 'Pols Voice',
  LIKE_LIKE: 'Like Like', PEAHAT: 'Peahat',
  BLUE_KEESE: 'Blue Keese', RED_KEESE: 'Red Keese', DARK_KEESE: 'Dark Keese',
  ARMOS: 'Armos', FALLING_ROCKS: 'Rocks', FALLING_ROCK: 'Rock',
  GHINI_1: 'Ghini', GHINI_2: 'Ghini',
  RED_WIZZROBE: 'Red Wizzrobe', BLUE_WIZZROBE: 'Blue Wizzrobe',
  WALLMASTER: 'Wallmaster', ROPE: 'Rope', STALFOS: 'Stalfos',
  BUBBLE: 'Bubble', BLUE_BUBBLE: 'Blue Bubble', RED_BUBBLE: 'Red Bubble',
  GIBDO: 'Gibdo', TRIPLE_DODONGO: '3 Dodongos', SINGLE_DODONGO: 'Dodongo',
  BLUE_GOHMA: 'Blue Gohma', RED_GOHMA: 'Red Gohma',
  RUPEE_BOSS: 'Rupee Boss', HUNGRY_GORIYA: 'Hungry Goriya',
  THE_KIDNAPPED: 'Kidnapped', TRIPLE_DIGDOGGER: '3 Digdogger',
  SINGLE_DIGDOGGER: 'Digdogger',
  RED_LANMOLA: 'Red Lanmola', BLUE_LANMOLA: 'Blue Lanmola',
  MANHANDLA: 'Manhandla', AQUAMENTUS: 'Aquamentus', THE_BEAST: 'Ganon',
  KILLABLE_FLAME: 'Flame', MIXED_FLAME: 'Mixed Flame', MOLDORM: 'Moldorm',
  GLEEOK_1: 'Gleeok (1)', GLEEOK_2: 'Gleeok (2)',
  GLEEOK_3: 'Gleeok (3)', GLEEOK_4: 'Gleeok (4)',
  PATRA_2: 'Patra 2', PATRA_1: 'Patra 1',
  THREE_PAIRS_OF_TRAPS: 'Traps', CORNER_TRAPS: 'Corner Traps',
  OLD_MAN: 'Old Man', OLD_MAN_2: 'Old Man', OLD_MAN_3: 'Old Man',
  OLD_MAN_4: 'Old Man', BOMB_UPGRADER: 'Bomb Upgrade',
  OLD_MAN_5: 'Old Man', MUGGER: 'Mugger', OLD_MAN_6: 'Old Man',
}

function enemyLabel(name) {
  return ENEMY_ABBREV[name] ?? name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).replace(/^Mixed Enemy Group /, 'Enemy Mix ')
}

function itemLabel(name) {
  if (!name) return null
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function getDoorClass(wallType) {
  switch (wallType) {
    case 'OPEN_DOOR': return 'd-open'
    case 'LOCKED_DOOR_1': case 'LOCKED_DOOR_2': return 'd-locked'
    case 'BOMB_HOLE': return 'd-bomb'
    case 'SHUTTER_DOOR': return 'd-shutter'
    case 'WALK_THROUGH_WALL_1': case 'WALK_THROUGH_WALL_2': return 'd-walk'
    default: return null
  }
}

function wallLabel(wallType) {
  switch (wallType) {
    case 'OPEN_DOOR': return 'Open'
    case 'SOLID_WALL': return 'Solid'
    case 'WALK_THROUGH_WALL_1': case 'WALK_THROUGH_WALL_2': return 'Walk-Through'
    case 'BOMB_HOLE': return 'Bomb'
    case 'LOCKED_DOOR_1': case 'LOCKED_DOOR_2': return 'Locked'
    case 'SHUTTER_DOOR': return 'Shutter'
    default: return wallType
  }
}

function getOverworldCellClass(screen) {
  if (!screen) return 'ow-cell--none'
  const et = screen.entrance_type
  if (et === 'NONE') return 'ow-cell--none'
  if (et === 'OPEN') return 'ow-cell--open'
  if (et === 'BOMB' || et === 'LADDER_AND_BOMB' || et === 'RAFT_AND_BOMB' || et === 'POWER_BRACELET_AND_BOMB') return 'ow-cell--bomb'
  if (et === 'CANDLE') return 'ow-cell--candle'
  if (et === 'RECORDER') return 'ow-cell--recorder'
  if (et === 'RAFT') return 'ow-cell--raft'
  if (et === 'LADDER') return 'ow-cell--ladder'
  if (et === 'POWER_BRACELET') return 'ow-cell--bracelet'
  if (et === 'LOST_HILLS_HINT' || et === 'DEAD_WOODS_HINT') return 'ow-cell--open'
  return 'ow-cell--none'
}

function getOwDestAbbrev(dest) {
  if (!dest || dest === 'NONE') return ''
  if (dest.startsWith('LEVEL_')) return 'L' + dest.replace('LEVEL_', '')
  const abbrevs = {
    WOOD_SWORD_CAVE: 'WSC', WHITE_SWORD_CAVE: 'WhSC', MAGICAL_SWORD_CAVE: 'MSC',
    LETTER_CAVE: 'Ltr', ARMOS_ITEM: 'Armos', COAST_ITEM: 'Coast',
    SHOP_1: 'Shop1', SHOP_2: 'Shop2', SHOP_3: 'Shop3', SHOP_4: 'Shop4',
    POTION_SHOP: 'Potion', TAKE_ANY: 'Take', ANY_ROAD: 'AnyRd',
    LOST_HILLS_HINT: 'LHint', MONEY_MAKING_GAME: 'MMG', DOOR_REPAIR: 'Door',
    DEAD_WOODS_HINT: 'DHint', HINT_SHOP_1: 'HS1', HINT_SHOP_2: 'HS2',
    MEDIUM_SECRET: 'MedS', LARGE_SECRET: 'LrgS', SMALL_SECRET: 'SmlS',
  }
  return abbrevs[dest] || dest.replace(/_/g, ' ').substring(0, 6)
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') }
function hex2(n) { return n.toString(16).toUpperCase().padStart(2, '0') }

/**
 * Build a self-contained HTML document string for the visualizer.
 * Opens in a new browser tab — no external dependencies.
 */
function buildVisualizerHTML(data) {
  const parts = []

  parts.push(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ZORA Visualizer — Seed ${esc(data.seed)} — ${esc(data.flag_string)}</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #1a1a18; color: #f0efe9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; line-height: 1.5; }
.viz-main { max-width: 1200px; margin: 0 auto; padding: 1.5rem; }
h1 { font-size: 18px; margin-bottom: 0.25rem; }
.viz-meta { color: #a0a09a; font-size: 12px; margin-bottom: 1.5rem; font-family: 'SFMono-Regular', Consolas, monospace; }

/* Tabs */
.viz-tabs { display: flex; gap: 0; border-bottom: 1px solid rgba(255,255,255,0.2); margin-bottom: 1.5rem; }
.viz-tab { background: none; border: none; border-bottom: 2px solid transparent; padding: 0.5rem 1rem; font-size: 13px; font-weight: 500; color: #a0a09a; cursor: pointer; }
.viz-tab:hover { color: #f0efe9; }
.viz-tab.active { color: #1D9E75; border-bottom-color: #1D9E75; }
.viz-panel { display: none; }
.viz-panel.active { display: block; }

/* Dungeon maps */
.dg-section { margin-bottom: 2rem; }
.dg-heading { font-size: 15px; font-weight: 600; margin-bottom: 0.75rem; }
.dg-wrap { overflow-x: auto; padding: 10px; }
.dg-map { display: grid; width: fit-content; }
.dg-room { width: 120px; height: 90px; position: relative; overflow: visible; border-radius: 3px; }
.dg-room--empty { visibility: hidden; }
.room-content { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; padding: 4px 6px; font-size: 9px; font-family: 'SFMono-Regular', Consolas, monospace; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.6), 0 0 4px rgba(0,0,0,0.4); text-align: center; line-height: 1.35; gap: 1px; }
.room-type { font-weight: 700; font-size: 9.5px; }
.room-enemy, .room-item, .room-stair { font-size: 8.5px; opacity: 0.92; }
.room-item { font-weight: 600; }
.room-stair { font-style: italic; }

/* Door indicators — square markers in the gap between rooms */
.di { position: absolute; z-index: 2; border-radius: 1px; }
.di-n { top: -6px; left: 50%; width: 8px; height: 5px; transform: translateX(-50%); }
.di-s { bottom: -6px; left: 50%; width: 8px; height: 5px; transform: translateX(-50%); }
.di-e { right: -6px; top: 50%; width: 5px; height: 8px; transform: translateY(-50%); }
.di-w { left: -6px; top: 50%; width: 5px; height: 8px; transform: translateY(-50%); }
.d-open { background: #999; }
.d-locked { background: #FFD700; }
.d-bomb { background: #4488FF; }
.d-shutter { background: #FF4444; }
.d-walk { background: #AA44FF; }
.ds-n { top: -7px; left: 5%; width: 90%; height: 2px; background: #FF4444; }
.ds-s { bottom: -7px; left: 5%; width: 90%; height: 2px; background: #FF4444; }
.ds-e { right: -7px; top: 5%; width: 2px; height: 90%; background: #FF4444; }
.ds-w { left: -7px; top: 5%; width: 2px; height: 90%; background: #FF4444; }

.dg-room--entrance { outline: 2px dashed #fff; outline-offset: -3px; }

/* Tooltip */
.tip { display: none; position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%); background: #222220; color: #f0efe9; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; padding: 8px 10px; font-size: 11px; line-height: 1.5; white-space: nowrap; z-index: 100; box-shadow: 0 4px 12px rgba(0,0,0,0.5); pointer-events: none; font-family: 'SFMono-Regular', Consolas, monospace; text-shadow: none; }
.tip--bottom { bottom: auto; top: calc(100% + 6px); }
.tip--left { left: 0; transform: none; }
.tip--right { left: auto; right: 0; transform: none; }
.dg-room:hover .tip, .ow-cell:hover .tip { display: block; }

/* Legend */
.legend { display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem; padding: 0.5rem 0; font-size: 11px; color: #a0a09a; }
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-sw { width: 18px; height: 8px; border-radius: 2px; display: inline-block; }
.legend-sw--solid { width: 18px; height: 2px; background: #FF4444; }

/* Overworld */
.ow-wrap { overflow-x: auto; padding: 8px 0; }
.ow-map { display: grid; grid-template-columns: repeat(16, 64px); grid-template-rows: repeat(8, 44px); gap: 1px; width: fit-content; }
.ow-cell { display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 8px; font-family: 'SFMono-Regular', Consolas, monospace; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.5); text-align: center; line-height: 1.3; padding: 2px; border-radius: 2px; position: relative; }
.ow-cell--none { background: #333; color: #777; text-shadow: none; }
.ow-cell--open { background: #2B6800; }
.ow-cell--bomb { background: #8B6500; }
.ow-cell--candle { background: #8B2500; }
.ow-cell--recorder { background: #5B2080; }
.ow-cell--raft { background: #0E5282; }
.ow-cell--ladder { background: #006363; }
.ow-cell--bracelet { background: #784600; }
.ow-cell--level { background: #1F56E1; }
.ow-cell--start { outline: 2px solid #FFD700; outline-offset: -1px; }
.ow-dest { font-weight: 700; font-size: 8.5px; }
.ow-num { font-size: 7px; opacity: 0.7; }

/* Tables */
.section { margin-bottom: 2rem; }
.section h3 { font-size: 16px; font-weight: 600; margin-bottom: 1rem; }
.section h4 { font-size: 13px; font-weight: 600; margin-bottom: 0.5rem; }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 2rem; }
.s-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: 'SFMono-Regular', Consolas, monospace; color: #f0efe9; }
.s-table th { text-align: left; font-weight: 600; font-size: 11px; padding: 4px 8px; border-bottom: 1px solid rgba(255,255,255,0.2); color: #a0a09a; }
.s-table td { padding: 3px 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
.s-table tr:last-child td { border-bottom: none; }

/* Hints */
.hint { padding: 6px 10px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 12px; font-family: 'SFMono-Regular', Consolas, monospace; line-height: 1.5; }
.hint:last-child { border-bottom: none; }
.hint-id { color: #606060; font-weight: 600; margin-right: 0.5rem; }

/* Enemies */
.enemy-set-section { margin-bottom: 2.5rem; padding-bottom: 1.5rem; border-bottom: 1px solid rgba(255,255,255,0.1); }
.enemy-set-section:last-child { border-bottom: none; }
.enemy-set-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 0.5rem; color: #1D9E75; }
.enemy-set-meta { font-size: 11px; color: #a0a09a; margin-bottom: 0.75rem; font-family: 'SFMono-Regular', Consolas, monospace; }
.enemy-set-members { font-size: 12px; margin-bottom: 1rem; font-family: 'SFMono-Regular', Consolas, monospace; }
.sprite-bank-section { margin-bottom: 1rem; }
.sprite-bank-label { font-size: 11px; font-weight: 600; color: #a0a09a; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.sprite-bank-canvas { display: block; image-rendering: pixelated; background: #222; border-radius: 4px; }
.enemy-frames-section { margin-bottom: 1rem; }
.enemy-frame-row { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.enemy-frame-name { font-size: 11px; font-family: 'SFMono-Regular', Consolas, monospace; color: #f0efe9; min-width: 140px; }
.enemy-frame-canvas { display: block; image-rendering: pixelated; }
.mixed-groups-section { margin-top: 1rem; }

@media (max-width: 768px) { .grid3 { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="viz-main">
<h1>ZORA Visualizer</h1>
<div class="viz-meta">Seed: ${esc(data.seed)} &nbsp; Flags: ${esc(data.flag_string)}</div>

<div class="viz-tabs">
  <button class="viz-tab active" onclick="switchTab('dungeons')">Dungeons</button>
  <button class="viz-tab" onclick="switchTab('overworld')">Overworld</button>
  <button class="viz-tab" onclick="switchTab('items')">Items</button>
  <button class="viz-tab" onclick="switchTab('enemies')">Enemies</button>
  <button class="viz-tab" onclick="switchTab('hints')">Hints</button>
</div>
`)

  // --- Dungeons panel ---
  parts.push('<div id="tab-dungeons" class="viz-panel active">')
  parts.push(buildLegendHTML())
  for (const level of data.levels) {
    parts.push(buildDungeonHTML(level))
  }
  parts.push('</div>')

  // --- Overworld panel ---
  parts.push('<div id="tab-overworld" class="viz-panel">')
  parts.push(buildOverworldLegendHTML())
  parts.push(buildOverworldHTML(data.overworld))
  parts.push('</div>')

  // --- Items panel ---
  parts.push('<div id="tab-items" class="viz-panel">')
  parts.push(buildItemsHTML(data))
  parts.push('</div>')

  // --- Enemies panel ---
  parts.push('<div id="tab-enemies" class="viz-panel">')
  parts.push(buildEnemiesHTML(data))
  parts.push('</div>')

  // --- Hints panel ---
  parts.push('<div id="tab-hints" class="viz-panel">')
  parts.push(buildHintsHTML(data))
  parts.push('</div>')

  parts.push(`
</div>
<script>
function switchTab(id) {
  document.querySelectorAll('.viz-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.viz-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  event.target.classList.add('active');
}

function renderSpriteBank(canvas, b64Data, cols) {
  const raw = atob(b64Data)
  const data = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) data[i] = raw.charCodeAt(i)

  const numTiles = Math.floor(data.length / 16)
  const numMeta = Math.floor((numTiles + 3) / 4)
  const rows = Math.ceil(numMeta / cols)
  const scale = 2
  const spritePx = 16 * scale
  const gap = 2

  canvas.width = cols * spritePx + (cols + 1) * gap
  canvas.height = rows * spritePx + (rows + 1) * gap

  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#222'
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  const palette = [[0,0,0], [85,85,85], [170,170,170], [255,255,255]]

  for (let mi = 0; mi < numMeta; mi++) {
    const mr = Math.floor(mi / cols)
    const mc = mi % cols
    const x0 = gap + mc * (spritePx + gap)
    const y0 = gap + mr * (spritePx + gap)
    const baseTile = mi * 4
    const pixels = decodeMetasprite(data, baseTile, numTiles)
    for (let py = 0; py < 16; py++) {
      for (let px = 0; px < 16; px++) {
        const c = palette[pixels[py][px]]
        ctx.fillStyle = 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')'
        ctx.fillRect(x0 + px * scale, y0 + py * scale, scale, scale)
      }
    }
  }
}

function decodeTile(data, offset) {
  const pixels = []
  for (let row = 0; row < 8; row++) {
    const lo = data[offset + row]
    const hi = data[offset + row + 8]
    const rowPx = []
    for (let bit = 7; bit >= 0; bit--) {
      rowPx.push(((hi >> bit) & 1) << 1 | ((lo >> bit) & 1))
    }
    pixels.push(rowPx)
  }
  return pixels
}

function decodeMetasprite(data, baseTile, numTiles) {
  function getTile(idx) {
    if (idx < numTiles) return decodeTile(data, idx * 16)
    return Array.from({length: 8}, () => Array(8).fill(0))
  }
  const tl = getTile(baseTile)
  const bl = getTile(baseTile + 1)
  const tr = getTile(baseTile + 2)
  const br = getTile(baseTile + 3)
  const rows = []
  for (let py = 0; py < 8; py++) rows.push([...tl[py], ...tr[py]])
  for (let py = 0; py < 8; py++) rows.push([...bl[py], ...br[py]])
  return rows
}

function decodeHalfSprite(data, baseTile, numTiles) {
  function getTile(idx) {
    if (idx < numTiles) return decodeTile(data, idx * 16)
    return Array.from({length: 8}, () => Array(8).fill(0))
  }
  const top = getTile(baseTile)
  const bot = getTile(baseTile + 1)
  const rows = []
  for (let py = 0; py < 8; py++) rows.push(top[py])
  for (let py = 0; py < 8; py++) rows.push(bot[py])
  return rows
}

function renderEnemyFrames(canvas, b64Data, frames, colStart) {
  const raw = atob(b64Data)
  const data = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) data[i] = raw.charCodeAt(i)

  const numTiles = Math.floor(data.length / 16)
  if (frames.length === 0) { canvas.width = 0; canvas.height = 0; return }

  const scale = 3
  const gap = 2
  const palette = [[0,0,0], [85,85,85], [170,170,170], [255,255,255]]

  let totalWidth = gap
  for (const f of frames) {
    const pxW = (f.width <= 2 ? 8 : 16) * scale
    totalWidth += pxW + gap
  }
  canvas.width = totalWidth
  canvas.height = 16 * scale + 2 * gap

  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#1a1a18'
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  let x0 = gap
  for (const f of frames) {
    const baseTile = f.col - colStart
    const isWide = f.width > 2
    const pxW = (isWide ? 16 : 8) * scale

    if (baseTile < 0 || baseTile >= numTiles) { x0 += pxW + gap; continue }

    const pixels = isWide
      ? decodeMetasprite(data, baseTile, numTiles)
      : decodeHalfSprite(data, baseTile, numTiles)

    const sprW = isWide ? 16 : 8
    for (let py = 0; py < 16; py++) {
      for (let px = 0; px < sprW; px++) {
        const c = palette[pixels[py][px]]
        ctx.fillStyle = 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')'
        ctx.fillRect(x0 + px * scale, gap + py * scale, scale, scale)
      }
    }
    x0 += pxW + gap
  }
}

function initEnemyCanvases() {
  document.querySelectorAll('canvas.sprite-bank-canvas').forEach(canvas => {
    const b64 = canvas.getAttribute('data-bank-b64')
    const cols = parseInt(canvas.getAttribute('data-cols') || '8')
    renderSpriteBank(canvas, b64, cols)
  })
  document.querySelectorAll('canvas.enemy-frame-canvas').forEach(canvas => {
    const b64 = canvas.getAttribute('data-bank-b64')
    const frames = JSON.parse(canvas.getAttribute('data-frames'))
    const colStart = parseInt(canvas.getAttribute('data-col-start') || '158')
    renderEnemyFrames(canvas, b64, frames, colStart)
  })
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initEnemyCanvases)
} else {
  setTimeout(initEnemyCanvases, 0)
}
<\/script>
</body>
</html>`)

  return parts.join('\n')
}

function buildLegendHTML() {
  const items = [
    ['Open Door', '#999'], ['Shutter Door', '#FF4444'], ['Key-Locked Door', '#FFD700'],
    ['Bombable Wall', '#4488FF'], ['Walk-Through Wall', '#AA44FF'],
  ]
  let h = '<div class="legend">'
  for (const [label, color] of items) {
    h += `<div class="legend-item"><span class="legend-sw" style="background:${color}"></span> ${esc(label)}</div>`
  }
  h += '<div class="legend-item"><span class="legend-sw legend-sw--solid"></span> Solid Wall</div>'
  h += '</div>'
  return h
}

function buildDungeonHTML(level) {
  const rooms = level.rooms
  if (!rooms.length) return ''

  const roomByPos = {}
  let minR = Infinity, maxR = -Infinity, minC = Infinity, maxC = -Infinity
  for (const room of rooms) {
    roomByPos[`${room.row},${room.col}`] = room
    minR = Math.min(minR, room.row); maxR = Math.max(maxR, room.row)
    minC = Math.min(minC, room.col); maxC = Math.max(maxC, room.col)
  }

  const cols = maxC - minC + 1
  let h = `<div class="dg-section"><h3 class="dg-heading">Level ${level.level_num}</h3>`
  h += `<div class="dg-wrap"><div class="dg-map" style="grid-template-columns:repeat(${cols},120px);gap:14px">`

  for (let r = minR; r <= maxR; r++) {
    for (let c = minC; c <= maxC; c++) {
      const room = roomByPos[`${r},${c}`]
      if (!room) { h += '<div class="dg-room dg-room--empty"></div>'; continue }

      const cls = ['dg-room']
      if (room.is_entrance) cls.push('dg-room--entrance')
      const bg = room.is_dark ? level.palette_hex_dark : level.palette_hex

      h += `<div class="${cls.join(' ')}" style="background:${bg}">`

      // Door indicators
      const dirs = [['north','n',0,-1],['south','s',0,1],['east','e',1,0],['west','w',-1,0]]
      for (const [dir, sd, dc, dr] of dirs) {
        const wt = room.walls[dir]
        const dc2 = getDoorClass(wt)
        if (dc2) {
          h += `<div class="di di-${sd} ${dc2}"></div>`
        } else if (wt === 'SOLID_WALL' && roomByPos[`${r+dr},${c+dc}`]) {
          h += `<div class="di ds-${sd}"></div>`
        }
      }

      // Content
      h += '<div class="room-content">'
      h += `<div class="room-type">${esc(ROOM_TYPE_ABBREV[room.room_type] || room.room_type)}</div>`
      const enemy = enemyLabel(room.enemy)
      if (enemy && room.enemy_quantity > 0) h += `<div class="room-enemy">${room.enemy_quantity} ${esc(enemy)}</div>`
      const isDrop = room.room_action === 'KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM'
      if (room.item) h += `<div class="room-item">${esc(itemLabel(room.item))}${isDrop ? ' (drop)' : ''}</div>`
      if (room.staircase_label) h += `<div class="room-stair">${esc(room.staircase_label)}</div>`
      h += '</div>'

      // Tooltip
      const tips = [
        `Room 0x${hex2(room.room_num)}`,
        `Type: ${ROOM_TYPE_ABBREV[room.room_type] || room.room_type}`,
        `N: ${wallLabel(room.walls.north)}  E: ${wallLabel(room.walls.east)}`,
        `S: ${wallLabel(room.walls.south)}  W: ${wallLabel(room.walls.west)}`,
      ]
      if (enemy && room.enemy_quantity > 0) tips.push(`Enemy: ${room.enemy_quantity}x ${enemy}`)
      if (room.item) tips.push(`Item: ${itemLabel(room.item)}`)
      tips.push(`Action: ${room.room_action.replace(/_/g, ' ').toLowerCase()}`)
      if (room.is_dark) tips.push('Dark room')
      if (room.movable_block) tips.push('Push block')
      if (room.is_entrance) tips.push('Entrance')
      if (room.is_boss) tips.push('Boss room')
      if (room.staircase_label) tips.push(room.staircase_label)
      const tipCls = ['tip']
      if (r === minR) tipCls.push('tip--bottom')
      if (c - minC <= 1) tipCls.push('tip--left')
      else if (maxC - c <= 1) tipCls.push('tip--right')
      h += `<div class="${tipCls.join(' ')}">${tips.map(esc).join('<br>')}</div>`

      h += '</div>'
    }
  }

  h += '</div></div></div>'
  return h
}

function buildOverworldLegendHTML() {
  const items = [
    ['Open','#2B6800'],['Bomb','#8B6500'],['Candle','#8B2500'],['Recorder','#5B2080'],
    ['Raft','#0E5282'],['Ladder','#006363'],['Bracelet','#784600'],['Level','#1F56E1'],
  ]
  let h = '<div class="legend">'
  for (const [label, color] of items) {
    h += `<div class="legend-item"><span class="legend-sw" style="background:${color}"></span> ${label}</div>`
  }
  h += '</div>'
  return h
}

function buildOverworldHTML(ow) {
  const screenByPos = {}
  for (const s of ow.screens) screenByPos[`${s.row},${s.col}`] = s

  let h = '<div class="ow-wrap"><div class="ow-map">'
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 16; c++) {
      const screen = screenByPos[`${r},${c}`]
      // Filter out second-quest-only entrances — treat as no destination
      const isQ2Only = screen && screen.quest_visibility === 'SECOND_QUEST'
      const hasDest = screen && !isQ2Only && screen.destination !== 'NONE'
      let cls = 'ow-cell'
      if (hasDest && screen.destination.startsWith('LEVEL_')) {
        cls += ' ow-cell--level'
      } else if (hasDest) {
        cls += ' ' + getOverworldCellClass(screen)
      } else {
        cls += ' ow-cell--none'
      }
      if (screen && screen.screen_num === ow.start_screen) cls += ' ow-cell--start'

      h += `<div class="${cls}">`
      h += `<div class="ow-dest">${hasDest ? esc(getOwDestAbbrev(screen.destination)) : ''}</div>`
      h += `<div class="ow-num">${screen ? hex2(screen.screen_num) : ''}</div>`

      if (screen) {
        const tips = [
          `Screen 0x${hex2(screen.screen_num)}`,
        ]
        if (hasDest) {
          tips.push(`Dest: ${screen.destination.replace(/_/g, ' ')}`)
          tips.push(`Entrance: ${screen.entrance_type.replace(/_/g, ' ')}`)
        } else if (isQ2Only) {
          tips.push('Second Quest only')
        }
        const enemy = enemyLabel(screen.enemy)
        if (enemy && screen.enemy_quantity > 0) tips.push(`Enemy: ${screen.enemy_quantity}x ${enemy}`)
        if (screen.screen_num === ow.start_screen) tips.push('Start screen')
        if (ow.any_road_screens.includes(screen.screen_num)) tips.push('Any Road')
        if (ow.recorder_warp_destinations.includes(screen.screen_num)) tips.push('Recorder Warp')
        const tipCls = ['tip']
        if (r === 0) tipCls.push('tip--bottom')
        if (c <= 2) tipCls.push('tip--left')
        else if (c >= 13) tipCls.push('tip--right')
        h += `<div class="${tipCls.join(' ')}">${tips.map(esc).join('<br>')}</div>`
      }
      h += '</div>'
    }
  }
  h += '</div></div>'
  return h
}

function buildItemsHTML(data) {
  let h = ''

  // Dungeon items
  h += '<div class="section"><h3>Dungeon Items</h3><div class="grid3">'
  for (const level of data.levels) {
    const items = []
    for (const room of level.rooms) {
      if (room.item) {
        let location = 'Drop'
        if (room.staircase_index) location = 'Item Stairway'
        else if (room.room_type === 'TRIFORCE_ROOM') location = 'Triforce Room'
        else if (room.room_action === 'NOTHING_OPENS_SHUTTERS' || room.room_action === 'PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE') location = 'Floor'
        items.push({ item: itemLabel(room.item), screen: hex2(room.room_num), location })
      }
    }
    for (const sr of level.staircase_rooms) {
      if (sr.item) items.push({ item: itemLabel(sr.item), screen: hex2(sr.room_num), location: 'Item Stairway' })
    }
    if (!items.length) continue
    h += `<div><h4>Level ${level.level_num}:</h4><table class="s-table"><thead><tr><th>Item</th><th>Screen</th><th>Location</th></tr></thead><tbody>`
    for (const it of items) h += `<tr><td>${esc(it.item)}</td><td>${it.screen}</td><td>${it.location}</td></tr>`
    h += '</tbody></table></div>'
  }
  h += '</div></div>'

  // Caves, Shops, Overworld Items
  h += '<div class="section"><h3>Caves, Shops, and Overworld Items</h3><div class="grid3">'

  const majorCaves = data.caves.filter(c => c.type === 'ItemCave')
  if (majorCaves.length) {
    h += '<div><h4>Major Caves:</h4><table class="s-table"><thead><tr><th>Cave</th><th>Item</th></tr></thead><tbody>'
    for (const c of majorCaves) h += `<tr><td>${esc(c.destination_label)}</td><td>${esc(c.item)}</td></tr>`
    h += '</tbody></table></div>'
  }

  const shops = data.caves.filter(c => c.type === 'Shop')
  if (shops.length) {
    h += '<div><h4>Shops:</h4><table class="s-table"><thead><tr><th>Shop</th><th>Item</th><th>Price</th></tr></thead><tbody>'
    for (const shop of shops) {
      for (const si of shop.items) h += `<tr><td>${esc(shop.destination_label)}</td><td>${esc(si.item)}</td><td>${si.price}</td></tr>`
    }
    h += '</tbody></table></div>'
  }

  const owItems = data.caves.filter(c => c.type === 'OverworldItem')
  if (owItems.length) {
    h += '<div><h4>Overworld Items:</h4><table class="s-table"><thead><tr><th>Location</th><th>Item</th></tr></thead><tbody>'
    for (const o of owItems) h += `<tr><td>${esc(o.destination_label)}</td><td>${esc(o.item)}</td></tr>`
    h += '</tbody></table></div>'
  }
  h += '</div></div>'

  // Other caves
  const otherCaves = data.caves.filter(c => c.type !== 'ItemCave' && c.type !== 'Shop' && c.type !== 'OverworldItem')
  if (otherCaves.length) {
    h += '<div class="section"><h3>Other Caves</h3><table class="s-table"><thead><tr><th>Cave</th><th>Type</th><th>Details</th></tr></thead><tbody>'
    for (const c of otherCaves) {
      let details = ''
      if (c.type === 'TakeAnyCave') details = (c.items || []).join(', ')
      else if (c.type === 'SecretCave') details = `${c.rupee_value >= 0 ? '+' : ''}${c.rupee_value} rupees`
      else if (c.type === 'DoorRepairCave') details = `${c.cost} rupees`
      else if (c.type === 'HintCave') details = `Quote ${c.quote_id}`
      else if (c.type === 'HintShop') details = (c.hints || []).map(x => `Q${x.quote_id} @${x.price}`).join(', ')
      else if (c.type === 'MoneyMakingGameCave') details = `Bets: ${c.bet_low}/${c.bet_mid}/${c.bet_high}`
      h += `<tr><td>${esc(c.destination_label)}</td><td>${esc(c.type.replace(/Cave$/, ''))}</td><td>${esc(details)}</td></tr>`
    }
    h += '</tbody></table></div>'
  }

  return h
}

function buildEnemiesHTML(data) {
  if (!data.enemies) return '<div class="section"><p>Enemy data not available.</p></div>'

  const enemies = data.enemies
  let h = ''

  // --- Enemy sprite sets ---
  h += '<div class="section"><h3>Enemy Sprite Sets</h3>'
  for (const set of enemies.enemy_sets) {
    h += `<div class="enemy-set-section">`
    h += `<h4>Set ${esc(set.set)}</h4>`

    h += `<div class="enemy-set-meta">`
    if (set.levels.length > 0) {
      h += `<span class="enemy-set-levels">Used by: ${set.levels.map(l => l === 'OW' ? 'Overworld' : 'Level ' + l).join(', ')}</span>`
    }
    h += `</div>`

    h += `<div class="enemy-set-members">`
    if (set.enemies.length > 0) {
      h += `<strong>Enemies:</strong> ${set.enemies.map(esc).join(', ')}`
    } else {
      h += `<em>No enemies assigned</em>`
    }
    h += `</div>`

    h += `<div class="sprite-bank-section">`
    h += `<div class="sprite-bank-label">Raw Sprite Bank</div>`
    h += `<canvas class="sprite-bank-canvas" data-bank-b64="${set.bank_b64}" data-cols="8"></canvas>`
    h += `</div>`

    if (set.tile_frames.length > 0) {
      h += `<div class="enemy-frames-section">`
      h += `<div class="sprite-bank-label">Enemy Poses</div>`
      for (const tf of set.tile_frames) {
        if (tf.frames.length === 0) continue
        h += `<div class="enemy-frame-row">`
        h += `<span class="enemy-frame-name">${esc(tf.enemy)}</span>`
        h += `<canvas class="enemy-frame-canvas" data-bank-b64="${set.frames_bank_b64}" data-frames='${JSON.stringify(tf.frames)}' data-col-start="${set.col_start}"></canvas>`
        h += `</div>`
      }
      h += `</div>`
    }

    if (set.mixed_groups.length > 0) {
      h += `<div class="mixed-groups-section">`
      h += `<div class="sprite-bank-label">Mixed Enemy Groups</div>`
      h += `<table class="s-table"><thead><tr><th>#</th><th>Members</th></tr></thead><tbody>`
      for (const mg of set.mixed_groups) {
        h += `<tr><td>Group ${mg.group_num}</td><td>${mg.members.map(esc).join(', ')}</td></tr>`
      }
      h += `</tbody></table>`
      h += `</div>`
    }

    h += `</div>`
  }
  h += '</div>'

  // --- Boss sprite sets ---
  h += '<div class="section"><h3>Boss Sprite Sets</h3>'
  for (const set of enemies.boss_sets) {
    h += `<div class="enemy-set-section">`
    h += `<h4>Boss Set ${esc(set.set)}</h4>`

    h += `<div class="enemy-set-meta">`
    if (set.levels.length > 0) {
      h += `<span class="enemy-set-levels">Used by: ${set.levels.map(l => 'Level ' + l).join(', ')}</span>`
    }
    h += `</div>`

    h += `<div class="enemy-set-members">`
    if (set.bosses && set.bosses.length > 0) {
      h += `<strong>Bosses:</strong> ${set.bosses.map(esc).join(', ')}`
    }
    h += `</div>`

    h += `<div class="sprite-bank-section">`
    h += `<div class="sprite-bank-label">Raw Sprite Bank</div>`
    h += `<canvas class="sprite-bank-canvas" data-bank-b64="${set.bank_b64}" data-cols="8"></canvas>`
    h += `</div>`

    if (set.tile_frames && set.tile_frames.length > 0) {
      h += `<div class="enemy-frames-section">`
      h += `<div class="sprite-bank-label">Boss Poses</div>`
      for (const tf of set.tile_frames) {
        if (tf.frames.length === 0) continue
        h += `<div class="enemy-frame-row">`
        h += `<span class="enemy-frame-name">${esc(tf.enemy)}</span>`
        h += `<canvas class="enemy-frame-canvas" data-bank-b64="${set.bank_b64}" data-frames='${JSON.stringify(tf.frames)}' data-col-start="${set.col_start}"></canvas>`
        h += `</div>`
      }
      h += `</div>`
    }

    h += `</div>`
  }

  if (enemies.boss_expansion_b64) {
    h += `<div class="enemy-set-section">`
    h += `<h4>Boss Shared Expansion</h4>`
    h += `<div class="sprite-bank-section">`
    h += `<canvas class="sprite-bank-canvas" data-bank-b64="${enemies.boss_expansion_b64}" data-cols="8"></canvas>`
    h += `</div>`
    h += `</div>`
  }
  h += '</div>'

  return h
}

function buildHintsHTML(data) {
  let h = '<div class="section"><h3>Quotes &amp; Hints</h3>'
  for (const q of data.quotes) {
    const text = q.text ? q.text.replace(/\|/g, ' / ') : '(blank)'
    const typeLabel = q.hint_type ? ` <span class="hint-type">(${esc(q.hint_type)})</span>` : ''
    h += `<div class="hint"><span class="hint-id">[${String(q.quote_id).padStart(2, '\u00a0')}]</span>${typeLabel} ${esc(text)}</div>`
  }
  h += '</div>'
  return h
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
  initDarkMode()
  initRomSection()
  await loadSession()  // restore seed + auto-load last ROM before other sections init
  initSeedSection()
  initGenerateSection()
  initFlagsSection()   // restores flag string internally after schema loads
})